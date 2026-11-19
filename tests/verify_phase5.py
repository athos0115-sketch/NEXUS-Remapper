"""Phase 5 단독 검증 스크립트.

검증 항목:
1. 시스템 트레이 상주 검증:
   - 닫기(`X`) 시 앱 종료 대신 트레이로 최소화(`isHidden()==True`, 엔진/감지기 계속 가동)
   - 트레이 우클릭 메뉴(`[콘솔 열기]`, `[현재 엔진/프로파일 상태]`, `[완전 종료]`) 존재 및 실시간 상태 갱신
2. `dist_release\\NEXUS_Remapper.exe` 단일 실행 파일 존재 및 실행(`--test-mode`) 검증
3. 외부 `config.json` 분리 영구 저장 검증:
   - `_MEIPASS`가 아닌 `NEXUS_Remapper.exe` 동일 폴더(`dist_release\\config.json`)에 자동 생성·로드·유지 확인
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.window_orchestrator import enable_per_monitor_dpi_v2  # noqa: E402

enable_per_monitor_dpi_v2()

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from core.context_watcher import ForegroundContext  # noqa: E402
from core.engine_manager import EngineMode  # noqa: E402
from main import build_application  # noqa: E402


def verify_system_tray_behavior() -> None:
    """닫기(X) 시 트레이 최소화 유지 및 우클릭 메뉴 3종/실시간 상태 갱신을 검증한다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_cfg = Path(tmpdir) / "config.json"
        app, win = build_application(test_mode=True, config_path=tmp_cfg)
        win.show()
        app.processEvents()

        tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        print(f"[1/3] System Tray Check -> available={tray_available}")

        if tray_available and win._tray_icon is not None and win._tray_menu is not None:  # noqa: SLF001
            actions_text = [a.text() for a in win._tray_menu.actions() if not a.isSeparator()]  # noqa: SLF001
            print(f"      Tray Menu Actions: {actions_text}")
            assert any("콘솔 열기" in t for t in actions_text)
            assert any("상태:" in t for t in actions_text)
            assert any("Bypass" in t for t in actions_text)
            assert any("완전 종료" in t for t in actions_text)

            # 트레이 메뉴에서 Bypass 토글 연동 확인
            assert win._tray_bypass_action is not None  # noqa: SLF001
            win._tray_bypass_action.trigger()  # noqa: SLF001
            app.processEvents()
            assert win.engine_manager.bypass is True
            win._tray_bypass_action.trigger()  # noqa: SLF001
            app.processEvents()
            assert win.engine_manager.bypass is False

            # 활성 프로세스 변경 시 트레이 상태 텍스트 실시간 반영 확인
            win._on_context_changed(  # noqa: SLF001
                ForegroundContext(
                    hwnd=1,
                    pid=100,
                    process_name="Revit.exe",
                    executable_path="Revit.exe",
                    window_title="Test.rvt",
                    matched_profile="bim_cad",
                )
            )
            assert "Revit.exe [bim_cad]" in win._tray_status_action.text()  # noqa: SLF001

            # X(닫기) 클릭 시 종료되지 않고 트레이로 숨겨지며 백그라운드 엔진은 계속 실행
            win.close()
            app.processEvents()
            assert win.isHidden() is True, "Window must hide to tray on close()!"
            assert win.engine_manager.mode != EngineMode.STOPPED, (
                "EngineManager must keep running in background tray!"
            )
            assert win.context_watcher.is_running is True, (
                "ContextWatcher must keep running in background tray!"
            )

            # [콘솔 열기] 복원 동작 확인
            win._restore_from_tray()  # noqa: SLF001
            app.processEvents()
            assert win.isVisible() is True

            print("      Close-to-Tray, Live Tray Status & Restore OK")
        else:
            print("      Tray unavailable in current session; skipping native tray icon check")

        win.force_quit()
        app.processEvents()
        assert win.engine_manager.mode == EngineMode.STOPPED


def verify_packaged_exe_and_external_config(dist_dir_name: str = "dist_release") -> None:
    """패키징된 `NEXUS_Remapper.exe` 실행 및 외부 `config.json` 생성·영구 유지를 검증한다."""
    dist_dir = ROOT_DIR / dist_dir_name
    exe_path = dist_dir / "NEXUS_Remapper.exe"
    ext_cfg_path = dist_dir / "config.json"

    assert exe_path.is_file(), f"Packaged exe not found at {exe_path}"
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[2/3] Packaged Executable Check -> {exe_path} ({size_mb:.1f} MB)")

    # 기존 외부 config.json 제거 후 최초 실행 시 exe 옆에 자동 생성되는지 확인
    if ext_cfg_path.exists():
        ext_cfg_path.unlink()

    proc1 = subprocess.run(
        [str(exe_path), "--test-mode"],
        cwd=str(dist_dir),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc1.returncode == 0, f"EXE run 1 failed ({proc1.returncode}): {proc1.stderr}"
    assert ext_cfg_path.is_file(), (
        "config.json MUST be created next to NEXUS_Remapper.exe (not inside _MEIPASS)!"
    )

    with ext_cfg_path.open("r", encoding="utf-8") as fh:
        cfg_data = json.load(fh)
    assert cfg_data.get("version") == 1
    assert "process_profiles" in cfg_data

    # 외부 config.json 수정 후 재실행 시 값이 덮어씌워지지 않고 영구 유지되는지 확인
    cfg_data["settings"]["active_layer"] = "bim"
    with ext_cfg_path.open("w", encoding="utf-8") as fh:
        json.dump(cfg_data, fh, ensure_ascii=False, indent=2)

    time.sleep(0.2)
    proc2 = subprocess.run(
        [str(exe_path), "--test-mode", "--minimized"],
        cwd=str(dist_dir),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc2.returncode == 0, f"EXE run 2 failed ({proc2.returncode}): {proc2.stderr}"

    with ext_cfg_path.open("r", encoding="utf-8") as fh:
        cfg_reloaded = json.load(fh)
    assert cfg_reloaded["settings"]["active_layer"] == "bim", (
        "External config.json changes must persist across .exe restarts!"
    )

    print(
        f"[3/3] External config.json Persistence Check OK -> {ext_cfg_path} "
        f"(active_layer={cfg_reloaded['settings']['active_layer']})"
    )
    # 배포 폴더 초기 상태 유지를 위해 테스트용 임시 config.json 정리
    if ext_cfg_path.exists():
        ext_cfg_path.unlink()


def main() -> int:
    dist_dir_name = sys.argv[1] if len(sys.argv) > 1 else "dist_release"
    verify_system_tray_behavior()
    verify_packaged_exe_and_external_config(dist_dir_name)
    print("\nALL PHASE 5 CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
