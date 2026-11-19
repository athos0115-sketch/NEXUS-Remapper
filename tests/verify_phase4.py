"""Phase 4 단독 검증 스크립트.

검증 항목:
1. `sys.frozen` 단일 .exe 경로 판별 및 `config.json` UTF-8 저장·로드 라운드트립
2. `QT_QPA_PLATFORM=offscreen` 헤드리스 환경에서 PyQt6 3단 UI(`MainWindow`, `DevicePanel`, `MappingCardsPanel`) 초기화
3. 백그라운드 워커 스레드 -> `pyqtSignal`(`NexusSignalBridge`) 크로스 스레드 UI 갱신 검증:
   - Listen Mode 보조 장치 포착 시 동적 매핑 카드 생성 및 네온 글로우 점등/소등
   - `ContextWatcher` 활성 프로세스 전환(`Revit.exe [bim_cad]`) 헤더 갱신
   - 실제 트리거 `InputEvent` 수신 시 카드 글로우 점등 및 `ActionExecutor` 실행
4. `python main.py --test-mode` 진입점 DPI V2 초기화 및 데드락 없는 정상 종료 검증
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import core.config_store as config_store_mod  # noqa: E402
from core.actions import (  # noqa: E402
    ACTION_REGISTRY,
    ActionExecutor,
    ActionResult,
    ActionSpec,
    ActionType,
    format_trigger_label,
    register_action,
)
from core.config_store import ConfigStore, MappingRule, build_startup_command  # noqa: E402
from core.context_watcher import ContextWatcher, ForegroundContext  # noqa: E402
from core.device_registry import RIM_TYPEHID, RIM_TYPEKEYBOARD, DeviceInfo, DeviceRegistry  # noqa: E402
from core.engine_manager import EngineManager  # noqa: E402
from core.events import DeviceType, EngineSource, EventType, InputEvent  # noqa: E402
from core.hid_dial import HidDialParser  # noqa: E402
from core.window_orchestrator import LayoutPreset, WindowOrchestrator, WindowPlacementSpec  # noqa: E402
from main import SingleInstanceGuard  # noqa: E402
from ui.main_window import MainWindow, NexusSignalBridge  # noqa: E402
from ui.widgets import ToggleSwitch, qt_key_event_to_combo  # noqa: E402


def verify_config_roundtrip_and_frozen_path() -> None:
    """`sys.frozen` 경로 계산 및 `config.json` 한글/규칙 저장·로드 라운드트립을 검증한다."""
    # 1) sys.frozen=True 시뮬레이션 경로 확인
    orig_frozen = getattr(sys, "frozen", False)
    orig_exe = sys.executable
    try:
        sys.frozen = True  # type: ignore[attr-defined]
        sys.executable = r"C:\Portable\NEXUS_Remapper\nexus.exe"
        frozen_path = config_store_mod.get_config_path("config.json")
        assert str(frozen_path).endswith(r"NEXUS_Remapper\config.json")
    finally:
        if orig_frozen:
            sys.frozen = orig_frozen  # type: ignore[attr-defined]
        else:
            delattr(sys, "frozen")
        sys.executable = orig_exe

    # 2) 임시 config.json 저장/로드 및 우선순위 조회 검증
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "config.json"
        store = ConfigStore(cfg_file)
        store.load()

        rule_global = MappingRule(
            device_id="HID#VID_328F&PID_0021#TEST",
            device_name="eMeet 다이얼",
            event_type=EventType.DIAL_CW.value,
            code=0x00E9,
            profile="*",
            layer="default",
            action=ActionSpec(ActionType.MEDIA, {"command": "volume_up"}),
        )
        rule_revit = MappingRule(
            device_id="HID#VID_328F&PID_0021#TEST",
            device_name="eMeet 다이얼",
            event_type=EventType.DIAL_CW.value,
            code=0x00E9,
            profile="bim_cad",
            layer="default",
            action=ActionSpec(ActionType.ZOOM, {"direction": 1, "accel": 1.5}),
        )
        store.upsert_mapping(rule_global)
        store.upsert_mapping(rule_revit)
        store.save()

        reloaded = ConfigStore(cfg_file)
        reloaded.load()
        assert len(reloaded.mappings) == 2

        ev = InputEvent(
            "HID#VID_328F&PID_0021#TEST",
            EventType.DIAL_CW,
            0x00E9,
            1,
            source=EngineSource.RAW_HID,
        )
        matched_bim = reloaded.find_matching_rule(ev, "bim_cad", "default")
        matched_other = reloaded.find_matching_rule(ev, "browser", "default")
        assert matched_bim is not None and matched_bim.action.type_enum == ActionType.ZOOM
        assert matched_other is not None and matched_other.action.type_enum == ActionType.MEDIA

    print("[1/4] ConfigStore UTF-8 Roundtrip & sys.frozen Path Check OK")


def verify_headless_ui_and_signals() -> None:
    """헤드리스 PyQt6 UI 초기화, pyqtSignal 크로스 스레드 통신, 동적 카드/글로우를 검증한다."""
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        store = ConfigStore(cfg_path)
        store.load()

        registry = DeviceRegistry()
        # 헤드리스 테스트용 장치 레지스트리 구성 (보조 다이얼 포함)
        dial_dev = DeviceInfo(
            device_id="HID#VID_328F&PID_0021&COL01#HEADLESS",
            raw_path="",
            h_device=55501,
            device_type=DeviceType.HID_DIAL,
            raw_type=RIM_TYPEHID,
            name="eMeet eMute-E1 (Test)",
            vid="0x328F",
            pid="0x0021",
            usage_page=0x0C,
            usage=0x01,
            protected=False,
        )
        registry._devices[dial_dev.device_id] = dial_dev  # noqa: SLF001

        orchestrator = WindowOrchestrator(init_dpi_v2=False)
        watcher = ContextWatcher()
        engine_mgr = EngineManager(registry=registry)
        executor = ActionExecutor(dry_run=True, layers=["default", "bim", "media"])
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
        win.show()
        app.processEvents()

        assert win.engine_badge.text() == "[ENGINE: STOPPED]"
        assert win.topology_combo.count() >= 1

        # 1) 백그라운드 스레드에서 Listen Capture 시그널 발행 -> 동적 카드 생성 & 글로우 점등
        ev_cw = InputEvent(
            dial_dev.device_id,
            EventType.DIAL_CW,
            0x00E9,
            1,
            source=EngineSource.RAW_HID,
            device_name=dial_dev.display_name,
        )
        t1 = threading.Thread(
            target=lambda: bridge.listen_captured.emit(dial_dev, ev_cw),
            daemon=True,
        )
        t1.start()
        t1.join()
        app.processEvents()

        assert len(win.mapping_panel._cards) == 1  # noqa: SLF001
        card = next(iter(win.mapping_panel._cards.values()))  # noqa: SLF001
        assert card.is_glowing is True, "New Listen card must illuminate with neon glow!"
        assert dial_dev.is_registered is True

        # 글로우 자동 소등 확인 (260ms 타이머)
        time.sleep(0.32)
        app.processEvents()
        assert card.is_glowing is False, "Neon glow must clear after timer!"

        # 2) 백그라운드 스레드에서 Context 변경 시그널 발행 -> 상단 헤더 및 자동 레이어 전환
        ctx = ForegroundContext(
            hwnd=1234,
            pid=999,
            process_name="Revit.exe",
            executable_path=r"C:\Program Files\Autodesk\Revit.exe",
            window_title="Project1.rvt",
            matched_profile="bim_cad",
            matched_layer="bim",
        )
        t2 = threading.Thread(
            target=lambda: bridge.context_changed.emit(ctx),
            daemon=True,
        )
        t2.start()
        t2.join()
        app.processEvents()
        assert "Revit.exe [bim_cad]" in win.active_proc_lbl.text()
        assert executor.active_layer == "bim"
        assert "LAYER: bim" in win.active_layer_lbl.text()

        # 매칭되지 않은 앱(notepad.exe)으로 전환 시 default 레이어로 자동 복귀
        ctx_fallback = ForegroundContext(
            hwnd=1235,
            pid=1000,
            process_name="notepad.exe",
            executable_path=r"C:\Windows\System32\notepad.exe",
            window_title="Untitled - Notepad",
            matched_profile="default",
            matched_layer="default",
        )
        bridge.context_changed.emit(ctx_fallback)
        app.processEvents()
        assert executor.active_layer == "default"
        assert "LAYER: default" in win.active_layer_lbl.text()

        # 3) 백그라운드 스레드에서 실제 InputEvent 수신 시그널 발행 -> 트리거 점등 & 로그 기록
        t3 = threading.Thread(
            target=lambda: bridge.input_received.emit(ev_cw),
            daemon=True,
        )
        t3.start()
        t3.join()
        app.processEvents()
        assert card.is_glowing is True, "Triggered card must flash neon glow!"
        assert "[TRIGGER]" in win.log_view.toPlainText()

        # 4) config.json 파일에 매핑과 등록 장치가 영구 저장되었는지 확인
        reloaded = ConfigStore(cfg_path)
        reloaded.load()
        assert len(reloaded.mappings) == 1
        assert len(reloaded.data["devices"]) == 1

        # 5) 키/마우스 Press 전용 필터링 & 1:1 바인딩 키 검증
        kp_dev = DeviceInfo(
            device_id="HID#VID_248A&PID_8327&MI_01#KEYPAD",
            raw_path="",
            h_device=55502,
            device_type=DeviceType.KEYPAD,
            raw_type=RIM_TYPEKEYBOARD,
            name="Test Keypad",
            vid="0x248A",
            pid="0x8327",
            key_count=19,
            protected=False,
        )
        mouse_dev = DeviceInfo(
            device_id="HID#VID_046D&PID_C53A#AUX_MOUSE",
            raw_path="",
            h_device=55503,
            device_type=DeviceType.MOUSE,
            raw_type=0,
            name="Test Aux Mouse",
            protected=False,
        )
        registry._devices[kp_dev.device_id] = kp_dev  # noqa: SLF001
        registry._devices[mouse_dev.device_id] = mouse_dev  # noqa: SLF001

        ev_key_down = InputEvent(
            kp_dev.device_id, EventType.KEY_DOWN, 0x0047, 1, device_name=kp_dev.name
        )
        ev_key_up = InputEvent(
            kp_dev.device_id, EventType.KEY_UP, 0x0047, 0, device_name=kp_dev.name
        )
        assert ev_key_down.binding_key == ev_key_up.binding_key
        assert ev_key_down.is_release is False and ev_key_up.is_release is True

        ev_mouse_down = InputEvent(
            mouse_dev.device_id, EventType.MOUSE_BUTTON, 0x0001, 1, device_name=mouse_dev.name
        )
        ev_mouse_up = InputEvent(
            mouse_dev.device_id, EventType.MOUSE_BUTTON, 0x0001, 0, device_name=mouse_dev.name
        )
        assert ev_mouse_down.binding_key == ev_mouse_up.binding_key
        assert ev_mouse_down.is_release is False and ev_mouse_up.is_release is True

        # Listen Mode에서 Key Down+Up, Mouse Down+Up 전달 -> 각 1개씩 총 +2개만 생성되어야 함
        bridge.listen_captured.emit(kp_dev, ev_key_down)
        bridge.listen_captured.emit(kp_dev, ev_key_up)
        bridge.listen_captured.emit(mouse_dev, ev_mouse_down)
        bridge.listen_captured.emit(mouse_dev, ev_mouse_up)
        app.processEvents()
        assert len(win.mapping_panel._cards) == 3, (  # noqa: SLF001
            f"Expected 3 cards (1 dial + 1 key + 1 mouse), got {len(win.mapping_panel._cards)}"
        )

        # 키보드 Press/Release 1:1 트리거 실행(Release 시 중복 실행 금지) 검증
        kp_card = next(
            c for c in win.mapping_panel._cards.values() if c.rule.device_id == kp_dev.device_id  # noqa: SLF001
        )
        kp_card.param_edit.setText("Ctrl+S")
        kp_card._emit_updated_rule()  # noqa: SLF001
        app.processEvents()

        trig_before = win.log_view.toPlainText().count("[TRIGGER]")
        bridge.input_received.emit(ev_key_down)
        bridge.input_received.emit(ev_key_up)
        app.processEvents()
        trig_after = win.log_view.toPlainText().count("[TRIGGER]")
        assert trig_after - trig_before == 1, "Key press+release must execute action only ONCE!"

        # 6) 매핑 카드 개별 [삭제(X)] 버튼 클릭 -> 즉시 UI 및 config.json 삭제 반영
        kp_card.delete_btn.click()
        app.processEvents()
        assert len(win.mapping_panel._cards) == 2  # noqa: SLF001
        reloaded_after_del = ConfigStore(cfg_path)
        reloaded_after_del.load()
        assert len(reloaded_after_del.mappings) == 2
        assert all(m.rule_id != kp_card.rule.rule_id for m in reloaded_after_del.mappings)

        # 7) [목록 초기화] 버튼 + QMessageBox 확인/취소 검증 (다른 레이어 카드는 보존)
        bim_rule = MappingRule(
            device_id=dial_dev.device_id,
            device_name=dial_dev.name,
            event_type="dial_cw",
            code=0x00E9,
            profile="*",
            layer="bim",
            action=ActionSpec(ActionType.ZOOM, {"direction": 1, "accel": 2.0}),
        )
        win.mapping_panel._add_card_widget(bim_rule)  # noqa: SLF001
        win.config_store.upsert_mapping(bim_rule)
        win._save_all_config()  # noqa: SLF001
        app.processEvents()
        assert len(win.mapping_panel._cards) == 3  # noqa: SLF001 (default 2 + bim 1)

        orig_question = QMessageBox.question
        try:
            # 취소(No) 시 아무것도 삭제되지 않아야 함
            QMessageBox.question = staticmethod(lambda *a, **kw: QMessageBox.StandardButton.No)  # type: ignore[assignment]
            win.mapping_panel.clear_btn.click()
            app.processEvents()
            assert len(win.mapping_panel._cards) == 3  # noqa: SLF001

            # 확인(Yes) 시 현재 레이어(default) 2개만 비우고 bim 레이어 1개는 보존
            QMessageBox.question = staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes)  # type: ignore[assignment]
            win.mapping_panel.clear_btn.click()
            app.processEvents()
            assert len(win.mapping_panel._cards) == 1  # noqa: SLF001
            remaining_card = next(iter(win.mapping_panel._cards.values()))  # noqa: SLF001
            assert remaining_card.rule.layer == "bim"
        finally:
            QMessageBox.question = orig_question  # type: ignore[assignment]

        reloaded_after_clear = ConfigStore(cfg_path)
        reloaded_after_clear.load()
        assert len(reloaded_after_clear.mappings) == 1
        assert reloaded_after_clear.mappings[0].layer == "bim"

        # 8) @register_action 확장형 액션 레지스트리 및 UI 드롭다운 동적 연동 검증
        @register_action(
            "custom_ping",
            display_name="테스트 핑 액션",
            tag_label="PING",
            accent_color="#00FFCC",
            placeholder="핑 메시지 입력",
        )
        def _handle_custom_ping(
            exec_inst: ActionExecutor, params: dict, event: InputEvent | None
        ) -> ActionResult:
            del event
            return ActionResult(
                True, "custom_ping", f"PING:{params.get('value', '')}", exec_inst.dry_run
            )

        try:
            win.mapping_panel.refresh_action_registry()
            assert remaining_card.action_combo.findData("custom_ping") >= 0
            remaining_card.select_action_type("custom_ping")
            remaining_card.param_edit.setText("HELLO_NEXUS")
            remaining_card._emit_updated_rule()  # noqa: SLF001
            ping_res = executor.execute(remaining_card.rule.action)
            assert ping_res.success and ping_res.detail == "PING:HELLO_NEXUS"
        finally:
            ACTION_REGISTRY.pop("custom_ping", None)
            win.mapping_panel.refresh_action_registry()

        # 9) 창 배치 프리셋 다중 저장/Export/Import + 매핑 카드 프리셋 드롭다운 바인딩 검증
        p1 = LayoutPreset(
            name="주:Revit / 보조:CAD",
            topology_fingerprint="2M|3440x1440@100|1920x1080@100",
            environment_label="사무실 듀얼",
            placements=[WindowPlacementSpec("Revit.exe", 0, 0.0, 0.0, 1.0, 1.0)],
        )
        p2 = LayoutPreset(
            name="주:CAD / 보조:Revit+웹",
            topology_fingerprint="2M|3440x1440@100|1920x1080@100",
            environment_label="사무실 듀얼",
            placements=[WindowPlacementSpec("acad.exe", 0, 0.0, 0.0, 1.0, 1.0)],
        )
        orchestrator.save_preset(p1)
        orchestrator.save_preset(p2)
        win._refresh_preset_list()  # noqa: SLF001
        app.processEvents()
        assert win.preset_list.count() == 2

        remaining_card.select_action_type(ActionType.WORKSPACE_LAYOUT.value)
        app.processEvents()
        assert remaining_card.preset_combo.findText("주:Revit / 보조:CAD") >= 0
        assert remaining_card.preset_combo.findText("주:CAD / 보조:Revit+웹") >= 0
        remaining_card.preset_combo.setCurrentText("주:Revit / 보조:CAD")
        app.processEvents()
        assert remaining_card.rule.action.type_name == ActionType.WORKSPACE_LAYOUT.value
        assert remaining_card.rule.action.params.get("preset") == "주:Revit / 보조:CAD"

        presets_export_path = Path(tmpdir) / "workspace_presets.json"
        assert win.export_workspace_presets(presets_export_path) == 2
        orchestrator.delete_preset("주:CAD / 보조:Revit+웹")
        win._refresh_preset_list()  # noqa: SLF001
        assert win.preset_list.count() == 1
        assert win.import_workspace_presets(presets_export_path, mode="merge") == 2
        assert win.preset_list.count() == 2

        # 10) 매핑 매트릭스 Export / Import (replace & merge) 라운드트립 검증
        matrix_export_path = Path(tmpdir) / "mapping_matrix.json"
        assert win.export_mapping_matrix(matrix_export_path) == 1
        assert matrix_export_path.is_file()

        # replace: 비우고 다시 복원
        win.config_store.mappings.clear()
        win.mapping_panel.load_rules([])
        assert len(win.mapping_panel._cards) == 0  # noqa: SLF001
        assert win.import_mapping_matrix(matrix_export_path, mode="replace") == 1
        assert len(win.mapping_panel._cards) == 1  # noqa: SLF001

        # merge: 다른 규칙이 담긴 파일 병합
        merge_path = Path(tmpdir) / "mapping_merge.json"
        extra_store = ConfigStore(Path(tmpdir) / "extra.json")
        extra_store.mappings = [
            MappingRule(
                device_id=kp_dev.device_id,
                device_name=kp_dev.name,
                event_type="key",
                code=0x0048,
                profile="*",
                layer="default",
                action=ActionSpec(ActionType.KEY_COMBO, {"combo": "Ctrl+Alt+T"}),
            )
        ]
        extra_store.export_mappings_to_file(merge_path)
        assert win.import_mapping_matrix(merge_path, mode="merge") == 1
        assert len(win.mapping_panel._cards) == 2  # noqa: SLF001

        # 11) 무제한 사용자 정의 레이어 생성, .exe 바인딩 및 ContextWatcher 자동 전환 검증
        watcher.add_context_callback(bridge.context_changed.emit)
        win._on_create_layer("cad_custom")  # noqa: SLF001
        win._on_layer_processes_updated("cad_custom", ["CustomCAD.exe"])  # noqa: SLF001
        app.processEvents()
        assert "cad_custom" in store.list_layers()
        assert "cad_custom" in win.mapping_panel._layer_buttons  # noqa: SLF001

        watcher.notify_foreground_process("CustomCAD.exe", window_title="Model.dwg")
        app.processEvents()
        assert executor.active_layer == "cad_custom"
        assert "LAYER: cad_custom" in win.active_layer_lbl.text()

        watcher.notify_foreground_process("explorer.exe", window_title="Desktop")
        app.processEvents()
        assert executor.active_layer == "default"

        # 단일 레이어 번들 .json Export/Import 라운드트립
        layer_bundle_path = Path(tmpdir) / "layer_cad_custom.json"
        assert win.export_single_layer("cad_custom", layer_bundle_path) == 0
        win._on_delete_layer("cad_custom")  # noqa: SLF001
        assert "cad_custom" not in store.list_layers()
        restored_name, _ = win.import_single_layer(layer_bundle_path, mode="merge")
        assert restored_name == "cad_custom"
        assert "CustomCAD.exe" in store.get_layer_config("cad_custom").processes  # type: ignore[union-attr]

        # 12) 좌측 내비게이션 레일 6개 전용 화면 전환 무결성 검증
        assert len(win.nav_buttons) == 6
        assert win.page_stack.count() == 6
        for idx in range(6):
            win.nav_buttons[idx].click()
            app.processEvents()
            assert win.page_stack.currentIndex() == idx
            assert win.nav_buttons[idx].isChecked() is True

        # 13) 05 SETTINGS 실사용 옵션 검증 (시작명령, Bypass, 전체 백업/복원, 3개국어 전환)
        cmd_py_min = build_startup_command(minimized=True)
        assert "main.py" in cmd_py_min and "--minimized" in cmd_py_min

        # Bypass 일시정지 모드: 매핑 실행 차단 확인 후 재개
        win.set_bypass(True)
        app.processEvents()
        assert engine_mgr.bypass is True
        assert win.settings_page.bypass_chk.isChecked() is True
        trig_bypass_before = win.log_view.toPlainText().count("[TRIGGER]")
        bridge.input_received.emit(ev_cw)
        app.processEvents()
        assert win.log_view.toPlainText().count("[TRIGGER]") == trig_bypass_before
        win.set_bypass(False)

        # 전체 설정 백업 & 복원 라운드트립
        backup_path = Path(tmpdir) / "full_backup.json"
        win.backup_full_config(backup_path)
        assert backup_path.is_file()
        win.config_store.mappings.clear()
        win.mapping_panel.load_rules([])
        assert len(win.mapping_panel._cards) == 0  # noqa: SLF001
        win.restore_full_config(backup_path)
        app.processEvents()
        assert len(win.mapping_panel._cards) == 2  # noqa: SLF001

        # UI 언어 전환 (한국어 -> 日本語 -> English -> 한국어) 및 6개 전체 페이지 반영 확인
        win.apply_language("ja")
        assert "ハードウェア" in win.nav_buttons[0].text()
        assert "緊急脱出" in win.readme_page.browser.toPlainText()
        win.apply_language("en")
        assert "HARDWARE HUB" in win.nav_buttons[0].text()
        assert "Emergency Panic Exit" in win.readme_page.browser.toPlainText()
        win.apply_language("ko")
        assert "HARDWARE HUB" in win.nav_buttons[0].text()
        assert "비상 탈출 안전장치" in win.readme_page.browser.toPlainText()

        # 14) v2.0 핵심 업그레이드 검증 (별칭, DWM 보정, 2D 미니맵, 다이얼 가속/멀티제스처, 키캡 라벨, 단일 인스턴스)
        # 14-a) 장치 별칭(Alias) 편집 및 config.json 영구 반영
        win._on_device_alias_changed(dial_dev.device_id, "내 메인 노브")  # noqa: SLF001
        app.processEvents()
        assert dial_dev.display_name == "내 메인 노브"
        reloaded_alias = ConfigStore(cfg_path)
        reloaded_alias.load()
        assert any(d.get("alias") == "내 메인 노브" for d in reloaded_alias.data["devices"])

        # 14-b) DWM 투명 테두리 보정 토글 & 2D 미니맵 렌더링 확인
        win.settings_page.compensate_dwm_chk.setChecked(False)
        app.processEvents()
        assert orchestrator.compensate_dwm_frame is False
        win.settings_page.compensate_dwm_chk.setChecked(True)
        app.processEvents()
        assert orchestrator.compensate_dwm_frame is True
        win.workspace_page.minimap.repaint()
        app.processEvents()
        assert isinstance(win.settings_page.bypass_chk.switch, ToggleSwitch)

        # 14-c) 휴먼 리더블 물리 키캡 라벨 확인
        assert format_trigger_label("dial_cw", 0x00E9) == "DIAL CW ↻"
        assert format_trigger_label("dial_double_click", 0x00B5) == "DBL CLICK"
        assert format_trigger_label("dial_long_press", 0x00B5) == "LONG PRESS"
        assert len(format_trigger_label("key", 0x0047)) > 0

        # 14-d) 로터리 다이얼 가속 곡선(dt -> velocity 1.0~3.0x) 및 더블클릭/롱프레스 제스처 검증
        dial_parser = HidDialParser()
        evs_slow = dial_parser.parse_raw_hid(dial_dev, b"\x02\xE9\x00", now=10.0).events
        evs_fast = dial_parser.parse_raw_hid(dial_dev, b"\x02\xE9\x00", now=10.02).events
        assert len(evs_slow) == 1 and evs_slow[0].velocity == 1.0
        assert len(evs_fast) == 1 and evs_fast[0].velocity == 3.0
        zoom_res = executor.execute(
            ActionSpec(ActionType.ZOOM, {"direction": 1, "accel": 1.0, "modifiers": ["ctrl"]}),
            event=evs_fast[0],
        )
        assert "360" in zoom_res.detail, f"Expected 3x velocity wheel delta 360, got: {zoom_res.detail}"

        # 더블클릭(<=0.35s) 검증
        dial_parser.parse_raw_hid(dial_dev, b"\x02\xB5\x00", now=20.00)
        dial_parser.parse_raw_hid(dial_dev, b"\x02\x00\x00", now=20.08)
        dial_parser.parse_raw_hid(dial_dev, b"\x02\xB5\x00", now=20.18)
        dbl_evs = dial_parser.parse_raw_hid(dial_dev, b"\x02\x00\x00", now=20.24).events
        assert any(e.event_type == EventType.DIAL_DOUBLE_CLICK for e in dbl_evs)

        # 롱프레스(>=0.45s) 검증
        dial_parser.parse_raw_hid(dial_dev, b"\x02\xB5\x00", now=30.00)
        hold_evs = dial_parser.parse_raw_hid(dial_dev, b"\x02\x00\x00", now=30.60).events
        assert any(e.event_type == EventType.DIAL_LONG_PRESS for e in hold_evs)

        # 14-e) 단일 인스턴스 Mutex 중복 차단 검증
        test_mutex = f"Local\\NEXUS_Verify_Mutex_{os.getpid()}"
        g1 = SingleInstanceGuard(test_mutex)
        g2 = SingleInstanceGuard(test_mutex)
        try:
            assert g1.acquire() is True
            assert g2.acquire() is False
        finally:
            g2.release()
            g1.release()
        g3 = SingleInstanceGuard(test_mutex)
        try:
            assert g3.acquire() is True
        finally:
            g3.release()

        win.force_quit()
        app.processEvents()

    print("[2/4] Headless Command Center, Custom Layers & 6-View Navigation OK")
    print("[3/4] Matrix/Preset/Layer Export-Import & Auto Layer Switch OK")


def verify_main_entrypoint_test_mode() -> None:
    """`main.py --test-mode` 실행이 DPI V2, 엔진/UI 초기화 후 데드락 없이 종료되는지 검증한다."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, str(ROOT_DIR / "main.py"), "--test-mode"],
        cwd=str(ROOT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, f"main.py --test-mode failed: {proc.stderr}"
    print("[4/4] main.py --test-mode Clean Boot & Auto-Exit Check OK")


def main() -> int:
    verify_config_roundtrip_and_frozen_path()
    verify_headless_ui_and_signals()
    verify_main_entrypoint_test_mode()
    print("\nALL PHASE 4 CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
