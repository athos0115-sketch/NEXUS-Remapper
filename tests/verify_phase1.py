"""Phase 1 단독 검증 스크립트.

검증 항목:
1. 디렉터리 구조 및 모듈 임포트 무결성
2. 64비트 Win32 ctypes 구조체 크기 및 포인터 안전성 검증
3. `InputEvent` 생성·직렬화·바인딩 키 규격 검증
4. `DeviceRegistry` 동적 HID/키보드/마우스 실시간 스캔 및 메인 키보드 `Protected` 잠금 검증
5. `ActionExecutor` 6대 액션 카테고리 디스패치 및 Layer/Layout 콜백 연동 검증 (dry_run 안전 모드)
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.actions import (  # noqa: E402
    INPUT,
    ActionExecutor,
    ActionSpec,
    ActionType,
    resolve_vk,
)
from core.device_registry import (  # noqa: E402
    RAWINPUTDEVICELIST,
    RID_DEVICE_INFO,
    DeviceRegistry,
)
from core.events import DeviceType, EngineSource, EventType, InputEvent  # noqa: E402


def verify_64bit_structures() -> None:
    """64비트 Windows 기준 Win32 구조체 바이트 크기를 검증한다."""
    ptr_size = ctypes.sizeof(ctypes.c_void_p)
    input_size = ctypes.sizeof(INPUT)
    raw_list_size = ctypes.sizeof(RAWINPUTDEVICELIST)
    rid_info_size = ctypes.sizeof(RID_DEVICE_INFO)

    print(f"[1/4] 64-bit ctypes Structure Check (ptr={ptr_size}B)")
    print(f"      - sizeof(INPUT)              = {input_size} bytes")
    print(f"      - sizeof(RAWINPUTDEVICELIST) = {raw_list_size} bytes")
    print(f"      - sizeof(RID_DEVICE_INFO)    = {rid_info_size} bytes")

    if ptr_size == 8:
        assert input_size == 40, f"Expected 40B INPUT on 64-bit, got {input_size}"
        assert raw_list_size == 16, f"Expected 16B RAWINPUTDEVICELIST on 64-bit, got {raw_list_size}"
        assert rid_info_size == 32, f"Expected 32B RID_DEVICE_INFO on 64-bit, got {rid_info_size}"


def verify_input_events() -> None:
    """표준 `InputEvent` 인터페이스와 직렬화를 검증한다."""
    ev = InputEvent(
        "HID#VID_328F&PID_0021#TEST",
        EventType.DIAL_CW,
        0x00E9,
        1,
        source=EngineSource.RAW_HID,
        raw_data=b"\x02\xe9\x00",
        device_name="Test Dial",
    )
    assert ev.binding_key == "HID#VID_328F&PID_0021#TEST|dial_cw|0x00E9"
    d = ev.to_dict()
    assert d["raw_data"] == "02e900"
    assert d["event_type"] == "dial_cw"
    print(f"[2/4] InputEvent Check OK -> {ev.binding_key}")


def verify_device_registry() -> None:
    """실제 PC에 연결된 입력 장치를 동적 스캔하고 메인 키보드 보호 정책을 검증한다."""
    registry = DeviceRegistry()
    diff = registry.refresh_devices()
    devices = registry.get_all_devices(connected_only=True)

    print(f"[3/4] DeviceRegistry Live Scan -> Total Connected: {diff.connected_count}")
    print("-" * 108)
    print(
        f"{'STATUS':10s} | {'TYPE':8s} | {'BUS':5s} | {'VID:PID':9s} | "
        f"{'UP:U':9s} | {'KEYS':4s} | {'NAME / REASON'}"
    )
    print("-" * 108)

    keyboards = []
    mice = []
    aux_devices = []

    for dev in devices:
        status = "PROTECTED" if dev.protected else "AUXILIARY"
        up_u = f"0x{dev.usage_page:02X}:0x{dev.usage:02X}"
        reason = f" [{dev.protection_reason}]" if dev.protection_reason else ""
        print(
            f"{status:10s} | {dev.device_type.value:8s} | {dev.bus_type[:5]:5s} | "
            f"{dev.vid_pid_label:9s} | {up_u:9s} | {dev.key_count:4d} | "
            f"{dev.display_name}{reason}"
        )
        print(f"           ID: {dev.device_id}")

        if dev.device_type in (DeviceType.KEYBOARD, DeviceType.KEYPAD):
            keyboards.append(dev)
        if dev.device_type == DeviceType.MOUSE:
            mice.append(dev)
        if not dev.protected:
            aux_devices.append(dev)

    print("-" * 108)

    # 메인 키보드 보호 확인
    protected_keyboards = [k for k in keyboards if k.protected]
    assert len(keyboards) > 0, "No keyboard detected via GetRawInputDeviceList!"
    assert len(protected_keyboards) >= 1, "Main keyboard MUST be protected!"
    assert any(k.is_primary_safeguard for k in protected_keyboards), (
        "At least one keyboard must carry primary safeguard flag!"
    )

    # 모든 마우스는 기본 보호 확인
    for m in mice:
        assert m.protected, f"Mouse {m.display_name} must be protected by default!"

    # Primary Safeguard 보호 해제 차단 테스트 (force=False 시 PermissionError 발생)
    primary_kb = next(k for k in protected_keyboards if k.is_primary_safeguard)
    try:
        registry.set_protected(primary_kb.device_id, False, force=False)
        raise AssertionError("Primary safeguard keyboard was unprotected without force=True!")
    except PermissionError:
        pass

    # Listen Mode 테스트: 보호된 장치는 Listen 등록 대상에서 배제되어야 함
    registry.begin_listen()
    assert registry.process_listen_handle(primary_kb.h_device) is None, (
        "Protected main keyboard must be ignored in Listen Mode!"
    )
    if aux_devices:
        captured = registry.process_listen_handle(aux_devices[0].h_device)
        assert captured is not None and captured.device_id == aux_devices[0].device_id
        print(f"      Listen Mode Auxiliary Capture OK -> {captured.display_name}")
    else:
        print("      Listen Mode Guard OK (Main keyboard ignored; no auxiliary device currently unlocked)")
    registry.end_listen()

    # Config 직렬화/복원 라운드트립 테스트
    exported = registry.export_devices()
    assert len(exported) == len(devices)
    restored_registry = DeviceRegistry()
    restored_registry.load_saved_devices(exported)
    assert len(restored_registry.get_all_devices()) == len(exported)
    print(f"      Config Roundtrip & Primary Safeguard Check OK (Primary: {primary_kb.display_name})")


def verify_action_executor() -> None:
    """ActionExecutor 6대 액션 카테고리 생성 및 디스패치를 검증한다(dry_run=True)."""
    applied_layouts: list[str] = []
    shifted_layers: list[str] = []

    executor = ActionExecutor(
        dry_run=True,
        layout_handler=lambda name: applied_layouts.append(name) or True,
        layer_change_handler=lambda layer: shifted_layers.append(layer),
        layers=["default", "bim", "media"],
    )

    assert resolve_vk("Ctrl") == 0x11
    assert resolve_vk("F12") == 0x7B

    specs = [
        ActionSpec(ActionType.KEY_COMBO, {"combo": "Ctrl+Shift+S"}),
        ActionSpec(ActionType.MOUSE_WHEEL, {"direction": -1, "steps": 2, "accel": 1.5}),
        ActionSpec(ActionType.ZOOM, {"direction": 1, "accel": 2.0}),
        ActionSpec(ActionType.TEXT, {"text": "NEXUS_OK", "method": "unicode"}),
        ActionSpec(ActionType.MEDIA, {"command": "play_pause"}),
        ActionSpec(ActionType.BRIGHTNESS, {"delta": 10}),
        ActionSpec(ActionType.LAUNCH_APP, {"executable": "notepad.exe"}),
        ActionSpec(ActionType.WORKSPACE_LAYOUT, {"preset": "Dual_CAD"}),
        ActionSpec(ActionType.LAYER_SHIFT, {"mode": "cycle"}),
    ]

    for spec in specs:
        res = executor.execute(spec)
        assert res.success, f"Action failed: {spec} -> {res}"

    assert executor.active_layer == "bim"
    assert shifted_layers == ["bim"]
    # dry_run=False 일 때 layout_handler 직접 호출 확인
    executor.dry_run = False
    res_layout = executor.apply_layout_preset("Dual_CAD")
    assert res_layout.success and applied_layouts == ["Dual_CAD"]

    print("[4/4] ActionExecutor 6-Category Dispatch Check OK")


def main() -> int:
    verify_64bit_structures()
    verify_input_events()
    verify_device_registry()
    verify_action_executor()
    print("\nALL PHASE 1 CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
