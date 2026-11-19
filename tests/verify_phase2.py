"""Phase 2 단독 검증 스크립트.

검증 항목:
1. 64비트 Win32 Raw Input / WH_KEYBOARD_LL / Interception 구조체 크기 검증
2. Interception 커널 드라이버 미설치 시 크래시 없이 `USER FALLBACK` 자동 전환 및 실 훅 기동/해제 검증
3. 메인 키보드(`Protected`) 입력 무차단 보장 및 `ESC + F12` 비상 탈출(Panic Exit) 즉시 해제 검증
4. 보조 키패드 버튼 및 eMeet 다이얼(`0x328F:0x0021`) 조작 시 원본 입력(숫자/볼륨) 차단 + `InputEvent` 변환 검증
   (선택 옵션 `--live <초>` 실행 시 실제 물리 다이얼/키패드 실시간 조작 테스트 가능)
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.device_registry import RIM_TYPEHID, RIM_TYPEKEYBOARD, DeviceInfo, DeviceRegistry  # noqa: E402
from core.engine_kernel import InterceptionKeyStroke, KernelEngine  # noqa: E402
from core.engine_manager import EngineManager, EngineMode  # noqa: E402
from core.engine_user import (  # noqa: E402
    KBDLLHOOKSTRUCT,
    LLKHF_INJECTED,
    LLKHF_UP,
    VK_ESCAPE,
    VK_F12,
    UserFallbackEngine,
)
from core.events import DeviceType, EngineSource, EventType, InputEvent  # noqa: E402
from core.hid_dial import RAWHID, RAWINPUTHEADER, RAWKEYBOARD, RAWMOUSE  # noqa: E402


def verify_64bit_phase2_structs() -> None:
    """Phase 2 Win32 / Interception 구조체 크기를 검증한다."""
    ptr_size = ctypes.sizeof(ctypes.c_void_p)
    hdr_sz = ctypes.sizeof(RAWINPUTHEADER)
    kb_sz = ctypes.sizeof(RAWKEYBOARD)
    mouse_sz = ctypes.sizeof(RAWMOUSE)
    ll_sz = ctypes.sizeof(KBDLLHOOKSTRUCT)
    stroke_sz = ctypes.sizeof(InterceptionKeyStroke)

    print(f"[1/4] Phase 2 64-bit Struct Check (ptr={ptr_size}B)")
    print(
        f"      RAWINPUTHEADER={hdr_sz}B, RAWKEYBOARD={kb_sz}B, "
        f"RAWMOUSE={mouse_sz}B, KBDLLHOOKSTRUCT={ll_sz}B, InterceptionKeyStroke={stroke_sz}B"
    )
    if ptr_size == 8:
        assert hdr_sz == 24
        assert kb_sz == 16
        assert mouse_sz == 24
        assert ll_sz == 24
        assert stroke_sz == 8
        assert ctypes.sizeof(RAWHID) >= 12


def verify_kernel_to_user_fallback() -> tuple[EngineManager, DeviceRegistry]:
    """드라이버 미설치 환경에서 크래시 없이 USER FALLBACK 전환 및 실 메시지 루프 기동을 검증한다."""
    avail, reason = KernelEngine.probe_availability()
    print(f"[2/4] Kernel Probe -> available={avail}, reason='{reason}'")

    registry = DeviceRegistry()
    registry.refresh_devices()

    mgr = EngineManager(registry=registry)
    mode = mgr.start(prefer_kernel=True)
    print(f"      EngineManager.start() -> mode={mode.value}, badge={mgr.status_badge}")

    if not avail:
        assert mode == EngineMode.USER_FALLBACK, f"Expected USER_FALLBACK, got {mode}"
        assert mgr.status_badge == "[ENGINE: USER FALLBACK]"
        assert mgr.user_engine is not None and mgr.user_engine.is_running
    else:
        assert mode == EngineMode.KERNEL

    return mgr, registry


def verify_aux_blocking_and_main_safeguard(
    mgr: EngineManager, registry: DeviceRegistry
) -> None:
    """보조 키패드·eMeet 다이얼 원본 차단, InputEvent 변환, 메인 키보드 보호를 검증한다."""
    captured_events: list[InputEvent] = []
    mgr.add_event_callback(captured_events.append)

    devices = registry.get_all_devices(connected_only=True)

    # 메인 키보드 확인
    main_kb = next(
        (d for d in devices if d.raw_type == RIM_TYPEKEYBOARD and d.protected),
        None,
    )
    assert main_kb is not None, "Protected main keyboard must exist!"

    # eMeet 다이얼(0x328F:0x0021, UP=0x0C) 탐색 (미연결 시 테스트용 가상 장치 객체 사용)
    dial_dev = next(
        (
            d
            for d in devices
            if d.raw_type == RIM_TYPEHID
            and d.usage_page == 0x0C
            and d.vid.upper() == "0X328F"
            and d.pid.upper() == "0X0021"
        ),
        None,
    )
    if dial_dev is None:
        dial_dev = DeviceInfo(
            device_id="HID#VID_328F&PID_0021&COL01#SIMULATED",
            raw_path="",
            h_device=99001,
            device_type=DeviceType.HID_DIAL,
            raw_type=RIM_TYPEHID,
            name="Simulated eMeet eMute-E1",
            vid="0x328F",
            pid="0x0021",
            usage_page=0x0C,
            usage=0x01,
            protected=False,
        )
        registry._devices[dial_dev.device_id] = dial_dev  # 테스트용 임시 등록
        dial_live = False
    else:
        dial_live = True

    # 보조 키패드/외장 키보드 탐색 (VID/PID 보유 외장 장치 우선, 미연결 시 테스트용 가상 키패드 사용)
    aux_kp = next(
        (
            d
            for d in devices
            if d.raw_type == RIM_TYPEKEYBOARD and not d.protected and d.vid
        ),
        None,
    ) or next(
        (
            d
            for d in devices
            if d.raw_type == RIM_TYPEKEYBOARD and not d.protected
        ),
        None,
    )
    if aux_kp is None:
        aux_kp = DeviceInfo(
            device_id="HID#VID_248A&PID_8327&MI_01#SIMULATED",
            raw_path="",
            h_device=99002,
            device_type=DeviceType.KEYPAD,
            raw_type=RIM_TYPEKEYBOARD,
            name="Simulated Auxiliary Keypad",
            vid="0x248A",
            pid="0x8327",
            key_count=19,
            protected=False,
        )
        registry._devices[aux_kp.device_id] = aux_kp
        kp_live = False
    else:
        kp_live = True

    registry.register_device(dial_dev.device_id, alias="Test Dial")
    registry.register_device(aux_kp.device_id, alias="Test Keypad")

    user_eng = mgr.user_engine
    assert user_eng is not None

    print(
        f"[3/4] Blocking & Event Conversion Check\n"
        f"      - Main Keyboard : {main_kb.name} (Protected={main_kb.protected})\n"
        f"      - Aux Keypad    : {aux_kp.name} ({aux_kp.vid_pid_label}, live={kp_live})\n"
        f"      - eMeet Dial    : {dial_dev.name} ({dial_dev.vid_pid_label}, live={dial_live})"
    )

    # A. 메인 키보드 입력 -> 절대 차단되지 않아야 함 + 이벤트 발행 안 됨
    ev_main = user_eng.process_raw_keyboard_data(
        device=main_kb, vk_code=0x41, scan_code=0x1E, is_up=False, is_extended=False
    )
    assert ev_main is None, "Protected main keyboard must NOT produce intercepted events!"
    block_main, panic_main = user_eng.evaluate_ll_keyboard_event(0x41, 0x1E, 0)
    assert not block_main and not panic_main, "Main keyboard MUST NOT be blocked!"

    # B. SendInput 소프트웨어 주입(LLKHF_INJECTED) -> 절대 차단되지 않아야 함
    block_inj, _ = user_eng.evaluate_ll_keyboard_event(0x67, 0x47, LLKHF_INJECTED)
    assert not block_inj, "Injected SendInput keystrokes MUST NOT be blocked!"

    # C. 보조 키패드 입력(Numpad 7: VK=0x67, Scan=0x47) -> 원본 차단 + InputEvent 생성
    captured_events.clear()
    ev_kp_down = user_eng.process_raw_keyboard_data(
        device=aux_kp, vk_code=0x67, scan_code=0x47, is_up=False, is_extended=False
    )
    assert ev_kp_down is not None
    assert ev_kp_down.event_type == EventType.KEY_DOWN
    assert ev_kp_down.code == 0x47
    assert ev_kp_down.vk_code == 0x67
    assert ev_kp_down.source == EngineSource.USER_FALLBACK

    block_kp_down, _ = user_eng.evaluate_ll_keyboard_event(0x67, 0x47, 0)
    assert block_kp_down is True, "Auxiliary keypad original key-down MUST be blocked!"

    ev_kp_up = user_eng.process_raw_keyboard_data(
        device=aux_kp, vk_code=0x67, scan_code=0x47, is_up=True, is_extended=False
    )
    assert ev_kp_up is not None and ev_kp_up.event_type == EventType.KEY_UP
    block_kp_up, _ = user_eng.evaluate_ll_keyboard_event(0x67, 0x47, LLKHF_UP)
    assert block_kp_up is True, "Auxiliary keypad original key-up MUST be blocked!"

    # 보조 키패드 직후 메인 키보드 동일 VK 입력은 통과해야 함
    user_eng.process_raw_keyboard_data(
        device=main_kb, vk_code=0x67, scan_code=0x47, is_up=False, is_extended=False
    )
    block_main_same, _ = user_eng.evaluate_ll_keyboard_event(0x67, 0x47, 0)
    assert not block_main_same, "Main keyboard same key MUST remain unblocked!"

    # D. eMeet 다이얼 Raw 패킷 검증 ([02 E9 00], [02 EA 00], [02 B5 00], [02 00 00])
    captured_events.clear()
    # 1) 우회전 [02 E9 00] -> DIAL_CW + VK_VOLUME_UP(0xAF) 차단
    cw_events = user_eng.process_raw_hid_data(dial_dev, b"\x02\xe9\x00")
    assert len(cw_events) == 1 and cw_events[0].event_type == EventType.DIAL_CW
    assert cw_events[0].code == 0x00E9 and cw_events[0].value == 1
    block_vol_up, _ = user_eng.evaluate_ll_keyboard_event(0xAF, 0, 0)
    assert block_vol_up is True, "Original VK_VOLUME_UP from eMeet dial MUST be blocked!"
    block_vol_up_rel, _ = user_eng.evaluate_ll_keyboard_event(0xAF, 0, LLKHF_UP)
    assert block_vol_up_rel is True, "Paired VK_VOLUME_UP key-up MUST be blocked!"

    # 2) 좌회전 [02 EA 00] -> DIAL_CCW + VK_VOLUME_DOWN(0xAE) 차단
    ccw_events = user_eng.process_raw_hid_data(dial_dev, b"\x02\xea\x00")
    assert len(ccw_events) == 1 and ccw_events[0].event_type == EventType.DIAL_CCW
    assert ccw_events[0].code == 0x00EA and ccw_events[0].value == -1
    block_vol_dn, _ = user_eng.evaluate_ll_keyboard_event(0xAE, 0, 0)
    assert block_vol_dn is True, "Original VK_VOLUME_DOWN from eMeet dial MUST be blocked!"

    # 3) 클릭 [02 B5 00] + 릴리즈 [02 00 00] -> DIAL_PRESS/DIAL_RELEASE + VK_MEDIA_NEXT_TRACK(0xB0) 차단
    click_events = user_eng.process_raw_hid_data(dial_dev, b"\x02\xb5\x00")
    assert len(click_events) == 1 and click_events[0].event_type == EventType.DIAL_PRESS
    assert click_events[0].code == 0x00B5
    block_next, _ = user_eng.evaluate_ll_keyboard_event(0xB0, 0, 0)
    assert block_next is True, "Original VK_MEDIA_NEXT_TRACK from eMeet dial MUST be blocked!"

    rel_events = user_eng.process_raw_hid_data(dial_dev, b"\x02\x00\x00")
    assert len(rel_events) == 1 and rel_events[0].event_type == EventType.DIAL_RELEASE
    assert rel_events[0].code == 0x00B5 and rel_events[0].value == 0

    # 4) 다이얼 패킷 없이 들어온 독립 볼륨 키(예: 노트북 Fn+Vol)는 통과
    block_fn_vol, _ = user_eng.evaluate_ll_keyboard_event(0xAF, 0, 0)
    assert not block_fn_vol, "Unassociated system volume key MUST NOT be blocked!"

    print(
        f"      Keypad & eMeet Dial Blocking + InputEvent Conversion OK "
        f"(captured={len(captured_events)} dial events)"
    )


def verify_panic_exit(mgr: EngineManager) -> None:
    """`ESC + F12` 동시 입력 시 비상 탈출(Panic Exit) 및 훅 즉시 해제를 검증한다."""
    panic_called = False

    def _on_panic() -> None:
        nonlocal panic_called
        panic_called = True

    mgr.add_panic_callback(_on_panic)
    user_eng = mgr.user_engine
    assert user_eng is not None and user_eng.is_running

    # ESC 누름 -> 아직 패닉 아님
    b1, p1 = user_eng.evaluate_ll_keyboard_event(VK_ESCAPE, 0x01, 0)
    assert not b1 and not p1

    # ESC 누른 상태에서 F12 동시 입력 -> 즉시 Panic Exit 발동
    b2, p2 = user_eng.evaluate_ll_keyboard_event(VK_F12, 0x58, 0)
    assert not b2 and p2 is True, "ESC + F12 must trigger Panic Exit!"

    # 훅 콜백과 동일하게 비상 탈출 실행 후 전체 엔진/스레드 즉시 해제 검증
    mgr.trigger_panic_exit()
    assert panic_called is True
    assert mgr.panic_triggered is True
    assert mgr.mode == EngineMode.STOPPED
    assert mgr.status_badge == "[ENGINE: STOPPED]"
    assert not user_eng.is_running, "UserFallbackEngine thread must stop immediately!"

    print("[4/4] Panic Exit (ESC + F12) Immediate Unhook & Stop Check OK")


def run_live_interactive(seconds: int) -> None:
    """선택 실행: 실제 물리 다이얼/보조 키패드를 조작해 차단 및 InputEvent 출력을 실시간 확인한다."""
    registry = DeviceRegistry()
    registry.refresh_devices()

    for d in registry.get_all_devices(connected_only=True):
        if not d.protected and (
            (d.vid.upper() == "0X328F" and d.pid.upper() == "0X0021" and d.usage_page == 0x0C)
            or (d.vid.upper() == "0X248A" and d.pid.upper() == "0X8327" and d.raw_type == RIM_TYPEKEYBOARD)
        ):
            registry.register_device(d.device_id)
            print(f"[LIVE] Registered auxiliary target: {d.display_name} ({d.device_id})")

    mgr = EngineManager(registry=registry)
    mgr.add_event_callback(
        lambda ev: print(
            f"[LIVE EVENT] {ev.source_str} | {ev.device_name} | "
            f"{ev.event_type_str} | code={ev.code} val={ev.value} raw={ev.raw_data.hex()}"
        )
    )
    mgr.add_panic_callback(lambda: print("[LIVE PANIC] ESC+F12 detected -> Exiting live test!"))
    mode = mgr.start(prefer_kernel=True)
    print(f"[LIVE] Engine started: {mgr.status_badge} ({mode.value}). Listening for {seconds}s (ESC+F12 to abort)...")

    end_t = time.monotonic() + seconds
    try:
        while time.monotonic() < end_t and mgr.mode != EngineMode.STOPPED:
            time.sleep(0.1)
    finally:
        mgr.stop()
    print("[LIVE] Stopped cleanly.")


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS Remapper Phase 2 Verification")
    parser.add_argument(
        "--live",
        type=int,
        default=0,
        help="Optional seconds to run live physical dial/keypad capture test",
    )
    args = parser.parse_args()

    verify_64bit_phase2_structs()
    mgr, registry = verify_kernel_to_user_fallback()
    try:
        verify_aux_blocking_and_main_safeguard(mgr, registry)
        verify_panic_exit(mgr)
    finally:
        mgr.stop()

    print("\nALL PHASE 2 CHECKS PASSED.")

    if args.live > 0:
        run_live_interactive(args.live)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
