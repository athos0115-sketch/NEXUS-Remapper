# GEMINI.md — Project: NEXUS Remapper & Universal Workspace Orchestrator

이 문서는 **NEXUS Remapper** 프로젝트의 최상위 개발 규격 및 에이전트 행동 지침이다. 모든 코드 생성, 리팩토링, 디버깅, 아키텍처 결정은 본 문서의 규칙을 엄격히 준수해야 한다.

---

## 1. 프로젝트 정체성 및 실행 환경

- **목표:** Windows PC에 연결되는 모든 보조 HID 입력 장치(외장 키패드, 매크로 패드, 로터리 다이얼 등)를 동적으로 인식·격리하여 제어하고, 활성 프로세스 감지 및 다중 모니터 창 레이아웃 정렬까지 통합 지휘하는 **범용 하드웨어 허브 및 워크스페이스 오케스트레이터**.
- **운용 시나리오:** 집(로터리 다이얼 중심, 울트라와이드+노트북)과 사무실(블루투스/무선 키패드 중심, 듀얼 모니터 및 AppGuard 보안 환경) 등 물리적으로 다른 환경에서 **단일 코드베이스 및 단일 `.exe` 파일**로 무결하게 동작해야 한다.
- **기술 스택:**
  - OS: Windows 11 (64-bit)
  - Runtime: Python 3.12 LTS (안정 버전 기준, 불필요한 C++ 컴파일 의존성 배제)
  - GUI: PyQt6
  - System / HID: Python `ctypes` (Win32 Native API), `Interception` Kernel Driver, `pyperclip`
  - Packaging: PyInstaller (단일 실행 파일 `.exe`)

---

## 2. 절대 타협 불가한 4대 설계 원칙 (Non-Negotiable)

1. **하드웨어 비종속성 (Zero Hardcoding):**
   - 특정 제조사의 VID/PID나 키 레이아웃을 코드에 고정하지 않는다.
   - `GetRawInputDeviceList` 및 `WM_DEVICECHANGE`를 통해 연결된 모든 보조 입력 장치를 동적으로 스캔하고, Hot-Plug(실행 중 장치 연결/해제/절전 복귀)를 완벽히 지원한다.
   - 사용자가 UI의 `Listen Mode`에서 물리 장치를 조작하면 해당 기기의 식별자를 추출해 `config.json`에 동적 등록한다.
   - 메인 키보드와 메인 마우스는 기본 `Protected` 상태로 보호하여 실수로 입력이 차단(Block)되는 사고를 원천 봉쇄한다.

2. **이중 입력 엔진 (Kernel Primary + User Fallback):**
   - **1순위 (`engine_kernel.py`):** `Interception` 커널 드라이버를 사용해 등록된 보조 키패드 신호를 OS 도달 전 커널 단에서 0ms 지연으로 차단(Drop) 및 치환한다.
   - **2순위 (`engine_user.py`):** 드라이버 미설치 또는 사내 보안 솔루션(AppGuard 등)에 의해 드라이버가 차단된 경우, 오류 종료 없이 즉시 `Raw Input + WH_KEYBOARD_LL` 유저 모드 엔진으로 자동 폴백(Fallback)한다.
   - **로터리/Consumer HID (`hid_dial.py`):** 키보드 커널 드라이버 관할 밖인 `UsagePage 0x0C` 및 커스텀 HID 장치는 엔진 모드와 무관하게 독립적인 Raw Input 파서가 전담한다.

3. **디스플레이 환경 독립성 (Relative Ratio & Auto-Topology):**
   - 창 배치 좌표는 절대 픽셀(`px`) 저장을 금지하며, 각 모니터 작업 영역(`rcWork`) 기준 **정규화 비율(`0.0 ~ 1.0`)**로만 저장·계산한다.
   - `EnumDisplayMonitors`로 현재 모니터 대수·순서·해상도를 자동 감지하되, UI 상단 드롭다운에서 `[자동 감지 / 저장된 환경 프로파일]`을 수동 선택할 수 있어야 한다.
   - 사용자가 마우스로 배치한 현재 창 구성을 원클릭으로 비율 환산해 저장하는 **스냅샷(Snapshot) 기능**을 반드시 제공한다.

4. **무간섭 백그라운드 운용 (No Screen Clutter):**
   - 작업 화면을 가리는 상시 HUD나 플로팅 오버레이를 만들지 않는다.
   - 메인 콘솔 창을 닫으면 프로세스를 종료하지 않고 시스템 트레이(System Tray)로 최소화하여 백그라운드에서 상시 구동한다.

---

## 3. 디렉터리 구조 및 모듈 경계 (Separation of Concerns)

입력 엔진은 UI나 액션 실행 로직을 직접 참조하지 않으며, 모든 입력은 `core/events.py`의 표준 이벤트 객체(`InputEvent`)로만 전달한다.

~~~text
NEXUS_Remapper/
├── GEMINI.md                     # 본 지침서
├── main.py                       # 진입점, DPI 초기화, 트레이 및 메인 윈도우 실행
├── config.json                   # 장치 바인딩, 레이어/앱별 매핑, 모니터 레이아웃 프리셋
├── core/
│   ├── events.py                 # 표준 InputEvent(device_id, event_type, code, value) 정의
│   ├── device_registry.py        # 동적 HID/키보드 스캔, Hot-Plug, Protected 장치 관리
│   ├── engine_kernel.py          # [1순위] Interception 커널 드라이버 입력 격리 엔진
│   ├── engine_user.py            # [2순위] Raw Input + WH_KEYBOARD_LL 유저 모드 폴백 엔진
│   ├── hid_dial.py               # 범용 Consumer Control(0x0C) / 로터리 다이얼 Raw 파서
│   ├── engine_manager.py         # 드라이버 자동 진단, 모드 스위칭, 비상 탈출(Panic Exit)
│   ├── context_watcher.py        # SetWinEventHook 기반 활성 프로세스 감지 및 프로파일 전환
│   ├── window_orchestrator.py    # DPI V2 비율 기반 다중 모니터 창 정렬 및 스냅샷 캡처
│   └── actions.py                # SendInput 단축키, 가속 휠, 텍스트, 앱/레이아웃/레이어 실행기
└── ui/
    ├── main_window.py            # 3단 레이아웃 PyQt6 콘솔 및 상단 모니터 환경 드롭다운
    ├── device_panel.py           # 연결 장치 목록, Protected 토글, 새 장치 Listen 등록
    └── mapping_cards.py          # 동적 매핑 카드 위젯 및 네온 글로우 트리거 피드백
~~~

---

## 4. 엄격한 기술 제약 및 Win32 코딩 규칙

1. **64비트 `ctypes` 타입 명시 의무화:**
   - 모든 Win32 API 함수(`CreateWindowExW`, `GetRawInputData`, `GetRawInputDeviceInfoW`, `SetWindowPos`, `SendInput`, `SetWinEventHook` 등)는 64비트 포인터 `OverflowError`를 방지하기 위해 호출 전 반드시 `argtypes`와 `restype`을 명시적으로 선언한다.
2. **Per-Monitor DPI V2 강제 적용:**
   - 앱 시작 최상단(PyQt6 `QApplication` 생성 전)에 `SetProcessDpiAwarenessContext(-4)`를 호출해 서로 다른 배율의 듀얼 모니터 간 좌표 왜곡을 차단한다.
3. **비상 탈출 안전장치 (Panic Exit):**
   - 훅 또는 인터셉션 오작동으로 입력이 잠기는 상황을 방지하기 위해, 메인 키보드의 `ESC + F12` 동시 입력 시 모든 훅/드라이버를 즉시 해제하고 안전 종료하는 로직을 `engine_manager.py`에 최우선 배치한다.
4. **무부하 활성 창 감지:**
   - `while` 루프 기반의 CPU 폴링(Polling)을 금지한다. 반드시 `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` 이벤트 훅을 사용해 포커스가 바뀔 때만 콜백을 실행한다.
5. **안전한 창 이동 시퀀스:**
   - `SetWindowPos` 호출 전, 대상 창이 최대화/최소화 상태라면 반드시 `ShowWindow(hwnd, SW_RESTORE)`로 일반 창 상태로 선행 복원한다.
   - 미실행 프로그램에 대해서는 `실행 중인 창만 정렬` 모드와 `미실행 앱 자동 실행 후 정렬` 옵션을 분리 제공한다.
6. **스레드 안전성:**
   - 커널 루프, 유저 훅, WinEventHook은 PyQt6 메인 스레드를 절대 블로킹하지 않도록 독립 워커 스레드에서 실행하고, UI 업데이트는 오직 `pyqtSignal`로만 통신한다.
7. **단일 `.exe` 경로 호환성:**
   - `config.json` 및 리소스 경로는 `getattr(sys, 'frozen', False)`를 판별해 개발 환경(`__file__`)과 패키징 환경(`sys.executable`) 모두에서 실행 파일 기준 상대 경로로 로드한다.

---

## 5. UI / UX 가이드라인 (Dark Luminous)

- **컬러 팔레트:** 딥 다크 배경(`#121214`, `#1A1A1E`), 미세한 보더(`#2D2D35`), 가독성 높은 실버/화이트 텍스트(`#ECECF1`), 활성 상태 및 트리거 점등용 네온 포인트 컬러(시안 `#00FFCC`, 퍼플 `#A855F7`, 오렌지 `#F97316`).
- **상태 가시성:** 상단 헤더에 현재 가동 중인 엔진 배지(`[ENGINE: KERNEL]` / `[ENGINE: USER FALLBACK]`), 활성 프로세스명, 그리고 모니터 환경 드롭다운을 상시 표시한다.
- **Listen Mode:** 활성화 상태에서 보조 장치의 키를 누르거나 다이얼을 돌리면 화면에 해당 입력의 매핑 카드가 동적으로 생성되며, 평소 조작 시 해당 카드 테두리가 네온 글로우로 짧게 점등된다.

---

## 6. 사전 검증된 레퍼런스 하드웨어 데이터 (참고 전용 — 하드코딩 금지)

실제 테스트 및 파서 검증 시 아래 실측 패킷 구조를 기준 샘플로 활용하되, 코드는 모든 동종 HID 장치를 수용할 수 있어야 한다.

- **로터리 다이얼 샘플 (eMeet eMute-E1):**
  - `VID: 0x328F`, `PID: 0x0021`, `UsagePage: 0x0C` (Consumer Control)
  - Raw 패킷: 우회전 `[02 E9 00]`, 좌회전 `[02 EA 00]`, 클릭 `[02 B5 00]`, 릴리즈 `[02 00 00]`
- **외장 키패드 샘플 (무선 2.4G / Bluetooth IC-KP09):**
  - 무선 동글 `VID: 0x248A`, `PID: 0x8327` 및 Bluetooth HID 키보드 인터페이스
  - 표준 스캔코드 기반 이산 입력 (메인 키보드와 `hDevice` / Hardware ID로 격리)
- **주요 컨텍스트 타깃 프로세스 예시:**
  - `Revit.exe`, `acad.exe`, `Code.exe`, `MinimalMediaPlayer.exe`, `WorldChronicleEngine.exe`, `chrome.exe`

---

## 7. 안티그래비티 에이전트 작업 프로토콜

1. **단계별 검증 우선 (Phase-Gated):** 각 모듈 작성 후 즉시 단독 실행 가능한 테스트 코드 또는 검증 커맨드를 제공해 동작을 확인한 뒤 다음 단계로 넘어간다.
   - `Phase 1`: `events.py`, `actions.py`, `device_registry.py`
   - `Phase 2`: `engine_kernel.py`, `engine_user.py`, `hid_dial.py`, `engine_manager.py`
   - `Phase 3`: `context_watcher.py`, `window_orchestrator.py`
   - `Phase 4`: `ui/*`, `main.py`, `config.json` 연동
   - `Phase 5`: 시스템 트레이 상주 및 `PyInstaller` 단일 `.exe` 빌드
2. **외부 라이브러리 최소화:** `hidapi`처럼 C++ 빌드를 강제해 Python 환경 충돌을 유발하는 패키지 설치를 피하고, Win32 `ctypes` 네이티브 구현을 최우선으로 한다.
3. **기존 기능 보존:** 리팩토링이나 기능 추가 시 이미 검증된 64비트 `argtypes` 선언, `Protected` 장치 잠금, `Panic Exit` 안전장치를 임의로 제거하거나 약화시키지 않는다.