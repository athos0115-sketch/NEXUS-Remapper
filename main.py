"""NEXUS Remapper & Universal Workspace Orchestrator 메인 진입점.

실행 순서:
1. QApplication 생성 전 최상단에서 `SetProcessDpiAwarenessContext(-4)`(DPI V2) 선언
2. 실행 파일 기준 경로(`sys.frozen` 판별)의 `config.json` 로드
3. 장치 레지스트리, 액션 실행기, 창 오케스트레이터, 활성 창 감지기, 이중 엔진 매니저 기동
4. PyQt6 3단 Dark Luminous 콘솔 및 시스템 트레이 상주 실행
"""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path
from ctypes import wintypes

from core.window_orchestrator import WindowOrchestrator, enable_per_monitor_dpi_v2

# 반드시 QApplication 생성 전에 Per-Monitor DPI Awareness V2를 최우선 선언
_DPI_V2_OK = enable_per_monitor_dpi_v2()

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
APP_WINDOW_TITLE = "NEXUS Remapper & Workspace Orchestrator"
SINGLE_INSTANCE_MUTEX_NAME = "Local\\NEXUS_Remapper_SingleInstance"

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)

_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE

_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND

_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL

_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL


class SingleInstanceGuard:
    """Win32 `CreateMutexW` 기반 단일 인스턴스 실행 잠금 가드."""

    def __init__(self, mutex_name: str = SINGLE_INSTANCE_MUTEX_NAME) -> None:
        self._mutex_name = mutex_name
        self._handle: int | None = None
        self.already_running: bool = False

    def acquire(self) -> bool:
        """뮤텍스 소유권 획득을 시도한다. 이미 실행 중이면 False를 반환한다."""
        handle = _kernel32.CreateMutexW(None, False, self._mutex_name)
        err = ctypes.get_last_error()
        if not handle:
            return True
        self._handle = int(handle)
        if err == ERROR_ALREADY_EXISTS:
            self.already_running = True
            return False
        self.already_running = False
        return True

    def focus_existing_window(self) -> bool:
        """이미 실행 중인 NEXUS 콘솔 창을 찾아 포그라운드로 복원한다."""
        hwnd = _user32.FindWindowW(None, APP_WINDOW_TITLE)
        if not hwnd:
            return False
        _user32.ShowWindow(hwnd, SW_RESTORE)
        _user32.SetForegroundWindow(hwnd)
        return True

    def release(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(wintypes.HANDLE(self._handle))
            self._handle = None

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from core.actions import ActionExecutor  # noqa: E402
from core.config_store import ConfigStore, get_config_path  # noqa: E402
from core.context_watcher import ContextWatcher  # noqa: E402
from core.device_registry import DeviceRegistry  # noqa: E402
from core.engine_manager import EngineManager  # noqa: E402
from ui.main_window import MainWindow, NexusSignalBridge  # noqa: E402


def build_application(
    test_mode: bool = False,
    config_path: Path | None = None,
) -> tuple[QApplication, MainWindow]:
    """전체 백엔드 서비스와 PyQt6 메인 콘솔을 조립한다."""
    config_store = ConfigStore(config_path or get_config_path("config.json"))
    cfg = config_store.load()
    settings = cfg.get("settings", {})

    registry = DeviceRegistry()
    registry.refresh_devices()
    registry.load_saved_devices(cfg.get("devices", []))
    registry.refresh_devices()

    orchestrator = WindowOrchestrator(
        init_dpi_v2=False,
        compensate_dwm_frame=bool(settings.get("compensate_dwm_frame", True)),
    )
    orchestrator.dpi_v2_enabled = _DPI_V2_OK
    orchestrator.load_presets(
        cfg.get("layout_presets", []),
        cfg.get("topology_labels", {}),
    )
    orchestrator.select_profile_mode(str(settings.get("selected_topology", "__auto__")))

    layers = config_store.list_layers()
    active_layer = str(settings.get("active_layer", "default"))
    executor = ActionExecutor(
        dry_run=test_mode,
        layout_handler=lambda preset: orchestrator.apply_preset(
            preset,
            auto_launch=bool(
                config_store.settings.get("auto_launch_missing_apps", False)
            ),
        ).moved_count
        > 0,
        layers=layers,
    )
    if active_layer in layers:
        executor.shift_layer(active_layer, mode="set")

    context_watcher = ContextWatcher(
        process_profiles=cfg.get("process_profiles"),
        layer_bindings=config_store.get_layer_bindings(),
        ignore_self=not test_mode,
    )
    engine_manager = EngineManager(registry=registry)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NEXUS Remapper")
    app.setQuitOnLastWindowClosed(False)

    bridge = NexusSignalBridge()
    window = MainWindow(
        config_store=config_store,
        registry=registry,
        engine_manager=engine_manager,
        context_watcher=context_watcher,
        orchestrator=orchestrator,
        executor=executor,
        bridge=bridge,
    )

    context_watcher.start()
    prefer_kernel = bool(settings.get("prefer_kernel_engine", True))
    engine_manager.set_bypass(bool(settings.get("bypass_remapping", False)))
    engine_manager.start(prefer_kernel=prefer_kernel)
    window._update_engine_badge(engine_manager.mode, engine_manager.fallback_reason)  # noqa: SLF001

    return app, window


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS Remapper Console")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Initialize GUI/services and auto-exit cleanly for automated testing",
    )
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Start hidden directly into the System Tray without showing the main window",
    )
    args = parser.parse_args()

    guard: SingleInstanceGuard | None = None
    if not args.test_mode:
        guard = SingleInstanceGuard()
        if not guard.acquire():
            guard.focus_existing_window()
            guard.release()
            return 0

    try:
        app, window = build_application(test_mode=args.test_mode)
        tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
        if args.minimized and tray_ok:
            window.hide()
        else:
            window.show()

        if args.test_mode:
            QTimer.singleShot(350, window.force_quit)

        return int(app.exec())
    finally:
        if guard is not None:
            guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
