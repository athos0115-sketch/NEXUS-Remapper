"""DPI V2 비율 기반 다중 모니터 창 오케스트레이터 및 스냅샷 캡처 모듈.

절대 픽셀(px) 저장을 배제하고 각 모니터 작업 영역(`rcWork`) 기준 정규화 비율(`0.0 ~ 1.0`)로
창 배치를 계산·저장하며, 모니터 토폴로지 지문(자동 감지 및 수동 환경 선택)과
원클릭 스냅샷 캡처, `ShowWindow(SW_RESTORE)` 선행 복원 후 `SetWindowPos` 정렬을 제공한다.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.context_watcher import query_window_process_info

# ============================================================================
# Win32 DPI / Monitor / Window 64비트 ctypes 선언
# ============================================================================

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
MDT_EFFECTIVE_DPI = 0

MONITORINFOF_PRIMARY = 0x00000001
MONITOR_DEFAULTTONEAREST = 0x00000002

SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
GW_OWNER = 4

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

_SHELL_WINDOW_CLASSES: frozenset[str] = frozenset(
    {
        "Progman",
        "WorkerW",
        "Shell_TrayWnd",
        "Shell_SecondaryTrayWnd",
        "Windows.UI.Core.CoreWindow",
    }
)


class MONITORINFOEXW(ctypes.Structure):
    """Win32 `MONITORINFOEXW` 구조체 (104바이트)."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class WINDOWPLACEMENT(ctypes.Structure):
    """Win32 `WINDOWPLACEMENT` 구조체 (44바이트)."""

    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HMONITOR,
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    wintypes.LPARAM,
)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_user32 = ctypes.WinDLL("user32", use_last_error=True)

try:
    _shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:
    _shcore = None

try:
    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
except OSError:
    _dwmapi = None

_user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL

_user32.GetThreadDpiAwarenessContext.argtypes = []
_user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p

_user32.AreDpiAwarenessContextsEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_user32.AreDpiAwarenessContextsEqual.restype = wintypes.BOOL

_user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    MONITORENUMPROC,
    wintypes.LPARAM,
]
_user32.EnumDisplayMonitors.restype = wintypes.BOOL

_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL

_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HMONITOR

_user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL

_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.IsWindow.restype = wintypes.BOOL

_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL

_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL

_user32.IsZoomed.argtypes = [wintypes.HWND]
_user32.IsZoomed.restype = wintypes.BOOL

_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindow.restype = wintypes.HWND

_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = wintypes.LONG

_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.restype = ctypes.c_int

_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL

_user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
_user32.GetWindowPlacement.restype = wintypes.BOOL

_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL

_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL

_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL

_user32.BringWindowToTop.argtypes = [wintypes.HWND]
_user32.BringWindowToTop.restype = wintypes.BOOL

if _shcore is not None:
    _shcore.GetDpiForMonitor.argtypes = [
        wintypes.HMONITOR,
        ctypes.c_int,
        ctypes.POINTER(wintypes.UINT),
        ctypes.POINTER(wintypes.UINT),
    ]
    _shcore.GetDpiForMonitor.restype = ctypes.c_long

    _shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
    _shcore.SetProcessDpiAwareness.restype = ctypes.c_long

if _dwmapi is not None:
    _dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


# ============================================================================
# DPI 초기화 및 정규화 비율 계산 유틸리티
# ============================================================================


def enable_per_monitor_dpi_v2() -> bool:
    """`SetProcessDpiAwarenessContext(-4)`(Per-Monitor DPI V2)를 활성화한다."""
    ok = bool(
        _user32.SetProcessDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    )
    if ok:
        return True

    # 이미 V2가 적용된 상태라면 정상으로 간주
    current_ctx = _user32.GetThreadDpiAwarenessContext()
    if current_ctx and _user32.AreDpiAwarenessContextsEqual(
        current_ctx, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    ):
        return True

    if _shcore is not None:
        # Fallback: PROCESS_PER_MONITOR_DPI_AWARE (2)
        hr = _shcore.SetProcessDpiAwareness(2)
        if hr == 0 or hr == -2147024891:  # S_OK or E_ACCESSDENIED (already set)
            return True
    return False


def rect_to_ratios(
    window_rect: tuple[int, int, int, int],
    work_rect: tuple[int, int, int, int],
) -> tuple[float, float, float, float]:
    """절대 픽셀 창 좌표 `(l, t, r, b)`를 모니터 작업 영역(`rcWork`) 기준 정규화 비율로 변환한다."""
    left, top, right, bottom = window_rect
    w_left, w_top, w_right, w_bottom = work_rect
    work_w = max(1, w_right - w_left)
    work_h = max(1, w_bottom - w_top)

    x_ratio = round((left - w_left) / work_w, 4)
    y_ratio = round((top - w_top) / work_h, 4)
    w_ratio = round(max(0.01, (right - left) / work_w), 4)
    h_ratio = round(max(0.01, (bottom - top) / work_h), 4)
    return x_ratio, y_ratio, w_ratio, h_ratio


def ratios_to_rect(
    x_ratio: float,
    y_ratio: float,
    w_ratio: float,
    h_ratio: float,
    work_rect: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """정규화 비율 `(x, y, w, h)`를 대상 모니터 `rcWork` 기준 `(x, y, width, height)` 픽셀로 환산한다."""
    w_left, w_top, w_right, w_bottom = work_rect
    work_w = max(1, w_right - w_left)
    work_h = max(1, w_bottom - w_top)

    x = w_left + int(round(x_ratio * work_w))
    y = w_top + int(round(y_ratio * work_h))
    width = max(50, int(round(w_ratio * work_w)))
    height = max(50, int(round(h_ratio * work_h)))
    return x, y, width, height


# ============================================================================
# 데이터 모델
# ============================================================================


@dataclass(frozen=True)
class MonitorInfo:
    """개별 물리 모니터의 작업 영역(`rcWork`), 해상도 및 배율 메타데이터."""

    index: int
    h_monitor: int
    device_name: str
    is_primary: bool
    monitor_rect: tuple[int, int, int, int]
    work_rect: tuple[int, int, int, int]
    dpi_x: int
    dpi_y: int

    @property
    def width(self) -> int:
        return self.monitor_rect[2] - self.monitor_rect[0]

    @property
    def height(self) -> int:
        return self.monitor_rect[3] - self.monitor_rect[1]

    @property
    def work_width(self) -> int:
        return self.work_rect[2] - self.work_rect[0]

    @property
    def work_height(self) -> int:
        return self.work_rect[3] - self.work_rect[1]

    @property
    def scale_percent(self) -> int:
        return int(round((self.dpi_x / 96.0) * 100))

    @property
    def descriptor(self) -> str:
        return f"{self.width}x{self.height}@{self.scale_percent}"


@dataclass
class WindowPlacementSpec:
    """모니터 인덱스 및 정규화 비율(`0.0 ~ 1.0`)로 표현된 단일 창 배치 규격."""

    process_name: str
    monitor_index: int
    x_ratio: float
    y_ratio: float
    w_ratio: float
    h_ratio: float
    title_hint: str = ""
    launch_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WindowPlacementSpec:
        return cls(
            process_name=str(data["process_name"]),
            monitor_index=int(data.get("monitor_index", 0)),
            x_ratio=float(data.get("x_ratio", 0.0)),
            y_ratio=float(data.get("y_ratio", 0.0)),
            w_ratio=float(data.get("w_ratio", 1.0)),
            h_ratio=float(data.get("h_ratio", 1.0)),
            title_hint=str(data.get("title_hint", "")),
            launch_path=str(data.get("launch_path", "")),
        )


@dataclass
class LayoutPreset:
    """특정 디스플레이 토폴로지 환경에 묶인 창 배치 프리셋."""

    name: str
    topology_fingerprint: str
    placements: list[WindowPlacementSpec] = field(default_factory=list)
    environment_label: str = ""
    focus_process: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "topology_fingerprint": self.topology_fingerprint,
            "environment_label": self.environment_label,
            "focus_process": self.focus_process,
            "placements": [p.to_dict() for p in self.placements],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutPreset:
        return cls(
            name=str(data["name"]),
            topology_fingerprint=str(data.get("topology_fingerprint", "")),
            environment_label=str(data.get("environment_label", "")),
            focus_process=str(data.get("focus_process", "")),
            placements=[
                WindowPlacementSpec.from_dict(p) for p in data.get("placements", [])
            ],
        )


@dataclass
class WindowSnapshotItem:
    """열려 있는 창 한 개를 스냅샷으로 추출한 원시/정규화 정보."""

    hwnd: int
    process_name: str
    executable_path: str
    window_title: str
    monitor_index: int
    pixel_rect: tuple[int, int, int, int]
    x_ratio: float
    y_ratio: float
    w_ratio: float
    h_ratio: float
    is_maximized: bool


@dataclass
class ApplyLayoutResult:
    """창 레이아웃 프리셋 적용 결과 보고서."""

    preset_name: str
    auto_launch: bool
    moved_count: int = 0
    launched_count: int = 0
    skipped_processes: list[str] = field(default_factory=list)
    failed_windows: list[str] = field(default_factory=list)


# ============================================================================
# WindowOrchestrator 구현
# ============================================================================

AUTO_PROFILE_KEY = "__auto__"


class WindowOrchestrator:
    """다중 모니터 토폴로지 감지, 비율 기반 창 정렬, 스냅샷 캡처 엔진."""

    def __init__(
        self,
        init_dpi_v2: bool = True,
        compensate_dwm_frame: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self.dpi_v2_enabled: bool = enable_per_monitor_dpi_v2() if init_dpi_v2 else False
        self.compensate_dwm_frame: bool = compensate_dwm_frame
        self._presets: dict[str, LayoutPreset] = {}
        self._topology_labels: dict[str, str] = {}
        self._selected_profile_mode: str = AUTO_PROFILE_KEY
        self._self_pid = os.getpid()

    @staticmethod
    def get_dwm_frame_margins(hwnd: int) -> tuple[int, int, int, int]:
        """Windows 10/11 창의 비가시 DWM 그림자 테두리 여백 `(left, top, right, bottom)`을 계산한다."""
        if _dwmapi is None:
            return (0, 0, 0, 0)
        h_wnd = wintypes.HWND(hwnd)
        rc_win = wintypes.RECT()
        rc_ext = wintypes.RECT()
        if not _user32.GetWindowRect(h_wnd, ctypes.byref(rc_win)):
            return (0, 0, 0, 0)
        hr = _dwmapi.DwmGetWindowAttribute(
            h_wnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rc_ext),
            ctypes.sizeof(rc_ext),
        )
        if hr != 0:
            return (0, 0, 0, 0)
        left_pad = max(0, int(rc_ext.left - rc_win.left))
        top_pad = max(0, int(rc_ext.top - rc_win.top))
        right_pad = max(0, int(rc_win.right - rc_ext.right))
        bottom_pad = max(0, int(rc_win.bottom - rc_ext.bottom))
        return (left_pad, top_pad, right_pad, bottom_pad)

    def enumerate_monitors(self) -> list[MonitorInfo]:
        """`EnumDisplayMonitors`로 현재 연결된 모니터를 좌→우 순으로 열거한다."""
        raw_monitors: list[MonitorInfo] = []

        def _enum_cb(
            h_mon: int,
            hdc: int,
            lprc: object,
            lparam: int,
        ) -> bool:
            del hdc, lprc, lparam
            mi = MONITORINFOEXW()
            mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if not _user32.GetMonitorInfoW(wintypes.HMONITOR(h_mon), ctypes.byref(mi)):
                return True

            dpi_x, dpi_y = 96, 96
            if _shcore is not None:
                dx = wintypes.UINT(96)
                dy = wintypes.UINT(96)
                if (
                    _shcore.GetDpiForMonitor(
                        wintypes.HMONITOR(h_mon),
                        MDT_EFFECTIVE_DPI,
                        ctypes.byref(dx),
                        ctypes.byref(dy),
                    )
                    == 0
                ):
                    dpi_x, dpi_y = int(dx.value), int(dy.value)

            mon_rect = (
                int(mi.rcMonitor.left),
                int(mi.rcMonitor.top),
                int(mi.rcMonitor.right),
                int(mi.rcMonitor.bottom),
            )
            work_rect = (
                int(mi.rcWork.left),
                int(mi.rcWork.top),
                int(mi.rcWork.right),
                int(mi.rcWork.bottom),
            )
            raw_monitors.append(
                MonitorInfo(
                    index=0,
                    h_monitor=int(h_mon),
                    device_name=str(mi.szDevice),
                    is_primary=bool(mi.dwFlags & MONITORINFOF_PRIMARY),
                    monitor_rect=mon_rect,
                    work_rect=work_rect,
                    dpi_x=dpi_x,
                    dpi_y=dpi_y,
                )
            )
            return True

        cb_ref = MONITORENUMPROC(_enum_cb)
        _user32.EnumDisplayMonitors(None, None, cb_ref, 0)

        # 물리적 배치 순서(좌 -> 우, 동일 X축이면 상 -> 하)로 인덱스 고정
        raw_monitors.sort(key=lambda m: (m.monitor_rect[0], m.monitor_rect[1]))
        return [
            MonitorInfo(
                index=idx,
                h_monitor=m.h_monitor,
                device_name=m.device_name,
                is_primary=m.is_primary,
                monitor_rect=m.monitor_rect,
                work_rect=m.work_rect,
                dpi_x=m.dpi_x,
                dpi_y=m.dpi_y,
            )
            for idx, m in enumerate(raw_monitors)
        ]

    def get_topology_fingerprint(
        self, monitors: list[MonitorInfo] | None = None
    ) -> str:
        """모니터 대수·순서·해상도·DPI 배율을 조합한 환경 지문 문자열을 생성한다."""
        mons = monitors if monitors is not None else self.enumerate_monitors()
        if not mons:
            return "0M"
        parts = [f"{len(mons)}M", *(m.descriptor for m in mons)]
        return "|".join(parts)

    def register_topology_label(self, fingerprint: str, label: str) -> None:
        """특정 토폴로지 지문에 사용자 친화적 환경 이름(예: 집 울트라와이드)을 지정한다."""
        with self._lock:
            self._topology_labels[fingerprint] = label

    def select_profile_mode(self, mode: str) -> None:
        """상단 드롭다운에서 `[자동 감지(__auto__)]` 또는 특정 환경 프로파일을 선택한다."""
        with self._lock:
            self._selected_profile_mode = mode or AUTO_PROFILE_KEY

    @property
    def selected_profile_mode(self) -> str:
        with self._lock:
            return self._selected_profile_mode

    def get_active_topology_fingerprint(self) -> str:
        """현재 선택 모드(자동 감지 또는 수동 지정 프로파일)에 따른 활성 토폴로지 지문을 반환한다."""
        with self._lock:
            selected = self._selected_profile_mode
        if selected != AUTO_PROFILE_KEY:
            return selected
        return self.get_topology_fingerprint()

    def get_available_environment_choices(self) -> list[tuple[str, str]]:
        """UI 드롭다운에 바인딩할 `(profile_key, display_label)` 목록을 반환한다."""
        live_fp = self.get_topology_fingerprint()
        live_label = self._topology_labels.get(live_fp, live_fp)
        choices: list[tuple[str, str]] = [
            (AUTO_PROFILE_KEY, f"자동 감지 ({live_label})"),
        ]
        seen: set[str] = set()
        with self._lock:
            for fp, lbl in self._topology_labels.items():
                if fp not in seen:
                    seen.add(fp)
                    choices.append((fp, f"{lbl} ({fp})"))
            for preset in self._presets.values():
                fp = preset.topology_fingerprint
                if fp and fp not in seen:
                    seen.add(fp)
                    lbl = preset.environment_label or fp
                    choices.append((fp, lbl))
        return choices

    @staticmethod
    def _is_window_cloaked(hwnd: int) -> bool:
        """UWP 백그라운드 숨김 창(Cloaked) 여부를 DWM API로 확인한다."""
        if _dwmapi is None:
            return False
        cloaked = wintypes.DWORD(0)
        hr = _dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        return hr == 0 and cloaked.value != 0

    @staticmethod
    def _get_window_class(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(128)
        _user32.GetClassNameW(wintypes.HWND(hwnd), buf, 128)
        return buf.value

    def _is_manageable_app_window(
        self, hwnd: int, exclude_self: bool = True, include_minimized: bool = False
    ) -> bool:
        """일반 사용자 애플리케이션 창인지 판별한다."""
        if not _user32.IsWindowVisible(wintypes.HWND(hwnd)):
            return False
        if not include_minimized and _user32.IsIconic(wintypes.HWND(hwnd)):
            return False
        if self._is_window_cloaked(hwnd):
            return False

        cls_name = self._get_window_class(hwnd)
        if cls_name in _SHELL_WINDOW_CLASSES:
            return False

        ex_style = _user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        if (ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW):
            return False

        owner = _user32.GetWindow(wintypes.HWND(hwnd), GW_OWNER)
        if owner and not (ex_style & WS_EX_APPWINDOW):
            return False

        pid, proc_name, _, title = query_window_process_info(hwnd)
        if not proc_name or not title:
            return False
        if exclude_self and pid == self._self_pid:
            return False
        return True

    def list_manageable_windows(
        self, exclude_self: bool = True, include_minimized: bool = False
    ) -> list[WindowSnapshotItem]:
        """현재 열려 있는 모든 관리 대상 창과 모니터별 정규화 비율을 추출한다."""
        monitors = self.enumerate_monitors()
        mon_by_handle = {m.h_monitor: m for m in monitors}
        items: list[WindowSnapshotItem] = []

        def _enum_win_cb(hwnd: int, lparam: int) -> bool:
            del lparam
            if not self._is_manageable_app_window(
                hwnd, exclude_self=exclude_self, include_minimized=include_minimized
            ):
                return True

            rect = wintypes.RECT()
            if _user32.IsIconic(wintypes.HWND(hwnd)):
                wp = WINDOWPLACEMENT()
                wp.length = ctypes.sizeof(WINDOWPLACEMENT)
                if not _user32.GetWindowPlacement(
                    wintypes.HWND(hwnd), ctypes.byref(wp)
                ):
                    return True
                rect = wp.rcNormalPosition
            else:
                if not _user32.GetWindowRect(
                    wintypes.HWND(hwnd), ctypes.byref(rect)
                ):
                    return True

            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 40 or height <= 40:
                return True

            h_mon = int(
                _user32.MonitorFromWindow(
                    wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST
                )
                or 0
            )
            mon = mon_by_handle.get(h_mon) or (monitors[0] if monitors else None)
            if mon is None:
                return True

            _, proc_name, exe_path, title = query_window_process_info(hwnd)
            pixel_rect = (
                int(rect.left),
                int(rect.top),
                int(rect.right),
                int(rect.bottom),
            )
            xr, yr, wr, hr = rect_to_ratios(pixel_rect, mon.work_rect)
            items.append(
                WindowSnapshotItem(
                    hwnd=int(hwnd),
                    process_name=proc_name,
                    executable_path=exe_path,
                    window_title=title,
                    monitor_index=mon.index,
                    pixel_rect=pixel_rect,
                    x_ratio=xr,
                    y_ratio=yr,
                    w_ratio=wr,
                    h_ratio=hr,
                    is_maximized=bool(_user32.IsZoomed(wintypes.HWND(hwnd))),
                )
            )
            return True

        cb_ref = WNDENUMPROC(_enum_win_cb)
        _user32.EnumWindows(cb_ref, 0)
        return items

    def capture_snapshot(
        self,
        preset_name: str,
        environment_label: str = "",
        focus_process: str = "",
        exclude_self: bool = True,
        include_minimized: bool = False,
    ) -> LayoutPreset:
        """현재 마우스로 배치된 열린 창 구성을 원클릭 비율 스냅샷으로 저장한다."""
        monitors = self.enumerate_monitors()
        fp = self.get_topology_fingerprint(monitors)
        windows = self.list_manageable_windows(
            exclude_self=exclude_self, include_minimized=include_minimized
        )

        placements = [
            WindowPlacementSpec(
                process_name=w.process_name,
                monitor_index=w.monitor_index,
                x_ratio=w.x_ratio,
                y_ratio=w.y_ratio,
                w_ratio=w.w_ratio,
                h_ratio=w.h_ratio,
                title_hint=w.window_title[:48],
                launch_path=w.executable_path,
            )
            for w in windows
        ]
        preset = LayoutPreset(
            name=preset_name,
            topology_fingerprint=fp,
            placements=placements,
            environment_label=environment_label or fp,
            focus_process=focus_process,
        )
        with self._lock:
            self._presets[preset_name] = preset
            if environment_label:
                self._topology_labels[fp] = environment_label
        return preset

    def save_preset(self, preset: LayoutPreset) -> None:
        """사용자 정의 또는 스냅샷 프리셋을 레지스트리에 등록한다."""
        with self._lock:
            self._presets[preset.name] = preset

    def get_preset(self, preset_name: str) -> LayoutPreset | None:
        """이름으로 저장된 레이아웃 프리셋을 조회한다."""
        with self._lock:
            return self._presets.get(preset_name)

    def list_presets(self) -> list[LayoutPreset]:
        """저장된 모든 레이아웃 프리셋 목록을 반환한다."""
        with self._lock:
            return list(self._presets.values())

    @staticmethod
    def move_window_safe(
        hwnd: int,
        x: int,
        y: int,
        width: int,
        height: int,
        compensate_dwm: bool = False,
    ) -> bool:
        """최대화/최소화 상태를 `ShowWindow(SW_RESTORE)`로 선행 해제한 뒤 `SetWindowPos`로 이동한다.

        `compensate_dwm=True`이면 Windows 11의 보이지 않는 7px DWM 그림자 테두리를 보정해
        실제 가시 프레임이 목표 비율 좌표에 빈틈없이 밀착되도록 조정한다.
        """
        h_wnd = wintypes.HWND(hwnd)
        if not _user32.IsWindow(h_wnd):
            return False

        if _user32.IsIconic(h_wnd) or _user32.IsZoomed(h_wnd):
            _user32.ShowWindow(h_wnd, SW_RESTORE)
            time.sleep(0.02)

        adj_x, adj_y, adj_w, adj_h = int(x), int(y), max(50, int(width)), max(50, int(height))
        if compensate_dwm:
            l_pad, t_pad, r_pad, b_pad = WindowOrchestrator.get_dwm_frame_margins(hwnd)
            adj_x -= l_pad
            adj_y -= t_pad
            adj_w += l_pad + r_pad
            adj_h += t_pad + b_pad

        return bool(
            _user32.SetWindowPos(
                h_wnd,
                None,
                adj_x,
                adj_y,
                adj_w,
                adj_h,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )
        )

    def _find_matching_window(
        self,
        spec: WindowPlacementSpec,
        open_windows: list[WindowSnapshotItem],
        used_hwnds: set[int],
    ) -> WindowSnapshotItem | None:
        target_proc = spec.process_name.lower()
        candidates = [
            w
            for w in open_windows
            if w.hwnd not in used_hwnds and w.process_name.lower() == target_proc
        ]
        if not candidates:
            return None
        if spec.title_hint:
            hint_lower = spec.title_hint.lower()
            for c in candidates:
                if hint_lower in c.window_title.lower():
                    return c
        return candidates[0]

    def apply_preset(
        self,
        preset_name: str,
        auto_launch: bool = False,
        launch_timeout_sec: float = 5.0,
    ) -> ApplyLayoutResult:
        """저장된 창 레이아웃 프리셋을 현재 모니터 토폴로지에 비율 환산해 적용한다.

        Args:
            preset_name: 적용할 프리셋 이름.
            auto_launch: False면 실행 중인 창만 정렬, True면 미실행 앱 자동 실행 후 정렬.
            launch_timeout_sec: `auto_launch=True`일 때 창 생성 대기 최대 시간(초).
        """
        preset = self.get_preset(preset_name)
        if preset is None:
            return ApplyLayoutResult(preset_name=preset_name, auto_launch=auto_launch)

        monitors = self.enumerate_monitors()
        if not monitors:
            return ApplyLayoutResult(preset_name=preset_name, auto_launch=auto_launch)

        result = ApplyLayoutResult(preset_name=preset_name, auto_launch=auto_launch)
        open_windows = self.list_manageable_windows(
            exclude_self=False, include_minimized=True
        )
        used_hwnds: set[int] = set()
        pending_launches: list[WindowPlacementSpec] = []

        # 1단계: 현재 실행 중인 창 즉시 정렬
        for spec in preset.placements:
            match = self._find_matching_window(spec, open_windows, used_hwnds)
            if match is None:
                if auto_launch and spec.launch_path and os.path.isfile(spec.launch_path):
                    pending_launches.append(spec)
                else:
                    result.skipped_processes.append(spec.process_name)
                continue

            used_hwnds.add(match.hwnd)
            mon = monitors[min(max(0, spec.monitor_index), len(monitors) - 1)]
            tx, ty, tw, th = ratios_to_rect(
                spec.x_ratio, spec.y_ratio, spec.w_ratio, spec.h_ratio, mon.work_rect
            )
            if self.move_window_safe(
                match.hwnd, tx, ty, tw, th, compensate_dwm=self.compensate_dwm_frame
            ):
                result.moved_count += 1
            else:
                result.failed_windows.append(f"{spec.process_name}({match.hwnd})")

        # 2단계: auto_launch=True 인 경우 미실행 앱 자동 실행 후 창 출현 시 정렬
        if pending_launches:
            creation_flags = (
                getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            )
            launched_specs: list[WindowPlacementSpec] = []
            for spec in pending_launches:
                try:
                    subprocess.Popen(
                        [spec.launch_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=creation_flags,
                    )
                    result.launched_count += 1
                    launched_specs.append(spec)
                except OSError:
                    result.failed_windows.append(spec.process_name)

            deadline = time.monotonic() + max(0.5, launch_timeout_sec)
            remaining = list(launched_specs)
            while remaining and time.monotonic() < deadline:
                time.sleep(0.2)
                current_wins = self.list_manageable_windows(
                    exclude_self=False, include_minimized=True
                )
                next_remaining: list[WindowPlacementSpec] = []
                for spec in remaining:
                    match = self._find_matching_window(spec, current_wins, used_hwnds)
                    if match is None:
                        next_remaining.append(spec)
                        continue
                    used_hwnds.add(match.hwnd)
                    mon = monitors[min(max(0, spec.monitor_index), len(monitors) - 1)]
                    tx, ty, tw, th = ratios_to_rect(
                        spec.x_ratio,
                        spec.y_ratio,
                        spec.w_ratio,
                        spec.h_ratio,
                        mon.work_rect,
                    )
                    if self.move_window_safe(
                        match.hwnd,
                        tx,
                        ty,
                        tw,
                        th,
                        compensate_dwm=self.compensate_dwm_frame,
                    ):
                        result.moved_count += 1
                    else:
                        result.failed_windows.append(spec.process_name)
                remaining = next_remaining

            for spec in remaining:
                result.failed_windows.append(f"{spec.process_name}(timeout)")

        # 3단계: 최종 포커스 받을 메인 앱이 지정되어 있으면 포그라운드 활성화
        if preset.focus_process:
            target_focus = preset.focus_process.strip().lower()
            latest_wins = self.list_manageable_windows(
                exclude_self=False, include_minimized=True
            )
            focus_win = next(
                (w for w in latest_wins if w.process_name.lower() == target_focus),
                None,
            )
            if focus_win is not None:
                h_focus = wintypes.HWND(focus_win.hwnd)
                if _user32.IsIconic(h_focus):
                    _user32.ShowWindow(h_focus, SW_RESTORE)
                _user32.BringWindowToTop(h_focus)
                _user32.SetForegroundWindow(h_focus)

        return result

    def load_presets(
        self,
        presets_data: list[dict[str, Any]],
        topology_labels: dict[str, str] | None = None,
    ) -> None:
        """`config.json`에서 저장된 레이아웃 프리셋 및 환경 라벨을 복원한다."""
        with self._lock:
            self._presets.clear()
            for item in presets_data:
                preset = LayoutPreset.from_dict(item)
                self._presets[preset.name] = preset
            if topology_labels:
                self._topology_labels.update(topology_labels)

    def export_presets(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """`config.json` 저장용 프리셋 리스트와 토폴로지 라벨 딕셔너리를 반환한다."""
        with self._lock:
            return (
                [p.to_dict() for p in self._presets.values()],
                dict(self._topology_labels),
            )

    def delete_preset(self, preset_name: str) -> bool:
        """저장된 레이아웃 프리셋을 이름으로 삭제한다."""
        with self._lock:
            return self._presets.pop(preset_name, None) is not None

    def export_presets_to_file(self, file_path: Path) -> int:
        """저장된 창 배치 프리셋 목록을 별도 `.json` 파일로 내보낸다(Export)."""
        presets_data, labels = self.export_presets()
        payload = {
            "format": "nexus_workspace_presets",
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "topology_labels": labels,
            "presets": presets_data,
        }
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return len(presets_data)

    def import_presets_from_file(self, file_path: Path, mode: str = "merge") -> int:
        """외부 `.json` 파일에서 창 배치 프리셋을 불러온다(Import: `merge` 또는 `replace`)."""
        with file_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)

        if not isinstance(raw, dict) or "presets" not in raw:
            raise ValueError("Invalid workspace presets JSON: missing 'presets' field")

        imported = [LayoutPreset.from_dict(item) for item in raw.get("presets", [])]
        labels = raw.get("topology_labels", {})

        with self._lock:
            if mode == "replace":
                self._presets.clear()
            elif mode != "merge":
                raise ValueError(f"Unsupported import mode: {mode}")

            for preset in imported:
                self._presets[preset.name] = preset
            if isinstance(labels, dict):
                self._topology_labels.update(
                    {str(k): str(v) for k, v in labels.items()}
                )

        return len(imported)


if __name__ == "__main__":
    orch = WindowOrchestrator()
    mons = orch.enumerate_monitors()
    print(
        f"[WindowOrchestrator] DPI_V2={orch.dpi_v2_enabled}, "
        f"Topology={orch.get_topology_fingerprint(mons)}"
    )
    for m in mons:
        print(
            f" - Monitor[{m.index}] {m.device_name} primary={m.is_primary} "
            f"rect={m.monitor_rect} rcWork={m.work_rect} scale={m.scale_percent}%"
        )
