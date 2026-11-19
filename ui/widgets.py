"""Obsidian Tactile HUD 시그니처 커스텀 위젯 모듈 (`DESIGN_SYSTEM.md` §6 준수).

- `make_vector_icon`: 1.5px 모노라인 벡터 아이콘 생성기 (`QPainter`)
- `ToggleSwitch` / `SettingToggleRow`: 음각(`#0D0E12`) 트랙 + 노브 중앙 발광 LED 토글 스위치
- `PhysicalKeycapBadge`: 음각 슬롯 내부 돌출 물리 키캡 배지 (240ms 트리거 발광)
- `PrecisionTickSlider`: 1px 미세 눈금(Tick Marks) 정밀 계측기 슬라이더
- `LedStatusPill`: 6px 발광 LED 점 + Monospace 텍스트 슬림 상태 배지
- `NavRailButton`: 3px 앰버 수직 인디케이터 + Monospace 인덱스 내비게이션 버튼
- `ShortcutRecorderDialog`: 단축키 실시간 녹화 대화상자
- `MonitorMinimapWidget`: 다중 모니터 및 창 배치 비율 2D 블루프린트 미니맵
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.window_orchestrator import LayoutPreset, MonitorInfo
from ui.theme import (
    ACCENT_AMBER,
    ACCENT_AMBER_BG,
    ACCENT_AMBER_BORDER,
    ACCENT_AMBER_GLOW,
    ACCENT_CYAN,
    ACCENT_CYAN_BG,
    BG_BASE,
    BG_HOVER,
    BG_INSET,
    BG_RAISED,
    BG_SURFACE,
    BORDER_BEVEL,
    BORDER_HAIRLINE,
    BORDER_INSET_BOTTOM,
    BORDER_INSET_TOP,
    BORDER_RAISED_SIDE,
    FONT_MONO,
    MINIMAP_PALETTE,
    STATUS_OK,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    inset_slot_qss,
    tactile_button_qss,
)

# ============================================================================
# 1. 1.5px 모노라인 벡터 아이콘 팩 (OS 이모지 배제)
# ============================================================================


def make_vector_icon(kind: str, color: str = TEXT_SECONDARY, size: int = 16) -> QIcon:
    """1.5px 선 두께의 미니멀 모노라인 벡터 아이콘을 동적 렌더링한다."""
    dpr = 2
    px = size * dpr
    pix = QPixmap(px, px)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(dpr, dpr)

    pen = QPen(
        QColor(color),
        1.45,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    m = 2.2

    if kind == "dial":
        p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))
        p.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.72, s * 0.28))
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 1.3, 1.3)
    elif kind == "keypad":
        step = (s - 2 * m) / 3.0
        for r in range(3):
            for c in range(3):
                p.drawRoundedRect(
                    QRectF(
                        m + c * step + 0.6,
                        m + r * step + 0.6,
                        step - 1.3,
                        step - 1.3,
                    ),
                    0.8,
                    0.8,
                )
    elif kind == "keyboard":
        p.drawRoundedRect(QRectF(1.6, s * 0.24, s - 3.2, s * 0.52), 1.6, 1.6)
        p.drawLine(QPointF(4.0, s * 0.44), QPointF(s - 4.0, s * 0.44))
        p.drawLine(QPointF(5.0, s * 0.60), QPointF(s - 5.0, s * 0.60))
    elif kind == "mouse":
        p.drawRoundedRect(QRectF(s * 0.26, 1.8, s * 0.48, s - 3.6), s * 0.24, s * 0.24)
        p.drawLine(QPointF(s * 0.5, 4.2), QPointF(s * 0.5, 7.0))
    elif kind == "shield":
        path = QPainterPath()
        path.moveTo(s * 0.5, 1.8)
        path.lineTo(s - 2.4, 4.2)
        path.lineTo(s - 2.8, s * 0.56)
        path.quadTo(s * 0.5, s - 1.4, s * 0.5, s - 1.4)
        path.quadTo(2.8, s * 0.78, 2.8, s * 0.56)
        path.lineTo(2.4, 4.2)
        path.closeSubpath()
        p.drawPath(path)
    elif kind in ("snapshot", "camera"):
        d = 3.2
        p.drawLine(QPointF(m, m), QPointF(m + d, m))
        p.drawLine(QPointF(m, m), QPointF(m, m + d))
        p.drawLine(QPointF(s - m, m), QPointF(s - m - d, m))
        p.drawLine(QPointF(s - m, m), QPointF(s - m, m + d))
        p.drawLine(QPointF(m, s - m), QPointF(m + d, s - m))
        p.drawLine(QPointF(m, s - m), QPointF(m, s - m - d))
        p.drawLine(QPointF(s - m, s - m), QPointF(s - m - d, s - m))
        p.drawLine(QPointF(s - m, s - m), QPointF(s - m, s - m - d))
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.2, 2.2)
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(1.8, 4.0)
        path.lineTo(6.2, 4.0)
        path.lineTo(7.6, 5.6)
        path.lineTo(s - 1.8, 5.6)
        path.lineTo(s - 1.8, s - 2.4)
        path.lineTo(1.8, s - 2.4)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "edit":
        p.drawLine(QPointF(3.2, s - 3.2), QPointF(s - 3.2, 3.2))
        p.drawLine(QPointF(s - 5.4, 2.6), QPointF(s - 2.6, 5.4))
    elif kind == "record":
        p.drawEllipse(QRectF(2.2, 2.2, s - 4.4, s - 4.4))
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.6, 2.6)
    elif kind == "workspace":
        p.drawRoundedRect(QRectF(1.6, 2.4, s * 0.52, s - 6.0), 1.2, 1.2)
        p.drawRoundedRect(QRectF(s * 0.52 + 2.4, 2.4, s * 0.34, s - 6.0), 1.2, 1.2)
        p.drawLine(QPointF(4.0, s - 1.8), QPointF(s - 4.0, s - 1.8))
    elif kind == "layers":
        p.drawPolygon(
            QPointF(s * 0.5, 2.2),
            QPointF(s - 2.0, s * 0.38),
            QPointF(s * 0.5, s * 0.56),
            QPointF(2.0, s * 0.38),
        )
        p.drawLine(QPointF(2.4, s * 0.62), QPointF(s * 0.5, s * 0.80))
        p.drawLine(QPointF(s * 0.5, s * 0.80), QPointF(s - 2.4, s * 0.62))
    elif kind == "matrix":
        half = (s - 2 * m - 2.0) / 2.0
        p.drawRoundedRect(QRectF(m, m, half, half), 1.0, 1.0)
        p.drawRoundedRect(QRectF(m + half + 2.0, m, half, half), 1.0, 1.0)
        p.drawRoundedRect(QRectF(m, m + half + 2.0, half, half), 1.0, 1.0)
        p.drawRoundedRect(QRectF(m + half + 2.0, m + half + 2.0, half, half), 1.0, 1.0)
    elif kind == "settings":
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.5, 2.5)
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 5.6, 5.6)
    elif kind == "book":
        p.drawRoundedRect(QRectF(2.8, 1.8, s - 5.6, s - 3.6), 1.2, 1.2)
        p.drawLine(QPointF(5.2, 5.6), QPointF(s - 5.2, 5.6))
        p.drawLine(QPointF(5.2, 8.4), QPointF(s - 5.2, 8.4))
        p.drawLine(QPointF(5.2, 11.2), QPointF(s - 7.0, 11.2))
    elif kind == "hub":
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.1, 2.1)
        for pt in (
            QPointF(s * 0.5, 2.4),
            QPointF(s - 2.4, s * 0.5),
            QPointF(s * 0.5, s - 2.4),
            QPointF(2.4, s * 0.5),
        ):
            p.drawLine(QPointF(s * 0.5, s * 0.5), pt)
            p.drawEllipse(pt, 1.1, 1.1)
    else:
        p.drawPolygon(
            QPointF(s * 0.5, m),
            QPointF(s - m, s * 0.5),
            QPointF(s * 0.5, s - m),
            QPointF(m, s * 0.5),
        )

    p.end()
    pix.setDevicePixelRatio(dpr)
    return QIcon(pix)


# ============================================================================
# 2. Tactile Toggle Switch (음각 트랙 + 노브 중앙 LED 발광 점)
# ============================================================================


class ToggleSwitch(QAbstractButton):
    """음각(#0D0E12) 트랙 내부를 원형 노브가 이동하며 ON 시 중앙 LED가 점등되는 토글 스위치."""

    def __init__(
        self,
        checked: bool = False,
        active_color: str = ACCENT_AMBER,
        width: int = 38,
        height: int = 19,
    ) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._active_color = QColor(active_color)
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, val: float) -> None:
        self._offset = val
        self.update()

    offset = pyqtProperty(float, fget=_get_offset, fset=_set_offset)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # type: ignore[override]
        super().setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        r = h / 2.0

        # 1) 음각 트랙 배경 (--bg-inset)
        track_rect = QRectF(0.75, 0.75, w - 1.5, h - 1.5)
        if self.isChecked():
            track_fill = QColor(self._active_color)
            track_fill.setAlpha(36)  # ~0.14 accent dim
            p.setBrush(QBrush(QColor(BG_INSET)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(track_rect, r - 0.75, r - 0.75)
            p.setBrush(QBrush(track_fill))
            p.setPen(QPen(self._active_color, 1.1))
            p.drawRoundedRect(track_rect, r - 0.75, r - 0.75)
        else:
            p.setBrush(QBrush(QColor(BG_INSET)))
            p.setPen(QPen(QColor(BORDER_HAIRLINE), 1.0))
            p.drawRoundedRect(track_rect, r - 0.75, r - 0.75)
            # 음각 상단 어두운 음영 힌트
            p.setPen(QPen(QColor(BORDER_INSET_TOP), 0.9))
            p.drawLine(QPointF(r, 1.2), QPointF(w - r, 1.2))

        # 2) 돌출 원형 노브
        margin = 2.8
        knob_d = h - 2.0 * margin
        knob_x = margin + self._offset * (w - 2.0 * margin - knob_d)
        knob_rect = QRectF(knob_x, margin, knob_d, knob_d)

        p.setBrush(QBrush(QColor(BG_RAISED if self.isChecked() else "#23262F")))
        p.setPen(
            QPen(
                QColor(BORDER_BEVEL if self.isChecked() else BORDER_HAIRLINE),
                1.0,
            )
        )
        p.drawEllipse(knob_rect)

        # 3) 노브 중앙 발광 LED 점
        center = knob_rect.center()
        if self.isChecked():
            glow = QColor(self._active_color)
            glow.setAlpha(90)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(center, knob_d * 0.30, knob_d * 0.30)
            p.setBrush(QBrush(self._active_color))
            p.drawEllipse(center, knob_d * 0.17, knob_d * 0.17)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(TEXT_MUTED)))
            p.drawEllipse(center, knob_d * 0.13, knob_d * 0.13)

        p.end()


class SettingToggleRow(QWidget):
    """라벨 + 음각 LED `ToggleSwitch` 한 줄 위젯 (`QCheckBox` 호환 API 제공)."""

    toggled = pyqtSignal(bool)

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        active_color: str = ACCENT_AMBER,
        label_color: str = TEXT_PRIMARY,
    ) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(12)

        self.label = QLabel(text)
        self.label.setStyleSheet(
            f"color: {label_color}; font-size: 11.5px; background: transparent; border: none;"
        )
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)

        self.switch = ToggleSwitch(checked=checked, active_color=active_color)
        self.switch.toggled.connect(self.toggled.emit)
        layout.addWidget(self.switch)

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.switch.setChecked(checked)

    def setText(self, text: str) -> None:
        self.label.setText(text)

    def blockSignals(self, block: bool) -> bool:  # type: ignore[override]
        self.switch.blockSignals(block)
        return super().blockSignals(block)


# ============================================================================
# 3. Physical Keycap Badge (Inset 슬롯 내부 Raised 키캡 + 240ms 트리거 발광)
# ============================================================================


class PhysicalKeycapBadge(QFrame):
    """음각 슬롯 내부에 놓인 돌출 물리 키캡 배지 (`DESIGN_SYSTEM.md` §6)."""

    def __init__(
        self,
        icon_kind: str,
        type_text: str,
        keycap_text: str,
        sub_text: str,
        accent_color: str = ACCENT_AMBER,
        tooltip: str = "",
    ) -> None:
        super().__init__()
        self._accent = accent_color
        self.setObjectName("KeycapInsetSlot")
        self.setFixedWidth(108)
        self.setStyleSheet(inset_slot_qss("KeycapInsetSlot", radius=4))

        slot_layout = QVBoxLayout(self)
        slot_layout.setContentsMargins(3, 3, 3, 3)
        slot_layout.setSpacing(0)

        self._cap = QFrame()
        self._cap.setObjectName("KeycapRaisedBody")
        cap_layout = QVBoxLayout(self._cap)
        cap_layout.setContentsMargins(6, 5, 6, 5)
        cap_layout.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)
        top_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(make_vector_icon(icon_kind, accent_color, 11).pixmap(QSize(11, 11)))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        top_row.addWidget(icon_lbl)

        type_lbl = QLabel(type_text)
        type_lbl.setStyleSheet(
            f"color: {accent_color}; border: none; background: transparent; "
            f"font-family: {FONT_MONO}; font-size: 8.5px; font-weight: 800; letter-spacing: 0.5px;"
        )
        top_row.addWidget(type_lbl)
        cap_layout.addLayout(top_row)

        self.keycap_label = QLabel(keycap_text)
        self.keycap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.keycap_label.setToolTip(tooltip or keycap_text)
        self.keycap_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; border: none; background: transparent; "
            f"font-family: {FONT_MONO}; font-size: 11.5px; font-weight: 800;"
        )
        cap_layout.addWidget(self.keycap_label)

        sub_lbl = QLabel(sub_text)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setToolTip(tooltip or sub_text)
        sub_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; border: none; background: transparent; "
            f"font-family: {FONT_MONO}; font-size: 8.5px;"
        )
        cap_layout.addWidget(sub_lbl)

        slot_layout.addWidget(self._cap)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._set_rest_style)
        self._set_rest_style()

    def _set_rest_style(self) -> None:
        self._cap.setStyleSheet(
            f"QFrame#KeycapRaisedBody {{ background-color: {BG_RAISED}; "
            f"border: 1px solid {BORDER_RAISED_SIDE}; border-top: 1px solid {BORDER_BEVEL}; "
            "border-radius: 4px; }"
        )

    def flash(self, color: str | None = None, duration_ms: int = 240) -> None:
        """입력 트리거 시 240ms 동안 키캡 테두리를 앰버/시안으로 점등 후 감쇠한다."""
        glow_hex = color or ACCENT_AMBER_GLOW
        self._cap.setStyleSheet(
            f"QFrame#KeycapRaisedBody {{ background-color: {BG_HOVER}; "
            f"border: 1px solid {glow_hex}; border-radius: 4px; }}"
        )
        self._flash_timer.start(duration_ms)


# ============================================================================
# 4. Precision Tick Slider (1px 미세 눈금 정밀 계측기 슬라이더)
# ============================================================================


class PrecisionTickSlider(QWidget):
    """음각 트랙 하단에 1px 미세 눈금(Tick Marks)이 각인된 정밀 계측기 슬라이더."""

    value_changed = pyqtSignal(float)

    def __init__(
        self,
        minimum: float = 0.5,
        maximum: float = 3.0,
        value: float = 1.0,
        step: float = 0.1,
        ticks: int = 11,
        accent_color: str = ACCENT_CYAN,
        unit: str = "x",
    ) -> None:
        super().__init__()
        self._min = float(minimum)
        self._max = max(float(maximum), self._min + 0.01)
        self._step = max(0.01, float(step))
        self._value = self._clamp(value)
        self._ticks = max(3, int(ticks))
        self._accent = QColor(accent_color)
        self._unit = unit
        self._dragging = False
        self.setMinimumHeight(28)
        self.setMinimumWidth(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _clamp(self, val: float) -> float:
        clamped = min(self._max, max(self._min, float(val)))
        snapped = round((clamped - self._min) / self._step) * self._step + self._min
        return round(min(self._max, max(self._min, snapped)), 2)

    def value(self) -> float:
        return self._value

    def setValue(self, val: float) -> None:
        new_val = self._clamp(val)
        if new_val != self._value:
            self._value = new_val
            self.update()
            self.value_changed.emit(self._value)

    def _pos_to_value(self, x: float) -> float:
        left = 8.0
        right = max(left + 10.0, self.width() - 44.0)
        ratio = min(1.0, max(0.0, (x - left) / (right - left)))
        return self._clamp(self._min + ratio * (self._max - self._min))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.setValue(self._pos_to_value(event.position().x()))
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging:
            self.setValue(self._pos_to_value(event.position().x()))
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._dragging = False
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        left = 8.0
        right = max(left + 16.0, w - 44.0)
        track_w = right - left
        track_y = 9.0
        track_h = 5.0
        ratio = (self._value - self._min) / (self._max - self._min)

        # 1) 음각 트랙
        p.setBrush(QBrush(QColor(BG_INSET)))
        p.setPen(QPen(QColor(BORDER_HAIRLINE), 1.0))
        p.drawRoundedRect(QRectF(left, track_y, track_w, track_h), 2.5, 2.5)

        # 활성 채움 바
        fill_w = max(0.0, track_w * ratio)
        if fill_w > 1.0:
            fill_col = QColor(self._accent)
            fill_col.setAlpha(180)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(fill_col))
            p.drawRoundedRect(QRectF(left + 0.5, track_y + 0.5, fill_w, track_h - 1.0), 2.0, 2.0)

        # 2) 하단 1px 미세 눈금 (Tick Marks)
        tick_top = track_y + track_h + 3.0
        for i in range(self._ticks):
            tx = left + (track_w * i / (self._ticks - 1))
            is_major = (i == 0) or (i == self._ticks - 1) or (i == self._ticks // 2)
            t_len = 5.0 if is_major else 3.0
            p.setPen(QPen(QColor(BORDER_BEVEL if is_major else BORDER_HAIRLINE), 1.0))
            p.drawLine(QPointF(tx, tick_top), QPointF(tx, tick_top + t_len))

        # 3) 돌출(Raised) 계측기 노브
        cx = left + fill_w
        knob_w, knob_h = 10.0, 14.0
        knob_rect = QRectF(cx - knob_w / 2.0, track_y + track_h / 2.0 - knob_h / 2.0, knob_w, knob_h)
        p.setBrush(QBrush(QColor(BG_RAISED)))
        p.setPen(QPen(QColor(BORDER_BEVEL), 1.0))
        p.drawRoundedRect(knob_rect, 2.0, 2.0)
        p.setPen(QPen(self._accent, 1.4))
        p.drawLine(QPointF(cx, knob_rect.top() + 3.0), QPointF(cx, knob_rect.bottom() - 3.0))

        # 4) 고정폭 수치 표시
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QColor(TEXT_PRIMARY))
        p.drawText(
            QRectF(right + 6.0, 0.0, 38.0, float(self.height())),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._value:.1f}{self._unit}",
        )
        p.end()


# ============================================================================
# 5. LED Status Pill (6px 발광 LED 점 + 고정폭 텍스트 슬림 배지)
# ============================================================================


class LedStatusPill(QFrame):
    """6px 발광 LED 점 + Monospace 텍스트로 구성된 슬림 상태 배지 (`DESIGN_SYSTEM.md` §6)."""

    def __init__(self, text: str = "", color: str = ACCENT_CYAN) -> None:
        super().__init__()
        self.setObjectName("LedStatusPill")
        self.setFixedHeight(26)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 0, 9, 0)
        layout.setSpacing(6)

        self.led = QLabel()
        self.led.setFixedSize(6, 6)
        layout.addWidget(self.led)

        self.text_label = QLabel(text)
        layout.addWidget(self.text_label)

        self.set_state(text, fg=color, bg=ACCENT_CYAN_BG, border=BORDER_HAIRLINE)

    def set_state(self, text: str, fg: str, bg: str, border: str) -> None:
        self.setStyleSheet(
            f"QFrame#LedStatusPill {{ background-color: {bg}; border: 1px solid {border}; border-radius: 4px; }}"
        )
        self.led.setStyleSheet(
            f"background-color: {fg}; border-radius: 3px; border: none;"
        )
        self.text_label.setText(text)
        self.text_label.setStyleSheet(
            f"color: {fg}; font-family: {FONT_MONO}; font-size: 10.5px; "
            "font-weight: 800; border: none; background: transparent;"
        )


# ============================================================================
# 6. Left Navigation Rail Button (3px Amber 수직 인디케이터 + Monospace 인덱스)
# ============================================================================


class NavRailButton(QPushButton):
    """좌측 내비게이션 레일 전용 버튼 (선택 시 좌측 3px 앰버 수직 바 + 앰버 틴트)."""

    def __init__(self, index_num: str, label: str, icon_kind: str) -> None:
        super().__init__()
        self._index_num = index_num
        self._icon_kind = icon_kind
        self.setCheckable(True)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(15, 15))
        self.set_label(label)
        self.apply_active_style(False)

    def set_label(self, label: str) -> None:
        self.setText(f"  {self._index_num}  {label}")

    def apply_active_style(self, active: bool) -> None:
        self.setIcon(
            make_vector_icon(
                self._icon_kind,
                ACCENT_AMBER_GLOW if active else TEXT_SECONDARY,
                15,
            )
        )
        if active:
            self.setStyleSheet(
                f"QPushButton {{ background-color: {ACCENT_AMBER_BG}; color: {TEXT_PRIMARY}; "
                f"border: 1px solid {ACCENT_AMBER_BORDER}; border-left: 3px solid {ACCENT_AMBER}; "
                f"border-radius: 4px; padding-left: 10px; text-align: left; "
                f"font-family: {FONT_MONO}; font-size: 11px; font-weight: 800; }}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ background-color: transparent; color: {TEXT_SECONDARY}; "
                "border: 1px solid transparent; border-left: 3px solid transparent; "
                "border-radius: 4px; padding-left: 10px; text-align: left; "
                f"font-family: {FONT_MONO}; font-size: 11px; font-weight: 600; }}"
                f"QPushButton:hover {{ background-color: {BG_HOVER}; color: {TEXT_PRIMARY}; }}"
            )


# ============================================================================
# 7. 단축키 입력 레코더 대화상자 (Shortcut Recorder)
# ============================================================================

_QT_KEY_NAMES: dict[int, str] = {
    Qt.Key.Key_Return: "Enter",
    Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Escape: "Esc",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PgUp",
    Qt.Key.Key_PageDown: "PgDn",
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Down: "Down",
}
for _i in range(1, 25):
    _QT_KEY_NAMES[getattr(Qt.Key, f"Key_F{_i}")] = f"F{_i}"


def qt_key_event_to_combo(event: QKeyEvent) -> str:
    """`QKeyEvent`를 `ActionExecutor` 호환 단축키 문자열(`Ctrl+Shift+S` 등)로 변환한다."""
    key = event.key()
    if key in (
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
        Qt.Key.Key_unknown,
    ):
        return ""

    mods = event.modifiers()
    tokens: list[str] = []
    if mods & Qt.KeyboardModifier.ControlModifier:
        tokens.append("Ctrl")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        tokens.append("Shift")
    if mods & Qt.KeyboardModifier.AltModifier:
        tokens.append("Alt")
    if mods & Qt.KeyboardModifier.MetaModifier:
        tokens.append("Win")

    if key in _QT_KEY_NAMES:
        tokens.append(_QT_KEY_NAMES[key])
    elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        tokens.append(chr(key))
    elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        tokens.append(chr(key))
    else:
        txt = event.text().strip().upper()
        if len(txt) == 1 and txt.isprintable():
            tokens.append(txt)
        else:
            return ""

    return "+".join(tokens)


class ShortcutRecorderDialog(QDialog):
    """사용자가 실제 키 조합을 한 번 눌러 단축키를 즉시 녹화하는 대화상자."""

    def __init__(self, initial_combo: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.recorded_combo: str = initial_combo
        self.setWindowTitle("단축키 녹화 (Shortcut Recorder)")
        self.setFixedSize(368, 172)
        self.setStyleSheet(
            f"QDialog {{ background-color: {BG_SURFACE}; border: 1px solid {BORDER_HAIRLINE}; border-radius: 8px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hint = QLabel("원하는 단축키 조합을 누르세요 (예: Ctrl + Shift + S)")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self.preview_lbl = QLabel(initial_combo or "키 입력 대기 중...")
        self.preview_lbl.setFixedHeight(44)
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet(
            f"background-color: {BG_INSET}; color: {ACCENT_AMBER_GLOW}; "
            f"border: 1px dashed {ACCENT_AMBER}; border-radius: 4px; "
            f"font-family: {FONT_MONO}; font-size: 15px; font-weight: 800;"
        )
        layout.addWidget(self.preview_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(28)
        cancel_btn.setStyleSheet(tactile_button_qss("default", padding="0 14px"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("적용")
        ok_btn.setFixedHeight(28)
        ok_btn.setStyleSheet(tactile_button_qss("amber_solid", padding="0 16px"))
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        combo = qt_key_event_to_combo(event)
        if combo:
            self.recorded_combo = combo
            self.preview_lbl.setText(combo)
            event.accept()
            return
        super().keyPressEvent(event)


# ============================================================================
# 8. 다중 모니터 창 배치 2D 아키텍처 블루프린트 미니맵 위젯
# ============================================================================


class MonitorMinimapWidget(QWidget):
    """모니터 토폴로지와 프리셋 창 비율(0.0 ~ 1.0)을 실시간 그리는 2D 제도판 미니맵."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(188)
        self._monitors: list[MonitorInfo] = []
        self._preset: LayoutPreset | None = None

    def set_data(
        self, monitors: list[MonitorInfo], preset: LayoutPreset | None
    ) -> None:
        self._monitors = list(monitors)
        self._preset = preset
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        # 음각(#0D0E12) 제도판 배경 + 미세 1px 격자
        p.fillRect(rect, QColor(BG_INSET))
        grid_pen = QPen(QColor("#181A22"), 1.0)
        p.setPen(grid_pen)
        step = 16
        for gx in range(step, rect.width(), step):
            p.drawLine(gx, 0, gx, rect.height())
        for gy in range(step, rect.height(), step):
            p.drawLine(0, gy, rect.width(), gy)

        # 외곽 음각 1px 헤어라인
        p.setPen(QPen(QColor(BORDER_HAIRLINE), 1.0))
        p.drawRoundedRect(QRectF(0.5, 0.5, rect.width() - 1.0, rect.height() - 1.0), 4, 4)

        if not self._monitors:
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 9))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "TOPOLOGY STANDBY")
            p.end()
            return

        min_x = min(m.monitor_rect[0] for m in self._monitors)
        min_y = min(m.monitor_rect[1] for m in self._monitors)
        max_x = max(m.monitor_rect[2] for m in self._monitors)
        max_y = max(m.monitor_rect[3] for m in self._monitors)
        span_w = max(1, max_x - min_x)
        span_h = max(1, max_y - min_y)

        pad_x, pad_y = 16.0, 22.0
        avail_w = max(40.0, rect.width() - 2 * pad_x)
        avail_h = max(40.0, rect.height() - 2 * pad_y)
        scale = min(avail_w / span_w, avail_h / span_h)

        draw_w = span_w * scale
        draw_h = span_h * scale
        origin_x = (rect.width() - draw_w) / 2.0
        origin_y = (rect.height() - draw_h) / 2.0

        def _to_canvas(x: float, y: float, w: float, h: float) -> QRectF:
            return QRectF(
                origin_x + (x - min_x) * scale,
                origin_y + (y - min_y) * scale,
                max(2.0, w * scale),
                max(2.0, h * scale),
            )

        font_small = QFont("Consolas", 8)
        font_win = QFont("Consolas", 8, QFont.Weight.Bold)

        # 1) 모니터 베젤 및 rcWork 영역 렌더링
        for m in self._monitors:
            ml, mt, mr, mb = m.monitor_rect
            m_rect = _to_canvas(ml, mt, mr - ml, mb - mt)
            p.setPen(QPen(QColor(BORDER_BEVEL if m.is_primary else BORDER_HAIRLINE), 1.2))
            p.setBrush(QColor(BG_SURFACE))
            p.drawRoundedRect(m_rect, 4, 4)

            wl, wt, wr, wb = m.work_rect
            w_rect = _to_canvas(wl, wt, wr - wl, wb - wt)
            p.setPen(QPen(QColor("#232630"), 0.8, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(w_rect)

            p.setFont(font_small)
            p.setPen(QColor(TEXT_MUTED))
            label = f"M{m.index} · {m.width}×{m.height} ({m.scale_percent}%)"
            p.drawText(
                QRectF(m_rect.left() + 4, m_rect.top() - 15, m_rect.width(), 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        # 2) 선택 프리셋의 창 비율 블록 렌더링
        if self._preset is not None:
            focus_low = self._preset.focus_process.strip().lower()
            for idx, spec in enumerate(self._preset.placements):
                mon = self._monitors[min(max(0, spec.monitor_index), len(self._monitors) - 1)]
                wl, wt, wr, wb = mon.work_rect
                ww = max(1, wr - wl)
                wh = max(1, wb - wt)
                px_x = wl + spec.x_ratio * ww
                px_y = wt + spec.y_ratio * wh
                px_w = spec.w_ratio * ww
                px_h = spec.h_ratio * wh

                win_rect = _to_canvas(px_x, px_y, px_w, px_h).adjusted(1.5, 1.5, -1.5, -1.5)
                is_focus = bool(focus_low and spec.process_name.lower() == focus_low)
                color_hex = (
                    ACCENT_AMBER_GLOW
                    if is_focus
                    else MINIMAP_PALETTE[idx % len(MINIMAP_PALETTE)]
                )

                fill_col = QColor(color_hex)
                fill_col.setAlpha(56 if is_focus else 32)
                p.setBrush(fill_col)
                p.setPen(QPen(QColor(color_hex), 1.5 if is_focus else 1.0))
                p.drawRoundedRect(win_rect, 3, 3)

                p.setFont(font_win)
                p.setPen(QColor(TEXT_PRIMARY))
                short_name = spec.process_name.replace(".exe", "")
                if is_focus:
                    short_name = f"★ {short_name}"
                p.drawText(
                    win_rect.adjusted(4, 2, -4, -2),
                    Qt.AlignmentFlag.AlignCenter,
                    short_name,
                )

        p.end()
