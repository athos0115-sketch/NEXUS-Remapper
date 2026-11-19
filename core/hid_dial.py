"""범용 Consumer Control(UsagePage 0x0C) 및 커스텀 HID Raw 파서 모듈.

특정 제조사 VID/PID에 종속되지 않고 Win32 Raw Input(`RIM_TYPEHID`)의
원시 바이트 패킷을 표준 `InputEvent`로 변환하며, 다이얼/미디어 키가 발생시키는
OS 기본 동작(볼륨 조절·트랙 이동 등)을 유저 모드 훅에서 차단할 수 있도록
레거시 가상 키(VK) 억제 정보를 함께 제공한다.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

from core.device_registry import DeviceInfo
from core.events import EngineSource, EventType, InputEvent

# ============================================================================
# Win32 Raw Input 구조체 및 64비트 ctypes 선언
# ============================================================================

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RID_HEADER = 0x10000005

RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RIM_TYPEHID = 2

RIDEV_REMOVE = 0x00000001
RIDEV_NOLEGACY = 0x00000030
RIDEV_INPUTSINK = 0x00000100
RIDEV_DEVNOTIFY = 0x00002000


class RAWINPUTDEVICE(ctypes.Structure):
    """Win32 `RAWINPUTDEVICE` 구조체."""

    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    """Win32 `RAWINPUTHEADER` 구조체 (64비트 환경 기준 24바이트)."""

    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class _RAWMOUSE_BUTTONS(ctypes.Structure):
    _fields_ = [
        ("usButtonFlags", wintypes.USHORT),
        ("usButtonData", wintypes.USHORT),
    ]


class _RAWMOUSE_UNION(ctypes.Union):
    _fields_ = [
        ("ulButtons", wintypes.ULONG),
        ("buttons", _RAWMOUSE_BUTTONS),
    ]


class RAWMOUSE(ctypes.Structure):
    """Win32 `RAWMOUSE` 구조체 (64비트 환경 기준 24바이트)."""

    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("u", _RAWMOUSE_UNION),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class RAWKEYBOARD(ctypes.Structure):
    """Win32 `RAWKEYBOARD` 구조체 (16바이트)."""

    _fields_ = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


class RAWHID(ctypes.Structure):
    """Win32 `RAWHID` 가변 길이 헤더 구조체."""

    _fields_ = [
        ("dwSizeHid", wintypes.DWORD),
        ("dwCount", wintypes.DWORD),
        ("bRawData", wintypes.BYTE * 1),
    ]


class _RAWINPUT_DATA(ctypes.Union):
    _fields_ = [
        ("mouse", RAWMOUSE),
        ("keyboard", RAWKEYBOARD),
        ("hid", RAWHID),
    ]


class RAWINPUT(ctypes.Structure):
    """Win32 `RAWINPUT` 구조체."""

    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("data", _RAWINPUT_DATA),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)

_user32.RegisterRawInputDevices.argtypes = [
    ctypes.POINTER(RAWINPUTDEVICE),
    wintypes.UINT,
    wintypes.UINT,
]
_user32.RegisterRawInputDevices.restype = wintypes.BOOL

_user32.GetRawInputData.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.UINT),
    wintypes.UINT,
]
_user32.GetRawInputData.restype = wintypes.UINT


# ============================================================================
# HID Consumer Control (UsagePage 0x0C) 표준 매핑 테이블
# ============================================================================

# HID UsagePage 0x0C 표준 코드 -> (EventType, 방향/값, 대응 OS 레거시 VK)
CONSUMER_USAGE_TABLE: dict[int, tuple[EventType, int, int | None]] = {
    0x00E9: (EventType.DIAL_CW, 1, 0xAF),       # Volume Increment -> VK_VOLUME_UP
    0x00EA: (EventType.DIAL_CCW, -1, 0xAE),     # Volume Decrement -> VK_VOLUME_DOWN
    0x00E2: (EventType.DIAL_PRESS, 1, 0xAD),    # Mute -> VK_VOLUME_MUTE
    0x00B5: (EventType.DIAL_PRESS, 1, 0xB0),    # Scan Next Track -> VK_MEDIA_NEXT_TRACK
    0x00B6: (EventType.DIAL_PRESS, 1, 0xB1),    # Scan Previous Track -> VK_MEDIA_PREV_TRACK
    0x00B7: (EventType.DIAL_PRESS, 1, 0xB2),    # Stop -> VK_MEDIA_STOP
    0x00CD: (EventType.DIAL_PRESS, 1, 0xB3),    # Play/Pause -> VK_MEDIA_PLAY_PAUSE
}

# 릴리즈([02 00 00]) 수신 시 직전 버튼 누름에 대응해 DIAL_RELEASE를 발생시킬 Usage 집합
_PRESS_USAGES: frozenset[int] = frozenset({0x00E2, 0x00B5, 0x00B6, 0x00B7, 0x00CD})


@dataclass(frozen=True)
class ParsedHidResult:
    """단일 Raw HID 패킷 파싱 결과."""

    events: list[InputEvent]
    suppress_vks: list[int]


def read_raw_input_from_lparam(
    lparam: int,
) -> tuple[RAWINPUTHEADER, RAWKEYBOARD | None, bytes, int, int]:
    """`WM_INPUT`의 `lParam`(`HRAWINPUT`)에서 헤더와 페이로드를 안전하게 추출한다.

    Returns:
        (header, raw_keyboard_or_none, hid_payload_bytes, dw_size_hid, dw_count)
    """
    h_raw = wintypes.HANDLE(lparam)
    cb_size = wintypes.UINT(0)
    header_size = ctypes.sizeof(RAWINPUTHEADER)

    res = _user32.GetRawInputData(
        h_raw, RID_INPUT, None, ctypes.byref(cb_size), header_size
    )
    if res == 0xFFFFFFFF or cb_size.value < header_size:
        raise OSError(ctypes.get_last_error(), "GetRawInputData size query failed")

    buf = (ctypes.c_ubyte * cb_size.value)()
    written = _user32.GetRawInputData(
        h_raw, RID_INPUT, buf, ctypes.byref(cb_size), header_size
    )
    if written == 0xFFFFFFFF:
        raise OSError(ctypes.get_last_error(), "GetRawInputData read failed")

    base_addr = ctypes.addressof(buf)
    header = RAWINPUTHEADER.from_buffer_copy(buf)

    if header.dwType == RIM_TYPEKEYBOARD:
        kb = RAWKEYBOARD.from_buffer_copy(
            (ctypes.c_ubyte * ctypes.sizeof(RAWKEYBOARD)).from_address(
                base_addr + header_size
            )
        )
        return header, kb, b"", 0, 0

    if header.dwType == RIM_TYPEHID:
        rawhid_offset = header_size
        # dwSizeHid (4B) + dwCount (4B) = 8B
        dw_size_hid = int.from_bytes(bytes(buf[rawhid_offset : rawhid_offset + 4]), "little")
        dw_count = int.from_bytes(bytes(buf[rawhid_offset + 4 : rawhid_offset + 8]), "little")
        payload_start = rawhid_offset + 8
        payload = bytes(buf[payload_start : min(written, payload_start + dw_size_hid * dw_count)])
        return header, None, payload, dw_size_hid, dw_count

    return header, None, b"", 0, 0


class HidDialParser:
    """UsagePage 0x0C(Consumer Control) 및 범용 Raw HID 패킷 상태 파서.

    연속 회전 간격(`dt`) 기반 동적 가속(`velocity`)과
    버튼 클릭·더블클릭(`DIAL_DOUBLE_CLICK`)·롱프레스(`DIAL_LONG_PRESS`)를 판별한다.
    """

    def __init__(
        self,
        long_press_sec: float = 0.45,
        double_click_sec: float = 0.35,
    ) -> None:
        self._lock = threading.Lock()
        self.long_press_sec = long_press_sec
        self.double_click_sec = double_click_sec
        # 장치별 직전 눌린 버튼 Usage 및 누름 시작 시각
        self._active_press_by_device: dict[str, tuple[int, float]] = {}
        # 장치별 직전 짧은 클릭 (usage, release_ts) — 더블 클릭 판별용
        self._last_click_by_device: dict[str, tuple[int, float]] = {}
        # 장치별 직전 회전 (direction, ts) — 동적 가속 곡선 산출용
        self._last_rotation_by_device: dict[str, tuple[int, float]] = {}

    def _compute_rotation_velocity(
        self, device_id: str, direction: int, now: float
    ) -> float:
        """연속 회전 시간 간격(`dt`)에 따라 동적 가속 배율(1.0 ~ 3.0)을 계산한다."""
        with self._lock:
            prev = self._last_rotation_by_device.get(device_id)
            self._last_rotation_by_device[device_id] = (direction, now)

        if prev is None or prev[0] != direction:
            return 1.0
        dt = now - prev[1]
        if dt <= 0.045:
            return 3.0
        if dt <= 0.095:
            return 2.0
        if dt <= 0.160:
            return 1.4
        return 1.0

    @staticmethod
    def get_legacy_vk_for_usage(usage: int) -> int | None:
        """Consumer Usage 코드에 대응하는 Win32 레거시 VK 코드를 반환한다."""
        entry = CONSUMER_USAGE_TABLE.get(usage)
        return entry[2] if entry is not None else None

    def _split_reports(
        self, raw_bytes: bytes, dw_size_hid: int, dw_count: int
    ) -> list[bytes]:
        """다중 리포트 패킷(`dwCount > 1`)을 개별 리포트 슬라이스로 분할한다."""
        if not raw_bytes:
            return []
        if dw_size_hid > 0 and dw_count > 1:
            reports = []
            for idx in range(dw_count):
                start = idx * dw_size_hid
                chunk = raw_bytes[start : start + dw_size_hid]
                if chunk:
                    reports.append(chunk)
            return reports
        return [raw_bytes]

    @staticmethod
    def _extract_consumer_usage(report: bytes) -> int | None:
        """Consumer Control HID 리포트에서 16비트 Usage ID를 추출한다."""
        if len(report) >= 3:
            # 표준 [ReportID, UsageLo, UsageHi, ...] 포맷 (예: 02 E9 00)
            return int.from_bytes(report[1:3], "little")
        if len(report) == 2:
            return int.from_bytes(report[0:2], "little")
        if len(report) == 1:
            return int(report[0])
        return None

    def parse_raw_hid(
        self,
        device: DeviceInfo,
        raw_bytes: bytes,
        dw_size_hid: int = 0,
        dw_count: int = 1,
        now: float | None = None,
    ) -> ParsedHidResult:
        """`RIM_TYPEHID` 페이로드를 파싱해 표준 `InputEvent` 및 차단 대상 VK 목록을 생성한다."""
        events: list[InputEvent] = []
        suppress_vks: list[int] = []
        reports = self._split_reports(raw_bytes, dw_size_hid, dw_count)
        ts = time.monotonic() if now is None else float(now)

        for report in reports:
            if device.usage_page == 0x0C:
                usage = self._extract_consumer_usage(report)
                if usage is None:
                    continue

                if usage == 0x0000:
                    with self._lock:
                        prev_press = self._active_press_by_device.pop(device.device_id, None)
                    if prev_press is not None:
                        prev_usage, pressed_ts = prev_press
                        held_sec = max(0.0, ts - pressed_ts)
                        legacy_vk = self.get_legacy_vk_for_usage(prev_usage) or 0
                        events.append(
                            InputEvent(
                                device_id=device.device_id,
                                event_type=EventType.DIAL_RELEASE,
                                code=prev_usage,
                                value=0,
                                timestamp=ts,
                                source=EngineSource.RAW_HID,
                                raw_data=report,
                                vk_code=legacy_vk,
                                device_name=device.display_name,
                            )
                        )
                        if held_sec >= self.long_press_sec:
                            with self._lock:
                                self._last_click_by_device.pop(device.device_id, None)
                            events.append(
                                InputEvent(
                                    device_id=device.device_id,
                                    event_type=EventType.DIAL_LONG_PRESS,
                                    code=prev_usage,
                                    value=1,
                                    timestamp=ts,
                                    source=EngineSource.RAW_HID,
                                    raw_data=report,
                                    vk_code=legacy_vk,
                                    device_name=device.display_name,
                                )
                            )
                        else:
                            is_double = False
                            with self._lock:
                                last_click = self._last_click_by_device.get(device.device_id)
                                if (
                                    last_click is not None
                                    and last_click[0] == prev_usage
                                    and (ts - last_click[1]) <= self.double_click_sec
                                ):
                                    is_double = True
                                    self._last_click_by_device.pop(device.device_id, None)
                                else:
                                    self._last_click_by_device[device.device_id] = (
                                        prev_usage,
                                        ts,
                                    )
                            if is_double:
                                events.append(
                                    InputEvent(
                                        device_id=device.device_id,
                                        event_type=EventType.DIAL_DOUBLE_CLICK,
                                        code=prev_usage,
                                        value=2,
                                        timestamp=ts,
                                        source=EngineSource.RAW_HID,
                                        raw_data=report,
                                        vk_code=legacy_vk,
                                        device_name=device.display_name,
                                    )
                                )
                    continue

                mapped = CONSUMER_USAGE_TABLE.get(usage)
                if mapped is not None:
                    ev_type, val, legacy_vk = mapped
                    velocity = 1.0
                    if ev_type in (EventType.DIAL_CW, EventType.DIAL_CCW):
                        velocity = self._compute_rotation_velocity(
                            device.device_id, val, ts
                        )
                    elif usage in _PRESS_USAGES or ev_type == EventType.DIAL_PRESS:
                        with self._lock:
                            self._active_press_by_device[device.device_id] = (usage, ts)
                    if legacy_vk is not None:
                        suppress_vks.append(legacy_vk)
                    events.append(
                        InputEvent(
                            device_id=device.device_id,
                            event_type=ev_type,
                            code=usage,
                            value=val,
                            timestamp=ts,
                            source=EngineSource.RAW_HID,
                            raw_data=report,
                            vk_code=legacy_vk or 0,
                            device_name=device.display_name,
                            velocity=velocity,
                        )
                    )
                else:
                    # 알려지지 않은 Consumer Usage도 버튼 누름으로 표준 이벤트화
                    with self._lock:
                        self._active_press_by_device[device.device_id] = (usage, ts)
                    events.append(
                        InputEvent(
                            device_id=device.device_id,
                            event_type=EventType.DIAL_PRESS,
                            code=usage,
                            value=1,
                            timestamp=ts,
                            source=EngineSource.RAW_HID,
                            raw_data=report,
                            device_name=device.display_name,
                        )
                    )
            else:
                # 비-0x0C 커스텀/벤더 HID 장치 패킷
                events.append(
                    InputEvent(
                        device_id=device.device_id,
                        event_type=EventType.HID_RAW,
                        code=f"0x{report.hex().upper()}",
                        value=1,
                        source=EngineSource.RAW_HID,
                        raw_data=report,
                        device_name=device.display_name,
                    )
                )

        return ParsedHidResult(events=events, suppress_vks=suppress_vks)


if __name__ == "__main__":
    from core.events import DeviceType

    sample_dial = DeviceInfo(
        device_id="HID#VID_328F&PID_0021&COL01#TEST",
        raw_path="",
        h_device=12345,
        device_type=DeviceType.HID_DIAL,
        raw_type=RIM_TYPEHID,
        name="Sample Consumer Dial",
        usage_page=0x0C,
        usage=0x01,
        protected=False,
        is_registered=True,
    )
    parser = HidDialParser()
    for pkt in (b"\x02\xe9\x00", b"\x02\xea\x00", b"\x02\xb5\x00", b"\x02\x00\x00"):
        res = parser.parse_raw_hid(sample_dial, pkt)
        print(pkt.hex(" "), "->", [(e.event_type_str, hex(int(e.code)), e.value) for e in res.events], "suppress:", [hex(v) for v in res.suppress_vks])
