"""Phase 3 단독 검증 스크립트.

검증 항목:
1. Per-Monitor DPI V2 (`SetProcessDpiAwarenessContext(-4)`) 및 64비트 구조체 검증
2. 다중 모니터 열거 (`EnumDisplayMonitors`), 토폴로지 지문 생성, 자동 감지/수동 프로파일 전환 검증
3. `rcWork` 기준 정규화 비율(`0.0 ~ 1.0`) 계산, 스냅샷 캡처, 임시 테스트 창을 이용한
   `ShowWindow(SW_RESTORE)` 선행 복원 -> `SetWindowPos` 정렬(`apply_preset`) 실증
4. `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` 기반 `ContextWatcher` 무폴링 활성 창/프로세스 감지 검증
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.context_watcher import ContextWatcher, ForegroundContext  # noqa: E402
from core.window_orchestrator import (  # noqa: E402
    AUTO_PROFILE_KEY,
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2,
    MONITORINFOEXW,
    WINDOWPLACEMENT,
    WindowOrchestrator,
    ratios_to_rect,
    rect_to_ratios,
)


def verify_dpi_v2_and_structs() -> WindowOrchestrator:
    """DPI V2 적용 및 64비트 구조체 크기를 검증한다."""
    orch = WindowOrchestrator(init_dpi_v2=True)
    mon_info_sz = ctypes.sizeof(MONITORINFOEXW)
    wp_sz = ctypes.sizeof(WINDOWPLACEMENT)

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetThreadDpiAwarenessContext.argtypes = []
    user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.AreDpiAwarenessContextsEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.AreDpiAwarenessContextsEqual.restype = wintypes.BOOL

    ctx = user32.GetThreadDpiAwarenessContext()
    is_v2 = bool(
        user32.AreDpiAwarenessContextsEqual(
            ctx, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    )

    print(
        f"[1/4] DPI V2 & Struct Check -> dpi_v2_enabled={orch.dpi_v2_enabled}, "
        f"thread_ctx_is_v2={is_v2}, MONITORINFOEXW={mon_info_sz}B, WINDOWPLACEMENT={wp_sz}B"
    )
    assert orch.dpi_v2_enabled and is_v2, "Per-Monitor DPI Awareness V2 must be active!"
    assert mon_info_sz == 104
    assert wp_sz == 44
    return orch


def verify_monitors_and_topology(orch: WindowOrchestrator) -> None:
    """모니터 열거, 토폴로지 지문 및 자동/수동 프로파일 선택을 검증한다."""
    monitors = orch.enumerate_monitors()
    assert len(monitors) >= 1, "At least 1 monitor must be detected!"

    fp = orch.get_topology_fingerprint(monitors)
    print(f"[2/4] Monitor & Topology Check -> Count={len(monitors)}, Fingerprint='{fp}'")
    for m in monitors:
        print(
            f"      - Monitor[{m.index}] {m.device_name} | primary={m.is_primary} | "
            f"rect={m.monitor_rect} | rcWork={m.work_rect} | scale={m.scale_percent}%"
        )

    orch.register_topology_label(fp, "Current Live Setup")
    orch.register_topology_label("2M|3440x1440@100|1920x1080@125", "Home Ultrawide+Laptop")

    assert orch.get_active_topology_fingerprint() == fp
    orch.select_profile_mode("2M|3440x1440@100|1920x1080@125")
    assert orch.get_active_topology_fingerprint() == "2M|3440x1440@100|1920x1080@125"
    orch.select_profile_mode(AUTO_PROFILE_KEY)
    assert orch.get_active_topology_fingerprint() == fp

    choices = orch.get_available_environment_choices()
    assert choices[0][0] == AUTO_PROFILE_KEY and len(choices) >= 3
    print(f"      Topology Dropdown Choices OK -> {len(choices)} items")


def verify_ratios_snapshot_and_safe_move(orch: WindowOrchestrator) -> None:
    """정규화 비율 환산, 스냅샷 캡처, SW_RESTORE->SetWindowPos 복원 정렬을 검증한다."""
    # 1) 이종 해상도(rcWork) 간 정규화 비율(0.0 ~ 1.0) 환산 검증
    work_laptop = (0, 0, 1920, 1032)
    win_half = (0, 0, 960, 1032)
    xr, yr, wr, hr = rect_to_ratios(win_half, work_laptop)
    assert (xr, yr, wr, hr) == (0.0, 0.0, 0.5, 1.0)

    work_uw = (1920, 0, 5360, 1400)
    tx, ty, tw, th = ratios_to_rect(xr, yr, wr, hr, work_uw)
    assert (tx, ty, tw, th) == (1920, 0, 1720, 1400)

    # 2) 임시 테스트 창으로 스냅샷 추출 -> 최대화 교란 -> apply_preset(SW_RESTORE + SetWindowPos) 실증
    from PyQt6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication([])
    monitors = orch.enumerate_monitors()
    mon0 = monitors[0]

    target_x, target_y, target_w, target_h = ratios_to_rect(
        0.1, 0.1, 0.4, 0.5, mon0.work_rect
    )

    win = QWidget()
    win.setWindowTitle("NEXUS_PHASE3_SNAPSHOT_TARGET")
    win.show()
    app.processEvents()

    hwnd = int(win.winId())
    assert orch.move_window_safe(hwnd, target_x, target_y, target_w, target_h)
    app.processEvents()
    time.sleep(0.05)

    # 현재 배치 스냅샷 캡처 (테스트 창 포함)
    snap = orch.capture_snapshot(
        "Verify_Snapshot_Preset",
        environment_label="Phase3 Test",
        exclude_self=False,
    )
    print(f"[3/4] Snapshot & Safe Window Move Check -> Captured {len(snap.placements)} windows")
    captured_spec = next(
        (p for p in snap.placements if "NEXUS_PHASE3_SNAPSHOT_TARGET" in p.title_hint),
        None,
    )
    assert captured_spec is not None, "Snapshot must capture the positioned test window!"
    assert abs(captured_spec.x_ratio - 0.1) <= 0.01
    assert abs(captured_spec.y_ratio - 0.1) <= 0.01
    assert abs(captured_spec.w_ratio - 0.4) <= 0.01
    assert abs(captured_spec.h_ratio - 0.5) <= 0.01
    print(
        f"      - Snapshot Ratio Captured: {captured_spec.process_name} | M{captured_spec.monitor_index} | "
        f"ratio=({captured_spec.x_ratio:.4f}, {captured_spec.y_ratio:.4f}, "
        f"{captured_spec.w_ratio:.4f}, {captured_spec.h_ratio:.4f})"
    )

    # 프리셋 직렬화/복원 라운드트립 검증
    presets_data, labels = orch.export_presets()
    orch2 = WindowOrchestrator(init_dpi_v2=False)
    orch2.load_presets(presets_data, labels)
    assert orch2.get_preset("Verify_Snapshot_Preset") is not None

    # 창을 최대화(SW_MAXIMIZE)로 교란한 뒤 apply_preset(auto_launch=False)로 원위치 복원
    win.showMaximized()
    app.processEvents()
    time.sleep(0.05)
    app.processEvents()

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL

    was_maximized = bool(user32.IsZoomed(wintypes.HWND(hwnd)))
    apply_res = orch2.apply_preset("Verify_Snapshot_Preset", auto_launch=False)
    app.processEvents()

    is_still_maximized = bool(user32.IsZoomed(wintypes.HWND(hwnd)))
    rc = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rc))
    actual_rect = (rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)

    win.close()
    app.processEvents()

    assert was_maximized is True
    assert apply_res.moved_count >= 1
    assert is_still_maximized is False, "SW_RESTORE must clear maximized state!"
    assert abs(actual_rect[0] - target_x) <= 3 and abs(actual_rect[1] - target_y) <= 3
    assert abs(actual_rect[2] - target_w) <= 3 and abs(actual_rect[3] - target_h) <= 3

    print(
        f"      Apply Preset & SW_RESTORE OK -> was_maximized={was_maximized}, "
        f"after_restore_maximized={is_still_maximized}, moved={apply_res.moved_count}, "
        f"actual={actual_rect}"
    )


def verify_context_watcher() -> None:
    """SetWinEventHook(EVENT_SYSTEM_FOREGROUND) 기반 활성 창/프로세스 감지를 검증한다."""
    watcher = ContextWatcher()
    assert watcher.resolve_profile("Revit.exe") == "bim_cad"
    assert watcher.resolve_profile("acad.exe") == "bim_cad"
    assert watcher.resolve_profile("Code.exe") == "ide"
    assert watcher.resolve_profile("MinimalMediaPlayer.exe") == "media"
    assert watcher.resolve_profile("WorldChronicleEngine.exe") == "simulation"
    assert watcher.resolve_profile("chrome.exe") == "browser"
    assert watcher.resolve_profile("notepad.exe") == "default"

    events: list[ForegroundContext] = []
    watcher.add_context_callback(events.append)

    started = watcher.start()
    assert started is True and watcher.is_running is True

    # 두 개의 테스트 창 간 포커스 전환을 통해 SetWinEventHook(EVENT_SYSTEM_FOREGROUND) 실발동 검증
    from PyQt6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication([])
    w1 = QWidget()
    w1.setWindowTitle("NEXUS_FG_WINDOW_A")
    w1.resize(260, 140)
    w1.show()
    w1.activateWindow()
    app.processEvents()
    time.sleep(0.1)

    w2 = QWidget()
    w2.setWindowTitle("NEXUS_FG_WINDOW_B")
    w2.resize(260, 140)
    w2.show()
    w2.activateWindow()
    app.processEvents()
    time.sleep(0.1)

    ctx_after = watcher.current_context
    w1.close()
    w2.close()
    app.processEvents()
    watcher.stop()
    assert not watcher.is_running

    titles = [e.window_title for e in events]
    assert ctx_after is not None and ctx_after.process_name != ""
    assert any("NEXUS_FG_WINDOW_A" in t for t in titles) or any(
        "NEXUS_FG_WINDOW_B" in t for t in titles
    ), f"Expected SetWinEventHook foreground callbacks for probe windows, got {titles}"

    print(
        f"[4/4] ContextWatcher (SetWinEventHook) Check OK -> "
        f"callbacks={len(events)}, last='{ctx_after.process_name}' ({ctx_after.window_title})"
    )


def main() -> int:
    orch = verify_dpi_v2_and_structs()
    verify_monitors_and_topology(orch)
    verify_ratios_snapshot_and_safe_move(orch)
    verify_context_watcher()
    print("\nALL PHASE 3 CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
