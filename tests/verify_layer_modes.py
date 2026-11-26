"""03 MAPPING LAYER 트리거 모드(`focus` vs `process`) 및 충돌 팝업 통합 검증 스크립트.

검증 항목:
1. `focus` 모드(복수 `.exe`) vs `process` 모드(단일 `.exe` 엄격 제한) 생성·편집 및 동일 모드 중복 정리
2. `config.json` 저장·로드 라운드트립(`trigger_mode` 보존) 및 구버전(`trigger_mode` 누락) 하위 호환성
3. 크로스-모드 상호 배타 검증 (`ConfigStore` 및 `MainWindow` UI 슬롯 + `QMessageBox.warning` 정확 문구)
   - `process` -> `focus`: "프로세스 지정 모드에서 등록된 프로세스입니다."
   - `focus` -> `process`: "포커스 모드에서 등록된 프로세스입니다."
4. 런타임 자동 전환 및 충돌 선택 팝업(`ProcessLayerConflictDialog`) + 중복 팝업 방지 가드:
   - 단일 `process` 레이어 실행 시 자동 활성화 및 포그라운드 전환 시 유지, 종료 시 포커스 모드 복귀
   - 2개 이상 동시 실행 시 정확한 후보 목록으로 팝업 표시 및 선택 즉시 `executor.active_layer` / `active_layer_lbl` 반영
   - 동일 조합 반복 평가 시 팝업 미재생성, 조합 변경(3번째 프로세스 추가) 및 0개->2개 복귀 시 재트리거 검증
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import ui.main_window as main_window_mod  # noqa: E402
from core.actions import ActionExecutor  # noqa: E402
from core.config_store import (  # noqa: E402
    ERR_BOUND_IN_FOCUS_MODE,
    ERR_BOUND_IN_PROCESS_MODE,
    ERR_PROCESS_MODE_SINGLE_ONLY,
    TRIGGER_MODE_FOCUS,
    TRIGGER_MODE_PROCESS,
    ConfigStore,
)
from core.context_watcher import ContextWatcher, ForegroundContext  # noqa: E402
from core.device_registry import DeviceRegistry  # noqa: E402
from core.engine_manager import EngineManager  # noqa: E402
from core.window_orchestrator import WindowOrchestrator  # noqa: E402
from ui.main_window import MainWindow, NexusSignalBridge  # noqa: E402
from ui.widgets import LayerCreateDialog, ProcessLayerConflictDialog  # noqa: E402


def _build_headless_window(tmpdir: str) -> tuple[MainWindow, ConfigStore, ContextWatcher, ActionExecutor, NexusSignalBridge]:
    cfg_path = Path(tmpdir) / "config.json"
    store = ConfigStore(cfg_path)
    store.load()

    registry = DeviceRegistry()
    orchestrator = WindowOrchestrator(init_dpi_v2=False)
    watcher = ContextWatcher(
        layer_bindings=store.get_focus_layer_bindings(),
        process_layer_bindings=store.get_process_layer_bindings(),
    )
    engine_mgr = EngineManager(registry=registry)
    executor = ActionExecutor(dry_run=True, layers=store.list_layers())
    bridge = NexusSignalBridge()

    win = MainWindow(
        config_store=store,
        registry=registry,
        engine_manager=engine_mgr,
        context_watcher=watcher,
        orchestrator=orchestrator,
        executor=executor,
        bridge=bridge,
    )
    return win, store, watcher, executor, bridge


def verify_mode_rules_and_roundtrip() -> None:
    """1~2. 모드별 프로세스 수 제한, 동일 모드 정리, 저장·로드 라운드트립 및 하위 호환성을 검증한다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        store = ConfigStore(cfg_path)
        store.load()

        # focus 모드: 복수 .exe 허용
        lc_focus = store.create_layer(
            "focus_multi",
            processes=["Code.exe", "notepad.exe"],
            trigger_mode=TRIGGER_MODE_FOCUS,
        )
        assert lc_focus.trigger_mode == TRIGGER_MODE_FOCUS
        assert lc_focus.processes == ["Code.exe", "notepad.exe"]

        # process 모드: 단일 .exe 허용, 2개 이상 차단
        try:
            store.create_layer(
                "proc_bad",
                processes=["AppA.exe", "AppB.exe"],
                trigger_mode=TRIGGER_MODE_PROCESS,
            )
            raise AssertionError("process mode with 2 processes must raise ValueError")
        except ValueError as exc:
            assert str(exc) == ERR_PROCESS_MODE_SINGLE_ONLY

        lc_proc = store.create_layer(
            "proc_single",
            processes=["AppA.exe"],
            trigger_mode=TRIGGER_MODE_PROCESS,
        )
        assert lc_proc.trigger_mode == TRIGGER_MODE_PROCESS
        assert lc_proc.processes == ["AppA.exe"]

        # process 모드 레이어에 2개 이상 설정 시 차단
        try:
            store.set_layer_processes("proc_single", ["AppA.exe", "AppB.exe"])
            raise AssertionError("set_layer_processes with 2+ exes in process mode must fail")
        except ValueError as exc:
            assert str(exc) == ERR_PROCESS_MODE_SINGLE_ONLY

        # 복수 .exe가 바인딩된 focus 레이어를 process 모드로 전환 시 차단
        try:
            store.set_layer_trigger_mode("focus_multi", TRIGGER_MODE_PROCESS)
            raise AssertionError("switching multi-exe focus layer to process mode must fail")
        except ValueError as exc:
            assert str(exc) == ERR_PROCESS_MODE_SINGLE_ONLY

        # default 레이어는 process 모드로 전환 불가
        assert store.set_layer_trigger_mode("default", TRIGGER_MODE_PROCESS) is False
        assert store.get_layer_config("default").trigger_mode == TRIGGER_MODE_FOCUS  # type: ignore[union-attr]

        # 동일 모드 내 중복 이동(deduplication) 유지 확인
        store.create_layer("proc_other", processes=["AppA.exe"], trigger_mode=TRIGGER_MODE_PROCESS)
        assert store.get_layer_config("proc_single").processes == []  # type: ignore[union-attr]
        assert store.get_layer_config("proc_other").processes == ["AppA.exe"]  # type: ignore[union-attr]
        store.set_layer_processes("proc_single", ["AppA.exe"])
        assert store.get_layer_config("proc_other").processes == []  # type: ignore[union-attr]

        # 바인딩 조회 분리 확인
        focus_bindings = store.get_focus_layer_bindings()
        proc_bindings = store.get_process_layer_bindings()
        assert "focus_multi" in focus_bindings
        assert "proc_single" not in focus_bindings
        assert proc_bindings == {"proc_single": "AppA.exe"}
        assert store.resolve_layer_for_process("AppA.exe") == "default"
        assert store.resolve_layer_for_process("Code.exe") == "focus_multi"
        assert store.resolve_running_process_layers(["appa.exe", "chrome.exe"]) == ["proc_single"]

        # config.json 저장/로드 라운드트립
        store.save()
        reloaded = ConfigStore(cfg_path)
        reloaded.load()
        assert reloaded.get_layer_config("focus_multi").trigger_mode == TRIGGER_MODE_FOCUS  # type: ignore[union-attr]
        assert reloaded.get_layer_config("proc_single").trigger_mode == TRIGGER_MODE_PROCESS  # type: ignore[union-attr]
        assert reloaded.get_process_layer_bindings() == {"proc_single": "AppA.exe"}

        # 단일 레이어 번들 Export/Import 라운드트립(trigger_mode 보존)
        bundle_path = Path(tmpdir) / "proc_single_bundle.json"
        reloaded.export_layer_to_file("proc_single", bundle_path)
        reloaded.delete_layer("proc_single")
        assert reloaded.get_layer_config("proc_single") is None
        imported_name, _ = reloaded.import_layer_from_file(bundle_path, mode="merge")
        assert imported_name == "proc_single"
        imported_lc = reloaded.get_layer_config("proc_single")
        assert imported_lc is not None
        assert imported_lc.trigger_mode == TRIGGER_MODE_PROCESS
        assert imported_lc.processes == ["AppA.exe"]

        # 하위 호환성: trigger_mode 필드가 없는 구버전 config.json 로드 시 focus 기본값
        legacy_path = Path(tmpdir) / "legacy_config.json"
        legacy_payload = {
            "version": 1,
            "settings": {"layers": ["default", "legacy_cad"]},
            "layer_configs": [
                {"name": "default", "processes": [], "description": ""},
                {"name": "legacy_cad", "processes": ["Revit.exe", "acad.exe"], "description": "old"},
            ],
            "mappings": [],
        }
        legacy_path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")
        legacy_store = ConfigStore(legacy_path)
        legacy_store.load()
        legacy_lc = legacy_store.get_layer_config("legacy_cad")
        assert legacy_lc is not None
        assert legacy_lc.trigger_mode == TRIGGER_MODE_FOCUS
        assert legacy_lc.processes == ["Revit.exe", "acad.exe"]

    print("[1/4] Mode Rules, Single-Exe Enforcement, Roundtrip & Legacy Compat OK")


def verify_cross_mode_mutual_exclusion() -> None:
    """3. 크로스-모드 상호 배타 검증(`ConfigStore` + `MainWindow` UI 슬롯 및 정확 경고 문구)."""
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmpdir:
        win, store, _watcher, _executor, _bridge = _build_headless_window(tmpdir)

        # 초기 레이어 구성: focus_layer(FocusApp.exe), proc_layer(ProcApp.exe)
        store.create_layer("focus_layer", processes=["FocusApp.exe"], trigger_mode=TRIGGER_MODE_FOCUS)
        store.create_layer("proc_layer", processes=["ProcApp.exe"], trigger_mode=TRIGGER_MODE_PROCESS)
        win._sync_layers_everywhere()  # noqa: SLF001
        app.processEvents()

        # 3-a) ConfigStore 직접 검증: process -> focus 차단 (대소문자 무시 포함)
        try:
            store.set_layer_processes("focus_layer", ["FocusApp.exe", "procapp.exe"])
            raise AssertionError("Adding process-mode exe to focus-mode layer must raise ValueError")
        except ValueError as exc:
            assert str(exc) == "프로세스 지정 모드에서 등록된 프로세스입니다."
            assert str(exc) == ERR_BOUND_IN_PROCESS_MODE

        # 3-b) ConfigStore 직접 검증: focus -> process 차단 (대소문자 무시 포함)
        try:
            store.set_layer_processes("proc_layer", ["focusapp.exe"])
            raise AssertionError("Adding focus-mode exe to process-mode layer must raise ValueError")
        except ValueError as exc:
            assert str(exc) == "포커스 모드에서 등록된 프로세스입니다."
            assert str(exc) == ERR_BOUND_IN_FOCUS_MODE

        # 3-c) MainWindow UI 슬롯 검증 (`QMessageBox.warning` 캡처)
        warnings: list[tuple[str, str]] = []
        orig_warning = QMessageBox.warning
        try:
            QMessageBox.warning = staticmethod(  # type: ignore[assignment]
                lambda _parent, title, text, *a, **kw: warnings.append((str(title), str(text)))
                or QMessageBox.StandardButton.Ok
            )

            # UI 슬롯: focus 레이어에 process-mode exe 추가 시도
            win._on_layer_processes_updated("focus_layer", ["FocusApp.exe", "ProcApp.exe"])  # noqa: SLF001
            app.processEvents()
            assert len(warnings) == 1
            assert warnings[-1][1] == "프로세스 지정 모드에서 등록된 프로세스입니다."
            assert store.get_layer_config("focus_layer").processes == ["FocusApp.exe"]  # type: ignore[union-attr]

            # UI 슬롯: process 레이어에 focus-mode exe 추가 시도
            win._on_layer_processes_updated("proc_layer", ["FocusApp.exe"])  # noqa: SLF001
            app.processEvents()
            assert len(warnings) == 2
            assert warnings[-1][1] == "포커스 모드에서 등록된 프로세스입니다."
            assert store.get_layer_config("proc_layer").processes == ["ProcApp.exe"]  # type: ignore[union-attr]

            # UI 슬롯: process 레이어에 2개 .exe 추가 시도
            win._on_layer_processes_updated("proc_layer", ["ProcApp.exe", "Extra.exe"])  # noqa: SLF001
            app.processEvents()
            assert len(warnings) == 3
            assert warnings[-1][1] == ERR_PROCESS_MODE_SINGLE_ONLY

            # UI 위젯 검증: LayerCreateDialog 라디오 선택 & MappingLayerPage 모드 태그
            dlg = LayerCreateDialog(lang="ko")
            dlg.name_edit.setText("new_proc")
            assert dlg.trigger_mode() == TRIGGER_MODE_FOCUS
            dlg.process_radio.setChecked(True)
            assert dlg.trigger_mode() == TRIGGER_MODE_PROCESS
            assert dlg.layer_name() == "new_proc"
            dlg.close()

            layer_texts = [
                win.layer_page.layer_list.item(i).text()
                for i in range(win.layer_page.layer_list.count())
            ]
            assert any("focus_layer" in t and "[포커스]" in t for t in layer_texts)
            assert any("proc_layer" in t and "[프로세스 지정]" in t for t in layer_texts)
        finally:
            QMessageBox.warning = orig_warning  # type: ignore[assignment]

        win.force_quit()
        app.processEvents()

    print("[2/4] Cross-Mode Mutual Exclusion (ConfigStore & MainWindow UI) OK")


def verify_runtime_switching_and_conflict_popup() -> None:
    """4. 런타임 프로세스 지정 전환, 포그라운드 유지, 충돌 팝업 선택 및 중복 팝업 방지 가드를 검증한다."""
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmpdir:
        win, store, watcher, executor, bridge = _build_headless_window(tmpdir)
        win.show()
        app.processEvents()

        # ContextWatcher 콜백 검증
        watcher_events: list[list[str]] = []
        watcher.add_process_layers_callback(watcher_events.append)

        # process-mode 레이어 3개 생성
        win._on_create_layer("proc_a", TRIGGER_MODE_PROCESS)  # noqa: SLF001
        win._on_layer_processes_updated("proc_a", ["AppA.exe"])  # noqa: SLF001
        win._on_create_layer("proc_b", TRIGGER_MODE_PROCESS)  # noqa: SLF001
        win._on_layer_processes_updated("proc_b", ["AppB.exe"])  # noqa: SLF001
        win._on_create_layer("proc_c", TRIGGER_MODE_PROCESS)  # noqa: SLF001
        win._on_layer_processes_updated("proc_c", ["AppC.exe"])  # noqa: SLF001
        app.processEvents()

        assert win._process_poll_timer.isActive() is True  # noqa: SLF001
        assert watcher.evaluate_process_layers(["AppA.exe"]) == ["proc_a"]
        assert watcher.evaluate_process_layers(["AppA.exe"]) == ["proc_a"]
        assert len(watcher_events) == 1, "ContextWatcher callback must fire only on change"

        # 4-a) 단일 process 레이어 실행 -> 자동 활성화 & 다른 앱으로 포커스 이동해도 유지
        cands = win.evaluate_process_layer_state(["AppA.exe", "explorer.exe"])
        app.processEvents()
        assert cands == ["proc_a"]
        assert executor.active_layer == "proc_a"
        assert "LAYER: proc_a" in win.active_layer_lbl.text()
        assert win._conflict_dialog is None  # noqa: SLF001

        # 다른 포커스 모드 앱(Revit.exe -> bim)으로 포커스가 넘어가도 proc_a 유지
        ctx_revit = ForegroundContext(
            hwnd=2001,
            pid=3001,
            process_name="Revit.exe",
            executable_path=r"C:\Program Files\Autodesk\Revit.exe",
            window_title="Test.rvt",
            matched_profile="bim_cad",
            matched_layer="bim",
        )
        bridge.context_changed.emit(ctx_revit)
        app.processEvents()
        assert executor.active_layer == "proc_a", "Process-mode layer must stay active on focus change"
        assert "LAYER: proc_a" in win.active_layer_lbl.text()

        # AppA.exe 종료 -> 오버라이드 해제 및 현재 포그라운드(Revit.exe -> bim) 포커스 모드로 복귀
        cands_empty = win.evaluate_process_layer_state(["explorer.exe"])
        app.processEvents()
        assert cands_empty == []
        assert executor.active_layer == "bim"
        assert "LAYER: bim" in win.active_layer_lbl.text()

        # 4-b) 2개 이상 동시 실행 -> ProcessLayerConflictDialog 생성 + 중복 팝업 방지 가드 검증
        created_dialogs: list[ProcessLayerConflictDialog] = []
        orig_dialog_cls = main_window_mod.ProcessLayerConflictDialog

        class _TrackedConflictDialog(orig_dialog_cls):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                created_dialogs.append(self)

        main_window_mod.ProcessLayerConflictDialog = _TrackedConflictDialog  # type: ignore[misc]
        try:
            # 2개 실행 -> 팝업 1회 생성, 정확한 후보 목록 확인
            cands_2 = win.evaluate_process_layer_state(["AppA.exe", "AppB.exe"])
            app.processEvents()
            assert cands_2 == ["proc_a", "proc_b"]
            assert len(created_dialogs) == 1
            dlg1 = win._conflict_dialog  # noqa: SLF001
            assert dlg1 is not None and dlg1 is created_dialogs[0]
            assert dlg1.candidate_layers == ["proc_a", "proc_b"]

            # 팝업에서 두 번째 후보(proc_b) 선택 및 적용 -> executor.active_layer 및 active_layer_lbl 즉시 반영
            dlg1.candidate_list.setCurrentRow(1)
            dlg1.apply_btn.click()
            app.processEvents()
            assert executor.active_layer == "proc_b"
            assert "LAYER: proc_b" in win.active_layer_lbl.text()

            # 중복 팝업 방지 가드: 동일 2개 조합(순서 무관) 반복 호출 시 새 팝업 미생성
            win.evaluate_process_layer_state(["AppA.exe", "AppB.exe"])
            win.evaluate_process_layer_state(["appb.exe", "appa.exe"])
            app.processEvents()
            assert len(created_dialogs) == 1, "Same 2+ combination must NOT open a duplicate popup!"

            # 조합 변경(3번째 프로세스 시작) -> 가드 갱신되어 새 팝업 생성
            cands_3 = win.evaluate_process_layer_state(["AppA.exe", "AppB.exe", "AppC.exe"])
            app.processEvents()
            assert cands_3 == ["proc_a", "proc_b", "proc_c"]
            assert len(created_dialogs) == 2
            assert win._conflict_dialog is created_dialogs[1]  # noqa: SLF001
            assert win._conflict_dialog.candidate_layers == ["proc_a", "proc_b", "proc_c"]  # noqa: SLF001

            # 3개 동일 조합 반복 호출 -> 중복 생성 금지
            win.evaluate_process_layer_state(["AppC.exe", "AppA.exe", "AppB.exe"])
            app.processEvents()
            assert len(created_dialogs) == 2

            # 0개로 감소 -> 가드 초기화 & 팝업 닫힘, 이후 다시 2개 실행 시 팝업 재트리거
            win.evaluate_process_layer_state([])
            app.processEvents()
            assert win._conflict_dialog is None  # noqa: SLF001
            assert win._last_conflict_combo is None  # noqa: SLF001

            win.evaluate_process_layer_state(["AppA.exe", "AppB.exe"])
            app.processEvents()
            assert len(created_dialogs) == 3, "Returning from 0 -> 2 running must re-trigger conflict popup!"
            assert win._conflict_dialog is created_dialogs[2]  # noqa: SLF001
            assert win._conflict_dialog.candidate_layers == ["proc_a", "proc_b"]  # noqa: SLF001
        finally:
            main_window_mod.ProcessLayerConflictDialog = orig_dialog_cls  # type: ignore[misc]

        win.force_quit()
        app.processEvents()
        assert win._process_poll_timer.isActive() is False  # noqa: SLF001
        assert win._conflict_dialog is None  # noqa: SLF001

    print("[3/4] Runtime Process-Mode Auto-Switch & Focus Persistence OK")
    print("[4/4] Conflict Popup Selection & Duplicate Popup Guard OK")


def main() -> int:
    verify_mode_rules_and_roundtrip()
    verify_cross_mode_mutual_exclusion()
    verify_runtime_switching_and_conflict_popup()
    print("\nALL LAYER MODE CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
