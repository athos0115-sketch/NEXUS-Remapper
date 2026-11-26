"""Darkroom Filament v1.1 커스텀 QPainter 위젯 모듈.

`QSS`(`ui/theme.py` `build_qss()`)와 `QPainter` 렌더링을 엄격히 분리한다:
- Qt 위젯 드롭 섀도우 이펙트 및 컴포넌트 내 인라인 `setStyleSheet` 사용 금지
- `snap_border_rect` 물리 픽셀 스냅 1px 스페큘러 보더
- `EmberCoreDot`: 3200ms 미세 호흡 광학 도트 + Thermal Load 연동 (`Gold → Orange → Red`)
- `DarkroomSurfaceCard`: 상단 `⌘K` 커맨드 바 & 활성 메인 카드 최대 2곳에만 허용되는 `1px Warm Rim-Light`
- `ToggleSwitch` / `SettingToggleRow`: Darkroom 알약형 토글 (`42×24px`, `160ms OutQuart`)
- `PrecisionTickSlider`: 1px 미세 눈금 필라멘트 슬라이더
- `LayerCreateDialog` / `ProcessLayerConflictDialog` / `ShortcutRecorderDialog`
- `MonitorMinimapWidget`: 92% 무채색 + 8% 필라멘트 2D 모니터 배치 미니맵
"""

from __future__ import annotations

import math

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core.config_store import TRIGGER_MODE_FOCUS, TRIGGER_MODE_PROCESS
from core.window_orchestrator import LayoutPreset, MonitorInfo
from ui.i18n import tr
from ui.theme import (
    MOTION_ENABLED,
    RIM_CLAMP_MAX,
    RIM_CLAMP_MIN,
    TOKENS,
    float_token,
    font_for,
    ms_int,
    px_int,
    qcolor,
    repolish,
    thermal_color_for_load,
)


def snap_border_rect(rect: QRectF, dpr: float = 1.0) -> QRectF:
    """논리 좌표를 물리 픽셀 0.5px 경계에 스냅해 레티나/고DPI 흐림을 방지한다."""
    step = 0.5 / max(1.0, float(dpr))
    return rect.adjusted(step, step, -step, -step)


# ============================================================================
# 1. 1.4px 모노라인 벡터 아이콘 팩 (동일 선 두께 & 역할 색상)
# ============================================================================


def make_vector_icon(
    kind: str, color_token: str = "--text-secondary", size: int = 16
) -> QIcon:
    """1.4px 선 두께의 미니멀 모노라인 벡터 아이콘을 동적 렌더링한다."""
    dpr = 2
    px = size * dpr
    pix = QPixmap(px, px)
    pix.fill(Qt.GlobalColor.transparent)

    col = qcolor(color_token) if color_token in TOKENS else QColor(color_token)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(dpr, dpr)

    pen = QPen(
        col,
        1.4,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    m = 2.4

    if kind == "dial":
        p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))
        p.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.72, s * 0.28))
        p.setBrush(col)
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 1.2, 1.2)
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
        p.drawRoundedRect(QRectF(1.8, s * 0.25, s - 3.6, s * 0.50), 1.6, 1.6)
        p.drawLine(QPointF(4.0, s * 0.44), QPointF(s - 4.0, s * 0.44))
        p.drawLine(QPointF(5.0, s * 0.58), QPointF(s - 5.0, s * 0.58))
    elif kind == "mouse":
        p.drawRoundedRect(QRectF(s * 0.27, 2.0, s * 0.46, s - 4.0), s * 0.23, s * 0.23)
        p.drawLine(QPointF(s * 0.5, 4.4), QPointF(s * 0.5, 7.2))
    elif kind == "shield":
        path = QPainterPath()
        path.moveTo(s * 0.5, 2.0)
        path.lineTo(s - 2.6, 4.2)
        path.lineTo(s - 3.0, s * 0.56)
        path.quadTo(s * 0.5, s - 1.6, s * 0.5, s - 1.6)
        path.quadTo(3.0, s * 0.78, 3.0, s * 0.56)
        path.lineTo(2.6, 4.2)
        path.closeSubpath()
        p.drawPath(path)
    elif kind in ("snapshot", "camera"):
        d = 3.0
        p.drawLine(QPointF(m, m), QPointF(m + d, m))
        p.drawLine(QPointF(m, m), QPointF(m, m + d))
        p.drawLine(QPointF(s - m, m), QPointF(s - m - d, m))
        p.drawLine(QPointF(s - m, m), QPointF(s - m, m + d))
        p.drawLine(QPointF(m, s - m), QPointF(m + d, s - m))
        p.drawLine(QPointF(m, s - m), QPointF(m, s - m - d))
        p.drawLine(QPointF(s - m, s - m), QPointF(s - m - d, s - m))
        p.drawLine(QPointF(s - m, s - m), QPointF(s - m, s - m - d))
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.0, 2.0)
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(2.0, 4.2)
        path.lineTo(6.2, 4.2)
        path.lineTo(7.6, 5.6)
        path.lineTo(s - 2.0, 5.6)
        path.lineTo(s - 2.0, s - 2.4)
        path.lineTo(2.0, s - 2.4)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "edit":
        p.drawLine(QPointF(3.4, s - 3.4), QPointF(s - 3.4, 3.4))
        p.drawLine(QPointF(s - 5.4, 2.8), QPointF(s - 2.8, 5.4))
    elif kind == "record":
        p.drawEllipse(QRectF(2.4, 2.4, s - 4.8, s - 4.8))
        p.setBrush(col)
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.4, 2.4)
    elif kind == "workspace":
        p.drawRoundedRect(QRectF(1.8, 2.6, s * 0.50, s - 6.2), 1.2, 1.2)
        p.drawRoundedRect(QRectF(s * 0.50 + 2.6, 2.6, s * 0.32, s - 6.2), 1.2, 1.2)
        p.drawLine(QPointF(4.2, s - 2.0), QPointF(s - 4.2, s - 2.0))
    elif kind == "layers":
        p.drawPolygon(
            QPointF(s * 0.5, 2.4),
            QPointF(s - 2.2, s * 0.39),
            QPointF(s * 0.5, s * 0.56),
            QPointF(2.2, s * 0.39),
        )
        p.drawLine(QPointF(2.6, s * 0.62), QPointF(s * 0.5, s * 0.79))
        p.drawLine(QPointF(s * 0.5, s * 0.79), QPointF(s - 2.6, s * 0.62))
    elif kind == "matrix":
        half = (s - 2 * m - 2.0) / 2.0
        p.drawRoundedRect(QRectF(m, m, half, half), 1.1, 1.1)
        p.drawRoundedRect(QRectF(m + half + 2.0, m, half, half), 1.1, 1.1)
        p.drawRoundedRect(QRectF(m, m + half + 2.0, half, half), 1.1, 1.1)
        p.drawRoundedRect(QRectF(m + half + 2.0, m + half + 2.0, half, half), 1.1, 1.1)
    elif kind == "settings":
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.3, 2.3)
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 5.3, 5.3)
    elif kind == "book":
        p.drawRoundedRect(QRectF(3.0, 2.0, s - 6.0, s - 4.0), 1.2, 1.2)
        p.drawLine(QPointF(5.2, 5.6), QPointF(s - 5.2, 5.6))
        p.drawLine(QPointF(5.2, 8.4), QPointF(s - 5.2, 8.4))
        p.drawLine(QPointF(5.2, 11.2), QPointF(s - 7.0, 11.2))
    elif kind == "hub":
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), 2.0, 2.0)
        for pt in (
            QPointF(s * 0.5, 2.6),
            QPointF(s - 2.6, s * 0.5),
            QPointF(s * 0.5, s - 2.6),
            QPointF(2.6, s * 0.5),
        ):
            p.drawLine(QPointF(s * 0.5, s * 0.5), pt)
            p.drawEllipse(pt, 1.0, 1.0)
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
# 2. Ember Core Dot (3200ms 미세 호흡 광학 도트 & 열 색온도 연동)
# ============================================================================


class EmberCoreDot(QWidget):
    """중심 웜 아이보리(`--ember-core`) + 외곽 열 헤일로가 은은히 호흡하는 시그니처 광학 도트."""

    def __init__(
        self,
        live: bool = True,
        tone: str = "orange",
        size: int = 16,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._live = live
        self._tone = tone  # "gold" | "orange" | "red" | "muted"
        self._phase = 0.0

        self._breath_anim = QVariantAnimation(self)
        self._breath_anim.setStartValue(0.0)
        self._breath_anim.setEndValue(2.0 * math.pi)
        self._breath_anim.setDuration(max(800, ms_int("--motion-breath") or 3200))
        self._breath_anim.setLoopCount(-1)
        self._breath_anim.valueChanged.connect(self._on_breath_tick)
        self._sync_animation()

    def _on_breath_tick(self, value: object) -> None:
        self._phase = float(value)  # type: ignore[arg-type]
        self.update()

    def _sync_animation(self) -> None:
        if self._live and MOTION_ENABLED and self._tone != "muted":
            if self._breath_anim.state() != QVariantAnimation.State.Running:
                self._breath_anim.start()
        else:
            if self._breath_anim.state() == QVariantAnimation.State.Running:
                self._breath_anim.stop()
            self._phase = 0.0
        self.update()

    def set_state(self, live: bool, tone: str = "orange") -> None:
        self._live = live
        self._tone = tone
        self._sync_animation()

    def set_thermal_load(self, load: float, live: bool = True) -> None:
        clamped = max(0.0, min(1.0, float(load)))
        tone = "gold" if clamped < 0.40 else ("orange" if clamped < 0.72 else "red")
        self.set_state(live=live, tone=tone)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0

        if self._tone == "muted":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor("--text-disabled"))
            p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)
            p.end()
            return

        outer_token = {
            "gold": "--filament-gold",
            "orange": "--filament-orange",
            "red": "--filament-red",
        }.get(self._tone, "--filament-orange")
        outer_col = qcolor(outer_token)
        core_col = qcolor("--ember-core")

        # 외곽 헤일로만 사인파 호흡 (0.55 <-> 0.95)
        breath = 0.75 + 0.20 * math.sin(self._phase) if (self._live and MOTION_ENABLED) else 0.75
        halo_r = min(cx, cy) * (0.94 + 0.06 * math.sin(self._phase) if self._live else 0.96)

        halo_grad = QRadialGradient(QPointF(cx, cy), halo_r)
        c0 = QColor(core_col)
        c0.setAlphaF(0.60 * breath)
        c1 = QColor(outer_col)
        c1.setAlphaF(0.45 * breath)
        c2 = QColor(outer_col)
        c2.setAlphaF(0.0)
        halo_grad.setColorAt(0.0, c0)
        halo_grad.setColorAt(0.38, c1)
        halo_grad.setColorAt(1.0, c2)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo_grad))
        p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        core_r = 3.2
        core_grad = QRadialGradient(QPointF(cx, cy), core_r)
        core_grad.setColorAt(0.0, core_col)
        core_grad.setColorAt(1.0, outer_col)
        p.setBrush(QBrush(core_grad))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)
        p.end()


# ============================================================================
# 3. Darkroom Surface Card (최대 2곳에만 1px Warm Rim-Light 허용)
# ============================================================================


class DarkroomSurfaceCard(QFrame):
    """Darkroom Filament 카드 컨테이너 (`warm_rim=True` 시 1px 상단 림라이트 커서 추적)."""

    def __init__(
        self,
        warm_rim: bool = False,
        radius_token: str = "--radius-card",
        bg_token: str = "--bg-surface",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._warm_rim = warm_rim
        self._radius = px_int(radius_token)
        self._bg_token = bg_token
        self._rim_center = float_token("--rim-center-default")
        self._rim_target = self._rim_center
        self._thermal_load = 0.35
        self._hovered = False

        if self._warm_rim:
            self.setMouseTracking(True)

        self._rim_anim = QVariantAnimation(self)
        self._rim_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._rim_anim.valueChanged.connect(self._on_rim_step)

    def _on_rim_step(self, val: object) -> None:
        self._rim_center = float(val)  # type: ignore[arg-type]
        self.update()

    def set_thermal_load(self, load: float) -> None:
        self._thermal_load = max(0.0, min(1.0, float(load)))
        self.update()

    def set_warm_rim(self, enabled: bool) -> None:
        self._warm_rim = enabled
        self.setMouseTracking(enabled)
        self.update()

    def _animate_rim_to(self, target: float, duration_token: str) -> None:
        dur = ms_int(duration_token)
        self._rim_target = max(RIM_CLAMP_MIN, min(RIM_CLAMP_MAX, target))
        if dur <= 0:
            self._rim_center = self._rim_target
            self.update()
            return
        self._rim_anim.stop()
        self._rim_anim.setDuration(dur)
        self._rim_anim.setStartValue(self._rim_center)
        self._rim_anim.setEndValue(self._rim_target)
        self._rim_anim.start()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._warm_rim and self.width() > 0:
            norm_x = event.position().x() / float(self.width())
            self._hovered = True
            self._animate_rim_to(norm_x, "--motion-rim-track")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        if self._warm_rim:
            self._animate_rim_to(float_token("--rim-center-default"), "--motion-rim-decay")
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dpr = self.devicePixelRatioF()
        rect = snap_border_rect(QRectF(self.rect()), dpr)
        r = min(float(self._radius), rect.width() * 0.5, rect.height() * 0.5)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(self._bg_token))
        p.drawRoundedRect(rect, r, r)

        # 스페큘러 헤어라인 외곽선
        spec_pen = QPen(qcolor("--border-specular"), 1.0)
        p.setPen(spec_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, r, r)

        # 1px Warm Rim-Light (상단 경계 + 24px 웜 워시 — 최대 2곳 제한)
        if self._warm_rim:
            p.save()
            clip_path = QPainterPath()
            clip_path.addRoundedRect(rect, r, r)
            p.setClipPath(clip_path)

            wash_grad = QLinearGradient(0.0, rect.top(), 0.0, rect.top() + 24.0)
            wash_grad.setColorAt(0.0, qcolor("--rim-wash"))
            wash_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 24.0), wash_grad)
            p.restore()

            mid_col = (
                qcolor("--rim-red")
                if self._thermal_load >= 0.72
                else qcolor("--rim-orange")
            )
            c = max(RIM_CLAMP_MIN, min(RIM_CLAMP_MAX, self._rim_center))
            left_s = max(0.0, c - 0.24)
            right_s = min(1.0, c + 0.28)
            x0 = rect.left() + max(2.0, r * 0.85)
            x1 = rect.right() - max(2.0, r * 0.85)
            if x1 > x0:
                rim_grad = QLinearGradient(x0, rect.top(), x1, rect.top())
                rim_grad.setColorAt(0.0, qcolor("--border-specular"))
                if left_s > 0.02:
                    rim_grad.setColorAt(left_s, mid_col)
                rim_grad.setColorAt(c, qcolor("--rim-gold"))
                if right_s < 0.98:
                    rim_grad.setColorAt(right_s, mid_col)
                rim_grad.setColorAt(1.0, qcolor("--border-specular"))

                p.setPen(QPen(QBrush(rim_grad), 1.0))
                p.drawLine(QPointF(x0, rect.top()), QPointF(x1, rect.top()))
        p.end()


# ============================================================================
# 4. Darkroom Mapped Rule Card (QPainter 보더 + 240ms 트리거 점등, 그림자 효과 금지)
# ============================================================================


class DarkroomGlowCard(QFrame):
    """`MappingCardWidget` 베이스: 기본 1px 스페큘러 보더, 트리거 시 1px 열 필라멘트 점등."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent_color: QColor | None = None
        self._hovered = False

    def set_glow_accent(self, color: str | None) -> None:
        self._accent_color = QColor(color) if color else None
        self.update()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dpr = self.devicePixelRatioF()
        rect = snap_border_rect(QRectF(self.rect()), dpr)
        r = float(px_int("--radius-item"))

        if self._accent_color is not None:
            bg = qcolor("--bg-elevated")
            border_col = self._accent_color
        elif self._hovered:
            bg = qcolor("--bg-elevated")
            border_col = qcolor("--border-specular-strong")
        else:
            bg = qcolor("--bg-surface")
            border_col = qcolor("--border-specular")

        p.setBrush(bg)
        p.setPen(QPen(border_col, 1.0))
        p.drawRoundedRect(rect, r, r)
        p.end()


# ============================================================================
# 5. Darkroom Toggle Switch (`42×24px` 알약형 트랙 + 160ms OutQuart 슬라이드)
# ============================================================================


class ToggleSwitch(QAbstractButton):
    """Darkroom Filament 알약형 토글 스위치 (bg-deep OFF / Solar Orange ON)."""

    def __init__(
        self,
        checked: bool = False,
        active_color: str = TOKENS["--filament-orange"],
        width: int = 42,
        height: int = 24,
    ) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._active_color = (
            qcolor(active_color) if active_color in TOKENS else QColor(active_color)
        )
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(ms_int("--motion-base") or 160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuart)
        self.toggled.connect(self._animate)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, val: float) -> None:
        self._offset = val
        self.update()

    offset = pyqtProperty(float, fget=_get_offset, fset=_set_offset)

    def _animate(self, checked: bool) -> None:
        dur = ms_int("--motion-base")
        if dur <= 0:
            self._offset = 1.0 if checked else 0.0
            self.update()
            return
        self._anim.stop()
        self._anim.setDuration(dur)
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
        dpr = self.devicePixelRatioF()
        rect = snap_border_rect(QRectF(self.rect()), dpr)
        r = rect.height() / 2.0

        if not self.isEnabled():
            p.setBrush(qcolor("--bg-inset"))
            p.setPen(QPen(qcolor("--border-subtle"), 1.0))
            knob_col = qcolor("--text-disabled")
        elif self.isChecked():
            track_bg = QColor(self._active_color)
            track_bg.setAlphaF(0.20)
            p.setBrush(qcolor("--bg-inset"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, r, r)
            p.setBrush(track_bg)
            border_c = QColor(self._active_color)
            border_c.setAlphaF(0.42)
            p.setPen(QPen(border_c, 1.0))
            knob_col = qcolor("--ember-core")
        else:
            p.setBrush(qcolor("--bg-inset"))
            p.setPen(QPen(qcolor("--border-specular-strong"), 1.0))
            knob_col = qcolor("--text-secondary")

        p.drawRoundedRect(rect, r, r)

        margin = 3.0
        knob_d = rect.height() - 2.0 * margin
        knob_x = rect.left() + margin + self._offset * (rect.width() - 2.0 * margin - knob_d)
        knob_rect = QRectF(knob_x, rect.top() + margin, knob_d, knob_d)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(knob_col)
        p.drawEllipse(knob_rect)

        if self.isChecked() and self.isEnabled():
            dot_r = knob_d * 0.22
            p.setBrush(self._active_color)
            p.drawEllipse(knob_rect.center(), dot_r, dot_r)
        p.end()


class SettingToggleRow(QWidget):
    """라벨 + Darkroom `ToggleSwitch` 한 줄 위젯 (`QCheckBox` 호환 API)."""

    toggled = pyqtSignal(bool)

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        active_color: str = "--filament-orange",
        label_role: str = "body",
        **kwargs: object,
    ) -> None:
        del kwargs
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(12)

        self.label = QLabel(text)
        self.label.setProperty("role", label_role)
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
# 6. Precision Tick Slider (미세 눈금 + Gold→Orange 필라멘트)
# ============================================================================


class PrecisionTickSlider(QWidget):
    """음각 트랙 하단 1px 미세 눈금과 필라멘트 게이지를 갖춘 정밀 슬라이더."""

    value_changed = pyqtSignal(float)

    def __init__(
        self,
        minimum: float = 0.5,
        maximum: float = 3.0,
        value: float = 1.0,
        step: float = 0.1,
        ticks: int = 11,
        unit: str = "x",
    ) -> None:
        super().__init__()
        self._min = float(minimum)
        self._max = max(float(maximum), self._min + 0.01)
        self._step = max(0.01, float(step))
        self._value = self._clamp(value)
        self._ticks = max(3, int(ticks))
        self._unit = unit
        self._dragging = False
        self.setMinimumHeight(26)
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
        right = max(left + 10.0, self.width() - 46.0)
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
        right = max(left + 16.0, w - 46.0)
        track_w = right - left
        track_y = 8.0
        track_h = 4.0
        ratio = (self._value - self._min) / (self._max - self._min)

        p.setBrush(qcolor("--bg-inset"))
        p.setPen(QPen(qcolor("--border-specular"), 1.0))
        p.drawRoundedRect(QRectF(left, track_y, track_w, track_h), 2.0, 2.0)

        fill_w = max(0.0, track_w * ratio)
        if fill_w > 1.0:
            grad = QLinearGradient(left, track_y, left + track_w, track_y)
            grad.setColorAt(0.0, qcolor("--filament-gold"))
            grad.setColorAt(1.0, qcolor("--filament-orange"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(left + 0.5, track_y + 0.5, fill_w, track_h - 1.0), 1.5, 1.5)

        tick_top = track_y + track_h + 3.0
        for i in range(self._ticks):
            tx = left + (track_w * i / (self._ticks - 1))
            is_major = (i == 0) or (i == self._ticks - 1) or (i == self._ticks // 2)
            t_len = 4.5 if is_major else 2.5
            p.setPen(QPen(qcolor("--border-specular-strong" if is_major else "--border-subtle"), 1.0))
            p.drawLine(QPointF(tx, tick_top), QPointF(tx, tick_top + t_len))

        cx = left + fill_w
        knob_r = 5.5
        p.setBrush(qcolor("--text-primary"))
        p.setPen(QPen(qcolor("--border-specular-strong"), 1.0))
        p.drawEllipse(QPointF(cx, track_y + track_h / 2.0), knob_r, knob_r)

        p.setFont(font_for("micro", mono=True))
        p.setPen(qcolor("--text-secondary"))
        p.drawText(
            QRectF(right + 6.0, 0.0, 40.0, float(self.height())),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._value:.1f}{self._unit}",
        )
        p.end()


# ============================================================================
# 7. LED Status Pill (`EmberCoreDot` + Monospace 텍스트 알약 배지)
# ============================================================================


class LedStatusPill(QFrame):
    """`EmberCoreDot` + 고정폭 텍스트로 구성된 Darkroom 슬림 상태 배지."""

    def __init__(self, text: str = "", tone: str = "neutral") -> None:
        super().__init__()
        self.setProperty("surfaceRole", "status-pill")
        self.setFixedHeight(26)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 10, 0)
        layout.setSpacing(6)

        self.led = EmberCoreDot(live=(tone != "muted"), tone=tone, size=12)
        layout.addWidget(self.led)

        self.text_label = QLabel(text)
        self.text_label.setProperty("role", "mono-secondary")
        layout.addWidget(self.text_label)

        self.set_state(text, pill_state=tone, live=(tone in ("gold", "orange")))

    def set_state(
        self,
        text: str,
        pill_state: str = "neutral",
        live: bool = False,
    ) -> None:
        self.setProperty("pillState", pill_state)
        self.text_label.setText(text)
        self.led.set_state(
            live=live,
            tone=(pill_state if pill_state in ("gold", "orange", "red") else "muted"),
        )
        repolish(self)


# ============================================================================
# 8. Sidebar Navigation Button (숫자 인덱스 제거, Quiet Pro 정렬 + Ember Dot)
# ============================================================================


class NavRailButton(QPushButton):
    """좌측 사이드바 메뉴 버튼 (동일 간격 모노라인 아이콘 + 활성 시 Ember 도트 표시)."""

    def __init__(self, label: str, icon_kind: str) -> None:
        super().__init__()
        self._icon_kind = icon_kind
        self.setCheckable(True)
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("btnRole", "sidebar-item")
        self.setIconSize(QSize(15, 15))
        self.set_label(label)
        self.apply_active_style(False)

    def set_label(self, label: str) -> None:
        self.setText(f"  {label}")

    def apply_active_style(self, active: bool) -> None:
        self.setProperty("active", active)
        self.setIcon(
            make_vector_icon(
                self._icon_kind,
                "--text-primary" if active else "--text-secondary",
                15,
            )
        )
        repolish(self)


# ============================================================================
# 9. 단축키 입력 레코더 대화상자 (Shortcut Recorder)
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
    """사용자가 실제 키 조합을 눌러 단축키를 즉시 녹화하는 Darkroom 대화상자."""

    def __init__(self, initial_combo: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.recorded_combo: str = initial_combo
        self.setWindowTitle("Shortcut Recorder")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hint = QLabel("원하는 단축키 조합을 누르세요 (예: Ctrl + Shift + S)")
        hint.setProperty("role", "secondary")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self.preview_lbl = QLabel(initial_combo or "키 입력 대기 중")
        self.preview_lbl.setFixedHeight(44)
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setProperty("pillState", "gold")
        layout.addWidget(self.preview_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(30)
        cancel_btn.setProperty("btnRole", "ghost")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("적용")
        ok_btn.setFixedHeight(30)
        ok_btn.setProperty("btnRole", "primary")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)
        self.setFixedSize(368, 168)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        combo = qt_key_event_to_combo(event)
        if combo:
            self.recorded_combo = combo
            self.preview_lbl.setText(combo)
            event.accept()
            return
        super().keyPressEvent(event)


# ============================================================================
# 10. 레이어 생성 & 발동 조건 선택 다이얼로그 (`LayerCreateDialog`)
# ============================================================================


class LayerCreateDialog(QDialog):
    """새 레이어 생성 시 레이어명과 발동 조건(`포커스` vs `프로세스 지정`)을 선택하는 다이얼로그."""

    def __init__(self, lang: str = "ko", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self.setWindowTitle(tr(lang, "layer_create_title"))
        self.setFixedSize(440, 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        name_lbl = QLabel(tr(lang, "layer_create_name_label"))
        name_lbl.setProperty("role", "card-title")
        layout.addWidget(name_lbl)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr(lang, "layer_create_name_placeholder"))
        self.name_edit.setFixedHeight(32)
        layout.addWidget(self.name_edit)

        mode_box = QFrame()
        mode_box.setProperty("surfaceRole", "inset")
        mb_layout = QVBoxLayout(mode_box)
        mb_layout.setContentsMargins(12, 10, 12, 10)
        mb_layout.setSpacing(8)

        mode_title = QLabel(tr(lang, "layer_create_mode_label"))
        mode_title.setProperty("role", "muted")
        mb_layout.addWidget(mode_title)

        self._mode_group = QButtonGroup(self)
        self.focus_radio = QRadioButton(tr(lang, "layer_mode_focus_desc"))
        self.process_radio = QRadioButton(tr(lang, "layer_mode_process_desc"))
        self.focus_radio.setChecked(True)
        self._mode_group.addButton(self.focus_radio)
        self._mode_group.addButton(self.process_radio)
        mb_layout.addWidget(self.focus_radio)
        mb_layout.addWidget(self.process_radio)
        layout.addWidget(mode_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        self.cancel_btn = QPushButton(tr(lang, "common_cancel"))
        self.cancel_btn.setFixedHeight(30)
        self.cancel_btn.setProperty("btnRole", "ghost")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.create_btn = QPushButton(tr(lang, "layer_create_confirm"))
        self.create_btn.setFixedHeight(30)
        self.create_btn.setProperty("btnRole", "primary")
        self.create_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.create_btn)
        layout.addLayout(btn_row)

    def layer_name(self) -> str:
        return self.name_edit.text().strip()

    def trigger_mode(self) -> str:
        return (
            TRIGGER_MODE_PROCESS
            if self.process_radio.isChecked()
            else TRIGGER_MODE_FOCUS
        )


# ============================================================================
# 11. 프로세스 지정 레이어 다중 실행 충돌 선택 팝업 (`ProcessLayerConflictDialog`)
# ============================================================================


class ProcessLayerConflictDialog(QDialog):
    """2개 이상의 `프로세스 지정` 레이어 대상 프로세스가 동시 실행 중일 때 뜨는 독립 선택 팝업."""

    layer_chosen = pyqtSignal(str)

    def __init__(
        self,
        candidates: list[tuple[str, str]],
        active_layer: str = "",
        lang: str = "ko",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._lang = lang
        self._candidates = list(candidates)
        self.setWindowTitle(tr(lang, "conflict_dialog_title"))
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumSize(420, 290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.addWidget(EmberCoreDot(live=True, tone="gold", size=14))
        title_lbl = QLabel(tr(lang, "conflict_dialog_header"))
        title_lbl.setProperty("role", "card-title")
        hdr.addWidget(title_lbl, 1)
        layout.addLayout(hdr)

        desc_lbl = QLabel(tr(lang, "conflict_dialog_desc"))
        desc_lbl.setProperty("role", "secondary")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        self.candidate_list = QListWidget()
        self.candidate_list.itemDoubleClicked.connect(lambda _i: self._emit_selected())
        select_row = 0
        for row, (layer_name, exe_name) in enumerate(self._candidates):
            item = QListWidgetItem(f"{layer_name}   [{exe_name}]")
            item.setData(Qt.ItemDataRole.UserRole, layer_name)
            self.candidate_list.addItem(item)
            if layer_name == active_layer:
                select_row = row
        if self._candidates:
            self.candidate_list.setCurrentRow(select_row)
        layout.addWidget(self.candidate_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        self.close_btn = QPushButton(tr(lang, "common_close"))
        self.close_btn.setFixedHeight(30)
        self.close_btn.setProperty("btnRole", "ghost")
        self.close_btn.clicked.connect(self.close)
        btn_row.addWidget(self.close_btn)

        self.apply_btn = QPushButton(tr(lang, "conflict_dialog_apply"))
        self.apply_btn.setFixedHeight(30)
        self.apply_btn.setProperty("btnRole", "primary")
        self.apply_btn.clicked.connect(self._emit_selected)
        btn_row.addWidget(self.apply_btn)
        layout.addLayout(btn_row)

    @property
    def candidate_layers(self) -> list[str]:
        return [name for name, _exe in self._candidates]

    def selected_layer(self) -> str:
        item = self.candidate_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def _emit_selected(self) -> None:
        chosen = self.selected_layer()
        if chosen:
            self.layer_chosen.emit(chosen)
            self.accept()


# ============================================================================
# 12. 다중 모니터 창 배치 2D 블루프린트 미니맵 (Darkroom Quiet Pro)
# ============================================================================


class MonitorMinimapWidget(QWidget):
    """모니터 토폴로지와 프리셋 창 비율(0.0 ~ 1.0)을 그리는 92% 무채색 + 8% 필라멘트 미니맵."""

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
        dpr = self.devicePixelRatioF()
        rect = snap_border_rect(QRectF(self.rect()), dpr)
        r = float(px_int("--radius-item"))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor("--bg-inset"))
        p.drawRoundedRect(rect, r, r)

        # 미세 격자선
        p.setPen(QPen(qcolor("--border-subtle"), 1.0))
        step = 18
        for gx in range(step, int(rect.width()), step):
            p.drawLine(QPointF(gx, rect.top() + 2), QPointF(gx, rect.bottom() - 2))
        for gy in range(step, int(rect.height()), step):
            p.drawLine(QPointF(rect.left() + 2, gy), QPointF(rect.right() - 2, gy))

        p.setPen(QPen(qcolor("--border-specular"), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, r, r)

        if not self._monitors:
            p.setPen(qcolor("--text-muted"))
            p.setFont(font_for("micro", mono=True))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Topology standby")
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

        font_small = font_for("micro", mono=True)
        font_win = font_for("micro", mono=True)

        for m in self._monitors:
            ml, mt, mr, mb = m.monitor_rect
            m_rect = _to_canvas(ml, mt, mr - ml, mb - mt)
            p.setPen(
                QPen(
                    qcolor("--border-specular-strong" if m.is_primary else "--border-specular"),
                    1.0,
                )
            )
            p.setBrush(qcolor("--bg-surface"))
            p.drawRoundedRect(m_rect, 6.0, 6.0)

            wl, wt, wr, wb = m.work_rect
            w_rect = _to_canvas(wl, wt, wr - wl, wb - wt)
            p.setPen(QPen(qcolor("--border-subtle"), 1.0, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(w_rect)

            p.setFont(font_small)
            p.setPen(qcolor("--text-muted"))
            label = f"M{m.index} · {m.width}×{m.height} ({m.scale_percent}%)"
            p.drawText(
                QRectF(m_rect.left() + 4, m_rect.top() - 15, m_rect.width(), 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        if self._preset is not None:
            focus_low = self._preset.focus_process.strip().lower()
            palette_tokens = ("--filament-gold", "--filament-orange", "--text-secondary")
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
                stroke_col = qcolor(
                    "--filament-gold" if is_focus else palette_tokens[idx % len(palette_tokens)]
                )
                fill_col = QColor(stroke_col)
                fill_col.setAlphaF(0.16 if is_focus else 0.08)

                p.setBrush(fill_col)
                p.setPen(QPen(stroke_col, 1.4 if is_focus else 1.0))
                p.drawRoundedRect(win_rect, 4.0, 4.0)

                p.setFont(font_win)
                p.setPen(qcolor("--text-primary"))
                short_name = spec.process_name.replace(".exe", "")
                if is_focus:
                    short_name = f"• {short_name}"
                p.drawText(
                    win_rect.adjusted(4, 2, -4, -2),
                    Qt.AlignmentFlag.AlignCenter,
                    short_name,
                )

        p.end()
