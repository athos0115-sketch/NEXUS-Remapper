"""Darkroom Filament v1.1 — Canonical Design Tokens, Assets & Global QSS.

`UI_darkroom` (Quiet Pro: 92% Monochrome + 8% Thermal Filament) 규격을 따르며,
순흑·순백, 컴포넌트 인라인 `setStyleSheet`, Qt 위젯 드롭 섀도우 이펙트를 배제한다.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import QApplication, QWidget

# 전역 모션 활성화 플래그 (Web prefers-reduced-motion 1:1 대응)
MOTION_ENABLED: bool = True

# 1px Warm Rim-Light 커서 추적 정규화 X 클램프 경계
RIM_CLAMP_MIN: float = 0.08
RIM_CLAMP_MAX: float = 0.92

TOKENS: Dict[str, str] = {
    # A. Surface Hierarchy (5)
    "--bg-inset": "#0E0F12",
    "--bg-canvas": "#121316",
    "--bg-sidebar": "#15161A",
    "--bg-surface": "#18191D",
    "--bg-elevated": "#1E2026",
    # B. Specular Hairlines & 1px Warm Rim-Light (8)
    "--border-subtle": "rgba(255, 255, 255, 0.04)",
    "--border-specular": "rgba(255, 255, 255, 0.07)",
    "--border-specular-strong": "rgba(255, 255, 255, 0.12)",
    "--rim-gold": "rgba(246, 196, 83, 0.45)",
    "--rim-orange": "rgba(240, 110, 53, 0.28)",
    "--rim-red": "rgba(229, 72, 77, 0.36)",
    "--rim-wash": "rgba(246, 196, 83, 0.05)",
    "--rim-center-default": "0.50",
    # C. Thermal Filament Spectrum & Semantic Accents (14)
    "--filament-gold": "#F6C453",
    "--filament-orange": "#F06E35",
    "--filament-orange-text": "#F48C5E",
    "--filament-red": "#E5484D",
    "--ember-core": "#FFF5DC",
    "--filament-gold-bg": "rgba(246, 196, 83, 0.12)",
    "--filament-gold-border": "rgba(246, 196, 83, 0.28)",
    "--filament-orange-bg": "rgba(240, 110, 53, 0.14)",
    "--filament-orange-border": "rgba(240, 110, 53, 0.30)",
    "--filament-red-bg": "rgba(229, 72, 77, 0.14)",
    "--filament-red-border": "rgba(229, 72, 77, 0.30)",
    "--filament-neutral-bg": "rgba(255, 255, 255, 0.06)",
    "--filament-neutral-border": "rgba(255, 255, 255, 0.10)",
    "--status-danger-text": "#FCA5A5",
    # D. CTA, Ghost & Typography Colors (10)
    "--cta-bg": "#F2F3F5",
    "--cta-hover": "#E6E8EC",
    "--cta-pressed": "#D8DBE0",
    "--cta-text": "#121316",
    "--btn-ghost-bg": "rgba(255, 255, 255, 0.04)",
    "--btn-ghost-hover": "rgba(255, 255, 255, 0.08)",
    "--text-primary": "#F2F3F5",
    "--text-secondary": "#9EA3AE",
    "--text-muted": "#848A96",
    "--text-disabled": "#50545E",
    # E. Shadows & Backdrop (5)
    "--shadow-floating": "0 12px 32px rgba(8, 9, 12, 0.55), 0 2px 6px rgba(8, 9, 12, 0.35)",
    "--shadow-card": "0 4px 16px rgba(8, 9, 12, 0.35)",
    "--backdrop-palette": "rgba(8, 9, 12, 0.68)",
    "--shadow-alpha-heavy": "rgba(8, 9, 12, 0.55)",
    "--shadow-alpha-soft": "rgba(8, 9, 12, 0.35)",
    # F. Typography, Spacing, Radius, Breakpoints & Motion
    "--font-sans": '"Inter", "Pretendard", "Segoe UI", "Malgun Gothic", sans-serif',
    "--font-mono": '"JetBrains Mono", "Cascadia Mono", "Consolas", monospace',
    "--text-editorial": "26px",
    "--text-metric": "24px",
    "--text-card-title": "14px",
    "--text-body": "13px",
    "--text-badge": "12px",
    "--text-micro": "11px",
    "--lh-editorial": "32px",
    "--lh-metric": "28px",
    "--lh-card-title": "20px",
    "--lh-body": "18px",
    "--lh-badge": "16px",
    "--lh-micro": "14px",
    "--space-1": "4px",
    "--space-2": "8px",
    "--space-3": "12px",
    "--space-4": "16px",
    "--space-5": "20px",
    "--space-6": "24px",
    "--space-8": "32px",
    "--radius-scroll": "3px",
    "--radius-xs": "6px",
    "--radius-sm": "8px",
    "--radius-item": "10px",
    "--radius-modal": "14px",
    "--radius-card": "16px",
    "--radius-pill": "999px",
    "--bp-min": "760px",
    "--bp-standard": "960px",
    "--bp-wide": "1360px",
    "--bp-content-max": "1120px",
    "--motion-fast": "120ms",
    "--motion-base": "160ms",
    "--motion-overlay": "220ms",
    "--motion-optic": "320ms",
    "--motion-rim-track": "160ms",
    "--motion-rim-decay": "360ms",
    "--motion-breath": "3200ms",
    "--ease-cubic": "cubic-bezier(0.22, 1, 0.36, 1)",
    "--ease-quart": "cubic-bezier(0.25, 1, 0.5, 1)",
    "--ease-overlay": "cubic-bezier(0.16, 1, 0.3, 1)",
}

_RGBA_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+)\s*)?\)"
)


def px_int(name: str) -> int:
    """'16px' 토큰을 정수 픽셀로 반환한다."""
    return int(TOKENS[name].replace("px", "").strip())


def ms_int(name: str) -> int:
    """'120ms' 모션 토큰을 밀리초 정수로 반환한다."""
    if not MOTION_ENABLED:
        return 0
    return int(TOKENS[name].replace("ms", "").strip())


def float_token(name: str) -> float:
    """부동소수점 토큰 값을 반환한다."""
    return float(TOKENS[name].strip())


def parse_color(value: str, alpha_override: float | None = None) -> QColor:
    """HEX 또는 rgba(...) 문자열을 QColor로 변환한다."""
    raw = value.strip()
    if raw.startswith("#"):
        col = QColor(raw)
    else:
        match = _RGBA_RE.match(raw)
        if not match:
            col = QColor(raw)
        else:
            r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
            a = float(match.group(4)) if match.group(4) is not None else 1.0
            col = QColor(r, g, b)
            col.setAlphaF(max(0.0, min(1.0, a)))
    if alpha_override is not None:
        col.setAlphaF(max(0.0, min(1.0, alpha_override)))
    return col


def qcolor(token_name: str, alpha_override: float | None = None) -> QColor:
    """토큰 키에서 QColor를 생성한다."""
    return parse_color(TOKENS[token_name], alpha_override=alpha_override)


def font_for(role: str = "body", weight: int | None = None, mono: bool = False) -> QFont:
    """역할별 DIP 픽셀 폰트를 생성한다 (`QFont.setPixelSize` 통일)."""
    role_map = {
        "editorial": ("--text-editorial", QFont.Weight.DemiBold, False, -2.0),
        "metric": ("--text-metric", QFont.Weight.Medium, False, 0.0),
        "card-title": ("--text-card-title", QFont.Weight.Medium, False, 0.0),
        "body": ("--text-body", QFont.Weight.Normal, False, 0.0),
        "badge": ("--text-badge", QFont.Weight.Medium, False, 0.0),
        "micro": ("--text-micro", QFont.Weight.Medium, False, 0.0),
    }
    size_key, default_weight, default_mono, tracking_pct = role_map.get(
        role, ("--text-body", QFont.Weight.Normal, False, 0.0)
    )
    use_mono = mono or default_mono
    families = (
        ["JetBrains Mono", "Cascadia Mono", "Consolas", "monospace"]
        if use_mono
        else ["Inter", "Pretendard", "Segoe UI", "Malgun Gothic", "sans-serif"]
    )
    f = QFont()
    f.setFamilies(families)
    f.setPixelSize(px_int(size_key))
    f.setWeight(QFont.Weight(weight) if weight is not None else default_weight)
    if tracking_pct != 0.0:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100.0 + tracking_pct)
    return f


def line_height(role: str = "body") -> int:
    """역할별 기준 행간(DIP px)을 반환한다."""
    lh_map = {
        "editorial": "--lh-editorial",
        "metric": "--lh-metric",
        "card-title": "--lh-card-title",
        "body": "--lh-body",
        "badge": "--lh-badge",
        "micro": "--lh-micro",
        "secondary": "--lh-body",
        "muted": "--lh-micro",
        "error": "--lh-micro",
        "disabled": "--lh-body",
    }
    return px_int(lh_map.get(role, "--lh-body"))


def apply_dpi_and_fonts(app: QApplication) -> None:
    """PassThrough DPI 정책 및 기본 픽셀 폰트를 적용한다."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app.setFont(font_for("body"))


def repolish(widget: QWidget) -> None:
    """동적 속성 변경 후 QSS 스타일을 즉시 재평가한다."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


# ============================================================================
# 번들 에셋 아이콘 경로 & Windows 11 다크 타이틀바
# ============================================================================

def get_asset_path(relative_path: str) -> Path:
    """개발 환경과 PyInstaller(`_MEIPASS`) 모두에서 `assets/` 경로를 안전하게 찾는다."""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(str(meipass)) / relative_path)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / relative_path)
    root_dir = Path(__file__).resolve().parent.parent
    candidates.append(root_dir / relative_path)
    for cand in candidates:
        if cand.is_file():
            return cand
    return candidates[-1]


def load_app_icon() -> QIcon:
    """Darkroom Filament Mode B 멀티 해상도 앱 아이콘(`app_icon.ico` / `.png`)을 로드한다."""
    for rel in ("assets/app_icon.ico", "assets/app_icon_256.png", "assets/app_icon.png"):
        path = get_asset_path(rel)
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return QIcon()


DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
DWMWA_USE_IMMERSIVE_DARK_MODE = 20

try:
    import ctypes
    from ctypes import wintypes

    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    _dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
except OSError:
    _dwmapi = None


def apply_win11_dark_titlebar(hwnd: int) -> bool:
    """Windows 10/11 OS 타이틀바를 Darkroom 딥 차콜 테마로 전환한다."""
    if os.name != "nt" or _dwmapi is None or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes

    value = ctypes.c_int(1)
    for attr in (DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1):
        hr = _dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(attr),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        if hr == 0:
            return True
    return False


# ============================================================================
# Thermal Load Color Helper
# ============================================================================

def thermal_color_for_load(load: float) -> str:
    """부하율(0.0~1.0)에 따른 3단계 Thermal Spectrum 색상을 반환한다."""
    clamped = max(0.0, min(1.0, float(load)))
    if clamped < 0.40:
        return TOKENS["--filament-gold"]
    if clamped < 0.72:
        return TOKENS["--filament-orange"]
    return TOKENS["--filament-red"]


def action_pill_state(action_type_str: str) -> str:
    """액션 유형을 Darkroom 배지 상태(`gold`/`orange`/`neutral`)로 매핑한다."""
    t = str(action_type_str).lower()
    if t in ("key_combo", "workspace_layout", "launch_app", "layer_shift"):
        return "gold"
    if t in ("zoom", "mouse_wheel", "brightness"):
        return "orange"
    return "neutral"


# ============================================================================
# Darkroom Filament v1.1 글로벌 QSS (모든 컴포넌트는 속성/role만 선언)
# ============================================================================

def build_qss() -> str:
    """`TOKENS` 기반 글로벌 QSS를 생성한다 (비-토큰 파일 raw HEX/인라인 QSS 0건)."""
    t = TOKENS
    return f"""
    QMainWindow#NexusMainWindow, QWidget#RootCentral {{
        background-color: {t["--bg-canvas"]};
        color: {t["--text-primary"]};
        font-family: {t["--font-sans"]};
        font-size: {t["--text-body"]};
    }}
    QDialog, QMessageBox {{
        background-color: {t["--bg-surface"]};
        color: {t["--text-primary"]};
        font-family: {t["--font-sans"]};
        font-size: {t["--text-body"]};
    }}
    QWidget {{
        color: {t["--text-primary"]};
        font-family: {t["--font-sans"]};
        font-size: {t["--text-body"]};
    }}

    /* Typography Roles */
    QLabel {{
        background-color: transparent;
        border: none;
    }}
    QLabel[role="editorial"] {{
        font-size: {t["--text-editorial"]};
        font-weight: 600;
        letter-spacing: -0.5px;
        color: {t["--text-primary"]};
    }}
    QLabel[role="metric"] {{
        font-size: {t["--text-metric"]};
        font-weight: 500;
        font-family: {t["--font-mono"]};
        color: {t["--text-primary"]};
    }}
    QLabel[role="card-title"] {{
        font-size: {t["--text-card-title"]};
        font-weight: 500;
        color: {t["--text-primary"]};
    }}
    QLabel[role="body"] {{
        font-size: {t["--text-body"]};
        color: {t["--text-primary"]};
    }}
    QLabel[role="secondary"] {{
        font-size: {t["--text-body"]};
        color: {t["--text-secondary"]};
    }}
    QLabel[role="muted"] {{
        font-size: {t["--text-micro"]};
        color: {t["--text-muted"]};
    }}
    QLabel[role="mono-muted"] {{
        font-family: {t["--font-mono"]};
        font-size: {t["--text-micro"]};
        color: {t["--text-muted"]};
    }}
    QLabel[role="mono-secondary"] {{
        font-family: {t["--font-mono"]};
        font-size: {t["--text-micro"]};
        color: {t["--text-secondary"]};
    }}
    QLabel[role="mono-code"] {{
        font-family: {t["--font-mono"]};
        font-size: {t["--text-body"]};
        font-weight: 600;
        color: {t["--text-primary"]};
    }}
    QLabel[role="error"] {{
        font-size: {t["--text-micro"]};
        color: {t["--status-danger-text"]};
    }}
    QLabel[role="disabled"] {{
        font-size: {t["--text-body"]};
        color: {t["--text-disabled"]};
    }}

    /* Compact Semantic Pills */
    QLabel[pillState="neutral"] {{
        background-color: {t["--filament-neutral-bg"]};
        color: {t["--text-secondary"]};
        border: 1px solid {t["--filament-neutral-border"]};
        border-radius: {t["--radius-xs"]};
        padding: 2px 8px;
        font-family: {t["--font-mono"]};
        font-size: {t["--text-micro"]};
        font-weight: 500;
    }}
    QLabel[pillState="gold"] {{
        background-color: {t["--filament-gold-bg"]};
        color: {t["--filament-gold"]};
        border: 1px solid {t["--filament-gold-border"]};
        border-radius: {t["--radius-xs"]};
        padding: 2px 8px;
        font-family: {t["--font-mono"]};
        font-size: {t["--text-micro"]};
        font-weight: 600;
    }}
    QLabel[pillState="orange"] {{
        background-color: {t["--filament-orange-bg"]};
        color: {t["--filament-orange-text"]};
        border: 1px solid {t["--filament-orange-border"]};
        border-radius: {t["--radius-xs"]};
        padding: 2px 8px;
        font-family: {t["--font-mono"]};
        font-size: {t["--text-micro"]};
        font-weight: 600;
    }}
    QLabel[pillState="red"] {{
        background-color: {t["--filament-red-bg"]};
        color: {t["--status-danger-text"]};
        border: 1px solid {t["--filament-red-border"]};
        border-radius: {t["--radius-xs"]};
        padding: 2px 8px;
        font-family: {t["--font-mono"]};
        font-size: {t["--text-micro"]};
        font-weight: 600;
    }}
    QLabel[role="listen-banner"] {{
        background-color: {t["--filament-gold-bg"]};
        color: {t["--filament-gold"]};
        border: 1px solid {t["--filament-gold-border"]};
        border-radius: {t["--radius-item"]};
        padding: 6px 12px;
        font-size: {t["--text-badge"]};
        font-weight: 500;
    }}
    QLabel[role="empty-hint"] {{
        background-color: {t["--bg-inset"]};
        color: {t["--text-muted"]};
        border: 1px solid {t["--border-subtle"]};
        border-radius: {t["--radius-item"]};
        padding: 32px;
        font-size: {t["--text-body"]};
    }}

    /* Surface Containers */
    QFrame[surfaceRole="sidebar"] {{
        background-color: {t["--bg-sidebar"]};
        border: none;
        border-right: 1px solid {t["--border-specular"]};
    }}
    QFrame[surfaceRole="panel"] {{
        background-color: {t["--bg-surface"]};
        border: 1px solid {t["--border-specular"]};
        border-radius: {t["--radius-card"]};
    }}
    QFrame[surfaceRole="inset"] {{
        background-color: {t["--bg-inset"]};
        border: 1px solid {t["--border-subtle"]};
        border-radius: {t["--radius-item"]};
    }}
    QFrame[surfaceRole="footer-bar"] {{
        background-color: {t["--bg-sidebar"]};
        border: 1px solid {t["--border-subtle"]};
        border-radius: {t["--radius-sm"]};
    }}
    QFrame[surfaceRole="keycap-slot"] {{
        background-color: {t["--bg-inset"]};
        border: 1px solid {t["--border-subtle"]};
        border-radius: {t["--radius-item"]};
    }}
    QFrame[surfaceRole="device-card"] {{
        background-color: {t["--bg-surface"]};
        border: 1px solid {t["--border-specular"]};
        border-radius: {t["--radius-item"]};
    }}
    QFrame[surfaceRole="device-card"]:hover {{
        background-color: {t["--bg-elevated"]};
        border: 1px solid {t["--border-specular-strong"]};
    }}
    QFrame[surfaceRole="device-card"][selected="true"] {{
        background-color: {t["--bg-elevated"]};
        border: 1px solid {t["--filament-gold-border"]};
    }}
    QFrame[surfaceRole="device-card"][registered="true"] {{
        border: 1px solid {t["--border-specular-strong"]};
    }}
    QFrame[surfaceRole="status-pill"] {{
        background-color: {t["--bg-surface"]};
        border: 1px solid {t["--border-specular"]};
        border-radius: {t["--radius-pill"]};
    }}
    QFrame[surfaceRole="status-pill"][pillState="gold"] {{
        background-color: {t["--filament-gold-bg"]};
        border: 1px solid {t["--filament-gold-border"]};
    }}
    QFrame[surfaceRole="status-pill"][pillState="orange"] {{
        background-color: {t["--filament-orange-bg"]};
        border: 1px solid {t["--filament-orange-border"]};
    }}
    QFrame[surfaceRole="status-pill"][pillState="red"] {{
        background-color: {t["--filament-red-bg"]};
        border: 1px solid {t["--filament-red-border"]};
    }}
    QFrame[surfaceRole="modal-card"] {{
        background-color: {t["--bg-surface"]};
        border: 1px solid {t["--border-specular-strong"]};
        border-radius: {t["--radius-modal"]};
    }}

    /* Hairline Dividers */
    QFrame[role="hairline-v"] {{
        background-color: {t["--border-specular"]};
        border: none;
    }}
    QFrame[role="hairline-h"] {{
        background-color: {t["--border-subtle"]};
        border: none;
    }}

    /* 7-State Buttons */
    QPushButton {{
        background-color: {t["--btn-ghost-bg"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular"]};
        border-radius: {t["--radius-sm"]};
        padding: 4px 12px;
        font-size: {t["--text-body"]};
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {t["--btn-ghost-hover"]};
        border-color: {t["--border-specular-strong"]};
    }}
    QPushButton:pressed {{
        background-color: {t["--bg-elevated"]};
        border-color: {t["--border-specular-strong"]};
    }}
    QPushButton:focus-visible {{
        border: 2px solid {t["--filament-orange"]};
    }}
    QPushButton:disabled {{
        background-color: {t["--bg-inset"]};
        border-color: {t["--border-subtle"]};
        color: {t["--text-disabled"]};
    }}

    /* High-Contrast Off-White Primary CTA (#F2F3F5 on #121316) */
    QPushButton[btnRole="primary"] {{
        background-color: {t["--cta-bg"]};
        color: {t["--cta-text"]};
        border: 1px solid {t["--cta-bg"]};
        border-radius: {t["--radius-pill"]};
        padding: 5px 14px;
        font-size: {t["--text-body"]};
        font-weight: 600;
    }}
    QPushButton[btnRole="primary"]:hover {{
        background-color: {t["--cta-hover"]};
        border-color: {t["--cta-hover"]};
    }}
    QPushButton[btnRole="primary"]:pressed {{
        background-color: {t["--cta-pressed"]};
        border-color: {t["--cta-pressed"]};
    }}
    QPushButton[btnRole="primary"]:disabled {{
        background-color: {t["--bg-inset"]};
        color: {t["--text-disabled"]};
        border-color: {t["--border-subtle"]};
    }}

    /* Secondary Ghost Glass Pill */
    QPushButton[btnRole="ghost"] {{
        background-color: {t["--btn-ghost-bg"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular-strong"]};
        border-radius: {t["--radius-pill"]};
        padding: 4px 12px;
        font-size: {t["--text-badge"]};
        font-weight: 500;
    }}
    QPushButton[btnRole="ghost"]:hover {{
        background-color: {t["--btn-ghost-hover"]};
    }}
    QPushButton[btnRole="ghost"]:pressed {{
        background-color: {t["--bg-elevated"]};
    }}

    /* Quiet Segment / Toolbar Action */
    QPushButton[btnRole="quiet"] {{
        background-color: transparent;
        color: {t["--text-secondary"]};
        border: 1px solid transparent;
        border-radius: {t["--radius-sm"]};
        padding: 3px 10px;
        font-size: {t["--text-badge"]};
        font-weight: 500;
    }}
    QPushButton[btnRole="quiet"]:hover {{
        background-color: {t["--btn-ghost-bg"]};
        color: {t["--text-primary"]};
    }}
    QPushButton[btnRole="quiet"][active="true"] {{
        background-color: {t["--bg-elevated"]};
        border-color: {t["--border-specular-strong"]};
        color: {t["--text-primary"]};
    }}

    /* Listen Mode Pill */
    QPushButton[btnRole="listen"] {{
        background-color: {t["--btn-ghost-bg"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular"]};
        border-radius: {t["--radius-pill"]};
        padding: 4px 12px;
        font-size: {t["--text-badge"]};
        font-weight: 500;
    }}
    QPushButton[btnRole="listen"]:hover {{
        background-color: {t["--btn-ghost-hover"]};
        border-color: {t["--border-specular-strong"]};
    }}
    QPushButton[btnRole="listen"][active="true"] {{
        background-color: {t["--filament-gold-bg"]};
        color: {t["--filament-gold"]};
        border: 1px solid {t["--filament-gold-border"]};
    }}

    /* Danger Action (No solid bright red fill — 92% quiet darkroom preservation) */
    QPushButton[btnRole="danger"] {{
        background-color: {t["--filament-red-bg"]};
        color: {t["--status-danger-text"]};
        border: 1px solid {t["--filament-red-border"]};
        border-radius: {t["--radius-sm"]};
        padding: 4px 10px;
        font-size: {t["--text-badge"]};
        font-weight: 500;
    }}
    QPushButton[btnRole="danger"]:hover {{
        background-color: {t["--bg-elevated"]};
        border-color: {t["--filament-red"]};
    }}
    QPushButton[btnRole="ghost-danger"] {{
        background-color: transparent;
        color: {t["--text-muted"]};
        border: 1px solid transparent;
        border-radius: {t["--radius-xs"]};
        padding: 2px;
        font-size: {t["--text-card-title"]};
        font-weight: 600;
    }}
    QPushButton[btnRole="ghost-danger"]:hover {{
        background-color: {t["--filament-red-bg"]};
        color: {t["--status-danger-text"]};
        border-color: {t["--filament-red-border"]};
    }}

    /* Device Protection Badges */
    QPushButton[btnRole="protect-badge"][state="protected"] {{
        background-color: {t["--filament-orange-bg"]};
        color: {t["--filament-orange-text"]};
        border: 1px solid {t["--filament-orange-border"]};
        border-radius: {t["--radius-pill"]};
        padding: 2px 8px;
        font-size: {t["--text-micro"]};
        font-weight: 500;
    }}
    QPushButton[btnRole="protect-badge"][state="active"] {{
        background-color: {t["--filament-gold-bg"]};
        color: {t["--filament-gold"]};
        border: 1px solid {t["--filament-gold-border"]};
        border-radius: {t["--radius-pill"]};
        padding: 2px 8px;
        font-size: {t["--text-micro"]};
        font-weight: 500;
    }}
    QPushButton[btnRole="protect-badge"][state="standby"] {{
        background-color: {t["--filament-neutral-bg"]};
        color: {t["--text-secondary"]};
        border: 1px solid {t["--filament-neutral-border"]};
        border-radius: {t["--radius-pill"]};
        padding: 2px 8px;
        font-size: {t["--text-micro"]};
        font-weight: 500;
    }}

    /* Bypass Header Pill */
    QPushButton[btnRole="bypass-pill"] {{
        background-color: {t["--filament-gold-bg"]};
        color: {t["--filament-gold"]};
        border: 1px solid {t["--filament-gold-border"]};
        border-radius: {t["--radius-pill"]};
        padding: 3px 12px;
        font-size: {t["--text-micro"]};
        font-weight: 600;
    }}
    QPushButton[btnRole="bypass-pill"][bypass="true"] {{
        background-color: {t["--filament-orange-bg"]};
        color: {t["--filament-orange-text"]};
        border: 1px solid {t["--filament-orange-border"]};
    }}

    /* Sidebar Navigation Items */
    QPushButton[btnRole="sidebar-item"] {{
        background-color: transparent;
        color: {t["--text-secondary"]};
        border: 1px solid transparent;
        border-radius: {t["--radius-sm"]};
        padding: 6px 10px;
        text-align: left;
        font-size: {t["--text-body"]};
        font-weight: 500;
    }}
    QPushButton[btnRole="sidebar-item"]:hover {{
        background-color: {t["--btn-ghost-bg"]};
        color: {t["--text-primary"]};
    }}
    QPushButton[btnRole="sidebar-item"][active="true"] {{
        background-color: {t["--bg-elevated"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular"]};
    }}

    /* Segmented Tabs */
    QPushButton[btnRole="segment"] {{
        background-color: transparent;
        color: {t["--text-muted"]};
        border: 1px solid transparent;
        border-radius: {t["--radius-xs"]};
        padding: 3px 10px;
        font-size: {t["--text-badge"]};
        font-weight: 500;
    }}
    QPushButton[btnRole="segment"]:hover {{
        color: {t["--text-primary"]};
    }}
    QPushButton[btnRole="segment"][active="true"] {{
        background-color: {t["--bg-elevated"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular-strong"]};
    }}

    /* Inputs */
    QLineEdit {{
        background-color: {t["--bg-inset"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular"]};
        border-radius: {t["--radius-sm"]};
        padding: 4px 10px;
        font-size: {t["--text-body"]};
    }}
    QLineEdit:hover {{
        border-color: {t["--border-specular-strong"]};
    }}
    QLineEdit:focus {{
        border: 1px solid {t["--filament-orange-border"]};
    }}
    QLineEdit[state="error"] {{
        border: 1px solid {t["--filament-red-border"]};
        color: {t["--status-danger-text"]};
    }}
    QLineEdit:disabled {{
        background-color: {t["--bg-inset"]};
        border-color: {t["--border-subtle"]};
        color: {t["--text-disabled"]};
    }}

    /* ComboBox */
    QComboBox {{
        background-color: {t["--bg-inset"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular"]};
        border-radius: {t["--radius-sm"]};
        padding: 3px 10px;
        font-size: {t["--text-badge"]};
    }}
    QComboBox:hover {{
        background-color: {t["--bg-elevated"]};
        border-color: {t["--border-specular-strong"]};
    }}
    QComboBox:disabled {{
        background-color: {t["--bg-inset"]};
        border-color: {t["--border-subtle"]};
        color: {t["--text-disabled"]};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {t["--bg-surface"]};
        border: 1px solid {t["--border-specular-strong"]};
        border-radius: {t["--radius-sm"]};
        padding: 4px;
        outline: none;
        color: {t["--text-primary"]};
        selection-background-color: {t["--bg-elevated"]};
        selection-color: {t["--text-primary"]};
    }}

    /* Lists, Logs & TextBrowsers */
    QListWidget {{
        background-color: {t["--bg-inset"]};
        color: {t["--text-secondary"]};
        border: 1px solid {t["--border-subtle"]};
        border-radius: {t["--radius-item"]};
        padding: 4px;
        outline: none;
        font-size: {t["--text-body"]};
    }}
    QListWidget::item {{
        padding: 7px 10px;
        border-radius: {t["--radius-xs"]};
        margin-bottom: 2px;
    }}
    QListWidget::item:hover {{
        background-color: {t["--btn-ghost-bg"]};
        color: {t["--text-primary"]};
    }}
    QListWidget::item:selected {{
        background-color: {t["--bg-elevated"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular"]};
    }}

    QPlainTextEdit {{
        background-color: {t["--bg-inset"]};
        color: {t["--text-secondary"]};
        border: 1px solid {t["--border-subtle"]};
        border-radius: {t["--radius-item"]};
        padding: 8px;
        font-family: {t["--font-mono"]};
        font-size: {t["--text-micro"]};
    }}
    QTextBrowser {{
        background-color: {t["--bg-inset"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-subtle"]};
        border-radius: {t["--radius-item"]};
        padding: 16px;
        font-size: {t["--text-body"]};
    }}

    /* Radio Buttons & ScrollBars & Menus */
    QRadioButton {{
        color: {t["--text-primary"]};
        font-size: {t["--text-body"]};
        spacing: 8px;
    }}
    QRadioButton::indicator {{
        width: 14px;
        height: 14px;
        border-radius: 7px;
        border: 1px solid {t["--border-specular-strong"]};
        background-color: {t["--bg-inset"]};
    }}
    QRadioButton::indicator:checked {{
        border: 4px solid {t["--filament-orange"]};
        background-color: {t["--ember-core"]};
    }}

    QScrollArea {{
        background-color: transparent;
        border: none;
    }}
    QWidget[role="transparent-bg"] {{
        background-color: transparent;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 4px 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {t["--border-specular-strong"]};
        border-radius: {t["--radius-scroll"]};
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t["--text-muted"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        height: 0px;
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 6px;
        margin: 0px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {t["--border-specular-strong"]};
        border-radius: {t["--radius-scroll"]};
        min-width: 28px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        width: 0px;
        background: transparent;
    }}

    QMenu {{
        background-color: {t["--bg-surface"]};
        color: {t["--text-primary"]};
        border: 1px solid {t["--border-specular-strong"]};
        border-radius: {t["--radius-sm"]};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 14px;
        border-radius: {t["--radius-xs"]};
    }}
    QMenu::item:selected {{
        background-color: {t["--bg-elevated"]};
        color: {t["--text-primary"]};
    }}
    QMenu::separator {{
        height: 1px;
        background: {t["--border-subtle"]};
        margin: 4px 8px;
    }}
    QSplitter::handle {{
        background-color: transparent;
    }}
    """
