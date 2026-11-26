"""PyQt6 Quiet Pro 2-Zone Darkroom Filament v1.1 메인 콘솔 윈도우.

- 92% 매트 흑요석/차콜 그레이 + 8% Thermal Filament (Gold / Solar Orange / Vermilion Red)
- 1px Warm Rim-Light는 최상단 커맨드 바(`TopCommandBar`)와 우측 메인 워크스페이스 프레임(`WorkspaceFocalShell`) 2곳에만 제한 적용
- 컴포넌트 인라인 `setStyleSheet` 및 Qt 위젯 드롭 섀도우 이펙트 0건
- 창/작업표시줄/트레이 전체에 `assets/app_icon.ico` (Darkroom Mode B) 일괄 적용
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core.actions import ActionExecutor
from core.config_store import (
    TRIGGER_MODE_FOCUS,
    ConfigStore,
    MappingRule,
    is_windows_startup_enabled,
    set_windows_startup,
)
from core.context_watcher import (
    ContextWatcher,
    ForegroundContext,
    list_running_process_names,
)
from core.device_registry import DeviceInfo, DeviceRegistry, DeviceScanDiff
from core.engine_manager import EngineManager, EngineMode
from core.events import InputEvent
from core.window_orchestrator import AUTO_PROFILE_KEY, WindowOrchestrator
from ui.device_panel import DevicePanel
from ui.i18n import tr
from ui.mapping_cards import MappingCardsPanel
from ui.theme import (
    apply_win11_dark_titlebar,
    build_qss,
    load_app_icon,
    repolish,
)
from ui.widgets import (
    DarkroomSurfaceCard,
    EmberCoreDot,
    LedStatusPill,
    NavRailButton,
    ProcessLayerConflictDialog,
)
from ui.workspace_views import (
    HardwareHubPage,
    MappingLayerPage,
    ReadMePage,
    SettingsPage,
    WorkspacePresetsPage,
)

_NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("Hardware Hub", "hub"),
    ("Workspace Presets", "workspace"),
    ("Mapping Layer", "layers"),
    ("Mapping Matrix", "matrix"),
    ("Settings", "settings"),
    ("Read Me", "book"),
)


def _create_nexus_tray_icon() -> QIcon:
    """번들된 Darkroom Mode B 멀티 해상도 앱 아이콘을 로드한다."""
    return load_app_icon()


class NexusSignalBridge(QObject):
    """백그라운드 워커 스레드와 PyQt6 UI 메인 스레드 간 안전한 pyqtSignal 브리지."""

    input_received = pyqtSignal(object)          # InputEvent
    listen_captured = pyqtSignal(object, object) # DeviceInfo, InputEvent
    context_changed = pyqtSignal(object)         # ForegroundContext
    devices_changed = pyqtSignal(object)         # DeviceScanDiff
    engine_mode_changed = pyqtSignal(object, str)
    panic_triggered = pyqtSignal()


class MainWindow(QMainWindow):
    """NEXUS Remapper 6뷰 전환형 Darkroom Filament v1.1 커맨드 센터."""

    def __init__(
        self,
        config_store: ConfigStore,
        registry: DeviceRegistry,
        engine_manager: EngineManager,
        context_watcher: ContextWatcher,
        orchestrator: WindowOrchestrator,
        executor: ActionExecutor,
        bridge: NexusSignalBridge | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("NexusMainWindow")
        self.config_store = config_store
        self.registry = registry
        self.engine_manager = engine_manager
        self.context_watcher = context_watcher
        self.orchestrator = orchestrator
        self.executor = executor
        self.bridge = bridge or NexusSignalBridge()

        self._active_profile: str = "default"
        self._active_process: str = "-"
        self._active_process_layer_override: str | None = None
        self._last_conflict_combo: frozenset[str] | None = None
        self._conflict_dialog: ProcessLayerConflictDialog | None = None
        self._process_poll_timer: QTimer = QTimer(self)
        self._process_poll_timer.setInterval(1500)
        self._process_poll_timer.timeout.connect(self._on_process_poll_tick)
        self._force_quit: bool = False
        self._language: str = str(self.config_store.settings.get("language", "ko"))
        self._app_icon: QIcon = load_app_icon()
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        self._tray_status_action: QAction | None = None
        self._tray_show_action: QAction | None = None
        self._tray_bypass_action: QAction | None = None
        self._tray_quit_action: QAction | None = None

        self.nav_buttons: list[NavRailButton] = []

        self.setWindowTitle("NEXUS Remapper & Workspace Orchestrator")
        if not self._app_icon.isNull():
            self.setWindowIcon(self._app_icon)
            app = QApplication.instance()
            if app is not None and app.windowIcon().isNull():
                app.setWindowIcon(self._app_icon)
        self.resize(1360, 840)
        self.setStyleSheet(build_qss())

        self._build_ui()
        self._wire_signals()
        self._init_tray_icon()
        self._sync_initial_state()
        apply_win11_dark_titlebar(int(self.winId()))

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        apply_win11_dark_titlebar(int(self.winId()))

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("RootCentral")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 1. 좌측 미니멀 사이드바 (220px, 1px right specular hairline) ─────
        nav_rail = QFrame()
        nav_rail.setProperty("surfaceRole", "sidebar")
        nav_rail.setFixedWidth(220)
        nav_layout = QVBoxLayout(nav_rail)
        nav_layout.setContentsMargins(14, 18, 14, 14)
        nav_layout.setSpacing(6)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(8, 0, 8, 8)
        brand_row.setSpacing(8)
        brand_dot = EmberCoreDot(live=True, tone="gold", size=14)
        brand_row.addWidget(brand_dot)
        brand = QLabel("NEXUS Remapper")
        brand.setProperty("role", "card-title")
        brand_row.addWidget(brand, 1)
        nav_layout.addLayout(brand_row)

        self.nav_hdr_lbl = QLabel("Workspace")
        self.nav_hdr_lbl.setProperty("role", "muted")
        nav_layout.addWidget(self.nav_hdr_lbl)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for idx, (label, icon_kind) in enumerate(_NAV_ITEMS):
            btn = NavRailButton(label, icon_kind)
            btn.clicked.connect(lambda _chk, page_idx=idx: self.switch_page(page_idx))
            self._nav_group.addButton(btn, idx)
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn)

        nav_layout.addStretch(1)

        rail_info = QFrame()
        rail_info.setProperty("surfaceRole", "inset")
        ri_layout = QVBoxLayout(rail_info)
        ri_layout.setContentsMargins(10, 10, 10, 10)
        ri_layout.setSpacing(8)

        self.panic_rail_lbl = QLabel("비상 탈출: ESC + F12")
        self.panic_rail_lbl.setProperty("role", "error")
        ri_layout.addWidget(self.panic_rail_lbl)

        self.hide_tray_btn = QPushButton("트레이로 숨기기")
        self.hide_tray_btn.setProperty("btnRole", "ghost")
        self.hide_tray_btn.setFixedHeight(28)
        self.hide_tray_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_tray_btn.clicked.connect(self.close)
        ri_layout.addWidget(self.hide_tray_btn)
        nav_layout.addWidget(rail_info)

        root.addWidget(nav_rail)

        # ── 2. 우측 메인 캔버스 (--bg-base) ──────────────────────────────────
        canvas = QWidget()
        c_layout = QVBoxLayout(canvas)
        c_layout.setContentsMargins(20, 16, 20, 14)
        c_layout.setSpacing(14)

        # (2-A) 상단 커맨드 바 — 1px Warm Rim-Light #1 (2곳 중 첫 번째)
        self.command_bar = DarkroomSurfaceCard(
            warm_rim=True, radius_token="--radius-pill", bg_token="--bg-surface"
        )
        self.command_bar.setFixedHeight(42)
        h_layout = QHBoxLayout(self.command_bar)
        h_layout.setContentsMargins(14, 0, 12, 0)
        h_layout.setSpacing(8)

        self.engine_pill = LedStatusPill(self.engine_manager.status_badge, tone="orange")
        self.engine_led = self.engine_pill.led
        self.engine_badge = self.engine_pill.text_label
        h_layout.addWidget(self.engine_pill)

        self.active_proc_lbl = QLabel("ACTIVE: - [default]")
        self.active_proc_lbl.setProperty("pillState", "neutral")
        self.active_proc_lbl.setFixedHeight(26)
        self.active_proc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(self.active_proc_lbl)

        self.active_layer_lbl = QLabel(f"LAYER: {self.executor.active_layer}")
        self.active_layer_lbl.setProperty("pillState", "gold")
        self.active_layer_lbl.setFixedHeight(26)
        self.active_layer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(self.active_layer_lbl)

        self.bypass_btn = QPushButton()
        self.bypass_btn.setProperty("btnRole", "bypass-pill")
        self.bypass_btn.setCheckable(True)
        self.bypass_btn.setFixedHeight(26)
        self.bypass_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bypass_btn.toggled.connect(self._on_bypass_toggled)
        h_layout.addWidget(self.bypass_btn)

        h_layout.addStretch(1)

        self.header_topology_lbl = QLabel("Monitors: Auto")
        self.header_topology_lbl.setProperty("pillState", "neutral")
        self.header_topology_lbl.setFixedHeight(26)
        self.header_topology_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(self.header_topology_lbl)

        c_layout.addWidget(self.command_bar)

        # (2-B) 에디토리얼 페이지 타이틀 + 활성 메인 워크스페이스 셸 (1px Warm Rim-Light #2)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(4, 0, 4, 0)
        self.page_title_lbl = QLabel("Hardware Hub")
        self.page_title_lbl.setProperty("role", "editorial")
        title_row.addWidget(self.page_title_lbl, 1)
        c_layout.addLayout(title_row)

        self.focal_shell = DarkroomSurfaceCard(
            warm_rim=True, radius_token="--radius-card", bg_token="--bg-canvas"
        )
        fs_layout = QVBoxLayout(self.focal_shell)
        fs_layout.setContentsMargins(12, 12, 12, 12)
        fs_layout.setSpacing(0)

        self.page_stack = QStackedWidget()

        self.device_panel = DevicePanel()
        self.hardware_page = HardwareHubPage(self.device_panel)

        self.workspace_page = WorkspacePresetsPage(
            initial_auto_launch=bool(
                self.config_store.settings.get("auto_launch_missing_apps", False)
            )
        )
        self.topology_combo = self.workspace_page.topology_combo
        self.snapshot_btn = self.workspace_page.snapshot_btn
        self.preset_list = self.workspace_page.preset_list
        self.auto_launch_chk = self.workspace_page.auto_launch_chk

        self.layer_page = MappingLayerPage()

        profiles_list = sorted(
            set(self.config_store.data.get("process_profiles", {}).values())
        )
        layers_list = self.config_store.list_layers()
        self.mapping_panel = MappingCardsPanel(
            profiles=profiles_list, layers=layers_list
        )

        startup_checked = bool(
            self.config_store.settings.get("run_at_startup", False)
            or is_windows_startup_enabled()
        )
        self.settings_page = SettingsPage(
            config_path=str(self.config_store.config_path),
            prefer_kernel=bool(
                self.config_store.settings.get("prefer_kernel_engine", True)
            ),
            minimize_tray=bool(
                self.config_store.settings.get("minimize_to_tray", True)
            ),
            auto_switch_layer=bool(
                self.config_store.settings.get("auto_switch_layer", True)
            ),
            compensate_dwm=bool(
                self.config_store.settings.get("compensate_dwm_frame", True)
            ),
            run_at_startup=startup_checked,
            start_minimized=bool(
                self.config_store.settings.get("start_minimized", False)
            ),
            bypass_remapping=bool(
                self.config_store.settings.get("bypass_remapping", False)
            ),
            language=self._language,
        )
        self.log_view = self.settings_page.log_view

        self.readme_page = ReadMePage()

        self.page_stack.addWidget(self.hardware_page)   # 0
        self.page_stack.addWidget(self.workspace_page)  # 1
        self.page_stack.addWidget(self.layer_page)      # 2
        self.page_stack.addWidget(self.mapping_panel)   # 3
        self.page_stack.addWidget(self.settings_page)   # 4
        self.page_stack.addWidget(self.readme_page)     # 5

        fs_layout.addWidget(self.page_stack, 1)
        c_layout.addWidget(self.focal_shell, 1)

        # (2-C) 하단 상태 피드백 바 (Quiet Darkroom)
        self.status_ticker = QFrame()
        self.status_ticker.setProperty("surfaceRole", "footer-bar")
        self.status_ticker.setFixedHeight(28)
        st_layout = QHBoxLayout(self.status_ticker)
        st_layout.setContentsMargins(12, 0, 12, 0)
        st_layout.setSpacing(8)

        self.ticker_dot = EmberCoreDot(live=True, tone="gold", size=12)
        st_layout.addWidget(self.ticker_dot)

        self.status_ticker_lbl = QLabel("NEXUS Darkroom ready")
        self.status_ticker_lbl.setProperty("role", "mono-muted")
        st_layout.addWidget(self.status_ticker_lbl, 1)

        panic_hint = QLabel("Panic Exit: ESC + F12")
        panic_hint.setProperty("role", "mono-muted")
        st_layout.addWidget(panic_hint)

        c_layout.addWidget(self.status_ticker)
        root.addWidget(canvas, 1)

        self.switch_page(0)

    def switch_page(self, index: int) -> None:
        """좌측 사이드바 선택에 따라 우측 워크스페이스 화면을 전환한다."""
        if not (0 <= index < self.page_stack.count()):
            return
        self.page_stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            active = i == index
            btn.blockSignals(True)
            btn.setChecked(active)
            btn.blockSignals(False)
            btn.apply_active_style(active)
        self.page_title_lbl.setText(tr(self._language, f"nav_{index}"))
        if index == 2:
            self.layer_page.refresh_running_processes()

    def _wire_signals(self) -> None:
        self.engine_manager.add_event_callback(self.bridge.input_received.emit)
        self.engine_manager.add_listen_callback(self.bridge.listen_captured.emit)
        self.engine_manager.add_mode_callback(self.bridge.engine_mode_changed.emit)
        self.engine_manager.add_panic_callback(self.bridge.panic_triggered.emit)
        self.context_watcher.add_context_callback(self.bridge.context_changed.emit)
        self.registry.add_change_callback(self.bridge.devices_changed.emit)

        self.bridge.input_received.connect(self._on_input_received)
        self.bridge.listen_captured.connect(self._on_listen_captured)
        self.bridge.context_changed.connect(self._on_context_changed)
        self.bridge.devices_changed.connect(self._on_devices_changed)
        self.bridge.engine_mode_changed.connect(self._on_engine_mode_changed)
        self.bridge.panic_triggered.connect(self._on_panic_triggered)

        self.device_panel.listen_toggled.connect(self._on_listen_toggled)
        self.device_panel.refresh_requested.connect(self._on_refresh_devices)
        self.device_panel.device_selected.connect(self._on_device_selected)
        self.device_panel.protection_toggled.connect(self._on_protection_toggled)
        self.device_panel.alias_changed.connect(self._on_device_alias_changed)

        self.workspace_page.topology_changed.connect(self._on_topology_key_changed)
        self.workspace_page.snapshot_requested.connect(self._on_capture_snapshot)
        self.workspace_page.apply_preset_requested.connect(self._on_apply_preset_by_name)
        self.workspace_page.delete_preset_requested.connect(self._on_delete_preset_by_name)
        self.workspace_page.focus_process_changed.connect(self._on_preset_focus_changed)
        self.workspace_page.auto_launch_toggled.connect(self._on_auto_launch_toggled)
        self.workspace_page.export_presets_requested.connect(self._on_export_presets_dialog)
        self.workspace_page.import_presets_requested.connect(self._on_import_presets_dialog)

        self.layer_page.layer_created.connect(self._on_create_layer)
        self.layer_page.layer_mode_changed.connect(self._on_layer_mode_changed)
        self.layer_page.layer_renamed.connect(self._on_rename_layer)
        self.layer_page.layer_deleted.connect(self._on_delete_layer)
        self.layer_page.layer_processes_updated.connect(self._on_layer_processes_updated)
        self.layer_page.export_layer_requested.connect(self._on_export_layer_dialog)
        self.layer_page.import_layer_requested.connect(self._on_import_layer_dialog)

        self.mapping_panel.rule_upserted.connect(self._on_rule_upserted)
        self.mapping_panel.rule_deleted.connect(self._on_rule_deleted)
        self.mapping_panel.rules_cleared.connect(self._on_rules_cleared)
        self.mapping_panel.layer_selected.connect(self._on_layer_selected)
        self.mapping_panel.listen_toggled.connect(self._on_listen_toggled)
        self.mapping_panel.export_matrix_requested.connect(self._on_export_matrix_dialog)
        self.mapping_panel.import_matrix_requested.connect(self._on_import_matrix_dialog)

        self.settings_page.prefer_kernel_toggled.connect(self._on_prefer_kernel_toggled)
        self.settings_page.minimize_tray_toggled.connect(self._on_minimize_tray_toggled)
        self.settings_page.auto_switch_layer_toggled.connect(self._on_auto_switch_layer_toggled)
        self.settings_page.compensate_dwm_toggled.connect(self._on_compensate_dwm_toggled)
        self.settings_page.run_at_startup_toggled.connect(self._on_run_at_startup_toggled)
        self.settings_page.start_minimized_toggled.connect(self._on_start_minimized_toggled)
        self.settings_page.bypass_toggled.connect(self._on_bypass_toggled)
        self.settings_page.language_changed.connect(self._on_language_changed)
        self.settings_page.open_config_folder_requested.connect(self._on_open_config_folder)
        self.settings_page.backup_config_requested.connect(self._on_backup_config_dialog)
        self.settings_page.restore_config_requested.connect(self._on_restore_config_dialog)
        self.settings_page.save_now_requested.connect(self._on_save_now)

        self.executor.register_layer_change_handler(self._on_executor_layer_changed)

    def _init_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray_ico = self._app_icon if not self._app_icon.isNull() else _create_nexus_tray_icon()
        tray = QSystemTrayIcon(tray_ico, self)

        menu = QMenu(self)
        show_act = QAction(tr(self._language, "tray_show"), self)
        show_act.triggered.connect(self._restore_from_tray)
        menu.addAction(show_act)

        status_act = QAction("현재 엔진/프로파일 상태: 초기화 중", self)
        status_act.setEnabled(False)
        menu.addAction(status_act)

        bypass_act = QAction(tr(self._language, "tray_bypass"), self)
        bypass_act.setCheckable(True)
        bypass_act.setChecked(self.engine_manager.bypass)
        bypass_act.toggled.connect(self._on_bypass_toggled)
        menu.addAction(bypass_act)

        menu.addSeparator()

        quit_act = QAction(tr(self._language, "tray_quit"), self)
        quit_act.triggered.connect(self.force_quit)
        menu.addAction(quit_act)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()

        self._tray_icon = tray
        self._tray_menu = menu
        self._tray_show_action = show_act
        self._tray_status_action = status_act
        self._tray_bypass_action = bypass_act
        self._tray_quit_action = quit_act
        self._update_tray_status()

    def _update_tray_status(self) -> None:
        bypass_tag = " [BYPASS]" if self.engine_manager.bypass else ""
        status_summary = (
            f"{self.engine_manager.status_badge}{bypass_tag} · "
            f"{self._active_process} [{self._active_profile}] · "
            f"Layer:{self.executor.active_layer}"
        )
        if self._tray_status_action is not None:
            self._tray_status_action.setText(f"상태: {status_summary}")
        if self._tray_icon is not None:
            self._tray_icon.setToolTip(f"NEXUS Remapper | {status_summary}")

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_from_tray()

    def _sync_initial_state(self) -> None:
        self._update_engine_badge(
            self.engine_manager.mode, self.engine_manager.fallback_reason
        )
        self.device_panel.refresh_devices(self.registry.get_all_devices())
        self._sync_layers_everywhere()
        self._refresh_topology_dropdown()
        self._refresh_preset_list()
        self.mapping_panel.load_rules(self.config_store.mappings)
        self.mapping_panel.set_active_layer(self.executor.active_layer)
        self.active_layer_lbl.setText(f"LAYER: {self.executor.active_layer}")
        self.layer_page.refresh_running_processes()
        self.set_bypass(
            bool(self.config_store.settings.get("bypass_remapping", False)),
            persist=False,
        )
        self.apply_language(self._language)

        if self.context_watcher.current_context is not None:
            self._on_context_changed(self.context_watcher.current_context)
        else:
            self.evaluate_process_layer_state()

        self.append_log(f"NEXUS 커맨드 센터 초기화 완료 | {self.engine_manager.status_badge}")

    def _sync_layers_everywhere(self) -> None:
        layers = self.config_store.list_layers()
        self.executor.set_layers(layers)
        focus_bindings = self.config_store.get_focus_layer_bindings()
        process_bindings = self.config_store.get_process_layer_bindings()
        self.context_watcher.set_layer_bindings(focus_bindings)
        self.context_watcher.set_process_layer_bindings(process_bindings)
        self.mapping_panel.set_layers(layers)
        self.layer_page.refresh_layers(self.config_store.layer_configs)
        if process_bindings:
            if not self._process_poll_timer.isActive():
                self._process_poll_timer.start()
        else:
            if self._process_poll_timer.isActive():
                self._process_poll_timer.stop()

    def _close_conflict_dialog(self) -> None:
        if self._conflict_dialog is not None:
            try:
                self._conflict_dialog.close()
            except RuntimeError:
                pass
            self._conflict_dialog = None

    def _on_process_poll_tick(self) -> None:
        if not self.config_store.get_process_layer_bindings():
            self._process_poll_timer.stop()
            return
        self.evaluate_process_layer_state()

    def _on_conflict_layer_chosen(self, chosen_layer: str) -> None:
        if chosen_layer not in self.config_store.list_layers():
            return
        self._active_process_layer_override = chosen_layer
        if self.executor.active_layer != chosen_layer:
            self.executor.shift_layer(chosen_layer, mode="set")
        else:
            self.active_layer_lbl.setText(f"LAYER: {chosen_layer}")
            self._update_tray_status()
        self.append_log(
            f"[PROCESS LAYER] 충돌 선택 적용 ➔ '{chosen_layer}'",
            tone="gold",
        )

    def evaluate_process_layer_state(
        self, running_processes: list[str] | set[str] | None = None
    ) -> list[str]:
        """실행 중인 프로세스 목록을 기준으로 `프로세스 지정` 모드 레이어를 평가·전환한다."""
        process_bindings = self.config_store.get_process_layer_bindings()
        if running_processes is None:
            if not process_bindings:
                candidates: list[str] = []
            else:
                candidates = self.config_store.resolve_running_process_layers(
                    list_running_process_names()
                )
        else:
            candidates = self.config_store.resolve_running_process_layers(
                running_processes
            )

        if len(candidates) == 0:
            was_override = self._active_process_layer_override is not None
            self._last_conflict_combo = None
            self._close_conflict_dialog()
            self._active_process_layer_override = None
            if was_override and self.config_store.settings.get("auto_switch_layer", True):
                fallback_layer = self.config_store.resolve_layer_for_process(
                    self._active_process
                )
                if fallback_layer != self.executor.active_layer:
                    self.executor.shift_layer(fallback_layer, mode="set")
            return candidates

        if len(candidates) == 1:
            chosen = candidates[0]
            self._last_conflict_combo = None
            self._close_conflict_dialog()
            self._active_process_layer_override = chosen
            if self.executor.active_layer != chosen:
                self.executor.shift_layer(chosen, mode="set")
            return candidates

        combo = frozenset(candidates)
        if combo == self._last_conflict_combo:
            return candidates

        self._last_conflict_combo = combo
        self._close_conflict_dialog()
        candidate_pairs = [
            (layer_name, process_bindings.get(layer_name, ""))
            for layer_name in candidates
        ]
        dlg = ProcessLayerConflictDialog(
            candidates=candidate_pairs,
            active_layer=self.executor.active_layer,
            lang=self._language,
            parent=None,
        )
        dlg.layer_chosen.connect(self._on_conflict_layer_chosen)
        self._conflict_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self.append_log(
            f"[PROCESS LAYER] 동시 실행 충돌 감지 ({', '.join(candidates)}) — 선택 팝업 표시",
            tone="orange",
        )
        return candidates

    def _update_engine_badge(self, mode: EngineMode, reason: str = "") -> None:
        badge_text = self.engine_manager.status_badge
        if mode == EngineMode.KERNEL:
            pill_state, live = "gold", True
        elif mode == EngineMode.USER_FALLBACK:
            pill_state, live = "orange", True
        else:
            pill_state, live = "red", False

        self.engine_pill.setToolTip(reason or badge_text)
        self.engine_pill.set_state(badge_text, pill_state=pill_state, live=live)
        self._update_tray_status()

    def _refresh_topology_dropdown(self) -> None:
        mons = self.orchestrator.enumerate_monitors()
        fp = self.orchestrator.get_topology_fingerprint(mons)
        self.workspace_page.set_monitors_summary(mons, fp)
        choices = self.orchestrator.get_available_environment_choices()
        selected = self.orchestrator.selected_profile_mode
        self.workspace_page.set_topology_choices(choices, selected)
        mode_tag = "Auto" if selected == AUTO_PROFILE_KEY else "Manual"
        self.header_topology_lbl.setText(f"Monitors({len(mons)}): {mode_tag} · {fp}")

    def _refresh_preset_list(self) -> None:
        presets = self.orchestrator.list_presets()
        self.workspace_page.refresh_presets(presets)
        self.mapping_panel.set_available_presets([p.name for p in presets])

    def _set_ticker(self, message: str, tone: str = "gold") -> None:
        self.ticker_dot.set_state(live=(tone in ("gold", "orange")), tone=tone)
        self.status_ticker_lbl.setText(message)

    def append_log(self, message: str, tone: str = "gold") -> None:
        self.log_view.appendPlainText(message)
        self._set_ticker(message, tone=tone)

    def _save_all_config(self) -> None:
        self.config_store.data["devices"] = self.registry.export_devices(
            registered_only=True
        )
        presets, labels = self.orchestrator.export_presets()
        self.config_store.data["layout_presets"] = presets
        self.config_store.data["topology_labels"] = labels
        self.config_store.settings["selected_topology"] = (
            self.orchestrator.selected_profile_mode
        )
        self.config_store.settings["active_layer"] = self.executor.active_layer
        self.config_store.save()

    # ── UI / Bridge 슬롯 ─────────────────────────────────────────────────────

    @pyqtSlot(object)
    def _on_input_received(self, event: InputEvent) -> None:
        self.hardware_page.append_signal(event)
        if self.registry.is_listening or event.is_release:
            return

        rule = self.config_store.find_matching_rule(
            event=event,
            active_profile=self._active_profile,
            active_layer=self.executor.active_layer,
        )
        if rule is not None:
            self.mapping_panel.flash_card_for_rule(rule.rule_id)
            res = self.executor.execute(rule.action, event=event)
            self.append_log(
                f"[TRIGGER] {event.device_name} | {event.event_type_str} ➔ {res.detail}",
                tone="orange",
            )
        else:
            self.mapping_panel.flash_matching_event(event)
            self._set_ticker(
                f"[INPUT] {event.device_name} | {event.event_type_str} (미매핑)",
                tone="muted",
            )

    @pyqtSlot(object, object)
    def _on_listen_captured(self, device: DeviceInfo, event: InputEvent) -> None:
        if device.protected or event.is_release:
            return
        if not device.is_registered:
            try:
                self.registry.register_device(device.device_id)
            except PermissionError:
                return
            self.device_panel.refresh_devices(self.registry.get_all_devices())

        rule = self.mapping_panel.create_or_focus_from_event(
            event=event,
            device_name=device.display_name,
            profile="*",
            layer=self.executor.active_layer,
        )
        if rule is None:
            return
        self.config_store.upsert_mapping(rule)
        self._save_all_config()
        self.append_log(
            f"[LISTEN CAPTURE] {device.display_name} | {rule.event_type} (code={event.code})",
            tone="gold",
        )

    @pyqtSlot(object)
    def _on_context_changed(self, ctx: ForegroundContext) -> None:
        self._active_profile = ctx.matched_profile
        self._active_process = ctx.process_name or "-"
        self.active_proc_lbl.setText(
            f"ACTIVE: {self._active_process} [{ctx.matched_profile}]"
        )

        if (
            self._active_process_layer_override is None
            and self.config_store.get_process_layer_bindings()
        ):
            self.evaluate_process_layer_state()

        if (
            self._active_process_layer_override is None
            and self.config_store.settings.get("auto_switch_layer", True)
        ):
            focus_layers = set(self.config_store.get_focus_layer_bindings().keys()) | {"default"}
            target_layer = (
                ctx.matched_layer
                if ctx.matched_layer in focus_layers
                else self.config_store.resolve_layer_for_process(self._active_process)
            )
            if target_layer != self.executor.active_layer:
                self.executor.shift_layer(target_layer, mode="set")

        self._update_tray_status()
        self._set_ticker(
            f"[CONTEXT] {self._active_process} (프로파일:{ctx.matched_profile} · 레이어:{self.executor.active_layer})",
            tone="gold",
        )

    @pyqtSlot(object)
    def _on_devices_changed(self, diff: DeviceScanDiff) -> None:
        self.device_panel.refresh_devices(self.registry.get_all_devices())
        if diff.added or diff.removed:
            self.append_log(
                f"[HOT-PLUG] +{len(diff.added)} / -{len(diff.removed)} (연결={diff.connected_count})",
                tone="orange",
            )

    @pyqtSlot(object, str)
    def _on_engine_mode_changed(self, mode: EngineMode, reason: str) -> None:
        self._update_engine_badge(mode, reason)
        self.append_log(f"[ENGINE] {self.engine_manager.status_badge} {reason}")

    @pyqtSlot()
    def _on_panic_triggered(self) -> None:
        self._update_engine_badge(EngineMode.STOPPED, "Panic Exit (ESC+F12)")
        self.append_log(
            "[PANIC EXIT] ESC + F12 감지 ➔ 모든 훅 및 엔진 즉시 해제",
            tone="red",
        )
        self.force_quit()

    @pyqtSlot(bool)
    def _on_listen_toggled(self, active: bool) -> None:
        self.device_panel.set_listen_active(active)
        self.mapping_panel.set_listen_active(active)
        if active:
            if not self.registry.is_listening:
                self.registry.begin_listen()
                self.append_log(
                    "[LISTEN MODE] 활성화 — 보조 키패드나 다이얼을 조작하세요.",
                    tone="gold",
                )
        else:
            if self.registry.is_listening:
                self.registry.end_listen()
                self.append_log("[LISTEN MODE] 종료", tone="muted")

    @pyqtSlot()
    def _on_refresh_devices(self) -> None:
        diff = self.registry.refresh_devices()
        self.device_panel.refresh_devices(self.registry.get_all_devices())
        self.append_log(f"[SCAN] 장치 재스캔 완료 (연결={diff.connected_count})")

    @pyqtSlot(str)
    def _on_device_selected(self, device_id: str) -> None:
        dev = self.registry.get_device(device_id) if device_id else None
        self.mapping_panel.set_device_filter(
            device_id, dev.display_name if dev else tr(self._language, "matrix_all_devices")
        )
        self.device_panel.refresh_devices(self.registry.get_all_devices())

    @pyqtSlot(str, str)
    def _on_device_alias_changed(self, device_id: str, alias: str) -> None:
        if self.registry.set_device_alias(device_id, alias):
            self.device_panel.refresh_devices(self.registry.get_all_devices())
            self._save_all_config()
            self.append_log(
                f"[ALIAS] {device_id} ➔ '{alias or '(기본 이름)'}'",
                tone="gold",
            )

    @pyqtSlot(str, bool)
    def _on_protection_toggled(self, device_id: str, protected: bool) -> None:
        try:
            self.registry.set_protected(device_id, protected, force=True)
        except PermissionError as exc:
            QMessageBox.warning(self, "장치 보호 오류", str(exc))
            return
        self.device_panel.refresh_devices(self.registry.get_all_devices())
        self._save_all_config()
        self.append_log(
            f"[SAFEGUARD] {device_id} ➔ {'PROTECTED' if protected else 'AUXILIARY'}",
            tone="orange" if protected else "gold",
        )

    # ── 사용자 정의 레이어 관리 슬롯 ─────────────────────────────────────────

    @pyqtSlot(str)
    @pyqtSlot(str, str)
    def _on_create_layer(
        self, name: str, trigger_mode: str = TRIGGER_MODE_FOCUS
    ) -> None:
        try:
            self.config_store.create_layer(name, trigger_mode=trigger_mode)
        except ValueError as exc:
            QMessageBox.warning(self, "레이어 생성 오류", str(exc))
            return
        self._sync_layers_everywhere()
        self._save_all_config()
        self.append_log(
            f"[LAYER] 새 레이어 생성 ➔ '{name}' ({trigger_mode})",
            tone="gold",
        )

    @pyqtSlot(str, str)
    def _on_layer_mode_changed(self, layer_name: str, trigger_mode: str) -> None:
        try:
            changed = self.config_store.set_layer_trigger_mode(layer_name, trigger_mode)
        except ValueError as exc:
            QMessageBox.warning(self, "레이어 모드 변경 오류", str(exc))
            self._sync_layers_everywhere()
            return
        self._sync_layers_everywhere()
        if changed:
            self._save_all_config()
            self.evaluate_process_layer_state()
            self.append_log(
                f"[LAYER MODE] '{layer_name}' ➔ {trigger_mode}",
                tone="gold",
            )

    @pyqtSlot(str, str)
    def _on_rename_layer(self, old_name: str, new_name: str) -> None:
        if not self.config_store.rename_layer(old_name, new_name):
            QMessageBox.warning(self, "이름 변경 실패", "중복되거나 유효하지 않은 이름입니다.")
            return
        if self._active_process_layer_override == old_name:
            self._active_process_layer_override = new_name
        self._sync_layers_everywhere()
        self.mapping_panel.load_rules(self.config_store.mappings)
        if self.executor.active_layer == old_name:
            self.executor.shift_layer(new_name, mode="set")
        self._save_all_config()
        self.evaluate_process_layer_state()
        self.append_log(f"[LAYER] 이름 변경 ➔ '{old_name}' → '{new_name}'", tone="gold")

    @pyqtSlot(str)
    def _on_delete_layer(self, name: str) -> None:
        if not self.config_store.delete_layer(name, delete_rules=True):
            return
        if self._active_process_layer_override == name:
            self._active_process_layer_override = None
        self._sync_layers_everywhere()
        self.mapping_panel.load_rules(self.config_store.mappings)
        if self.executor.active_layer == name:
            self.executor.shift_layer("default", mode="set")
        self._save_all_config()
        self.evaluate_process_layer_state()
        self.append_log(f"[LAYER] 레이어 삭제 완료 ➔ '{name}'", tone="red")

    @pyqtSlot(str, list)
    def _on_layer_processes_updated(self, layer_name: str, processes: list[str]) -> None:
        try:
            changed = self.config_store.set_layer_processes(layer_name, processes)
        except ValueError as exc:
            QMessageBox.warning(self, "프로세스 바인딩 오류", str(exc))
            self._sync_layers_everywhere()
            return
        if changed:
            self._sync_layers_everywhere()
            self._save_all_config()
            self.evaluate_process_layer_state()
            self.append_log(
                f"[LAYER BIND] '{layer_name}' ➔ {', '.join(processes) or '없음'}",
                tone="gold",
            )

    @pyqtSlot(object)
    def _on_rule_upserted(self, rule: MappingRule) -> None:
        self.config_store.upsert_mapping(rule)
        self._save_all_config()

    @pyqtSlot(str)
    def _on_rule_deleted(self, rule_id: str) -> None:
        self.config_store.remove_mapping(rule_id)
        self._save_all_config()
        self.append_log(f"[MAPPING] 매핑 카드 삭제 완료 (id={rule_id})", tone="muted")

    @pyqtSlot(list)
    def _on_rules_cleared(self, rule_ids: list[str]) -> None:
        removed = self.config_store.remove_mappings(rule_ids)
        self._save_all_config()
        self.append_log(
            f"[MAPPING] 선택 범위 매핑 목록 초기화 완료 ({removed}개 삭제)",
            tone="orange",
        )

    @pyqtSlot(str)
    def _on_layer_selected(self, layer: str) -> None:
        if self.executor.active_layer != layer:
            self.executor.shift_layer(layer, mode="set")

    def _on_executor_layer_changed(self, layer: str) -> None:
        self.mapping_panel.set_active_layer(layer)
        self.active_layer_lbl.setText(f"LAYER: {layer}")
        self._save_all_config()
        self._update_tray_status()
        self.append_log(f"[LAYER] 활성 레이어 전환 ➔ {layer}", tone="gold")

    @pyqtSlot(str)
    def _on_topology_key_changed(self, key: str) -> None:
        self.orchestrator.select_profile_mode(key or AUTO_PROFILE_KEY)
        self._refresh_topology_dropdown()
        self._save_all_config()
        self.append_log(f"[TOPOLOGY] 모니터 환경 모드 ➔ {key}", tone="gold")

    def _on_capture_snapshot(self) -> None:
        default_name = f"Preset_{len(self.orchestrator.list_presets()) + 1}"
        name, ok = QInputDialog.getText(
            self,
            "창 배치 스냅샷 저장",
            "저장할 레이아웃 프리셋 이름을 입력하세요:",
            text=default_name,
        )
        if not ok or not name.strip():
            return
        preset = self.orchestrator.capture_snapshot(name.strip())
        self._refresh_topology_dropdown()
        self._refresh_preset_list()
        self._save_all_config()
        self.append_log(
            f"[SNAPSHOT] '{preset.name}' 저장 ({len(preset.placements)}개 창, {preset.topology_fingerprint})",
            tone="gold",
        )

    @pyqtSlot(bool)
    def _on_auto_launch_toggled(self, checked: bool) -> None:
        self.config_store.settings["auto_launch_missing_apps"] = checked
        self.config_store.save()

    @pyqtSlot(str, bool)
    def _on_apply_preset_by_name(self, preset_name: str, auto_launch: bool) -> None:
        res = self.orchestrator.apply_preset(preset_name, auto_launch=auto_launch)
        self.append_log(
            f"[LAYOUT] '{preset_name}' 적용 ➔ 이동 {res.moved_count}, 실행 {res.launched_count}, "
            f"건너뜀 {len(res.skipped_processes)}",
            tone="gold",
        )

    @pyqtSlot(str)
    def _on_delete_preset_by_name(self, preset_name: str) -> None:
        self.orchestrator.delete_preset(preset_name)
        self._refresh_preset_list()
        self._save_all_config()
        self.append_log(f"[LAYOUT] '{preset_name}' 삭제 완료", tone="muted")

    @pyqtSlot(str, str)
    def _on_preset_focus_changed(self, preset_name: str, focus_process: str) -> None:
        preset = self.orchestrator.get_preset(preset_name)
        if preset is None:
            return
        preset.focus_process = focus_process
        self._refresh_preset_list()
        self._save_all_config()

    @pyqtSlot(bool)
    def _on_prefer_kernel_toggled(self, checked: bool) -> None:
        self.config_store.settings["prefer_kernel_engine"] = checked
        self._save_all_config()

    @pyqtSlot(bool)
    def _on_minimize_tray_toggled(self, checked: bool) -> None:
        self.config_store.settings["minimize_to_tray"] = checked
        self._save_all_config()

    @pyqtSlot(bool)
    def _on_compensate_dwm_toggled(self, checked: bool) -> None:
        self.config_store.settings["compensate_dwm_frame"] = checked
        self.orchestrator.compensate_dwm_frame = checked
        self._save_all_config()
        self.append_log(
            f"[DWM] 창 투명 테두리 보정 ➔ {'ON' if checked else 'OFF'}",
            tone="gold" if checked else "muted",
        )

    def set_bypass(self, enabled: bool, persist: bool = True) -> None:
        """리매핑 일시 정지(Bypass) 상태를 헤더, 설정 탭, 트레이, 엔진에 일괄 동기화한다."""
        self.engine_manager.set_bypass(enabled)
        self.config_store.settings["bypass_remapping"] = bool(enabled)

        self.bypass_btn.blockSignals(True)
        self.bypass_btn.setChecked(enabled)
        self.bypass_btn.blockSignals(False)
        self.bypass_btn.setProperty("bypass", enabled)
        self.bypass_btn.setText(tr(self._language, "bypass_on" if enabled else "bypass_off"))
        repolish(self.bypass_btn)

        self.settings_page.set_bypass_checked(enabled)
        if self._tray_bypass_action is not None:
            self._tray_bypass_action.blockSignals(True)
            self._tray_bypass_action.setChecked(enabled)
            self._tray_bypass_action.blockSignals(False)

        self._update_tray_status()
        if persist:
            self._save_all_config()

    def apply_language(self, lang: str) -> None:
        """내장 다국어 사전(`ko`/`ja`/`en`)을 6개 전체 페이지와 헤더·트레이에 즉시 적용한다."""
        self._language = lang if lang in ("ko", "ja", "en") else "ko"
        self.config_store.settings["language"] = self._language

        self.nav_hdr_lbl.setText(tr(self._language, "nav_header"))
        self.panic_rail_lbl.setText(tr(self._language, "panic_short"))
        for idx, btn in enumerate(self.nav_buttons):
            btn.set_label(tr(self._language, f"nav_{idx}"))

        cur_idx = self.page_stack.currentIndex()
        self.page_title_lbl.setText(tr(self._language, f"nav_{cur_idx}"))

        self.hide_tray_btn.setText(tr(self._language, "hide_to_tray"))
        self.bypass_btn.setText(
            tr(self._language, "bypass_on" if self.engine_manager.bypass else "bypass_off")
        )

        if self._tray_show_action is not None:
            self._tray_show_action.setText(tr(self._language, "tray_show"))
        if self._tray_bypass_action is not None:
            self._tray_bypass_action.setText(tr(self._language, "tray_bypass"))
        if self._tray_quit_action is not None:
            self._tray_quit_action.setText(tr(self._language, "tray_quit"))

        self.device_panel.apply_language(self._language)
        self.hardware_page.apply_language(self._language)
        self.workspace_page.apply_language(self._language)
        self.layer_page.apply_language(self._language)
        self.mapping_panel.apply_language(self._language)
        self.settings_page.apply_language(self._language)
        self.readme_page.apply_language(self._language)

    def backup_full_config(self, file_path: Path) -> None:
        """전체 `config.json` 설정을 지정 경로로 백업한다."""
        self.config_store.data["devices"] = self.registry.export_devices(
            registered_only=True
        )
        presets, labels = self.orchestrator.export_presets()
        self.config_store.data["layout_presets"] = presets
        self.config_store.data["topology_labels"] = labels
        self.config_store.backup_to_file(file_path)
        self.append_log(
            f"[BACKUP] 전체 설정 백업 완료 ➔ {file_path.name}",
            tone="gold",
        )

    def restore_full_config(self, file_path: Path) -> None:
        """전체 설정 백업 파일로부터 `config.json`을 복원하고 전 모듈을 재동기화한다."""
        cfg = self.config_store.restore_from_file(file_path)
        self.registry.load_saved_devices(cfg.get("devices", []))
        self.registry.refresh_devices()
        self.orchestrator.load_presets(
            cfg.get("layout_presets", []),
            cfg.get("topology_labels", {}),
        )
        settings = cfg.get("settings", {})
        self.orchestrator.select_profile_mode(str(settings.get("selected_topology", "__auto__")))
        self.orchestrator.compensate_dwm_frame = bool(
            settings.get("compensate_dwm_frame", True)
        )
        self.settings_page.sync_from_settings(settings)
        self._language = str(settings.get("language", "ko"))
        self._sync_initial_state()
        self.append_log(
            f"[RESTORE] 전체 설정 복원 완료 ➔ {file_path.name}",
            tone="gold",
        )

    @pyqtSlot(bool)
    def _on_auto_switch_layer_toggled(self, checked: bool) -> None:
        self.config_store.settings["auto_switch_layer"] = checked
        self._save_all_config()

    @pyqtSlot(bool)
    def _on_run_at_startup_toggled(self, checked: bool) -> None:
        self.config_store.settings["run_at_startup"] = checked
        minimized = bool(self.config_store.settings.get("start_minimized", False))
        try:
            cmd = set_windows_startup(checked, minimized=minimized)
            msg = f"등록 ({cmd})" if checked else "해제"
            self.append_log(f"[STARTUP] Windows 자동 실행 {msg}", tone="gold")
        except OSError as exc:
            QMessageBox.warning(self, "시작 프로그램 설정 오류", str(exc))
        self._save_all_config()

    @pyqtSlot(bool)
    def _on_start_minimized_toggled(self, checked: bool) -> None:
        self.config_store.settings["start_minimized"] = checked
        if self.config_store.settings.get("run_at_startup", False):
            try:
                set_windows_startup(True, minimized=checked)
            except OSError:
                pass
        self._save_all_config()

    @pyqtSlot(bool)
    def _on_bypass_toggled(self, checked: bool) -> None:
        self.set_bypass(checked, persist=True)
        self.append_log(
            "[BYPASS] 리매핑 일시 정지 활성화 (원본 입력 통과)"
            if checked
            else "[BYPASS] 리매핑 재개",
            tone="orange" if checked else "gold",
        )

    @pyqtSlot(str)
    def _on_language_changed(self, lang: str) -> None:
        self.apply_language(lang)
        self._save_all_config()
        self.append_log(f"[I18N] UI 언어 전환 ➔ {lang}", tone="gold")

    @pyqtSlot()
    def _on_backup_config_dialog(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self, "전체 설정 백업", "nexus_config_backup.json", "JSON Files (*.json)"
        )
        if path_str:
            try:
                self.backup_full_config(Path(path_str))
            except Exception as exc:
                QMessageBox.warning(self, "백업 실패", str(exc))

    @pyqtSlot()
    def _on_restore_config_dialog(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "전체 설정 복원", "", "JSON Files (*.json)"
        )
        if not path_str:
            return
        reply = QMessageBox.question(
            self,
            "전체 설정 복원",
            "선택한 백업 파일로 현재 config.json 전체를 덮어쓰시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.restore_full_config(Path(path_str))
        except Exception as exc:
            QMessageBox.warning(self, "복원 실패", str(exc))

    @pyqtSlot()
    def _on_open_config_folder(self) -> None:
        folder = self.config_store.config_path.parent
        if os.name == "nt":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @pyqtSlot()
    def _on_save_now(self) -> None:
        self._save_all_config()
        self.append_log(
            f"[CONFIG] 저장 완료 ➔ {self.config_store.config_path}",
            tone="gold",
        )

    def export_mapping_matrix(self, file_path: Path) -> int:
        count = self.config_store.export_mappings_to_file(
            file_path,
            devices_snapshot=self.registry.export_devices(registered_only=True),
        )
        self.append_log(
            f"[EXPORT] 매핑 매트릭스 {count}건 저장 완료 ➔ {file_path.name}",
            tone="gold",
        )
        return count

    def import_mapping_matrix(self, file_path: Path, mode: str = "merge") -> int:
        count, imported_devices = self.config_store.import_mappings_from_file(
            file_path, mode=mode
        )
        if imported_devices:
            self.registry.load_saved_devices(imported_devices)
            self.registry.refresh_devices()
            self.device_panel.refresh_devices(self.registry.get_all_devices())
        self.mapping_panel.load_rules(self.config_store.mappings)
        self._save_all_config()
        self.append_log(
            f"[IMPORT] 매핑 매트릭스 {count}건 불러오기({mode}) ➔ 총 {len(self.config_store.mappings)}건",
            tone="gold",
        )
        return count

    def export_workspace_presets(self, file_path: Path) -> int:
        count = self.orchestrator.export_presets_to_file(file_path)
        self.append_log(
            f"[EXPORT] 창 배치 프리셋 {count}건 저장 완료 ➔ {file_path.name}",
            tone="gold",
        )
        return count

    def import_workspace_presets(self, file_path: Path, mode: str = "merge") -> int:
        count = self.orchestrator.import_presets_from_file(file_path, mode=mode)
        self._refresh_topology_dropdown()
        self._refresh_preset_list()
        self._save_all_config()
        self.append_log(
            f"[IMPORT] 창 배치 프리셋 {count}건 불러오기({mode}) 완료",
            tone="gold",
        )
        return count

    def export_single_layer(self, layer_name: str, file_path: Path) -> int:
        count = self.config_store.export_layer_to_file(layer_name, file_path)
        self.append_log(
            f"[EXPORT] 레이어 '{layer_name}' ({count}건) 저장 완료 ➔ {file_path.name}",
            tone="gold",
        )
        return count

    def import_single_layer(self, file_path: Path, mode: str = "merge") -> tuple[str, int]:
        layer_name, count = self.config_store.import_layer_from_file(file_path, mode=mode)
        self._sync_layers_everywhere()
        self.mapping_panel.load_rules(self.config_store.mappings)
        self._save_all_config()
        self.append_log(
            f"[IMPORT] 레이어 '{layer_name}' ({count}건) 불러오기({mode}) 완료",
            tone="gold",
        )
        return layer_name, count

    def _ask_import_mode(self, title: str) -> str | None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText("불러오기 방식을 선택하세요.")
        box.addButton("병합 (Merge)", QMessageBox.ButtonRole.AcceptRole)
        replace_btn = box.addButton("덮어쓰기 (Replace)", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_btn or clicked is None:
            return None
        return "replace" if clicked == replace_btn else "merge"

    def _on_export_matrix_dialog(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self, "매핑 매트릭스 내보내기", "nexus_mapping_matrix.json", "JSON Files (*.json)"
        )
        if path_str:
            try:
                self.export_mapping_matrix(Path(path_str))
            except Exception as exc:
                QMessageBox.warning(self, "내보내기 실패", str(exc))

    def _on_import_matrix_dialog(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "매핑 매트릭스 불러오기", "", "JSON Files (*.json)"
        )
        if not path_str:
            return
        mode = self._ask_import_mode("매핑 매트릭스 불러오기 방식")
        if mode is None:
            return
        try:
            self.import_mapping_matrix(Path(path_str), mode=mode)
        except Exception as exc:
            QMessageBox.warning(self, "불러오기 실패", str(exc))

    def _on_export_presets_dialog(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self, "창 배치 프리셋 내보내기", "nexus_workspace_presets.json", "JSON Files (*.json)"
        )
        if path_str:
            try:
                self.export_workspace_presets(Path(path_str))
            except Exception as exc:
                QMessageBox.warning(self, "프리셋 내보내기 실패", str(exc))

    def _on_import_presets_dialog(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "창 배치 프리셋 가져오기", "", "JSON Files (*.json)"
        )
        if not path_str:
            return
        mode = self._ask_import_mode("창 배치 프리셋 가져오기 방식")
        if mode is None:
            return
        try:
            self.import_workspace_presets(Path(path_str), mode=mode)
        except Exception as exc:
            QMessageBox.warning(self, "프리셋 가져오기 실패", str(exc))

    def _on_export_layer_dialog(self, layer_name: str) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            f"레이어 '{layer_name}' 내보내기",
            f"nexus_layer_{layer_name}.json",
            "JSON Files (*.json)",
        )
        if path_str:
            try:
                self.export_single_layer(layer_name, Path(path_str))
            except Exception as exc:
                QMessageBox.warning(self, "레이어 내보내기 실패", str(exc))

    def _on_import_layer_dialog(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "레이어 불러오기", "", "JSON Files (*.json)"
        )
        if not path_str:
            return
        mode = self._ask_import_mode("레이어 불러오기 방식")
        if mode is None:
            return
        try:
            self.import_single_layer(Path(path_str), mode=mode)
        except Exception as exc:
            QMessageBox.warning(self, "레이어 불러오기 실패", str(exc))

    def force_quit(self) -> None:
        """트레이 최소화 없이 모든 백그라운드 엔진을 정리하고 앱을 완전 종료한다."""
        self._force_quit = True
        self._process_poll_timer.stop()
        self._close_conflict_dialog()
        self._save_all_config()
        self.context_watcher.stop()
        self.engine_manager.stop()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        minimize_to_tray = bool(
            self.config_store.settings.get("minimize_to_tray", True)
        )
        if (
            not self._force_quit
            and minimize_to_tray
            and self._tray_icon is not None
            and self._tray_icon.isVisible()
        ):
            event.ignore()
            self.hide()
            self._tray_icon.showMessage(
                "NEXUS Remapper",
                "백그라운드 트레이에서 계속 실행 중입니다.",
                QSystemTrayIcon.MessageIcon.Information,
                1500,
            )
            return

        self._process_poll_timer.stop()
        self._close_conflict_dialog()
        self.context_watcher.stop()
        self.engine_manager.stop()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        super().closeEvent(event)
