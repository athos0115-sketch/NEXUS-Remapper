"""[2순위] Raw Input + WH_KEYBOARD_LL 유저 모드 폴백 엔진 모듈.

커널 드라이버가 미설치되었거나 보안 솔루션에 의해 차단된 환경에서 작동한다.
또한 커널 모드 가동 시에도 `install_ll_hook=False` 모드로 동작하여
Consumer Control(0x0C) 다이얼 Raw Input 및 `WM_DEVICECHANGE` Hot-Plug 이벤트를 전담한다.
"""

from __future__ import annotations

import ctypes
import threading
import time
from collections import deque
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

from core.device_registry import WM_DEVICECHANGE, DeviceInfo, DeviceRegistry
from core.events import EngineSource, EventType, InputEvent
from core.hid_dial import (
    RAWINPUTDEVICE,
    RIDEV_INPUTSINK,
    RIM_TYPEHID,
    RIM_TYPEKEYBOARD,
    WM_INPUT,
    HidDialParser,
    _user32 as _raw_user32,
    read_raw_input_from_lparam,
)

# ============================================================================
# Win32 메시지 루프 / WH_KEYBOARD_LL 64비트 ctypes 선언
# ============================================================================

WH_KEYBOARD_LL = 13
HC_ACTION = 0

LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10
LLKHF_UP = 0x80

RI_KEY_MAKE = 0x00
RI_KEY_BREAK = 0x01
RI_KEY_E0 = 0x02
RI_KEY_E1 = 0x04

VK_ESCAPE = 0x1B
VK_F12 = 0x7B

WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
PM_REMOVE = 0x0001

WS_OVERLAPPED = 0x00000000
WS_EX_TOOLWINDOW = 0x00000080

# 64비트 Windows에서 LRESULT는 부호 있는 포인터 크기 정수(64비트)
LRESULT = ctypes.c_ssize_t
ULONG_PTR = (
    ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """Win32 `KBDLLHOOKSTRUCT` 구조체 (64비트 환경 기준 24바이트)."""

    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)
HOOKPROC = ctypes.WINFUNCTYPE(
    LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    """Win32 `WNDCLASSEXW` 구조체."""

    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD

_user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
_user32.RegisterClassExW.restype = wintypes.ATOM

_user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
_user32.UnregisterClassW.restype = wintypes.BOOL

_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    ctypes.c_void_p,
]
_user32.CreateWindowExW.restype = wintypes.HWND

_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.DestroyWindow.restype = wintypes.BOOL

_user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.DefWindowProcW.restype = LRESULT

_user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.GetMessageW.restype = wintypes.BOOL

_user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.PeekMessageW.restype = wintypes.BOOL

_user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.TranslateMessage.restype = wintypes.BOOL

_user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.restype = LRESULT

_user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.PostThreadMessageW.restype = wintypes.BOOL

_user32.PostQuitMessage.argtypes = [ctypes.c_int]
_user32.PostQuitMessage.restype = None

_user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK

_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL

_user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.CallNextHookEx.restype = LRESULT


@dataclass(frozen=True)
class _RawKeyAttribution:
    """`WM_INPUT`에서 관측된 최근 키보드 장치 귀속 레코드."""

    vk: int
    is_up: bool
    device: DeviceInfo
    timestamp: float


class UserFallbackEngine:
    """Raw Input + WH_KEYBOARD_LL 기반 [2순위] 유저 모드 입력 엔진."""

    def __init__(
        self,
        registry: DeviceRegistry,
        on_event: Callable[[InputEvent], None] | None = None,
        on_panic_exit: Callable[[], None] | None = None,
        install_ll_hook: bool = True,
        hid_parser: HidDialParser | None = None,
    ) -> None:
        self._registry = registry
        self._on_event = on_event
        self._on_panic_exit = on_panic_exit
        self._install_ll_hook = install_ll_hook
        self._hid_parser = hid_parser or HidDialParser()

        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hwnd: int | None = None
        self._hhook: int | None = None
        self._class_name: str = f"NexusRawInputSink_{id(self)}"
        self._ready_event = threading.Event()
        self._start_error: str = ""

        # 콜백 객체가 GC로 수거되지 않도록 인스턴스 속성에 참조 유지
        self._wnd_proc_ref: WNDPROC | None = None
        self._hook_proc_ref: HOOKPROC | None = None

        # Raw Input <-> WH_KEYBOARD_LL 상관 추적 버퍼
        self._recent_raw_keys: deque[_RawKeyAttribution] = deque(maxlen=32)
        self._suppressed_vks: dict[int, float] = {}
        self._suppressed_up_vks: dict[int, float] = {}

        # 비상 탈출(ESC + F12) 및 일시정지(Bypass) 상태
        self._esc_down = False
        self._f12_down = False
        self._panic_fired = False
        self.bypass: bool = False

    @property
    def is_running(self) -> bool:
        """메시지 루프 워커 스레드 가동 여부를 반환한다."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> str:
        """시작 실패 시 진단 메시지를 반환한다."""
        return self._start_error

    def _register_raw_input_devices(self, hwnd: int) -> None:
        """키보드(0x01:0x06), Consumer Control(0x0C:0x01) 및 등록된 커스텀 HID를 구독한다."""
        targets: set[tuple[int, int]] = {
            (0x01, 0x06),  # Keyboard / Keypad
            (0x0C, 0x01),  # Consumer Control / Rotary Dial
        }
        for dev in self._registry.get_all_devices(connected_only=True):
            if dev.raw_type == RIM_TYPEHID and dev.usage_page > 0 and dev.usage > 0:
                if not dev.protected:
                    targets.add((dev.usage_page, dev.usage))

        rid_array = (RAWINPUTDEVICE * len(targets))()
        for idx, (up, u) in enumerate(sorted(targets)):
            rid_array[idx].usUsagePage = up
            rid_array[idx].usUsage = u
            rid_array[idx].dwFlags = RIDEV_INPUTSINK
            rid_array[idx].hwndTarget = wintypes.HWND(hwnd)

        ok = _raw_user32.RegisterRawInputDevices(
            rid_array, len(targets), ctypes.sizeof(RAWINPUTDEVICE)
        )
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(err, f"RegisterRawInputDevices failed (err={err})")

    def _emit_event(self, event: InputEvent) -> None:
        """등록된 이벤트 수신기로 `InputEvent`를 전달한다."""
        if self._on_event is not None:
            self._on_event(event)

    def _mark_vk_suppressed(self, vk: int, ttl_sec: float = 0.15) -> None:
        """다이얼/Consumer HID에 의해 발생한 OS 레거시 VK를 한시적으로 차단 예약한다."""
        with self._lock:
            self._suppressed_vks[vk] = time.monotonic() + ttl_sec

    def _consume_suppressed_vk(self, vk: int, is_up: bool = False) -> bool:
        """차단 예약된 레거시 VK(및 대응 Key-Up)가 유효 시간 내에 있으면 소비(True)한다."""
        now = time.monotonic()
        with self._lock:
            if is_up:
                up_expiry = self._suppressed_up_vks.pop(vk, None)
                if up_expiry is not None and now <= up_expiry:
                    return True
                return False

            expiry = self._suppressed_vks.get(vk)
            if expiry is not None:
                del self._suppressed_vks[vk]
                if now <= expiry:
                    self._suppressed_up_vks[vk] = now + 0.25
                    return True
        return False

    def process_raw_keyboard_data(
        self,
        device: DeviceInfo,
        vk_code: int,
        scan_code: int,
        is_up: bool,
        is_extended: bool,
    ) -> InputEvent | None:
        """Raw Input 키보드 패킷을 평가하고 귀속 버퍼 및 이벤트를 생성한다."""
        if vk_code == 0xFF or vk_code == 0:
            return None

        now = time.monotonic()
        with self._lock:
            self._recent_raw_keys.append(
                _RawKeyAttribution(
                    vk=vk_code,
                    is_up=is_up,
                    device=device,
                    timestamp=now,
                )
            )

        # Protected 장치이거나 Bypass(일시정지) 상태에서는 차단/이벤트 발행을 생략
        if device.protected or (self.bypass and not self._registry.is_listening):
            return None

        # 등록된 보조 키패드이거나 Listen Mode가 켜져 있을 때만 표준 이벤트 발행
        if not device.is_registered and not self._registry.is_listening:
            return None

        event = InputEvent(
            device_id=device.device_id,
            event_type=EventType.KEY_UP if is_up else EventType.KEY_DOWN,
            code=scan_code,
            value=0 if is_up else 1,
            source=EngineSource.USER_FALLBACK,
            is_extended=is_extended,
            vk_code=vk_code,
            device_name=device.display_name,
        )
        self._emit_event(event)
        return event

    def process_raw_hid_data(
        self,
        device: DeviceInfo,
        payload: bytes,
        dw_size_hid: int = 0,
        dw_count: int = 1,
    ) -> list[InputEvent]:
        """Raw Input HID(다이얼 등) 패킷을 파싱하고 차단 VK 예약 및 이벤트를 생성한다."""
        if device.protected or (self.bypass and not self._registry.is_listening):
            return []

        if not device.is_registered and not self._registry.is_listening:
            return []

        parsed = self._hid_parser.parse_raw_hid(
            device=device,
            raw_bytes=payload,
            dw_size_hid=dw_size_hid,
            dw_count=dw_count,
        )

        # 이미 등록된 비보호 다이얼/HID인 경우에만 OS 기본 동작(볼륨 등)을 차단
        if device.is_registered:
            for vk in parsed.suppress_vks:
                self._mark_vk_suppressed(vk)

        for ev in parsed.events:
            self._emit_event(ev)

        return parsed.events

    def evaluate_ll_keyboard_event(
        self,
        vk_code: int,
        scan_code: int,
        flags: int,
    ) -> tuple[bool, bool]:
        """`WH_KEYBOARD_LL` 이벤트를 판정한다.

        Returns:
            `(should_block, panic_triggered)` 튜플.
            - `should_block=True`: 원본 키/미디어 동작을 OS로 전달하지 않고 차단.
            - `panic_triggered=True`: `ESC + F12` 비상 탈출 조건 성립.
        """
        del scan_code
        # SendInput 등 소프트웨어 주입 입력(LLKHF_INJECTED)은 절대 재차단하지 않음
        if flags & LLKHF_INJECTED:
            return False, False

        is_up = bool(flags & LLKHF_UP)

        # 최우선 비상 탈출(ESC + F12) 검사
        if vk_code == VK_ESCAPE:
            self._esc_down = not is_up
        elif vk_code == VK_F12:
            self._f12_down = not is_up

        if self._esc_down and self._f12_down and not self._panic_fired:
            self._panic_fired = True
            return False, True

        # 일시정지(Bypass) 중에는 모든 물리 키/미디어 키를 차단 없이 통과
        if self.bypass and not self._registry.is_listening:
            return False, False

        # 1) Consumer Control HID(다이얼 등)에서 예약한 레거시 미디어 VK 차단 확인
        if self._consume_suppressed_vk(vk_code, is_up=is_up):
            return True, False

        # 2) 최근 Raw Input 키보드 귀속 버퍼와 대조
        now = time.monotonic()
        with self._lock:
            matched_attr: _RawKeyAttribution | None = None
            # 최신 항목부터 역순 탐색 (100ms 이내 매칭)
            for idx in range(len(self._recent_raw_keys) - 1, -1, -1):
                attr = self._recent_raw_keys[idx]
                if now - attr.timestamp > 0.10:
                    continue
                if attr.vk == vk_code and attr.is_up == is_up:
                    matched_attr = attr
                    del self._recent_raw_keys[idx]
                    break

        if matched_attr is not None:
            dev = matched_attr.device
            if not dev.protected and dev.is_registered:
                return True, False

        return False, False

    def _drain_pending_raw_input(self) -> None:
        """`WH_KEYBOARD_LL` 판정 직전 대기 중인 `WM_INPUT` 메시지를 비블로킹으로 우선 처리한다."""
        if not self._hwnd:
            return
        msg = wintypes.MSG()
        for _ in range(16):
            has_msg = _user32.PeekMessageW(
                ctypes.byref(msg),
                wintypes.HWND(self._hwnd),
                WM_INPUT,
                WM_INPUT,
                PM_REMOVE,
            )
            if not has_msg:
                break
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _handle_wm_input(self, lparam: int) -> None:
        """`WM_INPUT` 메시지를 디코딩해 장치 귀속 및 이벤트 변환을 수행한다."""
        try:
            header, kb, payload, dw_size_hid, dw_count = read_raw_input_from_lparam(lparam)
        except OSError:
            return

        h_dev = int(header.hDevice or 0)
        if h_dev == 0:
            return

        device = self._registry.get_device_by_handle(h_dev)
        if device is None:
            return

        if header.dwType == RIM_TYPEKEYBOARD and kb is not None:
            is_up = bool(kb.Flags & RI_KEY_BREAK)
            is_ext = bool(kb.Flags & RI_KEY_E0)
            self.process_raw_keyboard_data(
                device=device,
                vk_code=int(kb.VKey),
                scan_code=int(kb.MakeCode),
                is_up=is_up,
                is_extended=is_ext,
            )
        elif header.dwType == RIM_TYPEHID and payload:
            self.process_raw_hid_data(
                device=device,
                payload=payload,
                dw_size_hid=dw_size_hid,
                dw_count=dw_count,
            )

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """숨김 Win32 메시지 윈도우 프로시저."""
        if msg == WM_INPUT:
            self._handle_wm_input(lparam)
            return 0
        if msg == WM_DEVICECHANGE:
            self._registry.handle_device_change(int(wparam), int(lparam))
            return 1
        if msg == WM_CLOSE:
            _user32.DestroyWindow(wintypes.HWND(hwnd))
            return 0
        if msg == WM_DESTROY:
            _user32.PostQuitMessage(0)
            return 0
        return int(
            _user32.DefWindowProcW(
                wintypes.HWND(hwnd), msg, wintypes.WPARAM(wparam), wintypes.LPARAM(lparam)
            )
        )

    def _ll_keyboard_proc(self, n_code: int, wparam: int, lparam: int) -> int:
        """`WH_KEYBOARD_LL` 전역 저수준 키보드 훅 프로시저."""
        if n_code == HC_ACTION and lparam:
            self._drain_pending_raw_input()
            kb_ll = KBDLLHOOKSTRUCT.from_address(lparam)
            should_block, panic = self.evaluate_ll_keyboard_event(
                vk_code=int(kb_ll.vkCode),
                scan_code=int(kb_ll.scanCode),
                flags=int(kb_ll.flags),
            )
            if panic:
                if self._on_panic_exit is not None:
                    threading.Thread(
                        target=self._on_panic_exit,
                        name="NexusPanicExit",
                        daemon=True,
                    ).start()
                return int(
                    _user32.CallNextHookEx(
                        None, n_code, wintypes.WPARAM(wparam), wintypes.LPARAM(lparam)
                    )
                )
            if should_block:
                return 1

        return int(
            _user32.CallNextHookEx(
                None, n_code, wintypes.WPARAM(wparam), wintypes.LPARAM(lparam)
            )
        )

    def start(self) -> bool:
        """숨김 메시지 루프 스레드, Raw Input 수신기, WH_KEYBOARD_LL 훅을 시작한다."""
        if self.is_running:
            return True

        self._ready_event.clear()
        self._start_error = ""
        self._esc_down = False
        self._f12_down = False
        self._panic_fired = False
        with self._lock:
            self._recent_raw_keys.clear()
            self._suppressed_vks.clear()
            self._suppressed_up_vks.clear()

        self._thread = threading.Thread(
            target=self._run_message_loop, name="NexusUserFallbackEngine", daemon=True
        )
        self._thread.start()
        self._ready_event.wait(timeout=3.0)
        return not self._start_error and self.is_running

    def _run_message_loop(self) -> None:
        """Win32 메시지 펌프 전용 스레드 본문."""
        h_instance = _kernel32.GetModuleHandleW(None)
        self._thread_id = int(_kernel32.GetCurrentThreadId())
        self._wnd_proc_ref = WNDPROC(self._wnd_proc)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = h_instance
        wc.lpszClassName = self._class_name

        atom = _user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            err = ctypes.get_last_error()
            # 1410 (ERROR_CLASS_ALREADY_EXISTS)는 무시 가능
            if err != 1410:
                self._start_error = f"RegisterClassExW failed (err={err})"
                self._ready_event.set()
                return

        hwnd = _user32.CreateWindowExW(
            WS_EX_TOOLWINDOW,
            self._class_name,
            "NEXUS_RawInput_Sink",
            WS_OVERLAPPED,
            0,
            0,
            0,
            0,
            None,
            None,
            h_instance,
            None,
        )
        if not hwnd:
            err = ctypes.get_last_error()
            self._start_error = f"CreateWindowExW failed (err={err})"
            _user32.UnregisterClassW(self._class_name, h_instance)
            self._ready_event.set()
            return

        self._hwnd = int(hwnd)
        try:
            self._register_raw_input_devices(self._hwnd)
        except OSError as exc:
            self._start_error = str(exc)
            _user32.DestroyWindow(wintypes.HWND(self._hwnd))
            self._hwnd = None
            _user32.UnregisterClassW(self._class_name, h_instance)
            self._ready_event.set()
            return

        if self._install_ll_hook:
            self._hook_proc_ref = HOOKPROC(self._ll_keyboard_proc)
            hhook = _user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._hook_proc_ref, h_instance, 0
            )
            if not hhook:
                err = ctypes.get_last_error()
                self._start_error = f"SetWindowsHookExW(WH_KEYBOARD_LL) failed (err={err})"
                _user32.DestroyWindow(wintypes.HWND(self._hwnd))
                self._hwnd = None
                _user32.UnregisterClassW(self._class_name, h_instance)
                self._ready_event.set()
                return
            self._hhook = int(hhook)

        self._ready_event.set()

        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        # 정리(Cleanup)
        with self._lock:
            if self._hhook:
                _user32.UnhookWindowsHookEx(wintypes.HHOOK(self._hhook))
                self._hhook = None
            if self._hwnd:
                _user32.DestroyWindow(wintypes.HWND(self._hwnd))
                self._hwnd = None
            self._thread_id = 0
        _user32.UnregisterClassW(self._class_name, h_instance)

    def stop(self) -> None:
        """훅과 메시지 윈도우를 즉시 해제하고 워커 스레드를 종료한다."""
        with self._lock:
            if self._hhook:
                _user32.UnhookWindowsHookEx(wintypes.HHOOK(self._hhook))
                self._hhook = None
            tid = self._thread_id

        if tid:
            _user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)

        if self._thread is not None and self._thread.is_alive():
            if threading.current_thread() is not self._thread:
                self._thread.join(timeout=1.5)
        self._thread = None


if __name__ == "__main__":
    reg = DeviceRegistry()
    reg.refresh_devices()
    eng = UserFallbackEngine(registry=reg, on_event=lambda ev: print("EVENT:", ev))
    started = eng.start()
    print(f"[UserFallbackEngine] started={started}, error='{eng.last_error}'")
    time.sleep(0.1)
    eng.stop()
    print(f"[UserFallbackEngine] stopped cleanly, running={eng.is_running}")
