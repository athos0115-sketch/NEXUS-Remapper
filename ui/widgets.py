"""Precision Architectural HUD 커스텀 위젯 모듈.

- `make_vector_icon`: 1.5px 모노라인 벡터 아이콘 생성기 (`QPainter`, 외부 파일 불필요)
- `ToggleSwitch` / `SettingToggleRow`: 슬라이드 애니메이션 Pill 토글 스위치
- `ShortcutRecorderDialog`: 키 조합 실시간 녹화(Key Combo Recorder) 대화상자
- `MonitorMinimapWidget`: 듀얼/다중 모니터 및 창 배치 비율 2D 아키텍처 미니맵
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QKeyEvent, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.window_orchestrator import LayoutPreset, MonitorInfo
from ui.theme import (
    ACCENT_CYAN,
    ACCENT_ORANGE,
    ACCENT_PURPLE,
    BG_CARD,
    BG_INPUT,
    BORDER_HAIRLINE,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

# ============================================================================
# 1.5px 모노라인 벡터 아이콘 팩 (OS 이모지 완전 대체)
# ============================================================================


def make_vector_icon(kind: str, color: str = "#94A3B8", size: int = 16) -> QIcon:
    """1.5px 선 두께의 미니멀 모노라인 벡터 아이콘을 동적 렌더링한다."""
    dpr = 2
    px = size * dpr
    pix = QPixmap(px, px)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(dpr, dpr)

    pen = QPen(QColor(color), 1.45, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
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
                    QRectF(m + c * step + 0.6, m + r * step + 0.6, step - 1.3, step - 1.3),
                    0.8,
                    0.8,
                )
    elif kind == "keyboard":
        p.drawRoundedRect(QRectF(1.6, s * 0.24, s - 3.2, s * 0.52), 1.8, 1.8)
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
        # 정밀 뷰파인더 프레임 + 중앙 타깃
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
        p.drawRoundedRect(QRectF(m, m, half, half), 1.2, 1.2)
        p.drawRoundedRect(QRectF(m + half + 2.0, m, half, half), 1.2, 1.2)
        p.drawRoundedRect(QRectF(m, m + half + 2.0, half, half), 1.2, 1.2)
        p.drawRoundedRect(QRectF(m + half + 2.0, m + half + 2.0, half, half), 1.2, 1.2)
    elif kind == "settings":
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.5, 2.5)
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 5.6, 5.6)
    elif kind == "book":
        p.drawRoundedRect(QRectF(2.8, 1.8, s - 5.6, s - 3.6), 1.4, 1.4)
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
# 슬라이드 애니메이션 Pill 토글 스위치
# ============================================================================


class ToggleSwitch(QAbstractButton):
    """부드럽게 슬라이딩하는 Architectural HUD Pill 토글 스위치."""

    def __init__(
        self,
        checked: bool = False,
        active_color: str = ACCENT_CYAN,
        width: int = 36,
        height: int = 18,
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

        w, h = self.width(), self.height()
        r = h / 2.0

        # 트랙 배경 & 보더
        if self.isChecked():
            track_bg = QColor(self._active_color)
            track_bg.setAlpha(42)
            track_border = self._active_color
            knob_color = self._active_color
        else:
            track_bg = QColor("#15151B")
            track_border = QColor("#32323E")
            knob_color = QColor("#64748B")

        p.setPen(QPen(track_border, 1.2))
        p.setBrush(QBrush(track_bg))
        p.drawRoundedRect(QRectF(0.8, 0.8, w - 1.6, h - 1.6), r - 0.8, r - 0.8)

        # 슬라이드 노브
        margin = 3.0
        knob_d = h - 2 * margin
        knob_x = margin + self._offset * (w - 2 * margin - knob_d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(knob_color))
        p.drawEllipse(QRectF(knob_x, margin, knob_d, knob_d))
        p.end()


class SettingToggleRow(QWidget):
    """라벨 + 슬라이드 `ToggleSwitch` 한 줄 위젯 (`QCheckBox` 호환 API 제공)."""

    toggled = pyqtSignal(bool)

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        active_color: str = ACCENT_CYAN,
        label_color: str = TEXT_PRIMARY,
    ) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 3, 2, 3)
        layout.setSpacing(12)

        self.label = QLabel(text)
        self.label.setStyleSheet(f"color: {label_color}; font-size: 11.5px;")
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
# 단축키 입력 레코더 대화상자 (Shortcut Recorder)
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
        self.setFixedSize(360, 168)
        self.setStyleSheet(
            f"QDialog {{ background-color: {BG_CARD}; border: 1px solid {BORDER_HAIRLINE}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        hint = QLabel("원하는 단축키 조합을 누르세요 (예: Ctrl + Shift + S)")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self.preview_lbl = QLabel(initial_combo or "키 입력 대기 중...")
        self.preview_lbl.setFixedHeight(44)
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet(
            f"background-color: {BG_INPUT}; color: {ACCENT_CYAN}; "
            f"border: 1px dashed {ACCENT_CYAN}; border-radius: 7px; "
            "font-family: 'Consolas', monospace; font-size: 15px; font-weight: 800;"
        )
        layout.addWidget(self.preview_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(28)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_INPUT}; color: {TEXT_SECONDARY}; "
            f"border: 1px solid {BORDER_HAIRLINE}; border-radius: 5px; padding: 0 14px; }}"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("적용")
        ok_btn.setFixedHeight(28)
        ok_btn.setStyleSheet(
            f"QPushButton {{ background: #0B2A26; color: {ACCENT_CYAN}; "
            f"border: 1px solid {ACCENT_CYAN}; border-radius: 5px; padding: 0 16px; font-weight: 700; }}"
        )
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
# 다중 모니터 창 배치 2D 아키텍처 미니맵 위젯
# ============================================================================

_WINDOW_PALETTE: tuple[str, ...] = (
    ACCENT_CYAN,
    ACCENT_PURPLE,
    ACCENT_ORANGE,
    "#38BDF8",
    "#34D399",
    "#F472B6",
)


class MonitorMinimapWidget(QWidget):
    """모니터 토폴로지와 프리셋 창 비율(0.0 ~ 1.0)을 실시간 그리는 2D Blueprint 미니맵."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(185)
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
        # Blueprint 다크 배경 + 미세 격자
        p.fillRect(rect, QColor("#0B0B0F"))
        grid_pen = QPen(QColor("#171720"), 1.0)
        p.setPen(grid_pen)
        step = 18
        for gx in range(step, rect.width(), step):
            p.drawLine(gx, 0, gx, rect.height())
        for gy in range(step, rect.height(), step):
            p.drawLine(0, gy, rect.width(), gy)

        # 외곽 1px 헤어라인
        p.setPen(QPen(QColor(BORDER_HAIRLINE), 1.0))
        p.drawRoundedRect(QRectF(0.5, 0.5, rect.width() - 1.0, rect.height() - 1.0), 7, 7)

        if not self._monitors:
            p.setPen(QColor(TEXT_MUTED))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "모니터 토폴로지 대기 중")
            p.end()
            return

        # 전체 가상 데스크톱 경계 계산
        min_x = min(m.monitor_rect[0] for m in self._monitors)
        min_y = min(m.monitor_rect[1] for m in self._monitors)
        max_x = max(m.monitor_rect[2] for m in self._monitors)
        max_y = max(m.monitor_rect[3] for m in self._monitors)
        span_w = max(1, max_x - min_x)
        span_h = max(1, max_y - min_y)

        pad_x, pad_y = 18.0, 22.0
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
        font_win = QFont("Segoe UI", 8, QFont.Weight.DemiBold)

        # 1) 모니터 베젤 및 rcWork 렌더링
        for m in self._monitors:
            ml, mt, mr, mb = m.monitor_rect
            m_rect = _to_canvas(ml, mt, mr - ml, mb - mt)
            p.setPen(QPen(QColor("#363646" if m.is_primary else "#282834"), 1.2))
            p.setBrush(QColor("#13131A"))
            p.drawRoundedRect(m_rect, 4, 4)

            wl, wt, wr, wb = m.work_rect
            w_rect = _to_canvas(wl, wt, wr - wl, wb - wt)
            p.setPen(QPen(QColor("#1F1F29"), 0.8, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(w_rect)

            p.setFont(font_small)
            p.setPen(QColor(TEXT_MUTED))
            label = f"M{m.index} · {m.width}x{m.height} ({m.scale_percent}%)"
            p.drawText(
                QRectF(m_rect.left() + 4, m_rect.top() - 14, m_rect.width(), 13),
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
                color_hex = ACCENT_CYAN if is_focus else _WINDOW_PALETTE[idx % len(_WINDOW_PALETTE)]

                fill_col = QColor(color_hex)
                fill_col.setAlpha(58 if is_focus else 36)
                p.setBrush(fill_col)
                p.setPen(QPen(QColor(color_hex), 1.6 if is_focus else 1.0))
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
