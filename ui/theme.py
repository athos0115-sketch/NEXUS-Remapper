"""Wonjae's Signature Design System — 'Obsidian Tactile HUD' 마스터 토큰 및 중앙 QSS 모듈.

- 순흑(#000000)·순백(#FFFFFF)·무분별한 다색 네온/퍼플 배제
- 매트 흑요석/차콜 베이스(#111216 ~ #1D1F26), 건축적 앰버 오렌지(#E87A3E) 주 포인트, 광학 시안(#38BDF8) 텔레메트리
- 돌출(Raised) / 음각(Inset) / 눌림(Pressed) 물성 셰이딩 및 Windows 11 네이티브 다크 타이틀바 제공
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

# ============================================================================
# 1. Color Tokens — Obsidian Tactile HUD
# ============================================================================

# A. Surface & Depth Hierarchy
BG_INSET = "#0D0E12"         # 음각 홈, 인풋 필드, 슬라이더 트랙, 로그 터미널 내부
BG_BASE = "#111216"          # 최하단 메인 윈도우 캔버스 베이스
BG_SURFACE = "#16181E"       # 좌측 내비게이션 레일, 상단 커맨드 헤더, 하단 상태 바
BG_RAISED = "#1D1F26"        # 돌출 카드, 물리 키캡, 기본 버튼 표면
BG_HOVER = "#242730"         # 호버 시 미세하게 밝아지는 인터랙티브 표면

BORDER_HAIRLINE = "#2A2D36"  # 기본 1px 구조 구분선 및 카드 외곽선
BORDER_BEVEL = "#353945"     # Raised 요소 상단 1px 빛 반사(Bevel Highlight)
BORDER_RAISED_SIDE = "#22252E"
BORDER_INSET_TOP = "#08090C"
BORDER_INSET_BOTTOM = "#282B34"

# B. Brand & Semantic Accents (이원화 컬러 규율: Amber Action / Cyan Telemetry)
ACCENT_AMBER = "#E87A3E"                # Primary Action, 활성 메뉴 3px 인디케이터, 핵심 강조
ACCENT_AMBER_GLOW = "#FF984F"           # 호버 하이라이트, 트리거 발광
ACCENT_AMBER_DIM = "rgba(232, 122, 62, 0.14)"
ACCENT_AMBER_BG = "#261B16"             # QSS 불투명 앰버 틴트 배경
ACCENT_AMBER_BORDER = "#7A4223"

ACCENT_CYAN = "#38BDF8"                 # Telemetry: 연결 LED, 활성 프로세스, 센서, Listen
ACCENT_CYAN_DIM = "rgba(56, 189, 248, 0.12)"
ACCENT_CYAN_BG = "#142029"              # QSS 불투명 시안 틴트 배경
ACCENT_CYAN_BORDER = "#1F5773"

STATUS_OK = "#34D399"                   # 정상 연결, 커널 모드 활성, 검증 통과
STATUS_OK_BG = "#13241E"
STATUS_OK_BORDER = "#1E5B45"

STATUS_WARN = "#F59E0B"                 # 폴백 모드, Bypass, 주의 알림
STATUS_WARN_BG = "#261E11"
STATUS_WARN_BORDER = "#70490D"

STATUS_DANGER = "#EF4444"               # 비상 탈출(Panic Exit), 삭제 확인, 치명적 오류
STATUS_DANGER_BG = "#281517"
STATUS_DANGER_BORDER = "#7F1D1D"

# C. Typography Hierarchy
TEXT_PRIMARY = "#ECEEF2"                # 제목, 핵심 라벨, 활성 수치 (오프화이트)
TEXT_SECONDARY = "#9CA3AF"              # 본문 설명, 비활성 메뉴 항목
TEXT_MUTED = "#646B7A"                  # 인덱스 번호(01), 단위 표기, 플레이스홀더

# D. Font Stacks
FONT_SANS = '"Pretendard", "Segoe UI", "Malgun Gothic", "Noto Sans JP", sans-serif'
FONT_MONO = '"JetBrains Mono", "Cascadia Mono", "Consolas", monospace'

# Minimap Window Palette (절제된 Obsidian HUD 조화 톤)
MINIMAP_PALETTE: tuple[str, ...] = (
    ACCENT_AMBER,
    ACCENT_CYAN,
    STATUS_OK,
    STATUS_WARN,
    TEXT_SECONDARY,
)


def action_accent_color(action_type_str: str) -> str:
    """액션 유형을 Obsidian Tactile HUD 이원화 포인트 컬러(Amber/Cyan/Silver)로 매핑한다."""
    t = str(action_type_str).lower()
    if t in ("key_combo", "workspace_layout", "launch_app", "layer_shift"):
        return ACCENT_AMBER
    if t in ("zoom", "mouse_wheel", "brightness"):
        return ACCENT_CYAN
    return TEXT_SECONDARY


# ============================================================================
# 2. Windows 11 네이티브 다크 타이틀바 (DwmSetWindowAttribute)
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
    """Windows 10/11 OS 타이틀바를 Obsidian 다크 모드로 전환한다."""
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
# 3. Tactile Elevation QSS 생성 헬퍼 (Raised / Inset / Pressed)
# ============================================================================

def surface_panel_qss(object_name: str, radius: int = 6) -> str:
    """1px 헤어라인 구분선과 매트 흑요석 표면을 적용한 패널 스타일."""
    return (
        f"QFrame#{object_name} {{"
        f"  background-color: {BG_SURFACE};"
        f"  border: 1px solid {BORDER_HAIRLINE};"
        f"  border-radius: {radius}px;"
        "}"
    )


def raised_card_qss(
    object_name: str,
    selected: bool = False,
    border_accent: str | None = None,
    bg_override: str | None = None,
    radius: int = 6,
) -> str:
    """상단 1px 빛 반사(Bevel)와 좌우하단 음영을 가진 돌출(Raised) 카드 스타일."""
    bg = bg_override or (ACCENT_AMBER_BG if selected else BG_RAISED)
    if border_accent:
        return (
            f"QFrame#{object_name} {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border_accent};"
            f"  border-radius: {radius}px;"
            "}"
        )
    if selected:
        return (
            f"QFrame#{object_name} {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {ACCENT_AMBER};"
            f"  border-radius: {radius}px;"
            "}"
        )
    return (
        f"QFrame#{object_name} {{"
        f"  background-color: {bg};"
        f"  border: 1px solid {BORDER_RAISED_SIDE};"
        f"  border-top: 1px solid {BORDER_BEVEL};"
        f"  border-radius: {radius}px;"
        "}"
        f"QFrame#{object_name}:hover {{"
        f"  background-color: {BG_HOVER};"
        f"  border: 1px solid {BORDER_HAIRLINE};"
        f"  border-top: 1px solid {BORDER_BEVEL};"
        "}"
    )


def inset_slot_qss(object_name: str = "", radius: int = 4) -> str:
    """표면 안쪽으로 파인 음각(Inset) 슬롯/트랙 컨테이너 스타일."""
    selector = f"QFrame#{object_name}" if object_name else "QFrame"
    return (
        f"{selector} {{"
        f"  background-color: {BG_INSET};"
        f"  border: 1px solid {BORDER_HAIRLINE};"
        f"  border-top: 1px solid {BORDER_INSET_TOP};"
        f"  border-bottom: 1px solid {BORDER_INSET_BOTTOM};"
        f"  border-radius: {radius}px;"
        "}"
    )


def tactile_button_qss(
    variant: str = "default",
    radius: int = 4,
    padding: str = "0 10px",
    font_size: int = 11,
    bold: bool = False,
) -> str:
    """Raised -> Hover -> Pressed 물리 눌림 피드백을 지원하는 버튼 QSS."""
    weight = "700" if bold else "600"
    if variant == "amber":
        return (
            f"QPushButton {{ background-color: {ACCENT_AMBER_BG}; color: {ACCENT_AMBER_GLOW}; "
            f"border: 1px solid {ACCENT_AMBER_BORDER}; border-top: 1px solid {ACCENT_AMBER}; "
            f"border-radius: {radius}px; padding: {padding}; font-size: {font_size}px; font-weight: 700; }}"
            f"QPushButton:hover {{ background-color: #302018; border-color: {ACCENT_AMBER_GLOW}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background-color: {BG_SURFACE}; border: 1px solid {ACCENT_AMBER_BORDER}; }}"
        )
    if variant == "amber_solid":
        return (
            f"QPushButton {{ background-color: {ACCENT_AMBER}; color: {BG_BASE}; "
            f"border: 1px solid {ACCENT_AMBER_BORDER}; border-top: 1px solid {ACCENT_AMBER_GLOW}; "
            f"border-radius: {radius}px; padding: {padding}; font-size: {font_size}px; font-weight: 800; }}"
            f"QPushButton:hover {{ background-color: {ACCENT_AMBER_GLOW}; }}"
            f"QPushButton:pressed {{ background-color: #C9642D; border-top: 1px solid {ACCENT_AMBER_BORDER}; }}"
        )
    if variant == "cyan":
        return (
            f"QPushButton {{ background-color: {ACCENT_CYAN_BG}; color: {ACCENT_CYAN}; "
            f"border: 1px solid {ACCENT_CYAN_BORDER}; border-top: 1px solid {ACCENT_CYAN}; "
            f"border-radius: {radius}px; padding: {padding}; font-size: {font_size}px; font-weight: 700; }}"
            f"QPushButton:hover {{ background-color: #192A36; border-color: {ACCENT_CYAN}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background-color: {BG_SURFACE}; border: 1px solid {ACCENT_CYAN_BORDER}; }}"
        )
    if variant == "danger":
        return (
            f"QPushButton {{ background-color: {STATUS_DANGER_BG}; color: {STATUS_DANGER}; "
            f"border: 1px solid {STATUS_DANGER_BORDER}; border-radius: {radius}px; "
            f"padding: {padding}; font-size: {font_size}px; font-weight: {weight}; }}"
            f"QPushButton:hover {{ background-color: #35191C; border-color: {STATUS_DANGER}; }}"
            f"QPushButton:pressed {{ background-color: {BG_SURFACE}; }}"
        )
    if variant == "ghost":
        return (
            f"QPushButton {{ background-color: transparent; color: {TEXT_SECONDARY}; "
            f"border: 1px solid transparent; border-radius: {radius}px; "
            f"padding: {padding}; font-size: {font_size}px; font-weight: {weight}; }}"
            f"QPushButton:hover {{ background-color: {BG_HOVER}; color: {TEXT_PRIMARY}; border-color: {BORDER_HAIRLINE}; }}"
            f"QPushButton:pressed {{ background-color: {BG_SURFACE}; }}"
        )
    if variant == "ghost_danger":
        return (
            f"QPushButton {{ background-color: transparent; color: {TEXT_MUTED}; "
            f"border: 1px solid transparent; border-radius: {radius}px; "
            f"padding: {padding}; font-size: {font_size}px; font-weight: 700; }}"
            f"QPushButton:hover {{ background-color: {STATUS_DANGER_BG}; color: {STATUS_DANGER}; border-color: {STATUS_DANGER_BORDER}; }}"
            f"QPushButton:pressed {{ background-color: {BG_SURFACE}; }}"
        )
    # default Raised button
    return (
        f"QPushButton {{ background-color: {BG_RAISED}; color: {TEXT_PRIMARY}; "
        f"border: 1px solid {BORDER_RAISED_SIDE}; border-top: 1px solid {BORDER_BEVEL}; "
        f"border-radius: {radius}px; padding: {padding}; font-size: {font_size}px; font-weight: {weight}; }}"
        f"QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {BORDER_BEVEL}; color: {ACCENT_AMBER_GLOW}; }}"
        f"QPushButton:pressed {{ background-color: {BG_SURFACE}; border: 1px solid {BORDER_HAIRLINE}; }}"
    )


def section_header_qss(color: str = TEXT_PRIMARY) -> str:
    """건축 계기판 라벨 감성의 대문자 섹션 헤더 스타일."""
    return (
        f"color: {color}; font-size: 11px; font-weight: 800; "
        "letter-spacing: 0.9px; border: none; background: transparent;"
    )


def badge_qss(
    fg: str,
    bg: str,
    border: str,
    mono: bool = True,
    left_accent: str | None = None,
    padding: str = "2px 8px",
    font_size: int = 10,
) -> str:
    """4px 절제된 모서리의 상태·카테고리 배지 QSS."""
    font_rule = f"font-family: {FONT_MONO};" if mono else ""
    left_rule = f"border-left: 2px solid {left_accent};" if left_accent else ""
    return (
        f"color: {fg}; background-color: {bg}; border: 1px solid {border}; {left_rule} "
        f"border-radius: 4px; padding: {padding}; {font_rule} "
        f"font-size: {font_size}px; font-weight: 700;"
    )


# ============================================================================
# 4. 중앙화된 Obsidian Tactile HUD 전역 스타일시트
# ============================================================================

OBSIDIAN_TACTILE_HUD_QSS = f"""
QMainWindow, QWidget#RootCentral {{
    background-color: {BG_BASE};
    color: {TEXT_PRIMARY};
    font-family: {FONT_SANS};
}}
QDialog, QMessageBox {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    font-family: {FONT_SANS};
}}
QMenu {{
    background-color: {BG_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 16px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_AMBER_BG};
    color: {ACCENT_AMBER_GLOW};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER_HAIRLINE};
    margin: 4px 8px;
}}
QSplitter::handle {{
    background-color: transparent;
}}
QComboBox, QLineEdit {{
    background-color: {BG_INSET};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-top: 1px solid {BORDER_INSET_TOP};
    border-bottom: 1px solid {BORDER_INSET_BOTTOM};
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
}}
QComboBox:hover, QLineEdit:hover {{
    border-color: {BORDER_BEVEL};
}}
QComboBox:focus, QLineEdit:focus {{
    border: 1px solid {ACCENT_AMBER};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_RAISED};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_AMBER_BG};
    selection-color: {ACCENT_AMBER_GLOW};
    border: 1px solid {BORDER_HAIRLINE};
    outline: 0px;
}}
QListWidget {{
    background-color: {BG_INSET};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-top: 1px solid {BORDER_INSET_TOP};
    border-bottom: 1px solid {BORDER_INSET_BOTTOM};
    border-radius: 4px;
    font-size: 11px;
    outline: 0px;
}}
QListWidget::item {{
    padding: 6px 10px;
    border-bottom: 1px solid #181A20;
}}
QListWidget::item:hover {{
    background-color: {BG_SURFACE};
}}
QListWidget::item:selected {{
    background-color: {ACCENT_AMBER_BG};
    color: {ACCENT_AMBER_GLOW};
    border-left: 3px solid {ACCENT_AMBER};
}}
QPlainTextEdit {{
    background-color: {BG_INSET};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-top: 1px solid {BORDER_INSET_TOP};
    border-bottom: 1px solid {BORDER_INSET_BOTTOM};
    border-radius: 4px;
    font-family: {FONT_MONO};
    font-size: 10.5px;
}}
QTextBrowser {{
    background-color: {BG_INSET};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HAIRLINE};
    border-top: 1px solid {BORDER_INSET_TOP};
    border-bottom: 1px solid {BORDER_INSET_BOTTOM};
    border-radius: 6px;
    padding: 16px;
    font-size: 12px;
}}
QScrollBar:vertical {{
    background: {BG_INSET};
    width: 6px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_HAIRLINE};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_AMBER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {BG_INSET};
    height: 6px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_HAIRLINE};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT_AMBER};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
"""

# 하위 호환 별칭
ARCHITECTURAL_HUD_QSS = OBSIDIAN_TACTILE_HUD_QSS
