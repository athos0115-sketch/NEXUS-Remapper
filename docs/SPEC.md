# **Project: NEXUS Remapper & Universal Workspace Orchestrator**

**Master Architecture Specification (GEMINI.md)**

## **1\. 프로젝트 개요 및 핵심 철학**

* **목표:** 특정 제조사나 모델에 종속되지 않고, Windows PC에 연결되는 모든 보조 HID 입력 장치(외장 키패드, 매크로 패드, 로터리 다이얼 등)를 동적으로 인식·격리하여 제어하는 **범용 하드웨어 허브 및 워크스페이스 오케스트레이터** 구축.  
* **환경 독립성 (Plug & Play):** 집과 사무실 등 물리적으로 분리된 다중 환경(서로 다른 입력 장치, 상이한 모니터 대수·해상도·DPI 배율)에서도 단일 코드베이스와 단일 실행 파일(.exe)로 무결하게 작동한다.  
* **개발 환경:** Windows 11 (64-bit), Python 3.12 LTS, PyQt6, ctypes (Win32 Native API), Interception Kernel Driver.  
* **디자인 및 UX 원칙:**  
  * **Dark Luminous 테마:** 딥 다크 배경 기반의 테크웨어 UI, 실시간 트리거 입력 시 네온 글로우 피드백.  
  * **무간섭 백그라운드 운용:** 작업 화면을 가리는 상시 오버레이를 배제하고, 설정 콘솔을 닫아도 시스템 트레이(System Tray)에 상주하여 백그라운드로 구동.

## **2\. 핵심 모듈 아키텍처 및 디렉터리 구조**

모든 입력 엔진은 UI 및 액션 실행기와 철저히 분리(관심사 분리)되어야 하며, 표준화된 내부 이벤트 객체 InputEvent(device\_id, event\_type, code, value)만을 주고받는다.

Plaintext

```
NEXUS_Remapper/
├── GEMINI.md                     # 프로젝트 마스터 규격서
├── main.py                       # 프로그램 진입점, DPI 초기화 및 트레이/UI 실행
├── config.json                   # 장치 등록, 레이어별 매핑, 모니터 레이아웃 프리셋 저장소
├── core/
│   ├── events.py                 # 표준 InputEvent 데이터 클래스 정의
│   ├── device_registry.py        # 동적 HID/키보드 스캐너, Hot-Plug 및 보호 장치 관리
│   ├── engine_kernel.py          # [1순위] Interception 커널 드라이버 기반 입력 차단/격리
│   ├── engine_user.py            # [2순위] Raw Input + WH_KEYBOARD_LL 유저 모드 폴백
│   ├── hid_dial.py               # 범용 Consumer Control(0x0C) / 로터리 다이얼 Raw 파서
│   ├── engine_manager.py         # 이중 엔진 자동 전환 매니저 및 비상 탈출(Panic Exit)
│   ├── context_watcher.py        # 이벤트 기반 활성 프로세스 감지 및 프로파일 자동 스위칭
│   ├── window_orchestrator.py    # 비율 기반 다중 모니터 창 정렬 및 스냅샷 캡처 엔진
│   └── actions.py                # SendInput 단축키, 가속 휠, 텍스트, 앱/레이아웃 실행기
└── ui/
    ├── main_window.py            # 3단 레이아웃 PyQt6 메인 콘솔 및 환경 드롭다운 헤더
    ├── device_panel.py           # 연결 장치 목록, 보호(Protected) 토글, Listen 등록
    └── mapping_cards.py          # 동적 매핑 카드 위젯 및 네온 글로우 애니메이션
```

## **3\. 모듈별 상세 기술 명세**

### **3.1 동적 장치 레지스트리 (core/device\_registry.py)**

* **하드코딩 배제:** 특정 VID/PID를 고정하지 않고 GetRawInputDeviceList를 통해 시스템의 모든 키보드 및 HID 장치 경로를 동적 열거한다.  
* **Hot-Plug 지원:** WM\_DEVICECHANGE 메시지를 수신하여 작업 중 블루투스 기기가 절전에서 깨어나거나 USB 장치가 추가/제거되어도 프로그램 재시작 없이 즉시 반영한다.  
* **메인 장치 보호(Safe-Guard):** 노트북 내장 키보드 및 메인 마우스는 기본 Protected 상태로 잠금 처리하여 실수로 입력이 차단되는 사고를 방지한다.  
* **Listen & Bind:** 사용자가 UI에서 \[새 장치 등록\]을 활성화한 뒤 보조 기기를 조작하면 해당 장치의 고유 식별자(VID/PID \+ Interface Path)를 추출해 config.json에 등록한다.  
* **사전 검증된 레퍼런스 하드웨어 (PoC 기준 데이터):**  
  * 로터리 다이얼 (eMeet eMute-E1): VID: 0x328F, PID: 0x0021, UsagePage 0x0C (우회전 02 E9 00 / 좌회전 02 EA 00 / 클릭 02 B5 00 / 릴리즈 02 00 00).  
  * 외장 키패드 (무선 2.4G / Bluetooth IC-KP09 등): VID: 0x248A, PID: 0x8327 및 Bluetooth HID 키보드 인터페이스.

### **3.2 이중 입력 엔진 아키텍처 (core/engine\_\*.py, core/hid\_dial.py)**

* **1순위 — 커널 모드 (engine\_kernel.py):**  
  * Interception 커널 드라이버를 통해 등록된 보조 키패드 신호만 OS 도달 전 커널 계층에서 0ms 지연으로 가로채고 원본 입력을 완전히 폐기(Drop)한다.  
  * 관리자 권한(UIPI)으로 실행되는 CAD/BIM 뷰포트에서도 입력 누수(Leak)나 씹힘이 발생하지 않는다.  
* **2순위 — 유저 모드 폴백 (engine\_user.py):**  
  * 드라이버가 설치되지 않았거나 사내 보안 솔루션(AppGuard 등)에 의해 커널 필터가 차단된 경우, 크래시 없이 자동으로 Raw Input(장치 판별) \+ WH\_KEYBOARD\_LL(키 차단) 모드로 전환된다.  
* **범용 로터리/HID 파서 (hid\_dial.py):**  
  * 키보드 드라이버 관할 밖인 Consumer Control(0x0C) 및 커스텀 HID 장치의 Raw 바이트 패킷을 직접 수신·파싱하여 회전 방향과 클릭 이벤트를 생성한다.  
* **엔진 매니저 및 안전장치 (engine\_manager.py):**  
  * 프로그램 구동 시 커널 핸들 가용성을 자동 진단해 \[KERNEL MODE\] 또는 \[USER FALLBACK\]을 선택하고 UI 배지에 현재 상태를 표시한다.  
  * **비상 탈출(Panic Exit):** 메인 키보드의 ESC \+ F12 조합이 입력되면 모든 훅과 인터셉션을 즉시 해제하고 안전 종료한다.

### **3.3 이벤트 기반 활성 창 감지기 (core/context\_watcher.py)**

* **무부하 감지:** CPU 폴링(while 루프)을 금지하고 Win32 SetWinEventHook(EVENT\_SYSTEM\_FOREGROUND)를 사용하여 활성 창이 바뀔 때만 콜백을 실행한다.  
* **컨텍스트 자동 프로파일 스위칭:** 포커스된 실행 파일명(Revit.exe, acad.exe, Code.exe, MinimalMediaPlayer.exe, WorldChronicleEngine.exe, 브라우저 등)을 감지하여 해당 앱에 매핑된 다이얼/키패드 프로파일로 실시간 전환한다.  
  * *예시:* MinimalMediaPlayer 활성 시 다이얼 \= 볼륨·밝기 제어 ➔ World Chronicle Engine으로 전환 시 다이얼 \= 시뮬레이션 시간 배속·줌 제어 ➔ Revit/AutoCAD 전환 시 다이얼 \= 뷰포트 정밀 줌(Ctrl+Wheel).

### **3.4 동적 다중 모니터 창 오케스트레이터 (core/window\_orchestrator.py)**

* **DPI 및 해상도 독립성:**  
  * 진입점 초기화 시 SetProcessDpiAwarenessContext(-4) (PER\_MONITOR\_AWARE\_V2)를 선언하여 서로 다른 배율의 모니터 간 좌표 왜곡을 방지한다.  
  * 창 위치는 절대 픽셀(px)이 아닌 각 모니터 작업 영역(rcWork) 기준 **정규화 상대 비율(0.0 \~ 1.0)** (monitor\_index, x\_ratio, y\_ratio, w\_ratio, h\_ratio)로 저장한다.  
* **디스플레이 토폴로지 자동 감지 & 드롭다운 스위처:**  
  * EnumDisplayMonitors로 현재 연결된 모니터 대수, 배치 순서(좌→우), 해상도를 조합한 환경 지문(Topology Fingerprint)을 생성한다.  
  * UI 상단 드롭다운에서 **\[자동 감지\]** 또는 사용자가 저장한 환경 프로파일(예: 집 울트라와이드+노트북, 사무실 듀얼 모니터, 단일 화면 등)을 즉시 선택·전환할 수 있다.  
* **원클릭 스냅샷 캡처(Snapshot):** 사용자가 마우스로 원하는 프로그램(예: 주 모니터 Revit \+ 보조 모니터 AutoCAD 및 브라우저)을 배치한 뒤 \[현재 창 배치 스냅샷 저장\]을 누르면, 각 창의 프로세스명과 정규화 비율을 자동 계산해 config.json 프리셋으로 저장한다.  
* **안전한 정렬 정책:** 대상 창이 최대화/최소화 상태인 경우 반드시 ShowWindow(hwnd, SW\_RESTORE)로 선행 해제한 뒤 SetWindowPos를 호출한다. 미실행 프로그램에 대해서는 실행 중인 창만 정렬과 앱 자동 실행 후 정렬 옵션을 분리 제공한다.

### **3.5 통합 액션 출력기 (core/actions.py)**

아래 6대 액션 카테고리를 표준 인터페이스로 실행한다.

1. **복합 단축키 (Key Combos):** SendInput 기반 저지연 키 조합 주입.  
2. **마우스 휠 및 줌 제어 (Mouse Wheel):** 가속 배율이 적용된 Ctrl \+ Wheel 및 수평/수직 스크롤.  
3. **상용구 텍스트 주입 (Text Injection):** pyperclip 클립보드 백업/복원 기반 고속 문자열 붙여넣기.  
4. **미디어 및 시스템 제어 (Media/System):** 볼륨, 음소거, 트랙 이동, 밝기 제어.  
5. **창 레이아웃 및 앱 실행 (Workspace/App):** 저장된 다중 모니터 창 배치 프리셋 호출 및 특정 프로그램 실행.  
6. **멀티 레이어 전환 (Layer Shift):** 단일 물리 장치 내에서 작업 모드(예: BIM 모드 ↔ 미디어/일반 모드)를 실시간 전환.

## **4\. 엄격한 구현 및 패키징 규칙**

1. **64비트 Win32 API 타입 안전성:** 모든 ctypes 기반 Windows API 호출(CreateWindowExW, GetRawInputData, SetWindowPos, SendInput 등)은 64비트 포인터 오버플로우(OverflowError)를 원천 차단하기 위해 반드시 argtypes와 restype을 명시적으로 선언한다.  
2. **스레드 안전성:** 커널 루프, 유저 훅, SetWinEventHook은 PyQt6 메인 UI 스레드를 블로킹하지 않도록 독립 워커 스레드에서 구동하고 pyqtSignal로만 UI와 통신한다.  
3. **단일 실행 파일 호환성:** PyInstaller로 단일 .exe 빌드 시에도 설정이 유지되도록 config.json 경로는 sys.frozen 여부를 판별해 실행 파일 기준 디렉터리로 고정한다.

## **5\. 안티그래비티(Antigravity) 병렬 개발 로드맵**

* **Phase 1 (코어 인프라 & 출력):** core/events.py, core/actions.py, core/device\_registry.py 동시 구현 및 장치 동적 스캔 검증.  
* **Phase 2 (이중 입력 엔진):** engine\_kernel.py, engine\_user.py, hid\_dial.py, engine\_manager.py 구현 및 커널↔폴백 자동 전환·비상 탈출 테스트.  
* **Phase 3 (워크스페이스 오케스트레이션):** context\_watcher.py와 window\_orchestrator.py(DPI V2 비율 계산 \+ 스냅샷 캡처) 구현 및 듀얼 모니터 정렬 검증.  
* **Phase 4 (PyQt6 Dark Luminous UI):** 3단 콘솔, 상단 모니터 환경 드롭다운, Listen Mode 동적 카드 생성, 네온 글로우 피드백 및 config.json 영구 저장 연동.  
* **Phase 5 (트레이 상주 & 배포):** 시스템 트레이 백그라운드 구동 처리 및 PyInstaller 단일 .exe 빌드 완료.

