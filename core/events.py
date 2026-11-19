"""표준 내부 입력 이벤트 및 장치/엔진 열거형 정의 모듈.

모든 입력 엔진(커널, 유저 폴백, Raw HID)은 UI 및 액션 실행기를 직접 참조하지 않고
본 모듈의 `InputEvent` 객체를 통해서만 이벤트를 전달한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """표준화된 입력 이벤트 유형."""

    KEY_DOWN = "key_down"
    KEY_UP = "key_up"
    DIAL_CW = "dial_cw"
    DIAL_CCW = "dial_ccw"
    DIAL_PRESS = "dial_press"
    DIAL_RELEASE = "dial_release"
    DIAL_DOUBLE_CLICK = "dial_double_click"
    DIAL_LONG_PRESS = "dial_long_press"
    HID_RAW = "hid_raw"
    MOUSE_BUTTON = "mouse_button"
    MOUSE_WHEEL = "mouse_wheel"


class DeviceType(str, Enum):
    """동적으로 분류된 HID/입력 장치 유형."""

    KEYBOARD = "keyboard"
    KEYPAD = "keypad"
    MOUSE = "mouse"
    HID_DIAL = "hid_dial"
    HID_OTHER = "hid_other"


class EngineSource(str, Enum):
    """이벤트를 생성한 입력 엔진 계층 식별자."""

    KERNEL = "kernel"
    USER_FALLBACK = "user_fallback"
    RAW_HID = "raw_hid"
    SYSTEM = "system"


def normalize_binding_event_type(event_type: EventType | str) -> str:
    """바인딩 키 1:1 매칭을 위해 press/release 쌍을 단일 이벤트 키로 정규화한다."""
    raw = event_type.value if isinstance(event_type, EventType) else str(event_type)
    if raw in (EventType.KEY_DOWN.value, EventType.KEY_UP.value, "key"):
        return "key"
    if raw in (EventType.DIAL_PRESS.value, EventType.DIAL_RELEASE.value):
        return EventType.DIAL_PRESS.value
    return raw


@dataclass(frozen=True, slots=True)
class InputEvent:
    """엔진 계층과 액션/UI 계층 사이를 오가는 표준 입력 이벤트 객체.

    Attributes:
        device_id: 정규화된 하드웨어 독립 장치 식별자.
        event_type: 이벤트 종류 (`EventType` 또는 문자열).
        code: 스캔코드, 가상 키(VK) 코드 또는 HID Usage/패킷 코드.
        value: 입력 값 (키 눌림=1/뗌=0, 다이얼 회전 방향/스텝 등).
        timestamp: 단조 증가 시각(`time.monotonic()`).
        source: 이벤트를 발생시킨 엔진 계층.
        raw_data: Raw HID 패킷 원본 바이트(선택).
        is_extended: Win32 확장 키(E0/E1) 여부.
        vk_code: 보조 참조용 Win32 가상 키 코드.
        device_name: 로그/UI 표시용 장치 이름.
    """

    device_id: str
    event_type: EventType | str
    code: int | str
    value: int = 1
    timestamp: float = field(default_factory=time.monotonic)
    source: EngineSource | str = EngineSource.USER_FALLBACK
    raw_data: bytes = b""
    is_extended: bool = False
    vk_code: int = 0
    device_name: str = ""
    velocity: float = 1.0

    @property
    def event_type_str(self) -> str:
        """열거형/문자열 여부에 무관하게 일관된 이벤트 타입 문자열을 반환한다."""
        if isinstance(self.event_type, EventType):
            return self.event_type.value
        return str(self.event_type)

    @property
    def source_str(self) -> str:
        """열거형/문자열 여부에 무관하게 일관된 엔진 소스 문자열을 반환한다."""
        if isinstance(self.source, EngineSource):
            return self.source.value
        return str(self.source)

    @property
    def is_release(self) -> bool:
        """버튼/키를 뗄 때 발생하는 release(up) 이벤트인지 여부를 반환한다."""
        et = self.event_type_str
        if et in (EventType.KEY_UP.value, EventType.DIAL_RELEASE.value):
            return True
        if et == EventType.MOUSE_BUTTON.value and int(self.value) == 0:
            return True
        return False

    @property
    def binding_key(self) -> str:
        """매핑 테이블 조회 및 Listen 카드 생성을 위한 정규화 키 문자열을 반환한다.

        키보드(KEY_DOWN/KEY_UP) 및 버튼(DIAL_PRESS/DIAL_RELEASE)의 press/release
        구분을 제거해 1:1 매핑을 유지한다.
        """
        code_str = (
            f"0x{self.code:04X}" if isinstance(self.code, int) else str(self.code)
        )
        norm_type = normalize_binding_event_type(self.event_type)
        return f"{self.device_id}|{norm_type}|{code_str}"

    def to_dict(self) -> dict[str, Any]:
        """직렬화 가능한 딕셔너리로 변환한다."""
        return {
            "device_id": self.device_id,
            "event_type": self.event_type_str,
            "code": self.code,
            "value": self.value,
            "timestamp": self.timestamp,
            "source": self.source_str,
            "raw_data": self.raw_data.hex() if self.raw_data else "",
            "is_extended": self.is_extended,
            "vk_code": self.vk_code,
            "device_name": self.device_name,
            "velocity": self.velocity,
        }


if __name__ == "__main__":
    sample = InputEvent(
        device_id="HID#VID_328F&PID_0021#SAMPLE",
        event_type=EventType.DIAL_CW,
        code=0x00E9,
        value=1,
        source=EngineSource.RAW_HID,
        raw_data=b"\x02\xe9\x00",
        device_name="Sample Rotary Dial",
    )
    print("InputEvent self-test:", sample.binding_key, sample.to_dict())
