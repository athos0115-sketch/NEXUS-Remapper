"""이벤트 기반 활성 창 및 프로세스 감지기 모듈 (`SetWinEventHook`).

CPU 폴링(`while` 루프)을 일절 사용하지 않고 Win32 `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)`
메시지 기반 훅을 통해 포그라운드 창이 전환될 때만 즉시 콜백을 실행한다.
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

# ============================================================================
# Win32 SetWinEventHook / Process Query 64비트 ctypes 선언
# ============================================================================

EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WM_QUIT = 0x0012

WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.SetWinEventHook.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HMODULE,
    WINEVENTPROC,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
]
_user32.SetWinEventHook.restype = wintypes.HANDLE

_user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
_user32.UnhookWinEvent.restype = wintypes.BOOL

_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = wintypes.HWND

_user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD

_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int

_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int

_user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.GetMessageW.restype = wintypes.BOOL

_user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.TranslateMessage.restype = wintypes.BOOL

_user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.restype = ctypes.c_ssize_t

_user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.PostThreadMessageW.restype = wintypes.BOOL

_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD

_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE

_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ULONG_PTR = (
    ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
)


class PROCESSENTRY32W(ctypes.Structure):
    """Win32 `PROCESSENTRY32W` 구조체."""

    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ULONG_PTR),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

_kernel32.Process32FirstW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(PROCESSENTRY32W),
]
_kernel32.Process32FirstW.restype = wintypes.BOOL

_kernel32.Process32NextW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(PROCESSENTRY32W),
]
_kernel32.Process32NextW.restype = wintypes.BOOL


DEFAULT_PROCESS_PROFILES: dict[str, str] = {
    "revit.exe": "bim_cad",
    "acad.exe": "bim_cad",
    "code.exe": "ide",
    "minimalmediaplayer.exe": "media",
    "worldchronicleengine.exe": "simulation",
    "chrome.exe": "browser",
    "msedge.exe": "browser",
}


@dataclass(frozen=True)
class ForegroundContext:
    """현재 활성 창(포그라운드)의 프로세스, 프로파일 및 자동 전환 레이어 정보."""

    hwnd: int
    pid: int
    process_name: str
    executable_path: str
    window_title: str
    matched_profile: str
    matched_layer: str = "default"


def list_running_process_names() -> list[str]:
    """현재 시스템에서 실행 중인 모든 `.exe` 프로세스명 목록을 정렬해 반환한다."""
    snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return []

    names: dict[str, str] = {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        ok = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            exe = str(entry.szExeFile).strip()
            if exe and exe.lower().endswith(".exe"):
                names.setdefault(exe.lower(), exe)
            ok = _kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snap)

    return sorted(names.values(), key=str.lower)


def query_window_process_info(hwnd: int) -> tuple[int, str, str, str]:
    """주어진 `HWND`로부터 `(pid, process_name, executable_path, window_title)`를 조회한다."""
    if not hwnd:
        return 0, "", "", ""

    pid_val = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid_val))
    pid = int(pid_val.value)

    title = ""
    title_len = _user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
    if title_len > 0:
        tbuf = ctypes.create_unicode_buffer(title_len + 1)
        _user32.GetWindowTextW(wintypes.HWND(hwnd), tbuf, title_len + 1)
        title = tbuf.value

    exe_path = ""
    proc_name = ""
    if pid > 0:
        h_proc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h_proc:
            try:
                size = wintypes.DWORD(1024)
                pbuf = ctypes.create_unicode_buffer(size.value)
                if _kernel32.QueryFullProcessImageNameW(
                    h_proc, 0, pbuf, ctypes.byref(size)
                ):
                    exe_path = pbuf.value
                    proc_name = os.path.basename(exe_path)
            finally:
                _kernel32.CloseHandle(h_proc)

    return pid, proc_name, exe_path, title


class ContextWatcher:
    """`SetWinEventHook` 기반 무부하 활성 프로세스 감지기."""

    def __init__(
        self,
        process_profiles: dict[str, str] | None = None,
        layer_bindings: dict[str, list[str]] | None = None,
        process_layer_bindings: dict[str, str] | None = None,
        ignore_self: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[str, str] = {
            k.lower(): v
            for k, v in (process_profiles or DEFAULT_PROCESS_PROFILES).items()
        }
        self._process_to_layer: dict[str, str] = {}
        self._process_layer_bindings: dict[str, str] = {}
        self._running_process_layers: list[str] = []
        if layer_bindings:
            self.set_layer_bindings(layer_bindings)
        if process_layer_bindings:
            self.set_process_layer_bindings(process_layer_bindings)
        self._ignore_self = ignore_self
        self._self_pid = os.getpid()

        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hook_handle: int | None = None
        self._hook_proc_ref: WINEVENTPROC | None = None
        self._ready_event = threading.Event()
        self._start_error: str = ""

        self._current_context: ForegroundContext | None = None
        self._callbacks: list[Callable[[ForegroundContext], None]] = []
        self._profile_callbacks: list[Callable[[ForegroundContext], None]] = []
        self._process_layers_callbacks: list[Callable[[list[str]], None]] = []

    @property
    def is_running(self) -> bool:
        """이벤트 훅 워커 스레드 가동 여부를 반환한다."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def current_context(self) -> ForegroundContext | None:
        """마지막으로 감지된 활성 창 컨텍스트를 반환한다."""
        with self._lock:
            return self._current_context

    def set_profile_mapping(self, mapping: dict[str, str]) -> None:
        """프로세스명 -> 프로파일명 매핑 테이블을 갱신한다."""
        with self._lock:
            self._profiles = {k.lower(): v for k, v in mapping.items()}

    def resolve_profile(self, process_name: str) -> str:
        """프로세스 실행 파일명에 대응하는 프로파일을 반환한다."""
        if not process_name:
            return "default"
        with self._lock:
            return self._profiles.get(process_name.lower(), "default")

    def set_layer_bindings(self, layer_bindings: dict[str, list[str]]) -> None:
        """`{layer_name: [exe1, exe2, ...]}` 레이어 바인딩 테이블을 갱신한다."""
        mapping: dict[str, str] = {}
        for layer_name, procs in layer_bindings.items():
            for proc in procs:
                clean = str(proc).strip().lower()
                if clean:
                    mapping[clean] = str(layer_name)
        with self._lock:
            self._process_to_layer = mapping

    def resolve_layer(self, process_name: str) -> str:
        """프로세스 실행 파일명에 매핑된 레이어를 반환한다(미매칭 시 `default`)."""
        if not process_name:
            return "default"
        with self._lock:
            return self._process_to_layer.get(process_name.lower(), "default")

    def set_process_layer_bindings(self, bindings: dict[str, str]) -> None:
        """프로세스 지정 모드(`process`) `{layer_name: exe}` 바인딩 테이블을 갱신한다."""
        cleaned: dict[str, str] = {}
        for layer_name, proc in bindings.items():
            name = str(layer_name).strip()
            exe = str(proc).strip().lower()
            if name and exe:
                cleaned[name] = exe
        with self._lock:
            self._process_layer_bindings = cleaned

    def add_process_layers_callback(self, cb: Callable[[list[str]], None]) -> None:
        """실행 중인 프로세스 지정 모드 레이어 목록이 변경될 때 호출될 콜백을 등록한다."""
        with self._lock:
            if cb not in self._process_layers_callbacks:
                self._process_layers_callbacks.append(cb)

    def evaluate_process_layers(
        self, running_processes: list[str] | set[str] | None = None
    ) -> list[str]:
        """현재 실행 중인 프로세스 목록을 기준으로 활성 `process` 모드 레이어를 평가·전파한다."""
        procs = (
            list_running_process_names()
            if running_processes is None
            else running_processes
        )
        running_low = {str(p).strip().lower() for p in procs if str(p).strip()}
        with self._lock:
            matched = [
                layer_name
                for layer_name, exe_low in self._process_layer_bindings.items()
                if exe_low in running_low
            ]
            changed = matched != self._running_process_layers
            if changed:
                self._running_process_layers = list(matched)
            cbs = list(self._process_layers_callbacks) if changed else []

        for cb in cbs:
            try:
                cb(list(matched))
            except Exception:
                pass
        return matched

    def add_context_callback(self, cb: Callable[[ForegroundContext], None]) -> None:
        """활성 창/프로세스 전환 시 호출될 콜백을 등록한다."""
        with self._lock:
            if cb not in self._callbacks:
                self._callbacks.append(cb)

    def add_profile_callback(self, cb: Callable[[ForegroundContext], None]) -> None:
        """프로파일 또는 활성 프로세스 이름이 실제로 바뀔 때만 호출될 콜백을 등록한다."""
        with self._lock:
            if cb not in self._profile_callbacks:
                self._profile_callbacks.append(cb)

    def get_foreground_snapshot(self) -> ForegroundContext:
        """현재 포그라운드 창의 컨텍스트를 즉시 조회한다."""
        hwnd = int(_user32.GetForegroundWindow() or 0)
        return self._build_context(hwnd)

    def _build_context(self, hwnd: int) -> ForegroundContext:
        pid, proc_name, exe_path, title = query_window_process_info(hwnd)
        profile = self.resolve_profile(proc_name)
        layer = self.resolve_layer(proc_name)
        return ForegroundContext(
            hwnd=hwnd,
            pid=pid,
            process_name=proc_name,
            executable_path=exe_path,
            window_title=title,
            matched_profile=profile,
            matched_layer=layer,
        )

    def notify_foreground_process(
        self,
        process_name: str,
        window_title: str = "",
        hwnd: int = 1,
        pid: int = 0,
    ) -> ForegroundContext:
        """테스트 및 수동 동기화용으로 특정 프로세스 포커스 전환을 즉시 평가·전파한다."""
        ctx = ForegroundContext(
            hwnd=hwnd,
            pid=pid,
            process_name=process_name,
            executable_path=process_name,
            window_title=window_title,
            matched_profile=self.resolve_profile(process_name),
            matched_layer=self.resolve_layer(process_name),
        )
        self._dispatch_context(ctx)
        return ctx

    def _handle_foreground_hwnd(self, hwnd: int) -> None:
        if not hwnd:
            return
        ctx = self._build_context(hwnd)
        if not ctx.process_name:
            return
        if self._ignore_self and ctx.pid == self._self_pid:
            return
        self._dispatch_context(ctx)

    def _dispatch_context(self, ctx: ForegroundContext) -> None:
        with self._lock:
            prev = self._current_context
            if (
                prev is not None
                and prev.hwnd == ctx.hwnd
                and prev.process_name == ctx.process_name
                and prev.matched_profile == ctx.matched_profile
                and prev.matched_layer == ctx.matched_layer
            ):
                return
            self._current_context = ctx
            proc_changed = (
                prev is None
                or prev.process_name.lower() != ctx.process_name.lower()
                or prev.matched_profile != ctx.matched_profile
                or prev.matched_layer != ctx.matched_layer
            )
            ctx_cbs = list(self._callbacks)
            prof_cbs = list(self._profile_callbacks) if proc_changed else []

        for cb in ctx_cbs:
            try:
                cb(ctx)
            except Exception:
                pass

        for cb in prof_cbs:
            try:
                cb(ctx)
            except Exception:
                pass

    def _win_event_proc(
        self,
        h_win_event_hook: int,
        event: int,
        hwnd: int,
        id_object: int,
        id_child: int,
        id_event_thread: int,
        dwms_event_time: int,
    ) -> None:
        del h_win_event_hook, id_object, id_child, id_event_thread, dwms_event_time
        if event == EVENT_SYSTEM_FOREGROUND and hwnd:
            self._handle_foreground_hwnd(int(hwnd))

    def start(self) -> bool:
        """`SetWinEventHook` 스레드를 시작하고 초기 포그라운드 상태를 동기화한다."""
        if self.is_running:
            return True

        self._ready_event.clear()
        self._start_error = ""
        self._thread = threading.Thread(
            target=self._run_loop, name="NexusContextWatcher", daemon=True
        )
        self._thread.start()
        self._ready_event.wait(timeout=3.0)
        return not self._start_error and self.is_running

    def _run_loop(self) -> None:
        self._thread_id = int(_kernel32.GetCurrentThreadId())
        self._hook_proc_ref = WINEVENTPROC(self._win_event_proc)

        hook = _user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            self._hook_proc_ref,
            0,
            0,
            WINEVENT_OUTOFCONTEXT,
        )
        if not hook:
            err = ctypes.get_last_error()
            self._start_error = f"SetWinEventHook failed (err={err})"
            self._ready_event.set()
            return

        self._hook_handle = int(hook)
        # 시작 직후 현재 활성 창 초기 상태 기록
        fg_hwnd = int(_user32.GetForegroundWindow() or 0)
        if fg_hwnd:
            self._handle_foreground_hwnd(fg_hwnd)

        self._ready_event.set()

        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        with self._lock:
            if self._hook_handle:
                _user32.UnhookWinEvent(wintypes.HANDLE(self._hook_handle))
                self._hook_handle = None
            self._thread_id = 0

    def stop(self) -> None:
        """`UnhookWinEvent` 호출 및 워커 스레드를 안전하게 종료한다."""
        with self._lock:
            tid = self._thread_id
        if tid:
            _user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)

        if self._thread is not None and self._thread.is_alive():
            if threading.current_thread() is not self._thread:
                self._thread.join(timeout=1.5)
        self._thread = None


if __name__ == "__main__":
    watcher = ContextWatcher()
    ok = watcher.start()
    print(f"[ContextWatcher] started={ok}, current={watcher.current_context}")
    watcher.stop()
    print(f"[ContextWatcher] stopped, running={watcher.is_running}")
