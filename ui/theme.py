"""Precision Architectural HUD (방향 A) 디자인 토큰, 중앙 QSS 및 Win11 다크 타이틀바 모듈."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

# ============================================================================
# 방향 A: Precision Architectural HUD 컬러 시스템 (3단 Elevation)
# ============================================================================

BG_CANVAS = "#0B0B0E"       # 최하단 캔버스
BG_SURFACE = "#131318"      # 패널 / 내비게이션 레일
BG_CARD = "#1A1A21"         # 상승 카드 (상단 미세 하이라이트 포함)
BG_INPUT = "#0E0E12"        # 입력창 / 물리 키캡 리세스

BORDER_HAIRLINE = "#25252E"
BORDER_HOVER = "#3A3A48"
BORDER_HIGHLIGHT = "rgba(255, 255, 255, 0.07)"

TEXT_PRIMARY = "#ECECF1"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED = "#64748B"

ACCENT_CYAN = "#00FFCC"     # 단축키 / 활성 / Listen
ACCENT_PURPLE = "#A855F7"   # 창 레이아웃 / 레이어 / 컨텍스트
ACCENT_ORANGE = "#F97316"   # 휠·줌 / 보호 / Bypass / 경고
ACCENT_SILVER = "#94A3B8"   # 텍스트 / 미디어 / 기본
ACCENT_DANGER = "#F87171"

# ============================================================================
# Windows 11 네이티브 다크 타이틀바 (DwmSetWindowAttribute)
# ============================================================================

DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
DWMWA_USE_IMMERSIVE_DARK_MODE = 20

try:
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
    """Windows 10/11 OS 타이틀바를 딥 다크 테마로 전환한다."""
    if _dwmapi is None or not hwnd:
        return False
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
# 중앙화된 Architectural HUD 전역 스타일시트
# ============================================================================

def surface_panel_qss(object_name: str) -> str:
    """1px 헤어라인 + 상단 미세 광택을 적용한 Surface 카드 스타일을 반환한다."""
    return (
        f"QFrame#{object_name} {{"
        f"  background-color: {BG_SURFACE};"
        f"  border: 1px solid {BORDER_HAIRLINE};"
        f"  border-top: 1px solid #30303C;"
        f"  border-radius: 9px;"
        "}"
    )


ARCHITECTURAL_HUD_QSS = f"""
QMainWindow, QWidget#RootCentral {{
    background-color: {BG_CANVAS};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Malgun Gothic", sans-serif;
}}
QDialog {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
}}
QSplitter::handle {{
    background-color: transparent;
}}
QComboBox, QLineEdit {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-radius: 5px;
    padding: 3px 8px;
    font-size: 11px;
}}
QComboBox:hover, QLineEdit:hover {{
    border-color: {BORDER_HOVER};
}}
QComboBox:focus, QLineEdit:focus {{
    border-color: {ACCENT_CYAN};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    selection-background-color: #0D2A26;
    selection-color: {ACCENT_CYAN};
    border: 1px solid {BORDER_HAIRLINE};
    outline: 0px;
}}
QListWidget {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-radius: 7px;
    font-size: 11px;
    outline: 0px;
}}
QListWidget::item {{
    padding: 6px 9px;
    border-bottom: 1px solid #18181F;
}}
QListWidget::item:hover {{
    background-color: #16161D;
}}
QListWidget::item:selected {{
    background-color: #1A1728;
    color: {ACCENT_PURPLE};
    border-left: 2px solid {ACCENT_PURPLE};
}}
QPlainTextEdit {{
    background-color: #09090C;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-radius: 7px;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 10.5px;
}}
QTextBrowser {{
    background-color: #0E0E12;
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-radius: 8px;
    padding: 16px;
    font-size: 12px;
}}
QScrollBar:vertical {{
    background: {BG_CANVAS};
    width: 6px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: #282834;
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_CYAN};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""
