"""좌측 사이드바와 연동되는 5개 전용 워크스페이스 뷰 모듈 — Darkroom Filament v1.1.

컴포넌트 내 인라인 `setStyleSheet` 및 raw HEX 하드코딩 0건을 엄격히 준수한다.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.config_store import (
    TRIGGER_MODE_FOCUS,
    TRIGGER_MODE_PROCESS,
    LayerConfig,
)
from core.context_watcher import list_running_process_names
from core.events import InputEvent
from core.window_orchestrator import LayoutPreset, MonitorInfo
from ui.device_panel import DevicePanel
from ui.i18n import LANGUAGE_LABELS, tr
from ui.theme import repolish
from ui.widgets import (
    DarkroomSurfaceCard,
    LayerCreateDialog,
    MonitorMinimapWidget,
    SettingToggleRow,
    make_vector_icon,
)


class HardwareHubPage(QWidget):
    """[Hardware Hub]: 좌측 장치 목록 + 우측 실시간 입력 신호 모니터."""

    def __init__(self, device_panel: DevicePanel) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)
        splitter.addWidget(device_panel)

        monitor_frame = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        m_layout = QVBoxLayout(monitor_frame)
        m_layout.setContentsMargins(16, 14, 16, 16)
        m_layout.setSpacing(10)

        hdr = QHBoxLayout()
        self.title_lbl = QLabel("Signal Monitor")
        self.title_lbl.setProperty("role", "card-title")
        hdr.addWidget(self.title_lbl, 1)

        self.clear_btn = QPushButton("비우기")
        self.clear_btn.setProperty("btnRole", "quiet")
        self.clear_btn.setFixedHeight(26)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hdr.addWidget(self.clear_btn)
        m_layout.addLayout(hdr)

        self.hint_lbl = QLabel(tr("ko", "signal_monitor_hint"))
        self.hint_lbl.setProperty("role", "secondary")
        self.hint_lbl.setWordWrap(True)
        m_layout.addWidget(self.hint_lbl)

        self.signal_monitor = QPlainTextEdit()
        self.signal_monitor.setReadOnly(True)
        self.signal_monitor.setMaximumBlockCount(400)
        self.signal_monitor.setPlaceholderText(tr("ko", "signal_monitor_placeholder"))
        m_layout.addWidget(self.signal_monitor, 1)

        self.clear_btn.clicked.connect(self.signal_monitor.clear)
        splitter.addWidget(monitor_frame)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter)

    def apply_language(self, lang: str) -> None:
        self.title_lbl.setText(tr(lang, "signal_monitor_title"))
        self.clear_btn.setText(tr(lang, "signal_monitor_clear"))
        self.hint_lbl.setText(tr(lang, "signal_monitor_hint"))
        self.signal_monitor.setPlaceholderText(tr(lang, "signal_monitor_placeholder"))

    def append_signal(self, event: InputEvent, extra: str = "") -> None:
        code_txt = (
            f"0x{event.code:04X}" if isinstance(event.code, int) else str(event.code)
        )
        vel_txt = f" vel={event.velocity:.1f}x" if event.velocity != 1.0 else ""
        raw_txt = f" raw=[{event.raw_data.hex(' ').upper()}]" if event.raw_data else ""
        suffix = f" | {extra}" if extra else ""
        self.signal_monitor.appendPlainText(
            f"[{event.source_str.upper():13s}] {event.device_name or event.device_id} | "
            f"{event.event_type_str:17s} | code={code_txt} val={event.value}{vel_txt}{raw_txt}{suffix}"
        )


class WorkspacePresetsPage(QWidget):
    """[Workspace Presets]: 모니터 토폴로지, 스냅샷 캡처, 2D 미니맵, 포커스 메인 앱."""

    topology_changed = pyqtSignal(str)
    snapshot_requested = pyqtSignal()
    apply_preset_requested = pyqtSignal(str, bool)
    delete_preset_requested = pyqtSignal(str)
    focus_process_changed = pyqtSignal(str, str)  # preset_name, focus_process
    auto_launch_toggled = pyqtSignal(bool)
    export_presets_requested = pyqtSignal()
    import_presets_requested = pyqtSignal()

    def __init__(self, initial_auto_launch: bool = False) -> None:
        super().__init__()
        self._monitors: list[MonitorInfo] = []
        self._presets_by_name: dict[str, LayoutPreset] = {}
        self._current_preset: LayoutPreset | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        topo_card = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        t_layout = QVBoxLayout(topo_card)
        t_layout.setContentsMargins(16, 14, 16, 14)
        t_layout.setSpacing(8)

        t_top = QHBoxLayout()
        t_top.setSpacing(10)
        self.topo_title_lbl = QLabel("Display Topology")
        self.topo_title_lbl.setProperty("role", "card-title")
        t_top.addWidget(self.topo_title_lbl)
        t_top.addStretch(1)

        self.topology_combo = QComboBox()
        self.topology_combo.setFixedHeight(30)
        self.topology_combo.setMinimumWidth(260)
        self.topology_combo.currentIndexChanged.connect(self._on_topo_idx_changed)
        t_top.addWidget(self.topology_combo)

        self.snapshot_btn = QPushButton("스냅샷 저장")
        self.snapshot_btn.setProperty("btnRole", "primary")
        self.snapshot_btn.setIcon(make_vector_icon("snapshot", "--cta-text", 14))
        self.snapshot_btn.setIconSize(QSize(14, 14))
        self.snapshot_btn.setFixedHeight(30)
        self.snapshot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.snapshot_btn.clicked.connect(self.snapshot_requested.emit)
        t_top.addWidget(self.snapshot_btn)
        t_layout.addLayout(t_top)

        self.monitors_summary_lbl = QLabel("Topology scanning")
        self.monitors_summary_lbl.setProperty("role", "mono-secondary")
        t_layout.addWidget(self.monitors_summary_lbl)
        root.addWidget(topo_card)

        body_split = QSplitter(Qt.Orientation.Horizontal)
        body_split.setHandleWidth(8)

        list_card = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        l_layout = QVBoxLayout(list_card)
        l_layout.setContentsMargins(16, 14, 16, 16)
        l_layout.setSpacing(10)

        l_hdr = QHBoxLayout()
        l_hdr.setSpacing(6)
        self.presets_title_lbl = QLabel("Layout Presets")
        self.presets_title_lbl.setProperty("role", "card-title")
        l_hdr.addWidget(self.presets_title_lbl, 1)

        self.export_presets_btn = QPushButton("내보내기")
        self.export_presets_btn.setProperty("btnRole", "quiet")
        self.export_presets_btn.setFixedHeight(26)
        self.export_presets_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_presets_btn.clicked.connect(self.export_presets_requested.emit)
        l_hdr.addWidget(self.export_presets_btn)

        self.import_presets_btn = QPushButton("가져오기")
        self.import_presets_btn.setProperty("btnRole", "quiet")
        self.import_presets_btn.setFixedHeight(26)
        self.import_presets_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_presets_btn.clicked.connect(self.import_presets_requested.emit)
        l_hdr.addWidget(self.import_presets_btn)
        l_layout.addLayout(l_hdr)

        self.preset_list = QListWidget()
        self.preset_list.currentItemChanged.connect(self._on_preset_selection_changed)
        self.preset_list.itemDoubleClicked.connect(lambda _i: self._emit_apply())
        l_layout.addWidget(self.preset_list, 1)

        self.auto_launch_chk = SettingToggleRow(
            text="미실행 앱 자동 실행 후 정렬",
            checked=initial_auto_launch,
            active_color="--filament-orange",
            label_role="secondary",
        )
        self.auto_launch_chk.toggled.connect(self.auto_launch_toggled.emit)
        l_layout.addWidget(self.auto_launch_chk)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.apply_preset_btn = QPushButton("선택 레이아웃 적용")
        self.apply_preset_btn.setProperty("btnRole", "primary")
        self.apply_preset_btn.setFixedHeight(30)
        self.apply_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_preset_btn.clicked.connect(self._emit_apply)
        btn_row.addWidget(self.apply_preset_btn, 1)

        self.del_preset_btn = QPushButton("삭제")
        self.del_preset_btn.setProperty("btnRole", "danger")
        self.del_preset_btn.setFixedHeight(30)
        self.del_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_preset_btn.clicked.connect(self._emit_delete)
        btn_row.addWidget(self.del_preset_btn)
        l_layout.addLayout(btn_row)
        body_split.addWidget(list_card)

        detail_card = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        d_layout = QVBoxLayout(detail_card)
        d_layout.setContentsMargins(16, 14, 16, 16)
        d_layout.setSpacing(10)

        self.inspector_title_lbl = QLabel("Inspector & Blueprint")
        self.inspector_title_lbl.setProperty("role", "card-title")
        d_layout.addWidget(self.inspector_title_lbl)

        self.minimap = MonitorMinimapWidget()
        d_layout.addWidget(self.minimap)

        focus_row = QHBoxLayout()
        focus_row.setSpacing(8)
        self.focus_lbl = QLabel("정렬 후 최종 포커스 메인 앱:")
        self.focus_lbl.setProperty("role", "secondary")
        focus_row.addWidget(self.focus_lbl)

        self.focus_process_combo = QComboBox()
        self.focus_process_combo.setEditable(True)
        self.focus_process_combo.setFixedHeight(28)
        self.focus_process_combo.addItem("")
        self.focus_process_combo.currentTextChanged.connect(self._on_focus_changed)
        focus_row.addWidget(self.focus_process_combo, 1)
        d_layout.addLayout(focus_row)

        self.preset_detail_view = QPlainTextEdit()
        self.preset_detail_view.setReadOnly(True)
        self.preset_detail_view.setPlaceholderText(tr("ko", "ws_detail_placeholder"))
        d_layout.addWidget(self.preset_detail_view, 1)

        body_split.addWidget(detail_card)
        body_split.setStretchFactor(0, 3)
        body_split.setStretchFactor(1, 4)
        root.addWidget(body_split, 1)

    def apply_language(self, lang: str) -> None:
        self.topo_title_lbl.setText(tr(lang, "ws_topo_title"))
        self.snapshot_btn.setText(tr(lang, "snapshot_btn"))
        self.presets_title_lbl.setText(tr(lang, "ws_presets_title"))
        self.export_presets_btn.setText(tr(lang, "ws_export"))
        self.import_presets_btn.setText(tr(lang, "ws_import"))
        self.auto_launch_chk.setText(tr(lang, "ws_auto_launch"))
        self.apply_preset_btn.setText(tr(lang, "ws_apply_btn"))
        self.del_preset_btn.setText(tr(lang, "ws_delete_btn"))
        self.inspector_title_lbl.setText(tr(lang, "ws_inspector_title"))
        self.focus_lbl.setText(tr(lang, "ws_focus_label"))
        self.preset_detail_view.setPlaceholderText(tr(lang, "ws_detail_placeholder"))

    def set_monitors_summary(self, monitors: list[MonitorInfo], fingerprint: str) -> None:
        self._monitors = list(monitors)
        desc = " | ".join(
            f"M{m.index}: {m.width}×{m.height}@{m.scale_percent}% rcWork={m.work_rect}"
            for m in monitors
        )
        self.monitors_summary_lbl.setText(f"[{fingerprint}] — {desc}")
        self.minimap.set_data(self._monitors, self._current_preset)

    def set_topology_choices(
        self, choices: list[tuple[str, str]], selected_key: str
    ) -> None:
        self.topology_combo.blockSignals(True)
        self.topology_combo.clear()
        for key, label in choices:
            self.topology_combo.addItem(label, key)
        idx = self.topology_combo.findData(selected_key)
        self.topology_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.topology_combo.blockSignals(False)

    def refresh_presets(self, presets: list[LayoutPreset]) -> None:
        cur_item = self.preset_list.currentItem()
        cur_name = str(cur_item.data(Qt.ItemDataRole.UserRole)) if cur_item else ""

        self._presets_by_name = {p.name: p for p in presets}
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        restore_row = -1
        for row, preset in enumerate(presets):
            focus_tag = f" · Focus:{preset.focus_process}" if preset.focus_process else ""
            item = QListWidgetItem(
                f"{preset.name} ({len(preset.placements)}창 · {preset.environment_label}{focus_tag})"
            )
            item.setData(Qt.ItemDataRole.UserRole, preset.name)
            self.preset_list.addItem(item)
            if preset.name == cur_name:
                restore_row = row
        self.preset_list.blockSignals(False)

        if restore_row >= 0:
            self.preset_list.setCurrentRow(restore_row)
            self._show_preset_detail(presets[restore_row])
        elif presets:
            self.preset_list.setCurrentRow(0)
            self._show_preset_detail(presets[0])
        else:
            self._show_preset_detail(None)

    def _on_topo_idx_changed(self, idx: int) -> None:
        if idx >= 0:
            key = str(self.topology_combo.itemData(idx) or "__auto__")
            self.topology_changed.emit(key)

    def _on_preset_selection_changed(
        self, current: QListWidgetItem | None, _prev: QListWidgetItem | None
    ) -> None:
        name = str(current.data(Qt.ItemDataRole.UserRole)) if current else ""
        self._show_preset_detail(self._presets_by_name.get(name))

    def _show_preset_detail(self, preset: LayoutPreset | None) -> None:
        self._current_preset = preset
        self.minimap.set_data(self._monitors, preset)

        self.focus_process_combo.blockSignals(True)
        self.focus_process_combo.clear()
        self.focus_process_combo.addItem("")
        if preset is None:
            self.focus_process_combo.blockSignals(False)
            self.preset_detail_view.clear()
            return

        procs = sorted({p.process_name for p in preset.placements if p.process_name})
        for p in procs:
            self.focus_process_combo.addItem(p)
        if preset.focus_process and self.focus_process_combo.findText(preset.focus_process) == -1:
            self.focus_process_combo.addItem(preset.focus_process)
        self.focus_process_combo.setCurrentText(preset.focus_process)
        self.focus_process_combo.blockSignals(False)

        lines = [
            f"Preset: {preset.name}",
            f"Topology: {preset.topology_fingerprint}",
            f"Focus App: {preset.focus_process or '(None)'}",
            "-" * 52,
        ]
        for p in preset.placements:
            lines.append(
                f"• {p.process_name:22s} | M{p.monitor_index} | "
                f"x={p.x_ratio:.3f}, y={p.y_ratio:.3f}, w={p.w_ratio:.3f}, h={p.h_ratio:.3f} "
                f"({p.title_hint})"
            )
        self.preset_detail_view.setPlainText("\n".join(lines))

    def _on_focus_changed(self, text: str) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            return
        name = str(item.data(Qt.ItemDataRole.UserRole))
        self.focus_process_changed.emit(name, text.strip())

    def _emit_apply(self) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            return
        self.apply_preset_requested.emit(
            str(item.data(Qt.ItemDataRole.UserRole)),
            self.auto_launch_chk.isChecked(),
        )

    def _emit_delete(self) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            return
        self.delete_preset_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))


class MappingLayerPage(QWidget):
    """[Mapping Layer]: 사용자 정의 레이어 CRUD, 트리거 모드(`focus`/`process`), `.exe` 바인딩."""

    layer_created = pyqtSignal(str, str)  # name, trigger_mode
    layer_mode_changed = pyqtSignal(str, str)  # layer_name, trigger_mode
    layer_renamed = pyqtSignal(str, str)
    layer_deleted = pyqtSignal(str)
    layer_processes_updated = pyqtSignal(str, list)
    export_layer_requested = pyqtSignal(str)
    import_layer_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._lang: str = "ko"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

        left_card = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        l_layout = QVBoxLayout(left_card)
        l_layout.setContentsMargins(16, 14, 16, 16)
        l_layout.setSpacing(10)

        self.l_title_lbl = QLabel("Custom Layers")
        self.l_title_lbl.setProperty("role", "card-title")
        l_layout.addWidget(self.l_title_lbl)

        self.layer_list = QListWidget()
        self.layer_list.currentItemChanged.connect(self._on_layer_selected)
        l_layout.addWidget(self.layer_list, 1)

        crud_row = QHBoxLayout()
        crud_row.setSpacing(6)
        self.add_layer_btn = QPushButton("+ 새 레이어")
        self.add_layer_btn.setProperty("btnRole", "primary")
        self.add_layer_btn.setFixedHeight(30)
        self.add_layer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_layer_btn.clicked.connect(self._on_add_layer)
        crud_row.addWidget(self.add_layer_btn, 1)

        self.rename_layer_btn = QPushButton("이름 변경")
        self.rename_layer_btn.setProperty("btnRole", "ghost")
        self.rename_layer_btn.setFixedHeight(30)
        self.rename_layer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rename_layer_btn.clicked.connect(self._on_rename_layer)
        crud_row.addWidget(self.rename_layer_btn)

        self.del_layer_btn = QPushButton("삭제")
        self.del_layer_btn.setProperty("btnRole", "danger")
        self.del_layer_btn.setFixedHeight(30)
        self.del_layer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_layer_btn.clicked.connect(self._on_delete_layer)
        crud_row.addWidget(self.del_layer_btn)
        l_layout.addLayout(crud_row)

        io_row = QHBoxLayout()
        io_row.setSpacing(6)
        self.export_layer_btn = QPushButton("레이어 내보내기")
        self.export_layer_btn.setProperty("btnRole", "quiet")
        self.export_layer_btn.setFixedHeight(26)
        self.export_layer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_layer_btn.clicked.connect(self._on_export_layer)
        io_row.addWidget(self.export_layer_btn, 1)

        self.import_layer_btn = QPushButton("레이어 불러오기")
        self.import_layer_btn.setProperty("btnRole", "quiet")
        self.import_layer_btn.setFixedHeight(26)
        self.import_layer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_layer_btn.clicked.connect(self.import_layer_requested.emit)
        io_row.addWidget(self.import_layer_btn, 1)
        l_layout.addLayout(io_row)
        splitter.addWidget(left_card)

        right_card = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        r_layout = QVBoxLayout(right_card)
        r_layout.setContentsMargins(16, 14, 16, 16)
        r_layout.setSpacing(10)

        self.bind_title_lbl = QLabel("Process Binding (.exe)")
        self.bind_title_lbl.setProperty("role", "card-title")
        r_layout.addWidget(self.bind_title_lbl)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self.mode_lbl = QLabel(tr(self._lang, "layer_mode_label"))
        self.mode_lbl.setProperty("role", "secondary")
        mode_row.addWidget(self.mode_lbl)

        self.mode_combo = QComboBox()
        self.mode_combo.setFixedHeight(28)
        self.mode_combo.setMinimumWidth(220)
        self.mode_combo.addItem(tr(self._lang, "layer_mode_focus_desc"), TRIGGER_MODE_FOCUS)
        self.mode_combo.addItem(tr(self._lang, "layer_mode_process_desc"), TRIGGER_MODE_PROCESS)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        r_layout.addLayout(mode_row)

        self.bind_hint_lbl = QLabel(tr(self._lang, "layer_bind_hint"))
        self.bind_hint_lbl.setProperty("role", "secondary")
        self.bind_hint_lbl.setWordWrap(True)
        r_layout.addWidget(self.bind_hint_lbl)

        cols = QHBoxLayout()
        cols.setSpacing(12)

        bound_col = QVBoxLayout()
        bound_col.setSpacing(6)
        self.bound_lbl = QLabel("바인딩된 프로세스 (.exe)")
        self.bound_lbl.setProperty("role", "body")
        bound_col.addWidget(self.bound_lbl)

        self.bound_proc_list = QListWidget()
        bound_col.addWidget(self.bound_proc_list, 1)

        manual_row = QHBoxLayout()
        manual_row.setSpacing(6)
        self.manual_exe_edit = QLineEdit()
        self.manual_exe_edit.setFixedHeight(28)
        self.manual_exe_edit.setPlaceholderText("Revit.exe, acad.exe")
        manual_row.addWidget(self.manual_exe_edit, 1)

        self.add_exe_btn = QPushButton("추가")
        self.add_exe_btn.setProperty("btnRole", "ghost")
        self.add_exe_btn.setFixedHeight(28)
        self.add_exe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_exe_btn.clicked.connect(self._on_add_manual_exe)
        manual_row.addWidget(self.add_exe_btn)

        self.rem_exe_btn = QPushButton("해제")
        self.rem_exe_btn.setProperty("btnRole", "danger")
        self.rem_exe_btn.setFixedHeight(28)
        self.rem_exe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rem_exe_btn.clicked.connect(self._on_remove_selected_exe)
        manual_row.addWidget(self.rem_exe_btn)
        bound_col.addLayout(manual_row)
        cols.addLayout(bound_col, 1)

        run_col = QVBoxLayout()
        run_col.setSpacing(6)
        run_hdr = QHBoxLayout()
        self.run_lbl = QLabel("실행 중인 프로세스")
        self.run_lbl.setProperty("role", "body")
        run_hdr.addWidget(self.run_lbl, 1)

        self.refresh_proc_btn = QPushButton("새로고침")
        self.refresh_proc_btn.setProperty("btnRole", "quiet")
        self.refresh_proc_btn.setFixedHeight(24)
        self.refresh_proc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_proc_btn.clicked.connect(self.refresh_running_processes)
        run_hdr.addWidget(self.refresh_proc_btn)
        run_col.addLayout(run_hdr)

        self.running_proc_list = QListWidget()
        self.running_proc_list.itemDoubleClicked.connect(lambda _i: self._on_bind_running_exe())
        run_col.addWidget(self.running_proc_list, 1)

        self.bind_btn = QPushButton("← 선택 프로세스 바인딩")
        self.bind_btn.setProperty("btnRole", "primary")
        self.bind_btn.setFixedHeight(28)
        self.bind_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bind_btn.clicked.connect(self._on_bind_running_exe)
        run_col.addWidget(self.bind_btn)
        cols.addLayout(run_col, 1)

        r_layout.addLayout(cols, 1)
        splitter.addWidget(right_card)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter)

        self._configs_by_name: dict[str, LayerConfig] = {}

    def apply_language(self, lang: str) -> None:
        self._lang = lang
        self.l_title_lbl.setText(tr(lang, "layer_title"))
        self.add_layer_btn.setText(tr(lang, "layer_add"))
        self.rename_layer_btn.setText(tr(lang, "layer_rename"))
        self.del_layer_btn.setText(tr(lang, "layer_delete"))
        self.export_layer_btn.setText(tr(lang, "layer_export"))
        self.import_layer_btn.setText(tr(lang, "layer_import"))
        self.mode_lbl.setText(tr(lang, "layer_mode_label"))
        self.mode_combo.blockSignals(True)
        self.mode_combo.setItemText(0, tr(lang, "layer_mode_focus_desc"))
        self.mode_combo.setItemText(1, tr(lang, "layer_mode_process_desc"))
        self.mode_combo.blockSignals(False)
        self.bound_lbl.setText(tr(lang, "layer_bound_label"))
        self.add_exe_btn.setText(tr(lang, "layer_add_exe"))
        self.rem_exe_btn.setText(tr(lang, "layer_rem_exe"))
        self.run_lbl.setText(tr(lang, "layer_running_label"))
        self.refresh_proc_btn.setText(tr(lang, "layer_refresh_proc"))
        self.bind_btn.setText(tr(lang, "layer_bind_btn"))
        if self._configs_by_name:
            self.refresh_layers(list(self._configs_by_name.values()))
        else:
            self.bind_hint_lbl.setText(tr(lang, "layer_bind_hint"))

    def refresh_layers(self, configs: list[LayerConfig]) -> None:
        cur = self.selected_layer_name()
        self._configs_by_name = {lc.name: lc for lc in configs}
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        restore_row = 0
        for row, lc in enumerate(configs):
            mode_tag = (
                tr(self._lang, "layer_mode_process_tag")
                if lc.trigger_mode == TRIGGER_MODE_PROCESS
                else tr(self._lang, "layer_mode_focus_tag")
            )
            proc_txt = ", ".join(lc.processes) if lc.processes else "default fallback"
            item = QListWidgetItem(f"{lc.name}  [{mode_tag}]  ({proc_txt})")
            item.setData(Qt.ItemDataRole.UserRole, lc.name)
            self.layer_list.addItem(item)
            if lc.name == cur:
                restore_row = row
        self.layer_list.blockSignals(False)
        if configs:
            self.layer_list.setCurrentRow(restore_row)
            self._sync_bound_processes(configs[restore_row])

    def refresh_running_processes(self) -> None:
        self.running_proc_list.clear()
        for exe in list_running_process_names():
            self.running_proc_list.addItem(exe)

    def selected_layer_name(self) -> str:
        item = self.layer_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def _on_layer_selected(
        self, current: QListWidgetItem | None, _prev: QListWidgetItem | None
    ) -> None:
        name = str(current.data(Qt.ItemDataRole.UserRole)) if current else ""
        lc = self._configs_by_name.get(name)
        self._sync_bound_processes(lc)

    def _sync_bound_processes(self, lc: LayerConfig | None) -> None:
        self.bound_proc_list.clear()
        if lc is None:
            self.bind_title_lbl.setText("Process Binding (.exe)")
            self.mode_combo.setEnabled(False)
            self.bind_hint_lbl.setText(tr(self._lang, "layer_bind_hint"))
            self.bind_hint_lbl.setProperty("role", "secondary")
            repolish(self.bind_hint_lbl)
            return

        is_process = lc.trigger_mode == TRIGGER_MODE_PROCESS
        mode_tag = (
            tr(self._lang, "layer_mode_process_tag")
            if is_process
            else tr(self._lang, "layer_mode_focus_tag")
        )
        self.bind_title_lbl.setText(f"Process Binding — {lc.name} ({mode_tag})")

        self.mode_combo.blockSignals(True)
        idx = self.mode_combo.findData(lc.trigger_mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.mode_combo.setEnabled(lc.name != "default")
        self.mode_combo.blockSignals(False)

        if is_process:
            self.bind_hint_lbl.setText(tr(self._lang, "layer_bind_hint_process"))
            self.bind_hint_lbl.setProperty("pillState", "gold")
            self.manual_exe_edit.setPlaceholderText("Revit.exe (단일 .exe)")
        else:
            self.bind_hint_lbl.setText(tr(self._lang, "layer_bind_hint"))
            self.bind_hint_lbl.setProperty("pillState", "")
            self.bind_hint_lbl.setProperty("role", "secondary")
            self.manual_exe_edit.setPlaceholderText("Revit.exe, acad.exe")
        repolish(self.bind_hint_lbl)

        for proc in lc.processes:
            self.bound_proc_list.addItem(proc)

    def _on_mode_combo_changed(self, idx: int) -> None:
        name = self.selected_layer_name()
        if not name or name == "default" or idx < 0:
            return
        mode = str(self.mode_combo.itemData(idx) or TRIGGER_MODE_FOCUS)
        lc = self._configs_by_name.get(name)
        if lc is not None and lc.trigger_mode == mode:
            return
        self.layer_mode_changed.emit(name, mode)

    def _on_add_layer(self) -> None:
        dlg = LayerCreateDialog(lang=self._lang, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.layer_name():
            self.layer_created.emit(dlg.layer_name(), dlg.trigger_mode())

    def _on_rename_layer(self) -> None:
        old_name = self.selected_layer_name()
        if not old_name or old_name == "default":
            QMessageBox.information(
                self, "안내", "`default` 기본 레이어는 이름을 변경할 수 없습니다."
            )
            return
        new_name, ok = QInputDialog.getText(
            self, "레이어 이름 변경", "새 레이어 이름:", text=old_name
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            self.layer_renamed.emit(old_name, new_name.strip())

    def _on_delete_layer(self) -> None:
        name = self.selected_layer_name()
        if not name or name == "default":
            QMessageBox.information(
                self, "안내", "`default` 기본 레이어는 삭제할 수 없습니다."
            )
            return
        reply = QMessageBox.question(
            self,
            "레이어 삭제",
            f"'{name}' 레이어와 해당 레이어에 소속된 매핑 카드를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.layer_deleted.emit(name)

    def _on_export_layer(self) -> None:
        name = self.selected_layer_name()
        if name:
            self.export_layer_requested.emit(name)

    def _on_add_manual_exe(self) -> None:
        name = self.selected_layer_name()
        raw = self.manual_exe_edit.text().strip()
        if not name or not raw:
            return
        lc = self._configs_by_name.get(name)
        current = list(lc.processes) if lc else []
        for token in raw.split(","):
            exe = token.strip()
            if exe and not exe.lower().endswith(".exe"):
                exe = f"{exe}.exe"
            if exe and exe.lower() not in {p.lower() for p in current}:
                current.append(exe)
        self.manual_exe_edit.clear()
        self.layer_processes_updated.emit(name, current)

    def _on_remove_selected_exe(self) -> None:
        name = self.selected_layer_name()
        item = self.bound_proc_list.currentItem()
        if not name or item is None:
            return
        target = item.text().strip().lower()
        lc = self._configs_by_name.get(name)
        if lc is None:
            return
        updated = [p for p in lc.processes if p.lower() != target]
        self.layer_processes_updated.emit(name, updated)

    def _on_bind_running_exe(self) -> None:
        name = self.selected_layer_name()
        item = self.running_proc_list.currentItem()
        if not name or item is None:
            return
        exe = item.text().strip()
        lc = self._configs_by_name.get(name)
        current = list(lc.processes) if lc else []
        if exe and exe.lower() not in {p.lower() for p in current}:
            current.append(exe)
            self.layer_processes_updated.emit(name, current)


class SettingsPage(QWidget):
    """[Settings]: Darkroom 토글 기반 엔진/DWM/시작프로그램/Bypass/백업·복원/다국어."""

    prefer_kernel_toggled = pyqtSignal(bool)
    minimize_tray_toggled = pyqtSignal(bool)
    auto_switch_layer_toggled = pyqtSignal(bool)
    compensate_dwm_toggled = pyqtSignal(bool)
    run_at_startup_toggled = pyqtSignal(bool)
    start_minimized_toggled = pyqtSignal(bool)
    bypass_toggled = pyqtSignal(bool)
    language_changed = pyqtSignal(str)
    open_config_folder_requested = pyqtSignal()
    backup_config_requested = pyqtSignal()
    restore_config_requested = pyqtSignal()
    save_now_requested = pyqtSignal()

    def __init__(
        self,
        config_path: str,
        prefer_kernel: bool,
        minimize_tray: bool,
        auto_switch_layer: bool,
        compensate_dwm: bool = True,
        run_at_startup: bool = False,
        start_minimized: bool = False,
        bypass_remapping: bool = False,
        language: str = "ko",
    ) -> None:
        super().__init__()
        self._lang = language if language in LANGUAGE_LABELS else "ko"
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        cfg_card = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        c_layout = QVBoxLayout(cfg_card)
        c_layout.setContentsMargins(16, 14, 16, 16)
        c_layout.setSpacing(6)

        top_bar = QHBoxLayout()
        self.title_lbl = QLabel()
        self.title_lbl.setProperty("role", "card-title")
        top_bar.addWidget(self.title_lbl, 1)

        self.lang_lbl = QLabel()
        self.lang_lbl.setProperty("role", "secondary")
        top_bar.addWidget(self.lang_lbl)

        self.lang_combo = QComboBox()
        self.lang_combo.setFixedHeight(28)
        for code, label in LANGUAGE_LABELS.items():
            self.lang_combo.addItem(label, code)
        idx = self.lang_combo.findData(self._lang)
        self.lang_combo.setCurrentIndex(max(0, idx))
        self.lang_combo.currentIndexChanged.connect(self._on_lang_idx_changed)
        top_bar.addWidget(self.lang_combo)
        c_layout.addLayout(top_bar)

        self.prefer_kernel_chk = SettingToggleRow(
            checked=prefer_kernel, active_color="--filament-gold"
        )
        self.prefer_kernel_chk.toggled.connect(self.prefer_kernel_toggled.emit)
        c_layout.addWidget(self.prefer_kernel_chk)

        self.minimize_tray_chk = SettingToggleRow(
            checked=minimize_tray, active_color="--filament-orange"
        )
        self.minimize_tray_chk.toggled.connect(self.minimize_tray_toggled.emit)
        c_layout.addWidget(self.minimize_tray_chk)

        self.auto_switch_layer_chk = SettingToggleRow(
            checked=auto_switch_layer, active_color="--filament-orange"
        )
        self.auto_switch_layer_chk.toggled.connect(self.auto_switch_layer_toggled.emit)
        c_layout.addWidget(self.auto_switch_layer_chk)

        self.compensate_dwm_chk = SettingToggleRow(
            checked=compensate_dwm, active_color="--filament-orange"
        )
        self.compensate_dwm_chk.toggled.connect(self.compensate_dwm_toggled.emit)
        c_layout.addWidget(self.compensate_dwm_chk)

        self.run_at_startup_chk = SettingToggleRow(
            checked=run_at_startup, active_color="--filament-gold"
        )
        self.run_at_startup_chk.toggled.connect(self.run_at_startup_toggled.emit)
        c_layout.addWidget(self.run_at_startup_chk)

        self.start_minimized_chk = SettingToggleRow(
            checked=start_minimized, active_color="--filament-orange", label_role="secondary"
        )
        self.start_minimized_chk.toggled.connect(self.start_minimized_toggled.emit)
        c_layout.addWidget(self.start_minimized_chk)

        self.bypass_chk = SettingToggleRow(
            checked=bypass_remapping, active_color="--filament-red"
        )
        self.bypass_chk.toggled.connect(self.bypass_toggled.emit)
        c_layout.addWidget(self.bypass_chk)

        sep = QFrame()
        sep.setProperty("role", "hairline-h")
        sep.setFixedHeight(1)
        c_layout.addWidget(sep)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.path_lbl = QLabel()
        self.path_lbl.setProperty("role", "secondary")
        path_row.addWidget(self.path_lbl)

        self.config_path_edit = QLineEdit(config_path)
        self.config_path_edit.setFixedHeight(28)
        self.config_path_edit.setReadOnly(True)
        path_row.addWidget(self.config_path_edit, 1)

        self.open_dir_btn = QPushButton()
        self.open_dir_btn.setProperty("btnRole", "ghost")
        self.open_dir_btn.setIcon(make_vector_icon("folder", "--text-secondary", 13))
        self.open_dir_btn.setIconSize(QSize(13, 13))
        self.open_dir_btn.setFixedHeight(28)
        self.open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_dir_btn.clicked.connect(self.open_config_folder_requested.emit)
        path_row.addWidget(self.open_dir_btn)

        self.backup_config_btn = QPushButton()
        self.backup_config_btn.setProperty("btnRole", "ghost")
        self.backup_config_btn.setFixedHeight(28)
        self.backup_config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.backup_config_btn.clicked.connect(self.backup_config_requested.emit)
        path_row.addWidget(self.backup_config_btn)

        self.restore_config_btn = QPushButton()
        self.restore_config_btn.setProperty("btnRole", "ghost")
        self.restore_config_btn.setFixedHeight(28)
        self.restore_config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_config_btn.clicked.connect(self.restore_config_requested.emit)
        path_row.addWidget(self.restore_config_btn)

        self.save_btn = QPushButton()
        self.save_btn.setProperty("btnRole", "primary")
        self.save_btn.setFixedHeight(28)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self.save_now_requested.emit)
        path_row.addWidget(self.save_btn)
        c_layout.addLayout(path_row)
        root.addWidget(cfg_card)

        log_card = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        l_layout = QVBoxLayout(log_card)
        l_layout.setContentsMargins(16, 14, 16, 16)
        l_layout.setSpacing(8)

        self.log_hdr = QLabel()
        self.log_hdr.setProperty("role", "card-title")
        l_layout.addWidget(self.log_hdr)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        l_layout.addWidget(self.log_view, 1)
        root.addWidget(log_card, 1)

        self.apply_language(self._lang)

    def _on_lang_idx_changed(self, idx: int) -> None:
        if idx < 0:
            return
        code = str(self.lang_combo.itemData(idx) or "ko")
        self.apply_language(code)
        self.language_changed.emit(code)

    def set_bypass_checked(self, enabled: bool) -> None:
        self.bypass_chk.blockSignals(True)
        self.bypass_chk.setChecked(enabled)
        self.bypass_chk.blockSignals(False)

    def sync_from_settings(self, settings: dict) -> None:
        for chk, key, default in (
            (self.prefer_kernel_chk, "prefer_kernel_engine", True),
            (self.minimize_tray_chk, "minimize_to_tray", True),
            (self.auto_switch_layer_chk, "auto_switch_layer", True),
            (self.compensate_dwm_chk, "compensate_dwm_frame", True),
            (self.run_at_startup_chk, "run_at_startup", False),
            (self.start_minimized_chk, "start_minimized", False),
            (self.bypass_chk, "bypass_remapping", False),
        ):
            chk.blockSignals(True)
            chk.setChecked(bool(settings.get(key, default)))
            chk.blockSignals(False)

        lang = str(settings.get("language", "ko"))
        idx = self.lang_combo.findData(lang)
        if idx >= 0:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)
        self.apply_language(lang)

    def apply_language(self, lang: str) -> None:
        self._lang = lang if lang in LANGUAGE_LABELS else "ko"
        self.title_lbl.setText(tr(self._lang, "settings_title"))
        self.lang_lbl.setText(tr(self._lang, "ui_language"))
        self.prefer_kernel_chk.setText(tr(self._lang, "prefer_kernel"))
        self.minimize_tray_chk.setText(tr(self._lang, "minimize_tray"))
        self.auto_switch_layer_chk.setText(tr(self._lang, "auto_switch_layer"))
        self.compensate_dwm_chk.setText(tr(self._lang, "compensate_dwm"))
        self.run_at_startup_chk.setText(tr(self._lang, "run_at_startup"))
        self.start_minimized_chk.setText(tr(self._lang, "start_minimized"))
        self.bypass_chk.setText(tr(self._lang, "bypass_remapping"))
        self.path_lbl.setText(tr(self._lang, "config_path"))
        self.open_dir_btn.setText(tr(self._lang, "open_folder"))
        self.backup_config_btn.setText(tr(self._lang, "backup_config"))
        self.restore_config_btn.setText(tr(self._lang, "restore_config"))
        self.save_btn.setText(tr(self._lang, "save_now"))
        self.log_hdr.setText(tr(self._lang, "log_title"))


class ReadMePage(QWidget):
    """[Read Me]: 3개 국어 내장 사용 설명서 및 비상 탈출 가이드."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        card = DarkroomSurfaceCard(
            warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface"
        )
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.apply_language("ko")
        c_layout.addWidget(self.browser)
        layout.addWidget(card)

    def apply_language(self, lang: str) -> None:
        self.browser.setHtml(tr(lang, "readme_html"))
