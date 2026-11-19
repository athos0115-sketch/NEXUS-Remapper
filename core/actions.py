"""통합 액션 출력기 모듈 (64비트 Win32 SendInput & 클립보드/시스템 제어).

표준 `ActionSpec` 인터페이스를 통해 아래 6대 액션 카테고리를 실행한다:
1. 복합 단축키 (Key Combos) — `SendInput` 기반 저지연 키 조합 주입
2. 마우스 휠 및 줌 제어 (Mouse Wheel / Zoom) — 가속 배율 적용 `Ctrl+Wheel` 및 스크롤
3. 상용구 텍스트 주입 (Text Injection) — 클립보드 백업/복원 기반 고속 붙여넣기 및 Unicode 직접 입력
4. 미디어 및 시스템 제어 (Media / System) — 볼륨, 음소거, 트랙 이동, 밝기 제어
5. 창 레이아웃 및 앱 실행 (Workspace / App) — 레이아웃 프리셋 호출 및 프로그램 실행
6. 멀티 레이어 전환 (Layer Shift) — 단일 장치 내 다중 작업 레이어 실시간 전환
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from core.events import InputEvent

try:
    import pyperclip  # type: ignore[import-not-found]
except ImportError:
    pyperclip = None


# ============================================================================
# Win32 SendInput / Clipboard 64비트 ctypes 구조체 및 API 선언
# ============================================================================

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000

WHEEL_DELTA = 120
MAPVK_VK_TO_VSC = 0

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

ULONG_PTR = (
    ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
)


class MOUSEINPUT(ctypes.Structure):
    """Win32 `MOUSEINPUT` 구조체."""

    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    """Win32 `KEYBDINPUT` 구조체."""

    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    """Win32 `HARDWAREINPUT` 구조체."""

    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    """64비트 환경에서 `INPUT` 크기(40바이트)를 맞추기 위해 3종 구조체를 모두 포함한다."""

    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    """Win32 `INPUT` 구조체 (64비트 환경 기준 40바이트)."""

    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.SendInput.argtypes = [
    wintypes.UINT,
    ctypes.POINTER(INPUT),
    ctypes.c_int,
]
_user32.SendInput.restype = wintypes.UINT

_user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_user32.MapVirtualKeyW.restype = wintypes.UINT

_user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
_user32.VkKeyScanW.restype = ctypes.c_short

_user32.GetKeyNameTextW.argtypes = [wintypes.LONG, wintypes.LPWSTR, ctypes.c_int]
_user32.GetKeyNameTextW.restype = ctypes.c_int

_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL

_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = wintypes.BOOL

_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = wintypes.BOOL

_user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
_user32.IsClipboardFormatAvailable.restype = wintypes.BOOL

_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.GetClipboardData.restype = wintypes.HANDLE

_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE

_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL

_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL

_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p

_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL


# ============================================================================
# 가상 키(VK) 코드 테이블
# ============================================================================

VK_MAP: dict[str, int] = {
    # 제어/수정자 키
    "ctrl": 0x11,
    "control": 0x11,
    "lctrl": 0xA2,
    "rctrl": 0xA3,
    "shift": 0x10,
    "lshift": 0xA0,
    "rshift": 0xA1,
    "alt": 0x12,
    "menu": 0x12,
    "lalt": 0xA4,
    "ralt": 0xA5,
    "win": 0x5B,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "apps": 0x5D,
    # 탐색/편집 키
    "backspace": 0x08,
    "bs": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "insert": 0x2D,
    "ins": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    # 넘패드
    "numlock": 0x90,
    "num0": 0x60,
    "num1": 0x61,
    "num2": 0x62,
    "num3": 0x63,
    "num4": 0x64,
    "num5": 0x65,
    "num6": 0x66,
    "num7": 0x67,
    "num8": 0x68,
    "num9": 0x69,
    "num*": 0x6A,
    "num+": 0x6B,
    "num-": 0x6D,
    "num.": 0x6E,
    "num/": 0x6F,
    # OEM 기호
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
    # 미디어 키
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3,
}

# F1 ~ F24 동적 등록
for _fn_idx in range(1, 25):
    VK_MAP[f"f{_fn_idx}"] = 0x6F + _fn_idx

# 확장 키 플래그(KEYEVENTF_EXTENDEDKEY)가 필요한 VK 집합
EXTENDED_VKS: frozenset[int] = frozenset(
    {
        0x21, 0x22, 0x23, 0x24,  # PgUp, PgDn, End, Home
        0x25, 0x26, 0x27, 0x28,  # Left, Up, Right, Down
        0x2C, 0x2D, 0x2E,        # PrintScreen, Insert, Delete
        0x5B, 0x5C, 0x5D,        # LWin, RWin, Apps
        0x6F, 0x90,              # Numpad Divide, NumLock
        0xA3, 0xA5,              # RCtrl, RAlt
        0xAD, 0xAE, 0xAF,        # Volume keys
        0xB0, 0xB1, 0xB2, 0xB3,  # Media keys
    }
)

MEDIA_COMMAND_VKS: dict[str, int] = {
    "mute": 0xAD,
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "vol_down": 0xAE,
    "volume_up": 0xAF,
    "vol_up": 0xAF,
    "next": 0xB0,
    "next_track": 0xB0,
    "prev": 0xB1,
    "prev_track": 0xB1,
    "stop": 0xB2,
    "play_pause": 0xB3,
}


def resolve_vk(key: str | int) -> int:
    """키 이름 또는 정수 코드를 Win32 가상 키(VK) 코드로 변환한다."""
    if isinstance(key, int):
        return key

    token = key.strip().lower()
    if token in VK_MAP:
        return VK_MAP[token]

    if token.startswith("0x"):
        return int(token, 16)

    if len(token) == 1:
        ch = token.upper()
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            return ord(ch)
        vk_scan = _user32.VkKeyScanW(token)
        if vk_scan != -1:
            return vk_scan & 0xFF

    raise ValueError(f"Unsupported key token: '{key}'")


_CONSUMER_USAGE_LABELS: dict[int, str] = {
    0x00E9: "DIAL CW ↻",
    0x00EA: "DIAL CCW ↺",
    0x00E2: "KNOB MUTE",
    0x00B5: "KNOB CLICK",
    0x00B6: "PREV TRACK",
    0x00B7: "STOP",
    0x00CD: "PLAY/PAUSE",
}

_MOUSE_BUTTON_LABELS: dict[int, str] = {
    1: "MOUSE L",
    2: "MOUSE R",
    3: "MOUSE M",
    4: "MOUSE X1",
    5: "MOUSE X2",
}


def format_trigger_label(
    event_type: str, code: int | str, is_extended: bool = False
) -> str:
    """스캔코드/HID Usage/마우스 코드를 사람이 바로 읽는 물리 키캡 라벨로 변환한다."""
    et = str(event_type).lower()

    if et == "dial_cw":
        return "DIAL CW ↻"
    if et == "dial_ccw":
        return "DIAL CCW ↺"
    if et == "dial_double_click":
        return "DBL CLICK"
    if et == "dial_long_press":
        return "LONG PRESS"
    if et in ("dial_press", "dial_release"):
        if isinstance(code, int) and code in _CONSUMER_USAGE_LABELS:
            return _CONSUMER_USAGE_LABELS[code]
        return f"DIAL 0x{code:02X}" if isinstance(code, int) else str(code)

    if et == "mouse_button":
        if isinstance(code, int):
            return _MOUSE_BUTTON_LABELS.get(code, f"BTN {code}")
        return str(code)

    if et in ("key", "key_down", "key_up") and isinstance(code, int) and code > 0:
        lparam = (code & 0xFF) << 16
        if is_extended:
            lparam |= 1 << 24
        buf = ctypes.create_unicode_buffer(64)
        length = _user32.GetKeyNameTextW(lparam, buf, 64)
        if length > 0 and buf.value.strip():
            label = buf.value.strip().upper()
            # 'NUM 7', 'NUM +', 'ENTER' 등 간결 표기 정돈
            label = label.replace("NUM ", "NUM")
            if len(label) <= 10:
                return label
            return label[:10]
        return f"SC 0x{code:02X}"

    return f"0x{code:04X}" if isinstance(code, int) else str(code)


class Win32Clipboard:
    """`pyperclip` 미설치 환경에서도 동작하는 64비트 Win32 유니코드 클립보드 헬퍼."""

    @staticmethod
    def get_text() -> str | None:
        """현재 클립보드의 유니코드 텍스트를 읽어온다. 텍스트가 아니면 None 반환."""
        if pyperclip is not None:
            try:
                return str(pyperclip.paste())
            except Exception:
                pass

        for _ in range(5):
            if _user32.OpenClipboard(None):
                break
            time.sleep(0.005)
        else:
            return None

        try:
            if not _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return None
            handle = _user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            ptr = _kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                _kernel32.GlobalUnlock(handle)
        finally:
            _user32.CloseClipboard()

    @staticmethod
    def set_text(text: str) -> bool:
        """클립보드에 유니코드 텍스트를 기록한다."""
        if pyperclip is not None:
            try:
                pyperclip.copy(text)
                return True
            except Exception:
                pass

        encoded = (text + "\0").encode("utf-16-le")
        h_mem = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False

        ptr = _kernel32.GlobalLock(h_mem)
        if not ptr:
            _kernel32.GlobalFree(h_mem)
            return False

        try:
            ctypes.memmove(ptr, encoded, len(encoded))
        finally:
            _kernel32.GlobalUnlock(h_mem)

        for _ in range(5):
            if _user32.OpenClipboard(None):
                break
            time.sleep(0.005)
        else:
            _kernel32.GlobalFree(h_mem)
            return False

        try:
            _user32.EmptyClipboard()
            if not _user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                _kernel32.GlobalFree(h_mem)
                return False
            # SetClipboardData 성공 시 OS가 h_mem 소유권을 가져감
            return True
        finally:
            _user32.CloseClipboard()


# ============================================================================
# 액션 명세 데이터 모델
# ============================================================================


class ActionType(str, Enum):
    """NEXUS 6대 표준 액션 카테고리."""

    KEY_COMBO = "key_combo"
    MOUSE_WHEEL = "mouse_wheel"
    ZOOM = "zoom"
    TEXT = "text"
    MEDIA = "media"
    BRIGHTNESS = "brightness"
    LAUNCH_APP = "launch_app"
    WORKSPACE_LAYOUT = "workspace_layout"
    LAYER_SHIFT = "layer_shift"
    NONE = "none"


@dataclass(frozen=True)
class ActionMeta:
    """확장형 액션 레지스트리에 등록되는 액션 메타데이터 및 실행 핸들러."""

    action_type: str
    display_name: str
    tag_label: str
    accent_color: str
    placeholder: str
    handler: Callable[[Any, dict[str, Any], InputEvent | None], ActionResult]


ACTION_REGISTRY: dict[str, ActionMeta] = {}


def register_action(
    action_type: ActionType | str,
    display_name: str = "",
    tag_label: str = "",
    accent_color: str = "#94A3B8",
    placeholder: str = "",
) -> Callable[
    [Callable[[Any, dict[str, Any], InputEvent | None], ActionResult]],
    Callable[[Any, dict[str, Any], InputEvent | None], ActionResult],
]:
    """새로운 실행 액션 카테고리를 전역 `ACTION_REGISTRY`에 등록하는 데코레이터."""
    key = action_type.value if isinstance(action_type, ActionType) else str(action_type)

    def _decorator(
        fn: Callable[[Any, dict[str, Any], InputEvent | None], ActionResult],
    ) -> Callable[[Any, dict[str, Any], InputEvent | None], ActionResult]:
        ACTION_REGISTRY[key] = ActionMeta(
            action_type=key,
            display_name=display_name or key,
            tag_label=tag_label or key.upper(),
            accent_color=accent_color,
            placeholder=placeholder,
            handler=fn,
        )
        return fn

    return _decorator


def get_registered_actions() -> list[ActionMeta]:
    """등록된 모든 액션 메타데이터를 등록 순서대로 반환한다."""
    return list(ACTION_REGISTRY.values())


def get_action_meta(action_type: ActionType | str) -> ActionMeta | None:
    """액션 타입 키로 등록된 메타데이터를 조회한다."""
    key = action_type.value if isinstance(action_type, ActionType) else str(action_type)
    return ACTION_REGISTRY.get(key)


@dataclass
class ActionSpec:
    """직렬화 가능한 단일 액션 정의 객체."""

    action_type: ActionType | str
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""

    @property
    def type_name(self) -> str:
        """확장 액션을 포함한 액션 타입 문자열을 반환한다."""
        if isinstance(self.action_type, ActionType):
            return self.action_type.value
        return str(self.action_type)

    @property
    def type_enum(self) -> ActionType:
        """문자열/열거형 구분 없이 `ActionType` 열거형을 반환한다."""
        if isinstance(self.action_type, ActionType):
            return self.action_type
        return ActionType(str(self.action_type))

    def to_dict(self) -> dict[str, Any]:
        """`config.json` 저장용 딕셔너리로 직렬화한다."""
        return {
            "action_type": self.type_name,
            "params": dict(self.params),
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionSpec:
        """딕셔너리에서 `ActionSpec`을 복원한다."""
        return cls(
            action_type=str(data.get("action_type", ActionType.NONE.value)),
            params=dict(data.get("params", {})),
            label=str(data.get("label", "")),
        )


@dataclass
class ActionResult:
    """액션 실행 결과 보고 객체."""

    success: bool
    action_type: str
    detail: str = ""
    dry_run: bool = False


# ============================================================================
# 통합 액션 실행기
# ============================================================================


class ActionExecutor:
    """Win32 SendInput 및 시스템/워크스페이스 액션을 수행하는 중앙 디스패처."""

    def __init__(
        self,
        dry_run: bool = False,
        layout_handler: Callable[[str], bool] | None = None,
        layer_change_handler: Callable[[str], None] | None = None,
        layers: list[str] | None = None,
    ) -> None:
        self.dry_run = dry_run
        self._layout_handler = layout_handler
        self._layer_change_handler = layer_change_handler
        self._layers: list[str] = list(layers or ["default"])
        self._active_layer: str = self._layers[0]

    @property
    def active_layer(self) -> str:
        """현재 활성화된 멀티 레이어 이름을 반환한다."""
        return self._active_layer

    def set_layers(self, layers: list[str]) -> None:
        """사용 가능한 레이어 목록을 갱신한다."""
        if layers:
            self._layers = list(layers)
            if self._active_layer not in self._layers:
                self._active_layer = self._layers[0]

    def register_layout_handler(self, handler: Callable[[str], bool]) -> None:
        """Phase 3 `WindowOrchestrator`의 레이아웃 적용 콜백을 주입한다."""
        self._layout_handler = handler

    def register_layer_change_handler(self, handler: Callable[[str], None]) -> None:
        """레이어 전환 시 UI/엔진에 알릴 콜백을 등록한다."""
        self._layer_change_handler = handler

    def _send_inputs(self, inputs: list[INPUT]) -> int:
        """`INPUT` 배열을 Win32 `SendInput`으로 일괄 전송한다."""
        if not inputs or self.dry_run:
            return len(inputs)
        arr = (INPUT * len(inputs))(*inputs)
        sent = _user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
        if sent == 0:
            err = ctypes.get_last_error()
            raise OSError(err, f"SendInput failed (err={err})")
        return int(sent)

    @staticmethod
    def _make_key_input(vk: int, key_up: bool = False) -> INPUT:
        """단일 키 누름/뗌 `INPUT` 구조체를 생성한다."""
        scan = _user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC) & 0xFFFF
        flags = KEYEVENTF_KEYUP if key_up else 0
        if vk in EXTENDED_VKS:
            flags |= KEYEVENTF_EXTENDEDKEY
        return INPUT(
            type=INPUT_KEYBOARD,
            u=_INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=vk,
                    wScan=scan,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )

    @staticmethod
    def _make_unicode_input(char: str, key_up: bool = False) -> INPUT:
        """유니코드 문자 직접 주입용 `INPUT` 구조체를 생성한다."""
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
        return INPUT(
            type=INPUT_KEYBOARD,
            u=_INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=ord(char),
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )

    @staticmethod
    def _make_wheel_input(delta: int, horizontal: bool = False) -> INPUT:
        """마우스 수직/수평 휠 `INPUT` 구조체를 생성한다."""
        flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
        # 음수 스크롤은 부호 없는 32비트 DWORD로 래핑해야 Win32에서 정상 인식됨
        unsigned_delta = delta & 0xFFFFFFFF
        return INPUT(
            type=INPUT_MOUSE,
            u=_INPUT_UNION(
                mi=MOUSEINPUT(
                    dx=0,
                    dy=0,
                    mouseData=unsigned_delta,
                    dwFlags=flag,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )

    def send_key_combo(
        self, combo: str | list[str | int], hold_ms: int = 0
    ) -> ActionResult:
        """1. 복합 단축키(`Ctrl+Shift+S` 등)를 `SendInput`으로 주입한다."""
        if isinstance(combo, str):
            tokens = [t.strip() for t in combo.split("+") if t.strip()]
        else:
            tokens = list(combo)

        if not tokens:
            return ActionResult(False, ActionType.KEY_COMBO.value, "Empty key combo", self.dry_run)

        vks = [resolve_vk(tok) for tok in tokens]
        down_inputs = [self._make_key_input(vk, key_up=False) for vk in vks]
        up_inputs = [self._make_key_input(vk, key_up=True) for vk in reversed(vks)]

        if hold_ms > 0 and not self.dry_run:
            self._send_inputs(down_inputs)
            time.sleep(hold_ms / 1000.0)
            self._send_inputs(up_inputs)
        else:
            self._send_inputs(down_inputs + up_inputs)

        return ActionResult(
            True,
            ActionType.KEY_COMBO.value,
            f"Sent combo: {'+'.join(str(t) for t in tokens)}",
            self.dry_run,
        )

    def send_mouse_wheel(
        self,
        direction: int = 1,
        steps: int = 1,
        accel: float = 1.0,
        horizontal: bool = False,
        modifiers: list[str] | str | None = None,
    ) -> ActionResult:
        """2. 가속 배율이 적용된 마우스 휠 및 `Ctrl+Wheel` 줌 입력을 전송한다."""
        signed_delta = int(round(WHEEL_DELTA * steps * accel * (1 if direction >= 0 else -1)))
        if signed_delta == 0:
            signed_delta = WHEEL_DELTA if direction >= 0 else -WHEEL_DELTA

        mod_vks: list[int] = []
        if isinstance(modifiers, str):
            mod_vks = [resolve_vk(m) for m in modifiers.split("+") if m.strip()]
        elif modifiers:
            mod_vks = [resolve_vk(m) for m in modifiers]

        seq: list[INPUT] = [self._make_key_input(vk, key_up=False) for vk in mod_vks]
        seq.append(self._make_wheel_input(signed_delta, horizontal=horizontal))
        seq.extend(self._make_key_input(vk, key_up=True) for vk in reversed(mod_vks))

        self._send_inputs(seq)
        return ActionResult(
            True,
            ActionType.ZOOM.value if mod_vks else ActionType.MOUSE_WHEEL.value,
            f"Wheel delta={signed_delta} horizontal={horizontal} mods={len(mod_vks)}",
            self.dry_run,
        )

    def inject_text(
        self,
        text: str,
        method: str = "clipboard",
        restore_delay_ms: int = 60,
    ) -> ActionResult:
        """3. 상용구 텍스트를 클립보드 백업/복원 또는 Unicode 직접 입력으로 주입한다."""
        if not text:
            return ActionResult(False, ActionType.TEXT.value, "Empty text", self.dry_run)

        if method == "unicode":
            seq: list[INPUT] = []
            for ch in text:
                if ch == "\n":
                    seq.append(self._make_key_input(0x0D, key_up=False))
                    seq.append(self._make_key_input(0x0D, key_up=True))
                else:
                    seq.append(self._make_unicode_input(ch, key_up=False))
                    seq.append(self._make_unicode_input(ch, key_up=True))
            self._send_inputs(seq)
            return ActionResult(
                True, ActionType.TEXT.value, f"Unicode injected ({len(text)} chars)", self.dry_run
            )

        if self.dry_run:
            return ActionResult(
                True, ActionType.TEXT.value, f"Clipboard paste simulated ({len(text)} chars)", True
            )

        previous = Win32Clipboard.get_text()
        if not Win32Clipboard.set_text(text):
            return ActionResult(False, ActionType.TEXT.value, "Failed to write clipboard", False)

        try:
            self.send_key_combo(["ctrl", "v"])
            time.sleep(max(restore_delay_ms, 20) / 1000.0)
        finally:
            if previous is not None:
                Win32Clipboard.set_text(previous)

        return ActionResult(
            True, ActionType.TEXT.value, f"Clipboard pasted ({len(text)} chars)", False
        )

    def execute_media_action(self, command: str, repeat: int = 1) -> ActionResult:
        """4-A. 미디어 및 볼륨 제어 키를 전송한다."""
        cmd_key = command.strip().lower()
        if cmd_key not in MEDIA_COMMAND_VKS:
            return ActionResult(
                False, ActionType.MEDIA.value, f"Unknown media command: {command}", self.dry_run
            )

        vk = MEDIA_COMMAND_VKS[cmd_key]
        seq: list[INPUT] = []
        for _ in range(max(1, repeat)):
            seq.append(self._make_key_input(vk, key_up=False))
            seq.append(self._make_key_input(vk, key_up=True))
        self._send_inputs(seq)
        return ActionResult(
            True, ActionType.MEDIA.value, f"Media command: {cmd_key} x{max(1, repeat)}", self.dry_run
        )

    def execute_brightness_action(self, delta: int = 10) -> ActionResult:
        """4-B. WMI를 통해 내장 디스플레이 밝기를 상대 조절한다."""
        if self.dry_run:
            return ActionResult(
                True, ActionType.BRIGHTNESS.value, f"Brightness delta={delta}", True
            )

        ps_script = (
            "$b = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness; "
            f"$target = [Math]::Max(0, [Math]::Min(100, $b + ({int(delta)}))); "
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, $target)"
        )
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            return ActionResult(
                True, ActionType.BRIGHTNESS.value, f"Brightness delta={delta}", False
            )
        except OSError as exc:
            return ActionResult(False, ActionType.BRIGHTNESS.value, str(exc), False)

    def launch_app(
        self,
        executable: str,
        args: list[str] | None = None,
        cwd: str | None = None,
    ) -> ActionResult:
        """5-A. 외부 애플리케이션을 비동기 분리 프로세스로 실행한다."""
        if not executable:
            return ActionResult(False, ActionType.LAUNCH_APP.value, "Empty executable path", self.dry_run)

        if self.dry_run:
            return ActionResult(
                True, ActionType.LAUNCH_APP.value, f"Launch simulated: {executable}", True
            )

        cmd = [executable, *(args or [])]
        creation_flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )
        try:
            work_dir = cwd if cwd and os.path.isdir(cwd) else None
            subprocess.Popen(
                cmd,
                cwd=work_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            return ActionResult(
                True, ActionType.LAUNCH_APP.value, f"Launched: {executable}", False
            )
        except OSError as exc:
            return ActionResult(False, ActionType.LAUNCH_APP.value, str(exc), False)

    def apply_layout_preset(self, preset_name: str) -> ActionResult:
        """5-B. 등록된 `WindowOrchestrator` 핸들러를 통해 모니터 창 레이아웃을 적용한다."""
        if not preset_name:
            return ActionResult(False, ActionType.WORKSPACE_LAYOUT.value, "Empty preset name", self.dry_run)

        if self.dry_run:
            return ActionResult(
                True, ActionType.WORKSPACE_LAYOUT.value, f"Layout simulated: {preset_name}", True
            )

        if self._layout_handler is None:
            return ActionResult(
                False,
                ActionType.WORKSPACE_LAYOUT.value,
                "Layout handler is not registered (available in Phase 3)",
                False,
            )

        ok = bool(self._layout_handler(preset_name))
        return ActionResult(
            ok,
            ActionType.WORKSPACE_LAYOUT.value,
            f"Layout '{preset_name}' applied={ok}",
            False,
        )

    def shift_layer(self, layer: str = "", mode: str = "set") -> ActionResult:
        """6. 멀티 레이어(`default`, `bim`, `media` 등)를 전환한다."""
        if mode == "cycle" and self._layers:
            idx = self._layers.index(self._active_layer) if self._active_layer in self._layers else -1
            target = self._layers[(idx + 1) % len(self._layers)]
        elif layer:
            target = layer
            if target not in self._layers:
                self._layers.append(target)
        else:
            return ActionResult(False, ActionType.LAYER_SHIFT.value, "No target layer", self.dry_run)

        self._active_layer = target
        if self._layer_change_handler is not None:
            self._layer_change_handler(target)

        return ActionResult(
            True, ActionType.LAYER_SHIFT.value, f"Active layer -> {target}", self.dry_run
        )

    @register_action(
        ActionType.KEY_COMBO,
        display_name="복합 단축키",
        tag_label="KEY COMBO",
        accent_color="#00FFCC",
        placeholder="예: Ctrl+Shift+S, Alt+Tab, F5",
    )
    def _handle_key_combo(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        del event
        return self.send_key_combo(
            combo=p.get("combo", p.get("keys", "")),
            hold_ms=int(p.get("hold_ms", 0)),
        )

    @register_action(
        ActionType.ZOOM,
        display_name="정밀 줌 (Ctrl+Wheel)",
        tag_label="ZOOM",
        accent_color="#F97316",
        placeholder="방향(:배율) 예: 1:1.5 또는 -1:1.5",
    )
    def _handle_zoom(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        base_accel = float(p.get("accel", 1.0))
        vel = float(event.velocity) if (event is not None and p.get("dynamic_accel", True)) else 1.0
        return self.send_mouse_wheel(
            direction=int(p.get("direction", 1)),
            steps=int(p.get("steps", 1)),
            accel=round(base_accel * vel, 2),
            horizontal=False,
            modifiers=p.get("modifiers", ["ctrl"]),
        )

    @register_action(
        ActionType.MOUSE_WHEEL,
        display_name="마우스 스크롤 휠",
        tag_label="WHEEL",
        accent_color="#F97316",
        placeholder="방향(:배율) 예: 1:1.0 또는 -1:2.0",
    )
    def _handle_mouse_wheel(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        base_accel = float(p.get("accel", 1.0))
        vel = float(event.velocity) if (event is not None and p.get("dynamic_accel", True)) else 1.0
        return self.send_mouse_wheel(
            direction=int(p.get("direction", 1)),
            steps=int(p.get("steps", 1)),
            accel=round(base_accel * vel, 2),
            horizontal=bool(p.get("horizontal", False)),
            modifiers=p.get("modifiers"),
        )

    @register_action(
        ActionType.WORKSPACE_LAYOUT,
        display_name="창 레이아웃 실행",
        tag_label="WORKSPACE",
        accent_color="#A855F7",
        placeholder="저장된 창 레이아웃 프리셋 선택",
    )
    def _handle_workspace_layout(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        del event
        return self.apply_layout_preset(preset_name=str(p.get("preset", "")))

    @register_action(
        ActionType.LAUNCH_APP,
        display_name="앱 실행",
        tag_label="APP LAUNCH",
        accent_color="#A855F7",
        placeholder="실행 파일 경로 예: notepad.exe",
    )
    def _handle_launch_app(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        del event
        return self.launch_app(
            executable=str(p.get("executable", p.get("path", ""))),
            args=p.get("args"),
            cwd=p.get("cwd"),
        )

    @register_action(
        ActionType.TEXT,
        display_name="상용구 텍스트 주입",
        tag_label="TEXT",
        accent_color="#94A3B8",
        placeholder="주입할 상용구 텍스트",
    )
    def _handle_text(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        del event
        return self.inject_text(
            text=str(p.get("text", "")),
            method=str(p.get("method", "clipboard")),
            restore_delay_ms=int(p.get("restore_delay_ms", 60)),
        )

    @register_action(
        ActionType.MEDIA,
        display_name="미디어 / 볼륨 제어",
        tag_label="MEDIA",
        accent_color="#94A3B8",
        placeholder="volume_up / volume_down / mute / play_pause",
    )
    def _handle_media(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        del event
        return self.execute_media_action(
            command=str(p.get("command", "")),
            repeat=int(p.get("repeat", 1)),
        )

    @register_action(
        ActionType.BRIGHTNESS,
        display_name="화면 밝기 조절",
        tag_label="SYSTEM",
        accent_color="#94A3B8",
        placeholder="밝기 변화량 예: 10 또는 -10",
    )
    def _handle_brightness(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        del event
        return self.execute_brightness_action(delta=int(p.get("delta", 10)))

    @register_action(
        ActionType.LAYER_SHIFT,
        display_name="멀티 레이어 전환",
        tag_label="LAYER",
        accent_color="#94A3B8",
        placeholder="레이어명(bim/media) 또는 cycle",
    )
    def _handle_layer_shift(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        del event
        return self.shift_layer(
            layer=str(p.get("layer", "")),
            mode=str(p.get("mode", "set")),
        )

    @register_action(
        ActionType.NONE,
        display_name="동작 없음",
        tag_label="NONE",
        accent_color="#64748B",
        placeholder="동작 없음",
    )
    def _handle_none(
        self, p: dict[str, Any], event: InputEvent | None
    ) -> ActionResult:
        del p, event
        return ActionResult(True, ActionType.NONE.value, "No-op", self.dry_run)

    def execute(
        self, spec: ActionSpec | dict[str, Any], event: InputEvent | None = None
    ) -> ActionResult:
        """`@register_action` 레지스트리를 조회하여 해당 액션 핸들러로 디스패치한다."""
        action = spec if isinstance(spec, ActionSpec) else ActionSpec.from_dict(spec)
        type_key = action.type_name
        meta = ACTION_REGISTRY.get(type_key)
        if meta is None:
            return ActionResult(
                False, type_key, f"Unsupported action type: {type_key}", self.dry_run
            )
        return meta.handler(self, action.params, event)


if __name__ == "__main__":
    print(f"[ActionExecutor] 64-bit INPUT struct size = {ctypes.sizeof(INPUT)} bytes")
    executor = ActionExecutor(dry_run=True, layers=["default", "bim", "media"])
    for sample in [
        ActionSpec(ActionType.KEY_COMBO, {"combo": "Ctrl+Shift+S"}),
        ActionSpec(ActionType.ZOOM, {"direction": 1, "accel": 1.5}),
        ActionSpec(ActionType.TEXT, {"text": "NEXUS_TEST"}),
        ActionSpec(ActionType.MEDIA, {"command": "volume_up"}),
        ActionSpec(ActionType.WORKSPACE_LAYOUT, {"preset": "Dual_CAD"}),
        ActionSpec(ActionType.LAYER_SHIFT, {"mode": "cycle"}),
    ]:
        print(" ->", executor.execute(sample))
