"""이중 입력 엔진 통합 매니저 및 비상 탈출(Panic Exit) 안전장치 모듈.

구동 시 Interception 커널 드라이버 가용성을 자동 진단하여
1순위 `KernelEngine` 또는 2순위 `UserFallbackEngine`으로 무중단 전환하며,
커널 모드 가동 중에도 Consumer Control(0x0C) 다이얼 및 Hot-Plug 처리를 위해
`hid_dial` Raw Input 수신기를 병행 운용한다.
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Callable

from core.device_registry import DeviceInfo, DeviceRegistry
from core.engine_kernel import KernelEngine
from core.engine_user import UserFallbackEngine
from core.events import InputEvent


class EngineMode(str, Enum):
    """현재 활성화된 입력 엔진 동작 모드."""

    KERNEL = "kernel"
    USER_FALLBACK = "user_fallback"
    STOPPED = "stopped"


class EngineManager:
    """커널/유저 엔진 자동 진단, 모드 전환, 비상 탈출을 총괄하는 매니저."""

    def __init__(self, registry: DeviceRegistry | None = None) -> None:
        self.registry = registry or DeviceRegistry()

        self._lock = threading.RLock()
        self._mode: EngineMode = EngineMode.STOPPED
        self._fallback_reason: str = ""
        self._panic_triggered: bool = False
        self._bypass: bool = False

        self._kernel_engine: KernelEngine | None = None
        self._user_engine: UserFallbackEngine | None = None

        self._event_callbacks: list[Callable[[InputEvent], None]] = []
        self._listen_callbacks: list[Callable[[DeviceInfo, InputEvent], None]] = []
        self._panic_callbacks: list[Callable[[], None]] = []
        self._mode_callbacks: list[Callable[[EngineMode, str], None]] = []

    @property
    def mode(self) -> EngineMode:
        """현재 엔진 모드를 반환한다."""
        with self._lock:
            return self._mode

    @property
    def bypass(self) -> bool:
        """리매핑 일시 정지(Bypass) 상태를 반환한다."""
        with self._lock:
            return self._bypass

    def set_bypass(self, enabled: bool) -> None:
        """리매핑 일시 정지(Bypass) 상태를 런타임에 전환한다."""
        with self._lock:
            self._bypass = bool(enabled)
            if self._kernel_engine is not None:
                self._kernel_engine.bypass = self._bypass
            if self._user_engine is not None:
                self._user_engine.bypass = self._bypass

    @property
    def status_badge(self) -> str:
        """UI 상단 헤더 표시용 엔진 상태 배지 문자열을 반환한다."""
        current = self.mode
        if current == EngineMode.KERNEL:
            return "[ENGINE: KERNEL]"
        if current == EngineMode.USER_FALLBACK:
            return "[ENGINE: USER FALLBACK]"
        return "[ENGINE: STOPPED]"

    @property
    def fallback_reason(self) -> str:
        """유저 모드 폴백 사유(커널 드라이버 미설치/차단 등)를 반환한다."""
        with self._lock:
            return self._fallback_reason

    @property
    def panic_triggered(self) -> bool:
        """비상 탈출(ESC + F12) 발동 여부를 반환한다."""
        with self._lock:
            return self._panic_triggered

    @property
    def user_engine(self) -> UserFallbackEngine | None:
        """현재 활성화된 유저 모드/Raw HID 엔진 인스턴스를 반환한다."""
        with self._lock:
            return self._user_engine

    @property
    def kernel_engine(self) -> KernelEngine | None:
        """현재 활성화된 커널 엔진 인스턴스를 반환한다."""
        with self._lock:
            return self._kernel_engine

    def add_event_callback(self, cb: Callable[[InputEvent], None]) -> None:
        """표준 `InputEvent` 수신 콜백을 등록한다."""
        with self._lock:
            if cb not in self._event_callbacks:
                self._event_callbacks.append(cb)

    def add_listen_callback(
        self, cb: Callable[[DeviceInfo, InputEvent], None]
    ) -> None:
        """Listen Mode 중 비보호 보조 장치 포착 시 호출될 콜백을 등록한다."""
        with self._lock:
            if cb not in self._listen_callbacks:
                self._listen_callbacks.append(cb)

    def add_panic_callback(self, cb: Callable[[], None]) -> None:
        """`ESC + F12` 비상 탈출 시 호출될 콜백을 등록한다."""
        with self._lock:
            if cb not in self._panic_callbacks:
                self._panic_callbacks.append(cb)

    def add_mode_callback(self, cb: Callable[[EngineMode, str], None]) -> None:
        """엔진 모드 전환 시 호출될 콜백을 등록한다."""
        with self._lock:
            if cb not in self._mode_callbacks:
                self._mode_callbacks.append(cb)

    def _dispatch_event(self, event: InputEvent) -> None:
        """하위 엔진으로부터 수신한 표준 `InputEvent`를 Listen/일반 콜백으로 분배한다."""
        if self.registry.is_listening:
            dev = self.registry.get_device(event.device_id)
            if dev is not None and not dev.protected:
                with self._lock:
                    listen_cbs = list(self._listen_callbacks)
                for cb in listen_cbs:
                    try:
                        cb(dev, event)
                    except Exception:
                        pass

        with self._lock:
            event_cbs = list(self._event_callbacks)
        for cb in event_cbs:
            try:
                cb(event)
            except Exception:
                pass

    def trigger_panic_exit(self) -> None:
        """비상 탈출(ESC + F12): 모든 훅, 커널 컨텍스트, 워커 스레드를 즉시 해제한다."""
        with self._lock:
            if self._panic_triggered and self._mode == EngineMode.STOPPED:
                return
            self._panic_triggered = True
            panic_cbs = list(self._panic_callbacks)

        self.stop()

        for cb in panic_cbs:
            try:
                cb()
            except Exception:
                pass

    def start(self, prefer_kernel: bool = True) -> EngineMode:
        """드라이버 가용성을 진단해 최적 엔진을 시작하고 실제 가동 모드를 반환한다."""
        with self._lock:
            if self._mode != EngineMode.STOPPED:
                return self._mode

            self._panic_triggered = False
            if not self.registry.get_all_devices(connected_only=True):
                self.registry.refresh_devices()

            selected_mode = EngineMode.STOPPED
            reason = ""

            if prefer_kernel:
                avail, diag_msg = KernelEngine.probe_availability()
                if avail:
                    kernel = KernelEngine(
                        registry=self.registry,
                        on_event=self._dispatch_event,
                        on_panic_exit=self.trigger_panic_exit,
                    )
                    # 커널 모드에서도 Consumer Control(0x0C) 다이얼 및 Hot-Plug는 Raw Input이 전담
                    raw_hid = UserFallbackEngine(
                        registry=self.registry,
                        on_event=self._dispatch_event,
                        on_panic_exit=self.trigger_panic_exit,
                        install_ll_hook=False,
                    )
                    if kernel.start():
                        raw_hid.start()
                        kernel.bypass = self._bypass
                        raw_hid.bypass = self._bypass
                        self._kernel_engine = kernel
                        self._user_engine = raw_hid
                        selected_mode = EngineMode.KERNEL
                        reason = diag_msg
                    else:
                        kernel.stop()
                        reason = "KernelEngine.start() failed; falling back to user mode"
                else:
                    reason = diag_msg
            else:
                reason = "User fallback mode explicitly requested"

            if selected_mode == EngineMode.STOPPED:
                user_eng = UserFallbackEngine(
                    registry=self.registry,
                    on_event=self._dispatch_event,
                    on_panic_exit=self.trigger_panic_exit,
                    install_ll_hook=True,
                )
                if user_eng.start():
                    user_eng.bypass = self._bypass
                    self._user_engine = user_eng
                    selected_mode = EngineMode.USER_FALLBACK
                else:
                    reason = f"{reason} | UserFallback failed: {user_eng.last_error}"
                    selected_mode = EngineMode.STOPPED

            self._mode = selected_mode
            self._fallback_reason = reason if selected_mode == EngineMode.USER_FALLBACK else ""
            mode_cbs = list(self._mode_callbacks)

        for cb in mode_cbs:
            try:
                cb(selected_mode, self._fallback_reason or reason)
            except Exception:
                pass

        return selected_mode

    def switch_mode(self, target_mode: EngineMode) -> EngineMode:
        """실행 중 엔진 모드를 안전하게 전환한다."""
        self.stop()
        if target_mode == EngineMode.STOPPED:
            return EngineMode.STOPPED
        return self.start(prefer_kernel=(target_mode == EngineMode.KERNEL))

    def stop(self) -> None:
        """활성화된 모든 입력 엔진과 훅을 안전하게 종료한다."""
        with self._lock:
            kernel = self._kernel_engine
            user = self._user_engine
            self._kernel_engine = None
            self._user_engine = None
            prev_mode = self._mode
            self._mode = EngineMode.STOPPED
            mode_cbs = list(self._mode_callbacks)

        if kernel is not None:
            kernel.stop()
        if user is not None:
            user.stop()

        if prev_mode != EngineMode.STOPPED:
            for cb in mode_cbs:
                try:
                    cb(EngineMode.STOPPED, "Engine stopped")
                except Exception:
                    pass


if __name__ == "__main__":
    mgr = EngineManager()
    active_mode = mgr.start(prefer_kernel=True)
    print(
        f"[EngineManager] badge={mgr.status_badge} mode={active_mode.value} "
        f"reason='{mgr.fallback_reason}'"
    )
    mgr.stop()
    print(f"[EngineManager] after stop -> badge={mgr.status_badge}")
