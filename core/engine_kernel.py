"""[1순위] Interception 커널 드라이버 기반 입력 격리 엔진 모듈.

`interception.dll`이 존재하고 커널 필터 컨텍스트 생성이 허용된 환경에서는
등록된 보조 키패드 입력을 OS 도달 전 커널 계층에서 0ms 지연으로 가로채 폐기(Drop)하고
표준 `InputEvent`로 변환한다.
드라이버 미설치 또는 사내 보안 솔루션(AppGuard 등) 차단 시 예외 종료 없이
`is_available() == (False, 사유)`를 반환하여 유저 모드 폴백 엔진으로 자동 전환된다.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from core.device_registry import DeviceInfo, DeviceRegistry
from core.events import EngineSource, EventType, InputEvent

# ============================================================================
# Interception C API 상수 및 64비트 ctypes 구조체 정의
# ============================================================================

INTERCEPTION_KEY_DOWN = 0x00
INTERCEPTION_KEY_UP = 0x01
INTERCEPTION_KEY_E0 = 0x02
INTERCEPTION_KEY_E1 = 0x04

INTERCEPTION_FILTER_KEY_NONE = 0x0000
INTERCEPTION_FILTER_KEY_ALL = 0xFFFF

# 비상 탈출 조합용 하드웨어 스캔코드 (AT Set-1)
SCANCODE_ESC = 0x01
SCANCODE_F12 = 0x58

_USER32 = ctypes.WinDLL("user32", use_last_error=True)
_USER32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_USER32.MapVirtualKeyW.restype = wintypes.UINT
MAPVK_VSC_TO_VK_EX = 3


class InterceptionKeyStroke(ctypes.Structure):
    """Interception 커널 드라이버 `InterceptionKeyStroke` 구조체 (8바이트)."""

    _fields_ = [
        ("code", ctypes.c_ushort),
        ("state", ctypes.c_ushort),
        ("information", ctypes.c_uint),
    ]


_PREDICATE_FUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)


def _get_base_dir() -> Path:
    """개발 환경 및 PyInstaller 단일 `.exe` 패키징 환경 모두 호환되는 기준 경로를 반환한다."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _find_interception_dll() -> str | None:
    """프로젝트/실행 파일 주변 경로 및 시스템 PATH에서 `interception.dll`을 탐색한다."""
    base = _get_base_dir()
    candidates = [
        base / "interception.dll",
        base / "drivers" / "interception.dll",
        base / "core" / "interception.dll",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return "interception.dll"


def _bind_interception_api(dll: ctypes.CDLL) -> None:
    """64비트 포인터 안전성을 보장하기 위해 Interception C API 타입을 명시 선언한다."""
    dll.interception_create_context.argtypes = []
    dll.interception_create_context.restype = ctypes.c_void_p

    dll.interception_destroy_context.argtypes = [ctypes.c_void_p]
    dll.interception_destroy_context.restype = None

    dll.interception_set_filter.argtypes = [
        ctypes.c_void_p,
        _PREDICATE_FUNC,
        ctypes.c_ushort,
    ]
    dll.interception_set_filter.restype = None

    dll.interception_wait_with_timeout.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    dll.interception_wait_with_timeout.restype = ctypes.c_int

    dll.interception_receive.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    dll.interception_receive.restype = ctypes.c_int

    dll.interception_send.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    dll.interception_send.restype = ctypes.c_int

    dll.interception_get_hardware_id.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    dll.interception_get_hardware_id.restype = ctypes.c_uint

    dll.interception_is_keyboard.argtypes = [ctypes.c_int]
    dll.interception_is_keyboard.restype = ctypes.c_int


class KernelEngine:
    """Interception 커널 드라이버 기반 [1순위] 입력 격리 엔진."""

    def __init__(
        self,
        registry: DeviceRegistry,
        on_event: Callable[[InputEvent], None] | None = None,
        on_panic_exit: Callable[[], None] | None = None,
    ) -> None:
        self._registry = registry
        self._on_event = on_event
        self._on_panic_exit = on_panic_exit

        self._dll: ctypes.CDLL | None = None
        self._ctx: ctypes.c_void_p | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._predicate_ref: object | None = None

        self._esc_down = False
        self._f12_down = False
        self._dev_cache: dict[int, DeviceInfo | None] = {}
        self.bypass: bool = False

    @classmethod
    def probe_availability(cls) -> tuple[bool, str]:
        """커널 드라이버 로드 및 컨텍스트 생성 가능 여부를 크래시 없이 진단한다."""
        dll_target = _find_interception_dll()
        if dll_target is None:
            return False, "interception.dll not found"

        try:
            # Windows DLL 탐색 시 프로젝트 경로 우선 적용
            if os.path.isabs(dll_target):
                dll = ctypes.CDLL(dll_target)
            else:
                dll = ctypes.CDLL(dll_target)
            _bind_interception_api(dll)
            ctx = dll.interception_create_context()
            if not ctx:
                return (
                    False,
                    "interception_create_context() returned NULL (driver not installed or blocked by security policy)",
                )
            dll.interception_destroy_context(ctx)
            return True, "Interception kernel driver available"
        except (OSError, AttributeError) as exc:
            return False, f"Interception unavailable: {exc}"

    @property
    def is_running(self) -> bool:
        """커널 루프 스레드 가동 여부를 반환한다."""
        return self._thread is not None and self._thread.is_alive()

    def _resolve_device_for_slot(self, device_slot: int) -> DeviceInfo | None:
        """Interception 장치 슬롯(`1..10`)의 Hardware ID를 `DeviceRegistry`와 매칭한다."""
        if device_slot in self._dev_cache:
            return self._dev_cache[device_slot]

        if self._dll is None or not self._ctx:
            return None

        buf = ctypes.create_unicode_buffer(512)
        length = self._dll.interception_get_hardware_id(
            self._ctx, device_slot, buf, ctypes.sizeof(buf)
        )
        if length == 0:
            self._dev_cache[device_slot] = None
            return None

        hw_id = buf.value.strip().upper().replace("\\", "#")
        matched: DeviceInfo | None = None
        for dev in self._registry.get_all_devices(connected_only=True):
            if hw_id and (hw_id in dev.device_id or dev.device_id.startswith(hw_id)):
                matched = dev
                break

        self._dev_cache[device_slot] = matched
        return matched

    def _check_panic_combo(self, stroke: InterceptionKeyStroke) -> bool:
        """메인/전체 키보드의 `ESC + F12` 동시 입력 여부를 추적한다."""
        is_up = bool(stroke.state & INTERCEPTION_KEY_UP)
        is_ext = bool(stroke.state & INTERCEPTION_KEY_E0)
        if not is_ext:
            if stroke.code == SCANCODE_ESC:
                self._esc_down = not is_up
            elif stroke.code == SCANCODE_F12:
                self._f12_down = not is_up

        if self._esc_down and self._f12_down:
            return True
        return False

    def start(self) -> bool:
        """커널 드라이버 컨텍스트와 워커 스레드를 시작한다."""
        if self.is_running:
            return True

        dll_target = _find_interception_dll()
        if dll_target is None:
            return False

        try:
            dll = ctypes.CDLL(dll_target)
            _bind_interception_api(dll)
            ctx = dll.interception_create_context()
            if not ctx:
                return False
        except (OSError, AttributeError):
            return False

        self._dll = dll
        self._ctx = ctx
        self._stop_event.clear()
        self._dev_cache.clear()
        self._esc_down = False
        self._f12_down = False

        # 키보드 장치만 필터링 (Consumer Control 0x0C 다이얼은 hid_dial/Raw Input이 전담)
        self._predicate_ref = _PREDICATE_FUNC(
            lambda dev: int(dll.interception_is_keyboard(dev))
        )
        dll.interception_set_filter(
            ctx, self._predicate_ref, INTERCEPTION_FILTER_KEY_ALL
        )

        self._thread = threading.Thread(
            target=self._run_loop, name="NexusKernelEngine", daemon=True
        )
        self._thread.start()
        return True

    def _run_loop(self) -> None:
        """커널 드라이버 스트로크 수신 및 격리/전달 루프."""
        assert self._dll is not None and self._ctx is not None
        dll = self._dll
        ctx = self._ctx
        stroke = InterceptionKeyStroke()

        try:
            while not self._stop_event.is_set():
                dev_slot = dll.interception_wait_with_timeout(ctx, 50)
                if dev_slot <= 0:
                    continue

                if dll.interception_receive(ctx, dev_slot, ctypes.byref(stroke), 1) <= 0:
                    continue

                if self._check_panic_combo(stroke):
                    # ESC+F12 비상 탈출 시 원본 키는 통과시키고 즉시 안전 종료 콜백 실행
                    dll.interception_send(ctx, dev_slot, ctypes.byref(stroke), 1)
                    self._stop_event.set()
                    if self._on_panic_exit is not None:
                        threading.Thread(
                            target=self._on_panic_exit,
                            name="NexusPanicExit",
                            daemon=True,
                        ).start()
                    break

                # 일시정지(Bypass) 모드에서는 Listen Mode가 아닌 한 모든 입력을 그대로 OS로 통과
                if self.bypass and not self._registry.is_listening:
                    dll.interception_send(ctx, dev_slot, ctypes.byref(stroke), 1)
                    continue

                dev_info = self._resolve_device_for_slot(dev_slot)
                is_up = bool(stroke.state & INTERCEPTION_KEY_UP)
                is_ext = bool(stroke.state & INTERCEPTION_KEY_E0)

                # Protected 또는 미등록 장치는 절대 차단하지 않고 즉시 OS로 통과
                should_intercept = (
                    dev_info is not None
                    and not dev_info.protected
                    and (dev_info.is_registered or self._registry.is_listening)
                )

                if not should_intercept:
                    dll.interception_send(ctx, dev_slot, ctypes.byref(stroke), 1)
                    continue

                # Listen Mode 중에는 등록 전 보조 장치 입력도 원본 차단 없이 포착 가능하게 허용할지/차단할지 결정:
                # 이미 등록된 보조 장치면 원본 폐기(Drop), Listen 전용이면 이벤트만 발행 후 통과
                if not dev_info.is_registered and self._registry.is_listening:
                    dll.interception_send(ctx, dev_slot, ctypes.byref(stroke), 1)

                vk_scan = stroke.code | (0xE000 if is_ext else 0)
                vk_code = int(_USER32.MapVirtualKeyW(vk_scan, MAPVK_VSC_TO_VK_EX))
                event = InputEvent(
                    device_id=dev_info.device_id,
                    event_type=EventType.KEY_UP if is_up else EventType.KEY_DOWN,
                    code=int(stroke.code),
                    value=0 if is_up else 1,
                    source=EngineSource.KERNEL,
                    is_extended=is_ext,
                    vk_code=vk_code,
                    device_name=dev_info.display_name,
                )
                if self._on_event is not None:
                    self._on_event(event)
        finally:
            if self._ctx:
                dll.interception_destroy_context(self._ctx)
                self._ctx = None

    def stop(self) -> None:
        """커널 루프를 중지하고 컨텍스트를 즉시 해제한다."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            if threading.current_thread() is not self._thread:
                self._thread.join(timeout=1.0)
        self._thread = None


if __name__ == "__main__":
    avail, reason = KernelEngine.probe_availability()
    print(f"[KernelEngine Probe] available={avail}, reason={reason}")
