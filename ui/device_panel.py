"""좌측 연결 장치 패널 — Obsidian Tactile HUD 스타일.

모든 색상·물성 스타일을 `ui/theme.py` 토큰에서 참조하며,
1.5px 모노라인 벡터 아이콘, 돌출(Raised) 장치 카드, 별칭 편집 및 보호 잠금 토글을 제공한다.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.device_registry import DeviceInfo
from core.events import DeviceType
from ui.i18n import tr
from ui.theme import (
    ACCENT_AMBER,
    ACCENT_CYAN,
    ACCENT_CYAN_BG,
    ACCENT_CYAN_BORDER,
    BG_INSET,
    BORDER_HAIRLINE,
    FONT_MONO,
    STATUS_OK,
    STATUS_OK_BG,
    STATUS_OK_BORDER,
    STATUS_WARN,
    STATUS_WARN_BG,
    STATUS_WARN_BORDER,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    badge_qss,
    inset_slot_qss,
    raised_card_qss,
    section_header_qss,
    surface_panel_qss,
    tactile_button_qss,
)
from ui.widgets import make_vector_icon


class DeviceItemWidget(QFrame):
    """개별 HID/입력 장치 돌출(Raised) 카드 위젯."""

    clicked = pyqtSignal(str)
    protection_toggled = pyqtSignal(str, bool)
    alias_changed = pyqtSignal(str, str)

    def __init__(self, device: DeviceInfo, selected: bool = False) -> None:
        super().__init__()
        self.device = device
        self._selected = selected
        self.setObjectName("DeviceItemCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(10)

        # 좌측 음각 슬롯 내부 1.5px 모노라인 벡터 아이콘
        icon_kind, accent_hex = self._device_icon_meta(device.device_type)
        icon_slot = QFrame()
        icon_slot.setObjectName("DeviceIconSlot")
        icon_slot.setFixedSize(32, 32)
        icon_slot.setStyleSheet(inset_slot_qss("DeviceIconSlot", radius=4))
        ic_lay = QHBoxLayout(icon_slot)
        ic_lay.setContentsMargins(0, 0, 0, 0)
        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(make_vector_icon(icon_kind, accent_hex, 17).pixmap(QSize(17, 17)))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        ic_lay.addWidget(icon_lbl)
        root.addWidget(icon_slot)

        # 중앙 정보 영역
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        status_dot = QLabel()
        status_dot.setFixedSize(6, 6)
        if device.protected:
            dot_color = STATUS_WARN
            status_dot.setToolTip("Protected (입력 보호 잠금)")
        elif device.is_registered and device.is_connected:
            dot_color = STATUS_OK
            status_dot.setToolTip("Active Auxiliary (리매핑 활성)")
        elif device.is_connected:
            dot_color = ACCENT_CYAN
            status_dot.setToolTip("Auxiliary Standby (대기 중)")
        else:
            dot_color = TEXT_MUTED
            status_dot.setToolTip("Offline")
        status_dot.setStyleSheet(
            f"background-color: {dot_color}; border-radius: 3px; border: none;"
        )
        top_row.addWidget(status_dot)

        self.name_lbl = QLabel(device.display_name)
        self.name_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-weight: 600; font-size: 12px; border: none; background: transparent;"
        )
        top_row.addWidget(self.name_lbl, 1)

        # 인라인 별칭 편집 버튼
        self.edit_alias_btn = QPushButton()
        self.edit_alias_btn.setIcon(make_vector_icon("edit", TEXT_SECONDARY, 12))
        self.edit_alias_btn.setIconSize(QSize(12, 12))
        self.edit_alias_btn.setToolTip("장치 별칭(Alias) 편집")
        self.edit_alias_btn.setFixedSize(20, 20)
        self.edit_alias_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_alias_btn.setStyleSheet(tactile_button_qss("ghost", radius=4, padding="0px"))
        self.edit_alias_btn.clicked.connect(self._on_edit_alias)
        top_row.addWidget(self.edit_alias_btn)

        type_badge = QLabel(self._type_badge_text(device.device_type))
        type_badge.setStyleSheet(
            badge_qss(
                fg=accent_hex,
                bg=BG_INSET,
                border=BORDER_HAIRLINE,
                mono=True,
                padding="1px 6px",
                font_size=9,
            )
        )
        top_row.addWidget(type_badge)
        info_col.addLayout(top_row)

        meta_parts = [device.vid_pid_label]
        if device.usage_page:
            meta_parts.append(f"UP:0x{device.usage_page:02X}")
        if device.key_count:
            meta_parts.append(f"{device.key_count}Keys")
        if device.is_registered:
            meta_parts.append("ACTIVE")
        elif not device.is_connected:
            meta_parts.append("OFFLINE")

        meta_lbl = QLabel(" · ".join(meta_parts))
        meta_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-family: {FONT_MONO}; font-size: 9.5px; "
            "border: none; background: transparent;"
        )
        info_col.addWidget(meta_lbl)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        reason_text = device.protection_reason or (
            "Remappable Auxiliary" if not device.protected else "Protected"
        )
        reason_lbl = QLabel(reason_text)
        reason_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none; background: transparent;"
        )
        bottom_row.addWidget(reason_lbl, 1)

        self.lock_btn = QPushButton()
        self.lock_btn.setFixedHeight(20)
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if device.protected:
            self.lock_btn.setIcon(make_vector_icon("shield", STATUS_WARN, 11))
            self.lock_btn.setIconSize(QSize(11, 11))
            self.lock_btn.setText("Protected")
            self.lock_btn.setStyleSheet(
                f"QPushButton {{ background-color: {STATUS_WARN_BG}; color: {STATUS_WARN}; "
                f"border: 1px solid {STATUS_WARN_BORDER}; border-radius: 4px; padding: 0 7px; "
                f"font-family: {FONT_MONO}; font-size: 9.5px; font-weight: 700; }}"
                f"QPushButton:hover {{ border-color: {STATUS_WARN}; }}"
            )
        else:
            btn_text = "Auxiliary" if device.is_registered else "Standby"
            btn_fg = STATUS_OK if device.is_registered else ACCENT_CYAN
            btn_bg = STATUS_OK_BG if device.is_registered else ACCENT_CYAN_BG
            btn_bd = STATUS_OK_BORDER if device.is_registered else ACCENT_CYAN_BORDER
            self.lock_btn.setText(btn_text)
            self.lock_btn.setStyleSheet(
                f"QPushButton {{ background-color: {btn_bg}; color: {btn_fg}; "
                f"border: 1px solid {btn_bd}; border-radius: 4px; padding: 0 7px; "
                f"font-family: {FONT_MONO}; font-size: 9.5px; font-weight: 700; }}"
                f"QPushButton:hover {{ border-color: {btn_fg}; }}"
            )

        self.lock_btn.clicked.connect(self._on_toggle_lock)
        bottom_row.addWidget(self.lock_btn)

        info_col.addLayout(bottom_row)
        root.addLayout(info_col, 1)

        self._apply_border_style()

    @staticmethod
    def _device_icon_meta(dev_type: DeviceType) -> tuple[str, str]:
        return {
            DeviceType.HID_DIAL: ("dial", ACCENT_CYAN),
            DeviceType.KEYPAD: ("keypad", ACCENT_AMBER),
            DeviceType.KEYBOARD: ("keyboard", TEXT_SECONDARY),
            DeviceType.MOUSE: ("mouse", STATUS_WARN),
            DeviceType.HID_OTHER: ("hid", TEXT_MUTED),
        }.get(dev_type, ("hid", TEXT_MUTED))

    @staticmethod
    def _type_badge_text(dev_type: DeviceType) -> str:
        return {
            DeviceType.HID_DIAL: "DIAL",
            DeviceType.KEYPAD: "KEYPAD",
            DeviceType.KEYBOARD: "KBD",
            DeviceType.MOUSE: "MOUSE",
            DeviceType.HID_OTHER: "HID",
        }.get(dev_type, "HID")

    def _apply_border_style(self) -> None:
        self.setStyleSheet(
            raised_card_qss(
                "DeviceItemCard",
                selected=self._selected,
                border_accent=(
                    STATUS_OK_BORDER
                    if (not self._selected and self.device.is_registered and not self.device.protected)
                    else None
                ),
                radius=6,
            )
        )

    def _on_edit_alias(self) -> None:
        new_alias, ok = QInputDialog.getText(
            self,
            "장치 별칭(Alias) 설정",
            f"'{self.device.name}' 장치에 표시할 별칭을 입력하세요 (비우면 기본 이름 복원):",
            text=self.device.alias or self.device.display_name,
        )
        if ok:
            self.alias_changed.emit(self.device.device_id, new_alias.strip())

    def _on_toggle_lock(self) -> None:
        target_protected = not self.device.protected
        if not target_protected and self.device.is_primary_safeguard:
            reply = QMessageBox.warning(
                self,
                "주 입력 장치 보호 해제 경고",
                f"'{self.device.display_name}' 장치는 메인 키보드 안전장치(Primary Safeguard)로 보호 중입니다.\n"
                "잠금을 해제하면 실수로 입력이 차단될 수 있습니다. 정말 해제하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.protection_toggled.emit(self.device.device_id, target_protected)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self.device.device_id)
        super().mousePressEvent(event)


class DevicePanel(QFrame):
    """좌측 장치 제어 패널 (연결 장치 스캔, 별칭 편집, Protected 토글, Listen 등록)."""

    listen_toggled = pyqtSignal(bool)
    refresh_requested = pyqtSignal()
    device_selected = pyqtSignal(str)
    protection_toggled = pyqtSignal(str, bool)
    alias_changed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("LeftDevicePanel")
        self.setMinimumWidth(296)
        self.setStyleSheet(surface_panel_qss("LeftDevicePanel", radius=6))

        self._selected_device_id: str = ""
        self._listening: bool = False
        self._lang: str = "ko"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.title_lbl = QLabel("HARDWARE HUB")
        self.title_lbl.setStyleSheet(section_header_qss())
        header.addWidget(self.title_lbl, 1)

        self.all_btn = QPushButton("전체")
        self.all_btn.setFixedHeight(24)
        self.all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_btn.setStyleSheet(tactile_button_qss("default", radius=4, padding="0 8px"))
        self.all_btn.clicked.connect(lambda: self._select_device(""))
        header.addWidget(self.all_btn)

        self.refresh_btn = QPushButton("스캔")
        self.refresh_btn.setFixedHeight(24)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(tactile_button_qss("default", radius=4, padding="0 8px"))
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        # Listen Mode 등록 버튼
        self.listen_btn = QPushButton()
        self.listen_btn.setCheckable(True)
        self.listen_btn.setFixedHeight(32)
        self.listen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.listen_btn.toggled.connect(self._on_listen_btn_toggled)
        self._update_listen_button_style(False)
        layout.addWidget(self.listen_btn)

        self.count_lbl = QLabel("SCANNING...")
        self.count_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-family: {FONT_MONO}; font-size: 10px;"
        )
        layout.addWidget(self.count_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)

        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll, 1)

    def apply_language(self, lang: str) -> None:
        """언어 전환 시 장치 패널 라벨을 즉시 갱신한다."""
        self._lang = lang
        self.title_lbl.setText(tr(lang, "hub_title"))
        self.all_btn.setText(tr(lang, "hub_all"))
        self.refresh_btn.setText(tr(lang, "hub_scan"))
        self._update_listen_button_style(self._listening)

    def _update_listen_button_style(self, active: bool) -> None:
        if active:
            self.listen_btn.setIcon(make_vector_icon("record", ACCENT_CYAN, 13))
            self.listen_btn.setIconSize(QSize(13, 13))
            self.listen_btn.setText(tr(self._lang, "hub_listen_on"))
            self.listen_btn.setStyleSheet(
                tactile_button_qss("cyan", radius=4, padding="0 10px", bold=True)
            )
        else:
            self.listen_btn.setIcon(make_vector_icon("record", ACCENT_AMBER, 13))
            self.listen_btn.setIconSize(QSize(13, 13))
            self.listen_btn.setText(tr(self._lang, "hub_listen_off"))
            self.listen_btn.setStyleSheet(
                tactile_button_qss("default", radius=4, padding="0 10px")
            )

    def _on_listen_btn_toggled(self, checked: bool) -> None:
        self._listening = checked
        self._update_listen_button_style(checked)
        self.listen_toggled.emit(checked)

    def set_listen_active(self, active: bool) -> None:
        """외부 상태 변경에 맞춰 Listen 버튼 상태를 동기화한다."""
        if self.listen_btn.isChecked() != active:
            self.listen_btn.blockSignals(True)
            self.listen_btn.setChecked(active)
            self.listen_btn.blockSignals(False)
        self._listening = active
        self._update_listen_button_style(active)

    def _select_device(self, device_id: str) -> None:
        self._selected_device_id = device_id
        self.device_selected.emit(device_id)

    def refresh_devices(self, devices: list[DeviceInfo]) -> None:
        """장치 목록을 정렬(등록 보조 -> 미등록 보조 -> Protected)하여 UI에 반영한다."""
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        sorted_devs = sorted(
            devices,
            key=lambda d: (
                0 if (d.is_registered and not d.protected) else (1 if not d.protected else 2),
                0 if d.device_type == DeviceType.HID_DIAL else 1,
                d.display_name.lower(),
            ),
        )

        aux_count = sum(1 for d in sorted_devs if not d.protected and d.is_connected)
        prot_count = sum(1 for d in sorted_devs if d.protected and d.is_connected)
        self.count_lbl.setText(
            f"DEVICES {len(sorted_devs):02d}  ·  AUX {aux_count:02d}  ·  PROTECTED {prot_count:02d}"
        )

        for dev in sorted_devs:
            card = DeviceItemWidget(
                dev, selected=(dev.device_id == self._selected_device_id)
            )
            card.clicked.connect(self._select_device)
            card.protection_toggled.connect(self.protection_toggled.emit)
            card.alias_changed.connect(self.alias_changed.emit)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)
