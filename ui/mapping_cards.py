"""중앙 모듈형 매핑 카드 그리드 — Darkroom Filament v1.1 (Quiet Pro) 스타일.

- Qt 위젯 드롭 섀도우 이펙트 및 컴포넌트 내 인라인 `setStyleSheet` 사용 금지
- `DarkroomGlowCard` 기반 QPainter 스페큘러 보더 및 240ms 열 필라멘트 점등
- `ToggleSwitch`, `PrecisionTickSlider`, `ShortcutRecorderDialog` 연동
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.actions import (
    ActionSpec,
    ActionType,
    format_trigger_label,
    get_action_meta,
    get_registered_actions,
)
from core.config_store import MappingRule
from core.events import InputEvent, normalize_binding_event_type
from ui.i18n import tr
from ui.theme import TOKENS, action_pill_state, repolish
from ui.widgets import (
    DarkroomGlowCard,
    DarkroomSurfaceCard,
    PrecisionTickSlider,
    ShortcutRecorderDialog,
    ToggleSwitch,
    make_vector_icon,
)


def _action_to_param_text(action: ActionSpec) -> str:
    """`ActionSpec` 파라미터를 카드 입력창 편집용 문자열로 변환한다."""
    t_str = action.type_name
    p = action.params
    if t_str == ActionType.KEY_COMBO.value:
        return str(p.get("combo", ""))
    if t_str in (ActionType.ZOOM.value, ActionType.MOUSE_WHEEL.value):
        d = int(p.get("direction", 1))
        a = float(p.get("accel", 1.0))
        return f"{d}:{a:g}"
    if t_str == ActionType.TEXT.value:
        return str(p.get("text", ""))
    if t_str == ActionType.MEDIA.value:
        return str(p.get("command", ""))
    if t_str == ActionType.BRIGHTNESS.value:
        return str(p.get("delta", 10))
    if t_str == ActionType.LAUNCH_APP.value:
        return str(p.get("executable", p.get("path", "")))
    if t_str == ActionType.WORKSPACE_LAYOUT.value:
        return str(p.get("preset", ""))
    if t_str == ActionType.LAYER_SHIFT.value:
        if p.get("mode") == "cycle":
            return "cycle"
        return str(p.get("layer", "default"))
    if t_str == ActionType.NONE.value:
        return ""
    return str(p.get("value", p.get("param", "")))


def _param_text_to_action(action_type_str: str, text: str) -> ActionSpec:
    """카드 입력창 문자열을 `ActionSpec` 객체로 파싱한다."""
    val = text.strip()
    if action_type_str == ActionType.KEY_COMBO.value:
        return ActionSpec(ActionType.KEY_COMBO, {"combo": val})
    if action_type_str in (ActionType.ZOOM.value, ActionType.MOUSE_WHEEL.value):
        direction, accel = 1, 1.0
        if ":" in val:
            parts = val.split(":", 1)
            try:
                direction = int(parts[0].strip() or "1")
                accel = float(parts[1].strip() or "1.0")
            except ValueError:
                pass
        elif val:
            try:
                direction = int(val)
            except ValueError:
                pass
        params: dict = {"direction": direction, "accel": accel}
        if action_type_str == ActionType.ZOOM.value:
            params["modifiers"] = ["ctrl"]
        return ActionSpec(action_type_str, params)
    if action_type_str == ActionType.TEXT.value:
        return ActionSpec(ActionType.TEXT, {"text": text, "method": "clipboard"})
    if action_type_str == ActionType.MEDIA.value:
        return ActionSpec(ActionType.MEDIA, {"command": val or "play_pause"})
    if action_type_str == ActionType.BRIGHTNESS.value:
        try:
            delta = int(val or "10")
        except ValueError:
            delta = 10
        return ActionSpec(ActionType.BRIGHTNESS, {"delta": delta})
    if action_type_str == ActionType.LAUNCH_APP.value:
        return ActionSpec(ActionType.LAUNCH_APP, {"executable": val})
    if action_type_str == ActionType.WORKSPACE_LAYOUT.value:
        return ActionSpec(ActionType.WORKSPACE_LAYOUT, {"preset": val})
    if action_type_str == ActionType.LAYER_SHIFT.value:
        if val.lower() == "cycle":
            return ActionSpec(ActionType.LAYER_SHIFT, {"mode": "cycle"})
        return ActionSpec(ActionType.LAYER_SHIFT, {"layer": val or "default", "mode": "set"})
    if action_type_str == ActionType.NONE.value:
        return ActionSpec(ActionType.NONE, {})
    return ActionSpec(action_type_str, {"value": val})


class MappingCardWidget(DarkroomGlowCard):
    """Darkroom 매핑 카드: [인셋 트리거 슬롯] → [액션 설정 + REC/슬라이더] → [삭제(×)]."""

    rule_changed = pyqtSignal(object)  # MappingRule
    delete_requested = pyqtSignal(str)  # rule_id

    def __init__(
        self,
        rule: MappingRule,
        profiles: list[str],
        layers: list[str],
        available_presets: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.rule = rule
        self._is_glowing = False
        self._available_presets: list[str] = list(available_presets or [])
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._glow_timer = QTimer(self)
        self._glow_timer.setSingleShot(True)
        self._glow_timer.timeout.connect(self._clear_glow)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 10, 12)
        root.setSpacing(10)

        # ── [좌측] 인셋 트리거 요약 슬롯 (물리 키캡 베벨 대신 Quiet Pro 슬롯) ──
        norm_type = normalize_binding_event_type(rule.event_type)
        code_txt = (
            f"0x{rule.code:04X}" if isinstance(rule.code, int) else str(rule.code)
        )
        human_label = format_trigger_label(norm_type, rule.code)
        icon_kind = (
            "dial" if "dial" in norm_type else ("mouse" if "mouse" in norm_type else "keypad")
        )
        icon_tok = "--filament-gold" if "dial" in norm_type else "--text-secondary"

        trigger_slot = QFrame()
        trigger_slot.setProperty("surfaceRole", "keycap-slot")
        trigger_slot.setFixedWidth(124)
        ts_layout = QVBoxLayout(trigger_slot)
        ts_layout.setContentsMargins(8, 8, 8, 8)
        ts_layout.setSpacing(4)

        kc_top = QHBoxLayout()
        kc_top.setContentsMargins(0, 0, 0, 0)
        kc_top.setSpacing(4)
        kc_top.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_mini = QLabel()
        icon_mini.setPixmap(make_vector_icon(icon_kind, icon_tok, 12).pixmap(QSize(12, 12)))
        kc_top.addWidget(icon_mini)

        type_lbl = QLabel(norm_type.replace("_", " ").title())
        type_lbl.setProperty("role", "muted")
        kc_top.addWidget(type_lbl)
        ts_layout.addLayout(kc_top)

        self.keycap_label = QLabel(human_label)
        self.keycap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.keycap_label.setProperty("role", "mono-code")
        self.keycap_label.setToolTip(f"{human_label} ({code_txt})")
        ts_layout.addWidget(self.keycap_label)

        raw_dev = (rule.device_name or rule.device_id).strip()
        short_dev = (raw_dev[:6] + "…") if len(raw_dev) > 7 else raw_dev
        sub_meta = QLabel(f"{code_txt} · {short_dev}")
        sub_meta.setToolTip(f"{raw_dev} ({code_txt})")
        sub_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_meta.setProperty("role", "mono-muted")
        ts_layout.addWidget(sub_meta)
        root.addWidget(trigger_slot)

        arrow_lbl = QLabel("→")
        arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow_lbl.setProperty("role", "muted")
        root.addWidget(arrow_lbl)

        # ── [중앙] 액션 유형 배지 & 상세 설정 ───────────────────────────────
        center_col = QVBoxLayout()
        center_col.setContentsMargins(0, 0, 0, 0)
        center_col.setSpacing(6)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        self.action_tag_lbl = QLabel()
        meta_row.addWidget(self.action_tag_lbl)

        self.profile_combo = QComboBox()
        self.profile_combo.setFixedHeight(24)
        for prof in ["*", *profiles]:
            if self.profile_combo.findText(prof) == -1:
                self.profile_combo.addItem(prof)
        if self.profile_combo.findText(rule.profile) == -1:
            self.profile_combo.addItem(rule.profile)
        self.profile_combo.setCurrentText(rule.profile)
        self.profile_combo.currentTextChanged.connect(self._emit_updated_rule)
        meta_row.addWidget(self.profile_combo)

        self.layer_combo = QComboBox()
        self.layer_combo.setFixedHeight(24)
        for lyr in [*layers, "*"]:
            if self.layer_combo.findText(lyr) == -1:
                self.layer_combo.addItem(lyr)
        if self.layer_combo.findText(rule.layer) == -1:
            self.layer_combo.addItem(rule.layer)
        self.layer_combo.setCurrentText(rule.layer)
        self.layer_combo.currentTextChanged.connect(self._emit_updated_rule)
        meta_row.addWidget(self.layer_combo)

        meta_row.addStretch(1)

        self.enabled_chk = ToggleSwitch(
            checked=rule.enabled,
            active_color="--filament-orange",
            width=36,
            height=20,
        )
        self.enabled_chk.setToolTip("규칙 활성/비활성 전환")
        self.enabled_chk.toggled.connect(self._emit_updated_rule)
        meta_row.addWidget(self.enabled_chk)
        center_col.addLayout(meta_row)

        act_row = QHBoxLayout()
        act_row.setSpacing(6)

        self.action_combo = QComboBox()
        self.action_combo.setFixedHeight(28)
        self._populate_action_combo(rule.action.type_name)
        self.action_combo.currentIndexChanged.connect(self._on_action_type_changed)
        act_row.addWidget(self.action_combo)

        initial_param = _action_to_param_text(rule.action)
        self.param_edit = QLineEdit(initial_param)
        self.param_edit.setFixedHeight(28)
        self.param_edit.editingFinished.connect(self._on_param_edited)
        act_row.addWidget(self.param_edit, 1)

        self.record_btn = QPushButton("REC")
        self.record_btn.setProperty("btnRole", "ghost")
        self.record_btn.setIcon(make_vector_icon("record", "--filament-orange", 11))
        self.record_btn.setIconSize(QSize(11, 11))
        self.record_btn.setToolTip("키보드 단축키 직접 녹화")
        self.record_btn.setFixedHeight(28)
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.clicked.connect(self._on_record_shortcut)
        act_row.addWidget(self.record_btn)

        self.preset_combo = QComboBox()
        self.preset_combo.setFixedHeight(28)
        self.preset_combo.setEditable(True)
        self.preset_combo.currentTextChanged.connect(self._on_preset_combo_changed)
        act_row.addWidget(self.preset_combo, 1)

        apply_btn = QPushButton("✓")
        apply_btn.setProperty("btnRole", "quiet")
        apply_btn.setToolTip("변경사항 적용")
        apply_btn.setFixedSize(28, 28)
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.clicked.connect(self._emit_updated_rule)
        act_row.addWidget(apply_btn)
        center_col.addLayout(act_row)

        self.accel_slider = PrecisionTickSlider(
            minimum=0.5,
            maximum=3.0,
            value=float(rule.action.params.get("accel", 1.0)),
            step=0.1,
            ticks=11,
            unit="x",
        )
        self.accel_slider.value_changed.connect(self._on_accel_slider_changed)
        center_col.addWidget(self.accel_slider)

        root.addLayout(center_col, 1)

        del_col = QVBoxLayout()
        del_col.setContentsMargins(0, 0, 0, 0)
        self.delete_btn = QPushButton("×")
        self.delete_btn.setProperty("btnRole", "ghost-danger")
        self.delete_btn.setToolTip("이 매핑 카드 삭제")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(
            lambda: self.delete_requested.emit(self.rule.rule_id)
        )
        del_col.addWidget(self.delete_btn, 0, Qt.AlignmentFlag.AlignTop)
        del_col.addStretch(1)
        root.addLayout(del_col)

        self.set_available_presets(self._available_presets)
        self._sync_action_input_mode(rule.action.type_name)
        self._update_action_tag_style(rule.action.type_name)

    def _on_record_shortcut(self) -> None:
        dlg = ShortcutRecorderDialog(initial_combo=self.param_edit.text().strip(), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.recorded_combo:
            self.param_edit.setText(dlg.recorded_combo)
            self._emit_updated_rule()

    def _on_param_edited(self) -> None:
        act_type = self.selected_action_type()
        if act_type in (ActionType.ZOOM.value, ActionType.MOUSE_WHEEL.value):
            parsed = _param_text_to_action(act_type, self.param_edit.text())
            self.accel_slider.blockSignals(True)
            self.accel_slider.setValue(float(parsed.params.get("accel", 1.0)))
            self.accel_slider.blockSignals(False)
        self._emit_updated_rule()

    def _on_accel_slider_changed(self, accel_val: float) -> None:
        act_type = self.selected_action_type()
        if act_type not in (ActionType.ZOOM.value, ActionType.MOUSE_WHEEL.value):
            return
        parsed = _param_text_to_action(act_type, self.param_edit.text())
        direction = int(parsed.params.get("direction", 1))
        self.param_edit.setText(f"{direction}:{accel_val:g}")
        self._emit_updated_rule()

    def _populate_action_combo(self, selected_type: str) -> None:
        self.action_combo.blockSignals(True)
        self.action_combo.clear()
        for meta in get_registered_actions():
            self.action_combo.addItem(meta.display_name, meta.action_type)
        idx = self.action_combo.findData(selected_type)
        if idx < 0:
            self.action_combo.addItem(selected_type, selected_type)
            idx = self.action_combo.findData(selected_type)
        self.action_combo.setCurrentIndex(max(0, idx))
        self.action_combo.blockSignals(False)

    def refresh_action_registry(self) -> None:
        """`@register_action` 레지스트리 목록을 다시 읽어 콤보박스를 갱신한다."""
        cur_type = self.selected_action_type()
        self._populate_action_combo(cur_type)

    def set_layers(self, layers: list[str]) -> None:
        """레이어 목록 변경 시 카드 내 레이어 선택 콤보박스를 동기화한다."""
        cur_layer = self.layer_combo.currentText()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        for lyr in [*layers, "*"]:
            if self.layer_combo.findText(lyr) == -1:
                self.layer_combo.addItem(lyr)
        if cur_layer and self.layer_combo.findText(cur_layer) == -1:
            self.layer_combo.addItem(cur_layer)
        self.layer_combo.setCurrentText(cur_layer or "default")
        self.layer_combo.blockSignals(False)

    def selected_action_type(self) -> str:
        """현재 선택된 액션 타입 키 문자열을 반환한다."""
        data = self.action_combo.currentData()
        return str(data) if data is not None else self.action_combo.currentText()

    def select_action_type(self, action_type_str: str) -> None:
        """액션 타입 키 문자열로 드롭다운 선택을 변경한다."""
        idx = self.action_combo.findData(action_type_str)
        if idx >= 0:
            self.action_combo.setCurrentIndex(idx)

    def set_available_presets(self, preset_names: list[str]) -> None:
        """`창 레이아웃 실행` 액션용 프리셋 드롭다운 목록을 갱신한다."""
        self._available_presets = list(preset_names)
        current_val = self.param_edit.text().strip()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for name in self._available_presets:
            self.preset_combo.addItem(name)
        if current_val and self.preset_combo.findText(current_val) == -1:
            self.preset_combo.addItem(current_val)
        if current_val:
            self.preset_combo.setCurrentText(current_val)
        elif self._available_presets and self.selected_action_type() == ActionType.WORKSPACE_LAYOUT.value:
            self.preset_combo.setCurrentIndex(0)
            self.param_edit.setText(self.preset_combo.currentText())
        self.preset_combo.blockSignals(False)

    def _sync_action_input_mode(self, action_type_str: str) -> None:
        meta = get_action_meta(action_type_str)
        self.param_edit.setPlaceholderText(meta.placeholder if meta else "")
        is_layout = action_type_str == ActionType.WORKSPACE_LAYOUT.value
        is_combo = action_type_str == ActionType.KEY_COMBO.value
        is_analog = action_type_str in (ActionType.ZOOM.value, ActionType.MOUSE_WHEEL.value)
        self.param_edit.setVisible(not is_layout)
        self.preset_combo.setVisible(is_layout)
        self.record_btn.setVisible(is_combo)
        self.accel_slider.setVisible(is_analog)
        if is_analog:
            parsed = _param_text_to_action(action_type_str, self.param_edit.text())
            self.accel_slider.blockSignals(True)
            self.accel_slider.setValue(float(parsed.params.get("accel", 1.0)))
            self.accel_slider.blockSignals(False)
        if is_layout:
            cur = self.param_edit.text().strip()
            if cur:
                self.preset_combo.blockSignals(True)
                if self.preset_combo.findText(cur) == -1:
                    self.preset_combo.addItem(cur)
                self.preset_combo.setCurrentText(cur)
                self.preset_combo.blockSignals(False)
            elif self.preset_combo.count() > 0:
                self.param_edit.setText(self.preset_combo.currentText())

    def _on_preset_combo_changed(self, text: str) -> None:
        if self.selected_action_type() == ActionType.WORKSPACE_LAYOUT.value:
            self.param_edit.setText(text)
            self._emit_updated_rule()

    def _update_action_tag_style(self, action_type_str: str) -> None:
        meta = get_action_meta(action_type_str)
        tag_text = meta.tag_label if meta else action_type_str.upper()
        self.action_tag_lbl.setText(tag_text)
        self.action_tag_lbl.setProperty("pillState", action_pill_state(action_type_str))
        repolish(self.action_tag_lbl)

    def _on_action_type_changed(self, _idx: int) -> None:
        new_type = self.selected_action_type()
        self._sync_action_input_mode(new_type)
        self._update_action_tag_style(new_type)
        self._emit_updated_rule()

    def _emit_updated_rule(self) -> None:
        action_type_str = self.selected_action_type()
        param_text = (
            self.preset_combo.currentText()
            if action_type_str == ActionType.WORKSPACE_LAYOUT.value
            else self.param_edit.text()
        )
        updated = MappingRule(
            rule_id=self.rule.rule_id,
            device_id=self.rule.device_id,
            device_name=self.rule.device_name,
            event_type=self.rule.event_type,
            code=self.rule.code,
            profile=self.profile_combo.currentText(),
            layer=self.layer_combo.currentText(),
            label=self.rule.label,
            enabled=self.enabled_chk.isChecked(),
            action=_param_text_to_action(action_type_str, param_text),
        )
        self.rule = updated
        self.rule_changed.emit(updated)

    def trigger_glow(self, color: str | None = None, duration_ms: int = 240) -> None:
        """실제 입력 트리거 시 240ms 동안 카드 테두리를 열 필라멘트 색조로 점등한다."""
        if color is None:
            pill = action_pill_state(self.rule.action.type_name)
            color = (
                TOKENS["--filament-gold"]
                if pill == "gold"
                else TOKENS["--filament-orange"]
            )
        self._is_glowing = True
        self.set_glow_accent(color)
        self._glow_timer.start(duration_ms)

    def _clear_glow(self) -> None:
        self._is_glowing = False
        self.set_glow_accent(None)

    @property
    def is_glowing(self) -> bool:
        """테스트 및 상태 확인용 점등 여부를 반환한다."""
        return self._is_glowing


class MappingCardsPanel(DarkroomSurfaceCard):
    """2열 모듈형 매핑 카드 그리드, 세그먼트 레이어 탭, Listen 배너 컨테이너."""

    rule_upserted = pyqtSignal(object)  # MappingRule
    rule_deleted = pyqtSignal(str)      # rule_id
    rules_cleared = pyqtSignal(list)    # list[str]
    layer_selected = pyqtSignal(str)
    listen_toggled = pyqtSignal(bool)
    export_matrix_requested = pyqtSignal()
    import_matrix_requested = pyqtSignal()

    def __init__(
        self,
        profiles: list[str] | None = None,
        layers: list[str] | None = None,
    ) -> None:
        super().__init__(warm_rim=False, radius_token="--radius-card", bg_token="--bg-surface")

        self._profiles = list(
            profiles or ["bim_cad", "ide", "media", "simulation", "browser", "default"]
        )
        self._layers = list(layers or ["default", "bim", "media"])
        self._available_presets: list[str] = []
        self._filter_device_id: str = ""
        self._filter_profile: str = "전체"
        self._lang: str = "ko"
        self._listen_active: bool = False
        self._cards: dict[str, MappingCardWidget] = {}
        self._layer_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.title_lbl = QLabel("Mapping Matrix")
        self.title_lbl.setProperty("role", "card-title")
        header.addWidget(self.title_lbl)

        self.filter_lbl = QLabel("전체 장치")
        self.filter_lbl.setProperty("pillState", "gold")
        header.addWidget(self.filter_lbl)

        self._seg_frame = QFrame()
        self._seg_frame.setProperty("surfaceRole", "inset")
        self._seg_layout = QHBoxLayout(self._seg_frame)
        self._seg_layout.setContentsMargins(3, 3, 3, 3)
        self._seg_layout.setSpacing(2)

        self._layer_btn_group = QButtonGroup(self)
        self._layer_btn_group.setExclusive(True)
        header.addWidget(self._seg_frame)

        self.layer_selector = QComboBox()
        self.layer_selector.setVisible(False)
        self.layer_selector.currentTextChanged.connect(self._on_layer_changed)

        header.addStretch(1)

        ctrl_frame = QFrame()
        ctrl_frame.setProperty("surfaceRole", "inset")
        ctrl_layout = QHBoxLayout(ctrl_frame)
        ctrl_layout.setContentsMargins(4, 3, 4, 3)
        ctrl_layout.setSpacing(4)

        self.listen_btn = QPushButton("Listen Mode")
        self.listen_btn.setProperty("btnRole", "listen")
        self.listen_btn.setCheckable(True)
        self.listen_btn.setFixedHeight(24)
        self.listen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.listen_btn.toggled.connect(self._on_listen_btn_toggled)
        ctrl_layout.addWidget(self.listen_btn)

        self.clear_btn = QPushButton("목록 초기화")
        self.clear_btn.setProperty("btnRole", "ghost-danger")
        self.clear_btn.setFixedHeight(24)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(lambda: self.clear_scoped_cards(confirm=True))
        ctrl_layout.addWidget(self.clear_btn)

        self.export_btn = QPushButton("내보내기")
        self.export_btn.setProperty("btnRole", "quiet")
        self.export_btn.setFixedHeight(24)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.clicked.connect(self.export_matrix_requested.emit)
        ctrl_layout.addWidget(self.export_btn)

        self.import_btn = QPushButton("불러오기")
        self.import_btn.setProperty("btnRole", "quiet")
        self.import_btn.setFixedHeight(24)
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.clicked.connect(self.import_matrix_requested.emit)
        ctrl_layout.addWidget(self.import_btn)
        header.addWidget(ctrl_frame)

        self.profile_filter_combo = QComboBox()
        self.profile_filter_combo.setFixedHeight(28)
        self.profile_filter_combo.addItem("전체")
        self.profile_filter_combo.addItem("*")
        for prof in self._profiles:
            if self.profile_filter_combo.findText(prof) == -1:
                self.profile_filter_combo.addItem(prof)
        self.profile_filter_combo.currentTextChanged.connect(
            self._on_profile_filter_changed
        )
        header.addWidget(self.profile_filter_combo)
        layout.addLayout(header)

        self.listen_banner = QLabel(tr("ko", "matrix_listen_banner"))
        self.listen_banner.setProperty("role", "listen-banner")
        self.listen_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.listen_banner.setVisible(False)
        layout.addWidget(self.listen_banner)

        self.empty_hint = QLabel(tr("ko", "matrix_empty_hint"))
        self.empty_hint.setProperty("role", "empty-hint")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.cards_container = QWidget()
        self.cards_container.setProperty("role", "transparent-bg")
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 4, 0)
        self.cards_layout.setHorizontalSpacing(12)
        self.cards_layout.setVerticalSpacing(12)
        self.cards_layout.setColumnStretch(0, 1)
        self.cards_layout.setColumnStretch(1, 1)

        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll, 1)

        self.set_layers(self._layers)
        self._update_listen_btn_style(False)

    def apply_language(self, lang: str) -> None:
        """언어 전환 시 매핑 매트릭스 라벨을 즉시 갱신한다."""
        self._lang = lang
        self.title_lbl.setText(tr(lang, "matrix_title"))
        if not self._filter_device_id:
            self.filter_lbl.setText(tr(lang, "matrix_all_devices"))
        self.clear_btn.setText(tr(lang, "clear_mappings"))
        self.export_btn.setText(tr(lang, "export_matrix"))
        self.import_btn.setText(tr(lang, "import_matrix"))
        self.listen_banner.setText(tr(lang, "matrix_listen_banner"))
        self.empty_hint.setText(tr(lang, "matrix_empty_hint"))
        self._update_listen_btn_style(self._listen_active)

    def set_layers(self, layers: list[str]) -> None:
        """사용자 정의 레이어 목록 변경 시 세그먼트 탭과 카드 드롭다운을 동적 재구성한다."""
        self._layers = list(layers or ["default"])
        cur_active = self.layer_selector.currentText() or self._layers[0]
        if cur_active not in self._layers:
            cur_active = self._layers[0]

        for btn in self._layer_buttons.values():
            self._layer_btn_group.removeButton(btn)
            self._seg_layout.removeWidget(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._layer_buttons.clear()

        for lyr in self._layers:
            btn = QPushButton(lyr)
            btn.setProperty("btnRole", "segment")
            btn.setCheckable(True)
            btn.setFixedHeight(22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _chk, name=lyr: self._on_layer_tab_clicked(name))
            self._layer_btn_group.addButton(btn)
            self._layer_buttons[lyr] = btn
            self._seg_layout.addWidget(btn)

        self.layer_selector.blockSignals(True)
        self.layer_selector.clear()
        for lyr in self._layers:
            self.layer_selector.addItem(lyr)
        self.layer_selector.setCurrentText(cur_active)
        self.layer_selector.blockSignals(False)

        for card in self._cards.values():
            card.set_layers(self._layers)

        self._sync_layer_tab_styles(cur_active)
        self._apply_filter_visibility()

    def _update_listen_btn_style(self, active: bool) -> None:
        self._listen_active = active
        self.listen_btn.setProperty("active", active)
        self.listen_btn.setIcon(
            make_vector_icon(
                "record",
                "--filament-gold" if active else "--text-secondary",
                11,
            )
        )
        self.listen_btn.setIconSize(QSize(11, 11))
        self.listen_btn.setText(tr(self._lang, "listen_on" if active else "listen_mode"))
        repolish(self.listen_btn)

    def _sync_layer_tab_styles(self, active_layer: str) -> None:
        for lyr, btn in self._layer_buttons.items():
            is_active = lyr == active_layer
            btn.blockSignals(True)
            btn.setChecked(is_active)
            btn.blockSignals(False)
            btn.setProperty("active", is_active)
            repolish(btn)

    def _on_layer_tab_clicked(self, layer: str) -> None:
        self.layer_selector.setCurrentText(layer)

    def _on_listen_btn_toggled(self, checked: bool) -> None:
        self._update_listen_btn_style(checked)
        self.listen_banner.setVisible(checked)
        self.listen_toggled.emit(checked)

    def set_listen_active(self, active: bool) -> None:
        """좌측 패널과 Listen 상태 표시 및 배너를 양방향 동기화한다."""
        if self.listen_btn.isChecked() != active:
            self.listen_btn.blockSignals(True)
            self.listen_btn.setChecked(active)
            self.listen_btn.blockSignals(False)
        self._update_listen_btn_style(active)
        self.listen_banner.setVisible(active)

    def _on_profile_filter_changed(self, profile: str) -> None:
        self._filter_profile = profile or "전체"
        self._apply_filter_visibility()

    def _on_layer_changed(self, layer: str) -> None:
        self._sync_layer_tab_styles(layer)
        self._apply_filter_visibility()
        self.layer_selected.emit(layer)

    def set_active_layer(self, layer: str) -> None:
        """활성 레이어 탭과 숨김 콤보박스를 동기화한다."""
        if self.layer_selector.findText(layer) == -1:
            self.layer_selector.addItem(layer)
        self.layer_selector.blockSignals(True)
        self.layer_selector.setCurrentText(layer)
        self.layer_selector.blockSignals(False)
        self._sync_layer_tab_styles(layer)
        self._apply_filter_visibility()

    def set_device_filter(self, device_id: str, label: str = "") -> None:
        """좌측 패널에서 선택한 장치만 필터링해 표시한다."""
        self._filter_device_id = device_id
        self.filter_lbl.setText(
            label or (tr(self._lang, "matrix_all_devices") if not device_id else device_id)
        )
        self._apply_filter_visibility()

    def _card_matches_current_scope(self, card: MappingCardWidget) -> bool:
        if self._filter_device_id and card.rule.device_id != self._filter_device_id:
            return False
        if self._filter_profile != "전체" and card.rule.profile != self._filter_profile:
            return False
        active_layer = self.layer_selector.currentText()
        if active_layer and card.rule.layer not in (active_layer, "*"):
            return False
        return True

    def _apply_filter_visibility(self) -> None:
        while self.cards_layout.count():
            self.cards_layout.takeAt(0)

        visible_cards: list[MappingCardWidget] = []
        for card in self._cards.values():
            show = self._card_matches_current_scope(card)
            card.setVisible(show)
            if show:
                visible_cards.append(card)

        for idx, card in enumerate(visible_cards):
            self.cards_layout.addWidget(card, idx // 2, idx % 2)

        spacer_row = (len(visible_cards) + 1) // 2
        self.cards_layout.setRowStretch(spacer_row, 1)
        for r in range(spacer_row):
            self.cards_layout.setRowStretch(r, 0)

        self.empty_hint.setVisible(len(visible_cards) == 0)
        self.scroll.setVisible(len(visible_cards) > 0)

    def load_rules(self, rules: list[MappingRule]) -> None:
        """저장된 `MappingRule` 목록으로부터 2열 카드 그리드를 일괄 재구성한다."""
        while self.cards_layout.count():
            self.cards_layout.takeAt(0)

        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        for rule in rules:
            self._add_card_widget(rule)
        self._apply_filter_visibility()

    def set_available_presets(self, preset_names: list[str]) -> None:
        """모든 매핑 카드의 `창 레이아웃 실행` 프리셋 드롭다운을 일괄 갱신한다."""
        self._available_presets = list(preset_names)
        for card in self._cards.values():
            card.set_available_presets(self._available_presets)

    def refresh_action_registry(self) -> None:
        """동적 등록된 액션을 모든 매핑 카드 드롭다운에 즉시 반영한다."""
        for card in self._cards.values():
            card.refresh_action_registry()

    def _add_card_widget(self, rule: MappingRule) -> MappingCardWidget:
        card = MappingCardWidget(
            rule,
            profiles=self._profiles,
            layers=self._layers,
            available_presets=self._available_presets,
        )
        card.rule_changed.connect(self.rule_upserted.emit)
        card.delete_requested.connect(self._on_delete_card)
        self._cards[rule.rule_id] = card
        self._apply_filter_visibility()
        return card

    def _on_delete_card(self, rule_id: str) -> None:
        card = self._cards.pop(rule_id, None)
        if card is not None:
            self.cards_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._apply_filter_visibility()
        self.rule_deleted.emit(rule_id)

    def clear_scoped_cards(self, confirm: bool = True) -> list[str]:
        """확인 대화상자를 거쳐 현재 레이어/프로파일 범위의 매핑 카드를 일괄 삭제한다."""
        active_layer = self.layer_selector.currentText() or "default"
        target_ids = [
            rid
            for rid, card in self._cards.items()
            if self._card_matches_current_scope(card)
        ]
        if not target_ids:
            return []

        if confirm:
            prof_label = self._filter_profile
            reply = QMessageBox.question(
                self,
                "매핑 목록 초기화",
                f"현재 레이어('{active_layer}') / 프로파일('{prof_label}')의 "
                f"매핑 카드 {len(target_ids)}개를 모두 삭제하시겠습니까?\n"
                "삭제된 항목은 config.json에서도 즉시 제거됩니다.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return []

        for rid in target_ids:
            card = self._cards.pop(rid, None)
            if card is not None:
                self.cards_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()

        self._apply_filter_visibility()
        self.rules_cleared.emit(target_ids)
        return target_ids

    def create_or_focus_from_event(
        self,
        event: InputEvent,
        device_name: str,
        profile: str = "*",
        layer: str = "default",
    ) -> MappingRule | None:
        """Listen Mode에서 포착된 `InputEvent`에 대한 매핑 카드를 동적 생성 또는 점등한다."""
        if event.is_release:
            return None

        for card in self._cards.values():
            if (
                card.rule.trigger_key == event.binding_key
                and card.rule.profile == profile
                and card.rule.layer == layer
            ):
                card.trigger_glow(TOKENS["--filament-orange"])
                return card.rule

        norm_type = normalize_binding_event_type(event.event_type)
        default_action = self._suggest_default_action(event)
        new_rule = MappingRule(
            device_id=event.device_id,
            device_name=device_name or event.device_name,
            event_type=norm_type,
            code=event.code,
            profile=profile,
            layer=layer,
            action=default_action,
        )
        card = self._add_card_widget(new_rule)
        card.trigger_glow(TOKENS["--filament-gold"])
        self.rule_upserted.emit(new_rule)
        return new_rule

    @staticmethod
    def _suggest_default_action(event: InputEvent) -> ActionSpec:
        et = event.event_type_str
        if et == "dial_cw":
            return ActionSpec(ActionType.ZOOM, {"direction": 1, "accel": 1.2, "modifiers": ["ctrl"]})
        if et == "dial_ccw":
            return ActionSpec(ActionType.ZOOM, {"direction": -1, "accel": 1.2, "modifiers": ["ctrl"]})
        if et in ("dial_press", "dial_double_click"):
            return ActionSpec(ActionType.MEDIA, {"command": "play_pause"})
        if et == "dial_long_press":
            return ActionSpec(ActionType.LAYER_SHIFT, {"mode": "cycle"})
        return ActionSpec(ActionType.KEY_COMBO, {"combo": ""})

    def flash_card_for_rule(self, rule_id: str, color: str | None = None) -> bool:
        """트리거된 규칙의 카드 테두리를 240ms 동안 점등한다."""
        card = self._cards.get(rule_id)
        if card is None:
            return False
        card.trigger_glow(color=color)
        return True

    def flash_matching_event(self, event: InputEvent) -> int:
        """이벤트와 일치하는 모든 카드를 240ms 동안 점등한다."""
        flashed = 0
        ev_key = event.binding_key
        for card in self._cards.values():
            if card.rule.trigger_key == ev_key:
                card.trigger_glow()
                flashed += 1
        return flashed
