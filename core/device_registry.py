"""동적 HID 및 입력 장치 레지스트리 모듈 (Win32 Raw Input 기반).

특정 제조사의 VID/PID를 코드에 고정하지 않고 `GetRawInputDeviceList` 및
`GetRawInputDeviceInfoW`를 통해 연결된 모든 키보드·마우스·HID 장치를 동적으로 열거한다.
메인 키보드와 마우스는 기본 `Protected` 상태로 잠금 보호하여 입력 차단 사고를 방지한다.
"""

from __future__ import annotations

import ctypes
import re
import threading
import winreg
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from core.events import DeviceType

# ============================================================================
# Win32 Raw Input 상수 및 64비트 ctypes 구조체 선언
# ============================================================================

RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RIM_TYPEHID = 2

RIDI_DEVICENAME = 0x20000007
RIDI_DEVICEINFO = 0x2000000B

WM_DEVICECHANGE = 0x0219
DBT_DEVNODES_CHANGED = 0x0007
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004

ERROR_INSUFFICIENT_BUFFER = 0x0000007A
INVALID_UINT = 0xFFFFFFFF


class RAWINPUTDEVICELIST(ctypes.Structure):
    """Win32 `RAWINPUTDEVICELIST` 구조체 (64비트 환경 기준 16바이트)."""

    _fields_ = [
        ("hDevice", wintypes.HANDLE),
        ("dwType", wintypes.DWORD),
    ]


class RID_DEVICE_INFO_MOUSE(ctypes.Structure):
    """Win32 `RID_DEVICE_INFO_MOUSE` 구조체."""

    _fields_ = [
        ("dwId", wintypes.DWORD),
        ("dwNumberOfButtons", wintypes.DWORD),
        ("dwSampleRate", wintypes.DWORD),
        ("fHasHorizontalWheel", wintypes.BOOL),
    ]


class RID_DEVICE_INFO_KEYBOARD(ctypes.Structure):
    """Win32 `RID_DEVICE_INFO_KEYBOARD` 구조체."""

    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSubType", wintypes.DWORD),
        ("dwKeyboardMode", wintypes.DWORD),
        ("dwNumberOfFunctionKeys", wintypes.DWORD),
        ("dwNumberOfIndicators", wintypes.DWORD),
        ("dwNumberOfKeysTotal", wintypes.DWORD),
    ]


class RID_DEVICE_INFO_HID(ctypes.Structure):
    """Win32 `RID_DEVICE_INFO_HID` 구조체."""

    _fields_ = [
        ("dwVendorId", wintypes.DWORD),
        ("dwProductId", wintypes.DWORD),
        ("dwVersionNumber", wintypes.DWORD),
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
    ]


class _RID_DEVICE_INFO_UNION(ctypes.Union):
    _fields_ = [
        ("mouse", RID_DEVICE_INFO_MOUSE),
        ("keyboard", RID_DEVICE_INFO_KEYBOARD),
        ("hid", RID_DEVICE_INFO_HID),
    ]


class RID_DEVICE_INFO(ctypes.Structure):
    """Win32 `RID_DEVICE_INFO` 공용체 포함 구조체 (64비트 환경 기준 32바이트)."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
        ("u", _RID_DEVICE_INFO_UNION),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)

_user32.GetRawInputDeviceList.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.UINT),
    wintypes.UINT,
]
_user32.GetRawInputDeviceList.restype = wintypes.UINT

_user32.GetRawInputDeviceInfoW.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.UINT),
]
_user32.GetRawInputDeviceInfoW.restype = wintypes.UINT


# USB (`VID_XXXX`) 및 Bluetooth HID (`VID&0002XXXX` / `PID&XXXX`) 파싱 정규식
_RE_VID_USB = re.compile(r"VID_([0-9A-Fa-f]{4})", re.IGNORECASE)
_RE_PID_USB = re.compile(r"PID_([0-9A-Fa-f]{4})", re.IGNORECASE)
_RE_VID_BTH = re.compile(r"VID&[0-9A-Fa-f]{0,4}([0-9A-Fa-f]{4})", re.IGNORECASE)
_RE_PID_BTH = re.compile(r"PID&([0-9A-Fa-f]{4})", re.IGNORECASE)


@dataclass
class DeviceInfo:
    """동적 스캔으로 수집된 단일 입력 장치의 메타데이터."""

    device_id: str
    raw_path: str
    h_device: int
    device_type: DeviceType
    raw_type: int
    name: str
    alias: str = ""
    vid: str = ""
    pid: str = ""
    usage_page: int = 0
    usage: int = 0
    bus_type: str = ""
    key_count: int = 0
    protected: bool = True
    protection_reason: str = ""
    is_connected: bool = True
    is_registered: bool = False
    is_primary_safeguard: bool = False

    @property
    def display_name(self) -> str:
        """UI 및 로그에 표시할 대표 이름을 반환한다."""
        return self.alias or self.name or self.device_id

    @property
    def vid_pid_label(self) -> str:
        """VID/PID가 존재하는 경우 표준 16진수 표기를 반환한다."""
        if self.vid and self.pid:
            return f"{self.vid}:{self.pid}"
        return "N/A"

    def to_dict(self) -> dict[str, Any]:
        """`config.json` 저장용 직렬화 딕셔너리를 생성한다."""
        data = asdict(self)
        data["device_type"] = self.device_type.value
        # 런타임 OS 핸들은 재부팅 시 변동되므로 영구 저장에서 제외
        data.pop("h_device", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceInfo:
        """저장된 딕셔너리로부터 오프라인 `DeviceInfo` 복원본을 생성한다."""
        raw_dev_type = data.get("device_type", DeviceType.HID_OTHER.value)
        try:
            dev_type = DeviceType(raw_dev_type)
        except ValueError:
            dev_type = DeviceType.HID_OTHER

        return cls(
            device_id=str(data["device_id"]),
            raw_path=str(data.get("raw_path", "")),
            h_device=0,
            device_type=dev_type,
            raw_type=int(data.get("raw_type", RIM_TYPEHID)),
            name=str(data.get("name", data["device_id"])),
            alias=str(data.get("alias", "")),
            vid=str(data.get("vid", "")),
            pid=str(data.get("pid", "")),
            usage_page=int(data.get("usage_page", 0)),
            usage=int(data.get("usage", 0)),
            bus_type=str(data.get("bus_type", "")),
            key_count=int(data.get("key_count", 0)),
            protected=bool(data.get("protected", True)),
            protection_reason=str(data.get("protection_reason", "")),
            is_connected=False,
            is_registered=bool(data.get("is_registered", False)),
            is_primary_safeguard=bool(data.get("is_primary_safeguard", False)),
        )


@dataclass
class DeviceScanDiff:
    """장치 재스캔(Hot-Plug 포함) 결과 요약."""

    added: list[DeviceInfo] = field(default_factory=list)
    removed: list[DeviceInfo] = field(default_factory=list)
    connected_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _clean_registry_string(raw_value: str) -> str:
    """Windows 레지스트리 `@inf,...;장치명` 형식에서 실제 표시명을 추출한다."""
    if not raw_value:
        return ""
    if ";" in raw_value:
        return raw_value.split(";", 1)[1].strip()
    return raw_value.strip()


def _query_registry_device_name(raw_path: str) -> str:
    """Raw Input 장치 경로로부터 Windows 레지스트리의 장치 표시명을 조회한다."""
    if not raw_path:
        return ""

    trimmed = raw_path
    if trimmed.startswith("\\\\?\\") or trimmed.startswith("\\\\.\\"):
        trimmed = trimmed[4:]

    parts = trimmed.split("#")
    if len(parts) < 3:
        return ""

    # 마지막 부분이 인터페이스 GUID(`{...}`)라면 제거하여 PnP Enum 경로 구성
    pnp_parts = parts[:-1] if parts[-1].startswith("{") else parts
    if len(pnp_parts) < 3:
        return ""

    enum_subkey = "\\".join(["SYSTEM", "CurrentControlSet", "Enum", *pnp_parts[:3]])
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, enum_subkey) as key:
            for value_name in ("FriendlyName", "DeviceDesc"):
                try:
                    val, _ = winreg.QueryValueEx(key, value_name)
                    cleaned = _clean_registry_string(str(val))
                    if cleaned:
                        return cleaned
                except FileNotFoundError:
                    continue
    except OSError:
        return ""
    return ""


def _parse_bus_vid_pid(raw_path: str, rid_info: RID_DEVICE_INFO) -> tuple[str, str, str]:
    """장치 경로와 `RID_DEVICE_INFO`에서 버스 종류, VID, PID를 추출한다."""
    trimmed = raw_path[4:] if raw_path.startswith("\\\\?\\") else raw_path
    if "#" in trimmed:
        bus_type = trimmed.split("#", 1)[0].upper()
    elif trimmed:
        bus_type = "SYSTEM"
    else:
        bus_type = "UNKNOWN"

    vid = ""
    pid = ""

    if rid_info.dwType == RIM_TYPEHID:
        if rid_info.u.hid.dwVendorId:
            vid = f"0x{rid_info.u.hid.dwVendorId:04X}"
        if rid_info.u.hid.dwProductId:
            pid = f"0x{rid_info.u.hid.dwProductId:04X}"

    if not vid:
        m_vid = _RE_VID_USB.search(raw_path) or _RE_VID_BTH.search(raw_path)
        if m_vid:
            vid = f"0x{m_vid.group(1).upper()}"
    if not pid:
        m_pid = _RE_PID_USB.search(raw_path) or _RE_PID_BTH.search(raw_path)
        if m_pid:
            pid = f"0x{m_pid.group(1).upper()}"

    return bus_type, vid, pid


def _normalize_device_id(raw_path: str, usage_page: int, usage: int) -> str:
    """인터페이스 GUID를 제외한 안정적 하드웨어 식별자를 생성한다."""
    if not raw_path:
        return f"UNKNOWN#UP{usage_page:02X}_U{usage:02X}"

    trimmed = raw_path
    if trimmed.startswith("\\\\?\\") or trimmed.startswith("\\\\.\\"):
        trimmed = trimmed[4:]

    parts = trimmed.split("#")
    if len(parts) >= 2 and parts[-1].startswith("{"):
        core_id = "#".join(parts[:-1])
    else:
        core_id = trimmed

    return core_id.upper()


class DeviceRegistry:
    """연결된 모든 입력 장치를 동적으로 관리하고 안전 잠금을 적용하는 레지스트리."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._devices: dict[str, DeviceInfo] = {}
        self._handle_to_id: dict[int, str] = {}
        self._protected_overrides: dict[str, bool] = {}
        self._listen_mode: bool = False
        self._on_change_callbacks: list[Callable[[DeviceScanDiff], None]] = []

    def add_change_callback(self, callback: Callable[[DeviceScanDiff], None]) -> None:
        """Hot-Plug 등 장치 목록 변경 시 호출될 콜백을 등록한다."""
        with self._lock:
            if callback not in self._on_change_callbacks:
                self._on_change_callbacks.append(callback)

    def remove_change_callback(self, callback: Callable[[DeviceScanDiff], None]) -> None:
        """등록된 장치 변경 콜백을 제거한다."""
        with self._lock:
            if callback in self._on_change_callbacks:
                self._on_change_callbacks.remove(callback)

    def _read_raw_device_list(self) -> list[RAWINPUTDEVICELIST]:
        """`GetRawInputDeviceList`를 안전하게 호출하여 원시 장치 핸들 목록을 가져온다."""
        struct_size = ctypes.sizeof(RAWINPUTDEVICELIST)
        for _ in range(4):
            num_devices = wintypes.UINT(0)
            res = _user32.GetRawInputDeviceList(None, ctypes.byref(num_devices), struct_size)
            if res == INVALID_UINT:
                err = ctypes.get_last_error()
                raise OSError(err, f"GetRawInputDeviceList count query failed (err={err})")

            if num_devices.value == 0:
                return []

            buffer = (RAWINPUTDEVICELIST * num_devices.value)()
            res = _user32.GetRawInputDeviceList(buffer, ctypes.byref(num_devices), struct_size)
            if res == INVALID_UINT:
                err = ctypes.get_last_error()
                if err == ERROR_INSUFFICIENT_BUFFER:
                    # 스캔 도중 새 장치가 꽂힌 경우 재시도
                    continue
                raise OSError(err, f"GetRawInputDeviceList read failed (err={err})")

            return list(buffer[:res])

        raise OSError(ERROR_INSUFFICIENT_BUFFER, "GetRawInputDeviceList failed after retries")

    def _read_device_path(self, h_device: int) -> str:
        """`GetRawInputDeviceInfoW(RIDI_DEVICENAME)`로 장치 인터페이스 경로를 조회한다."""
        char_count = wintypes.UINT(0)
        res = _user32.GetRawInputDeviceInfoW(
            wintypes.HANDLE(h_device),
            RIDI_DEVICENAME,
            None,
            ctypes.byref(char_count),
        )
        if res == INVALID_UINT or char_count.value == 0:
            return ""

        buf = ctypes.create_unicode_buffer(char_count.value + 1)
        res = _user32.GetRawInputDeviceInfoW(
            wintypes.HANDLE(h_device),
            RIDI_DEVICENAME,
            buf,
            ctypes.byref(char_count),
        )
        if res == INVALID_UINT:
            return ""
        return buf.value

    def _read_device_info(self, h_device: int) -> RID_DEVICE_INFO | None:
        """`GetRawInputDeviceInfoW(RIDI_DEVICEINFO)`로 장치 세부 스펙을 조회한다."""
        info = RID_DEVICE_INFO()
        info.cbSize = ctypes.sizeof(RID_DEVICE_INFO)
        cb_size = wintypes.UINT(info.cbSize)
        res = _user32.GetRawInputDeviceInfoW(
            wintypes.HANDLE(h_device),
            RIDI_DEVICEINFO,
            ctypes.byref(info),
            ctypes.byref(cb_size),
        )
        if res == INVALID_UINT:
            return None
        return info

    def _classify_device(
        self,
        raw_path: str,
        rid_info: RID_DEVICE_INFO,
        name: str,
        bus_type: str,
    ) -> tuple[DeviceType, int, int, int, bool, str]:
        """하드웨어 경로와 RID 속성을 기반으로 장치 유형 및 기본 Protected 정책을 판별한다."""
        upper_path = raw_path.upper()
        lower_name = name.lower()

        if rid_info.dwType == RIM_TYPEMOUSE:
            return (
                DeviceType.MOUSE,
                0x01,
                0x02,
                0,
                True,
                "Mouse / Pointer Device (Default Safeguard)",
            )

        if rid_info.dwType == RIM_TYPEKEYBOARD:
            key_count = int(rid_info.u.keyboard.dwNumberOfKeysTotal)
            is_virtual = bus_type == "ROOT" or "RDP_" in upper_path or "TERMINAL" in upper_path

            if is_virtual:
                return (
                    DeviceType.KEYBOARD,
                    0x01,
                    0x06,
                    key_count,
                    True,
                    "System / Virtual Keyboard",
                )

            if bus_type == "ACPI":
                return (
                    DeviceType.KEYBOARD,
                    0x01,
                    0x06,
                    key_count,
                    True,
                    "Built-in Keyboard (ACPI)",
                )

            # 외장 키보드/키패드 구분 (특정 VID/PID 고정 없이 키 수와 명칭으로 보조 분류)
            is_keypad = (0 < key_count < 80) or any(
                kw in lower_name for kw in ("keypad", "numpad", "macro", "키패드")
            )
            dev_type = DeviceType.KEYPAD if is_keypad else DeviceType.KEYBOARD
            return (
                dev_type,
                0x01,
                0x06,
                key_count,
                False,
                "",
            )

        # RIM_TYPEHID
        usage_page = int(rid_info.u.hid.usUsagePage)
        usage = int(rid_info.u.hid.usUsage)

        if usage_page == 0x0C:
            return (
                DeviceType.HID_DIAL,
                usage_page,
                usage,
                0,
                False,
                "",
            )

        # 시스템 제어(0x01/0x80), 디지타이저/터치패드(0x0D) 등 OS 핵심 HID는 기본 보호
        if usage_page == 0x0D or (usage_page == 0x01 and usage in (0x01, 0x02, 0x80)):
            return (
                DeviceType.HID_OTHER,
                usage_page,
                usage,
                0,
                True,
                f"System / Digitizer HID (UsagePage=0x{usage_page:02X})",
            )

        return (
            DeviceType.HID_OTHER,
            usage_page,
            usage,
            0,
            False,
            "",
        )

    def _apply_primary_keyboard_safeguard(self, scanned: dict[str, DeviceInfo]) -> None:
        """ACPI 내장 키보드가 없는 데스크톱/도킹 환경에서도 메인 키보드를 자동 보호한다."""
        physical_keyboards = [
            dev
            for dev in scanned.values()
            if dev.raw_type == RIM_TYPEKEYBOARD
            and dev.bus_type != "ROOT"
            and "RDP_" not in dev.raw_path.upper()
        ]
        if not physical_keyboards:
            return

        # 이미 ACPI 내장 키보드가 보호되어 있으면 주 키보드 안전장치 충족
        if any(dev.bus_type == "ACPI" and dev.protected for dev in physical_keyboards):
            for dev in physical_keyboards:
                if dev.bus_type == "ACPI":
                    dev.is_primary_safeguard = True
            return

        # 물리 키보드가 단 1대뿐이면 키 개수와 무관하게 무조건 보호
        if len(physical_keyboards) == 1:
            sole = physical_keyboards[0]
            sole.protected = True
            sole.is_primary_safeguard = True
            sole.protection_reason = "Sole Physical Keyboard Safeguard"
            return

        # 다수의 외장 키보드 중 ACPI가 없으면 첫 번째 풀배열(>=80키) 또는 첫 번째 장치를 주 키보드로 보호
        full_keyboards = [
            dev for dev in physical_keyboards if dev.key_count == 0 or dev.key_count >= 80
        ]
        primary = full_keyboards[0] if full_keyboards else physical_keyboards[0]
        primary.protected = True
        primary.is_primary_safeguard = True
        primary.protection_reason = "Primary Keyboard Safeguard (No ACPI internal keyboard)"

    def refresh_devices(self) -> DeviceScanDiff:
        """현재 시스템에 연결된 모든 입력 장치를 다시 스캔하여 레지스트리를 갱신한다."""
        raw_entries = self._read_raw_device_list()

        scanned: dict[str, DeviceInfo] = {}
        new_handle_map: dict[int, str] = {}
        warnings: list[str] = []
        handle_errors = 0

        for entry in raw_entries:
            h_dev = int(entry.hDevice or 0)
            if h_dev == 0:
                continue

            raw_path = self._read_device_path(h_dev)
            rid_info = self._read_device_info(h_dev)
            if rid_info is None:
                handle_errors += 1
                continue

            bus_type, vid, pid = _parse_bus_vid_pid(raw_path, rid_info)
            reg_name = _query_registry_device_name(raw_path)

            dev_type, usage_page, usage, key_count, default_protected, reason = (
                self._classify_device(raw_path, rid_info, reg_name, bus_type)
            )

            fallback_name = {
                RIM_TYPEMOUSE: "Mouse Device",
                RIM_TYPEKEYBOARD: "Keyboard Device",
                RIM_TYPEHID: f"HID Device (UP:0x{usage_page:02X} U:0x{usage:02X})",
            }.get(rid_info.dwType, "Unknown Input Device")
            display = reg_name or fallback_name

            device_id = _normalize_device_id(raw_path, usage_page, usage)
            if device_id in scanned:
                device_id = f"{device_id}#UP{usage_page:02X}_U{usage:02X}"
            if device_id in scanned:
                device_id = f"{device_id}#H{h_dev:X}"

            scanned[device_id] = DeviceInfo(
                device_id=device_id,
                raw_path=raw_path,
                h_device=h_dev,
                device_type=dev_type,
                raw_type=int(rid_info.dwType),
                name=display,
                vid=vid,
                pid=pid,
                usage_page=usage_page,
                usage=usage,
                bus_type=bus_type,
                key_count=key_count,
                protected=default_protected,
                protection_reason=reason,
                is_connected=True,
            )
            new_handle_map[h_dev] = device_id

        if raw_entries and not scanned and handle_errors == len(raw_entries):
            warnings.append(
                "GetRawInputDeviceInfoW failed for all handles (restricted token or isolated desktop session)."
            )

        self._apply_primary_keyboard_safeguard(scanned)

        with self._lock:
            prev_connected = {
                dev_id for dev_id, dev in self._devices.items() if dev.is_connected
            }
            added: list[DeviceInfo] = []
            removed: list[DeviceInfo] = []

            # 기존에 저장/등록된 메타데이터(alias, is_registered, 사용자 protected 오버라이드) 보존
            for dev_id, new_dev in scanned.items():
                prev_dev = self._devices.get(dev_id)
                if prev_dev is not None:
                    new_dev.alias = prev_dev.alias
                    new_dev.is_registered = prev_dev.is_registered
                if dev_id in self._protected_overrides:
                    new_dev.protected = self._protected_overrides[dev_id]
                    if new_dev.protected and not new_dev.protection_reason:
                        new_dev.protection_reason = "User Protected"
                    elif not new_dev.protected:
                        new_dev.protection_reason = "Unlocked by User"

                if dev_id not in prev_connected:
                    added.append(new_dev)

            # 연결 해제된 장치 처리: 등록된 장치는 오프라인 상태로 유지, 미등록 장치는 제거
            next_devices: dict[str, DeviceInfo] = dict(scanned)
            for dev_id, old_dev in self._devices.items():
                if dev_id not in scanned:
                    if old_dev.is_connected:
                        removed.append(old_dev)
                    if old_dev.is_registered:
                        old_dev.is_connected = False
                        old_dev.h_device = 0
                        next_devices[dev_id] = old_dev

            self._devices = next_devices
            self._handle_to_id = new_handle_map

            diff = DeviceScanDiff(
                added=added,
                removed=removed,
                connected_count=len(scanned),
                warnings=warnings,
            )
            callbacks = list(self._on_change_callbacks)

        if added or removed:
            for cb in callbacks:
                try:
                    cb(diff)
                except Exception:
                    pass

        return diff

    def handle_device_change(self, wparam: int, lparam: int = 0) -> DeviceScanDiff | None:
        """Win32 `WM_DEVICECHANGE` 메시지를 처리해 Hot-Plug 변경을 즉시 반영한다."""
        del lparam
        if wparam in (DBT_DEVICEARRIVAL, DBT_DEVICEREMOVECOMPLETE, DBT_DEVNODES_CHANGED):
            return self.refresh_devices()
        return None

    def get_all_devices(self, connected_only: bool = False) -> list[DeviceInfo]:
        """등록 및 연결된 장치 목록을 반환한다."""
        with self._lock:
            devices = list(self._devices.values())
            if connected_only:
                devices = [d for d in devices if d.is_connected]
            return devices

    def get_device(self, device_id: str) -> DeviceInfo | None:
        """`device_id`로 장치를 조회한다."""
        with self._lock:
            return self._devices.get(device_id)

    def get_device_by_handle(self, h_device: int) -> DeviceInfo | None:
        """Raw Input `hDevice` 핸들로 O(1) 장치 조회를 수행한다.

        미확인 핸들이 유입되면 Hot-Plug 직후일 수 있으므로 1회 재스캔을 시도한다.
        """
        if not h_device:
            return None
        with self._lock:
            dev_id = self._handle_to_id.get(h_device)
            if dev_id is not None:
                return self._devices.get(dev_id)

        self.refresh_devices()
        with self._lock:
            dev_id = self._handle_to_id.get(h_device)
            return self._devices.get(dev_id) if dev_id is not None else None

    def is_protected(self, device_id: str) -> bool:
        """해당 장치가 보호(`Protected`) 상태인지 확인한다."""
        with self._lock:
            dev = self._devices.get(device_id)
            return dev.protected if dev is not None else True

    def is_handle_protected(self, h_device: int) -> bool:
        """Raw Input 핸들이 보호 장치 소속인지 확인한다. 미확인 핸들은 안전상 보호로 간주한다."""
        dev = self.get_device_by_handle(h_device)
        return dev.protected if dev is not None else True

    def set_protected(self, device_id: str, protected: bool, force: bool = False) -> bool:
        """장치의 `Protected` 잠금 상태를 변경한다.

        주 키보드/유일 키보드 보호 해제 시에는 `force=True`가 필요하다.
        """
        with self._lock:
            dev = self._devices.get(device_id)
            if dev is None:
                return False

            if not protected and dev.is_primary_safeguard and not force:
                raise PermissionError(
                    f"Primary safeguard device '{dev.display_name}' cannot be unprotected without force=True."
                )

            dev.protected = protected
            self._protected_overrides[device_id] = protected
            dev.protection_reason = (
                "User Protected" if protected else "Unlocked by User"
            )
            return True

    def register_device(self, device_id: str, alias: str = "") -> DeviceInfo | None:
        """Listen Mode 등에서 포착된 보조 장치를 리매핑 대상으로 등록한다."""
        with self._lock:
            dev = self._devices.get(device_id)
            if dev is None:
                return None
            if dev.protected:
                raise PermissionError(
                    f"Protected device '{dev.display_name}' cannot be registered for interception."
                )
            dev.is_registered = True
            if alias:
                dev.alias = alias
            return dev

    def unregister_device(self, device_id: str) -> bool:
        """보조 장치 등록을 해제한다."""
        with self._lock:
            dev = self._devices.get(device_id)
            if dev is None:
                return False
            dev.is_registered = False
            return True

    def set_device_alias(self, device_id: str, alias: str) -> bool:
        """장치의 사용자 지정 별칭(Alias)을 설정한다."""
        with self._lock:
            dev = self._devices.get(device_id)
            if dev is None:
                return False
            dev.alias = alias.strip()
            return True

    def begin_listen(self) -> None:
        """Listen Mode를 활성화한다."""
        with self._lock:
            self._listen_mode = True

    def end_listen(self) -> None:
        """Listen Mode를 종료한다."""
        with self._lock:
            self._listen_mode = False

    @property
    def is_listening(self) -> bool:
        """현재 Listen Mode 활성화 여부를 반환한다."""
        with self._lock:
            return self._listen_mode

    def process_listen_handle(self, h_device: int) -> DeviceInfo | None:
        """Listen Mode 중 수신된 `hDevice`가 비보호 보조 장치이면 해당 장치 정보를 반환한다."""
        if not self.is_listening:
            return None
        dev = self.get_device_by_handle(h_device)
        if dev is None or dev.protected:
            return None
        return dev

    def load_saved_devices(self, saved_items: list[dict[str, Any]]) -> None:
        """`config.json`에서 저장된 장치 목록과 보호 설정을 복원한다."""
        with self._lock:
            for item in saved_items:
                dev_id = item.get("device_id")
                if not dev_id:
                    continue
                if "protected" in item:
                    self._protected_overrides[dev_id] = bool(item["protected"])
                existing = self._devices.get(dev_id)
                if existing is not None:
                    existing.alias = str(item.get("alias", existing.alias))
                    existing.is_registered = bool(
                        item.get("is_registered", existing.is_registered)
                    )
                    if dev_id in self._protected_overrides:
                        existing.protected = self._protected_overrides[dev_id]
                else:
                    self._devices[dev_id] = DeviceInfo.from_dict(item)

    def export_devices(self, registered_only: bool = False) -> list[dict[str, Any]]:
        """현재 레지스트리 상태를 `config.json` 저장용 리스트로 직렬화한다."""
        with self._lock:
            items = self._devices.values()
            if registered_only:
                items = [d for d in items if d.is_registered or d.device_id in self._protected_overrides]
            return [d.to_dict() for d in items]


if __name__ == "__main__":
    reg = DeviceRegistry()
    diff = reg.refresh_devices()
    print(f"[DeviceRegistry] Connected devices: {diff.connected_count}")
    for d in reg.get_all_devices(connected_only=True):
        flag = "PROTECTED" if d.protected else "AUXILIARY"
        print(
            f" - [{flag}] {d.device_type.value:8s} | {d.vid_pid_label:9s} | "
            f"UP=0x{d.usage_page:02X} U=0x{d.usage:02X} | Keys={d.key_count:3d} | "
            f"{d.display_name} ({d.protection_reason or 'Remappable'})"
        )
