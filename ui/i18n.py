"""경량 다국어(한국어 / 日本語 / English) 내장 사전 모듈 — Darkroom Filament v1.1 (Quiet Pro)."""

from __future__ import annotations

from ui.theme import TOKENS

LANGUAGE_LABELS: dict[str, str] = {
    "ko": "한국어",
    "ja": "日本語",
    "en": "English",
}

_GOLD = TOKENS["--filament-gold"]
_ORANGE = TOKENS["--filament-orange-text"]
_DANGER = TOKENS["--status-danger-text"]
_MUTED = TOKENS["--text-secondary"]
_BORDER = TOKENS["--border-specular"]

_README_KO = f"""
<h2 style="color:{TOKENS["--text-primary"]}; margin-top:0;">NEXUS Remapper &amp; Workspace Orchestrator</h2>
<p style="color:{_MUTED};">Windows 11 64-bit 범용 보조 HID 허브 및 다중 모니터 창 오케스트레이터 (Darkroom Filament v1.1)</p>
<hr style="border:1px solid {_BORDER};">
<h3 style="color:{_DANGER};">1. 비상 탈출 안전장치 (Panic Exit)</h3>
<p>훅 또는 인터셉션 오작동으로 입력이 잠긴 경우, <b>메인 키보드의 <code>ESC + F12</code></b>를 동시에 누르면
모든 커널/유저 모드 훅을 즉시 해제하고 안전 종료합니다.</p>
<h3 style="color:{_GOLD};">2. 빠른 시작 (Listen Mode → 리매핑 &amp; 단축키 녹화)</h3>
<ul>
  <li><b>Hardware Hub</b>에서 내장 키보드/마우스가 <code>Protected</code>로 보호되어 있는지 확인하고, 편집 아이콘으로 보조 장치 별칭(Alias)을 지정할 수 있습니다.</li>
  <li><b>Mapping Matrix</b>의 <b>Listen Mode</b>를 켜고 보조 키패드나 다이얼을 조작하면 물리 키캡 라벨(<code>NUM7</code>, <code>DIAL CW</code> 등)로 카드가 자동 생성됩니다.</li>
  <li>단축키(<code>KEY_COMBO</code>) 액션에서는 <b>REC</b> 버튼을 눌러 원하는 키 조합을 직접 녹화할 수 있습니다.</li>
</ul>
<h3 style="color:{_ORANGE};">3. 로터리 다이얼 가속 곡선 &amp; 멀티 제스처</h3>
<ul>
  <li>다이얼 회전 속도(<code>dt</code>)에 따라 줌/휠 가속 배율(<code>1.0x ~ 3.0x</code>)이 실시간 동적 적용됩니다.</li>
  <li>다이얼 클릭 외에 <b>더블 클릭(<code>DIAL_DOUBLE_CLICK</code>)</b>과 <b>길게 누르기(<code>DIAL_LONG_PRESS</code>, 0.45초 이상)</b> 제스처를 지원합니다.</li>
</ul>
<h3 style="color:{_GOLD};">4. 사용자 정의 레이어 &amp; 발동 조건 (포커스 / 프로세스 지정)</h3>
<ul>
  <li><b>Mapping Layer</b>에서 <b>포커스 모드</b>(복수 <code>.exe</code> 포커스 전환) 또는 <b>프로세스 지정 모드</b>(단일 <code>.exe</code> 실행 유지 전환)를 선택해 레이어를 생성할 수 있습니다.</li>
  <li>모드 간 동일 <code>.exe</code> 중복 등록은 차단되며, 2개 이상의 프로세스 지정 앱이 동시 실행되면 독립 선택 팝업이 표시됩니다.</li>
</ul>
<h3 style="color:{_ORANGE};">5. 다중 모니터 창 배치 프리셋 &amp; 2D 미니맵 / DWM 테두리 보정</h3>
<ul>
  <li><b>Workspace Presets</b>에서 스냅샷을 저장하면 <code>rcWork</code> 기준 <code>0.0 ~ 1.0</code> 상대 비율로 저장되며, 우측 2D 미니맵에서 배치를 즉시 미리 볼 수 있습니다.</li>
  <li><b>Settings</b>의 <code>DWM 투명 그림자 테두리 보정</code>을 켜면 Windows 11 창 외곽 7px 오차를 자동 보정해 빈틈없는 타일링을 구현합니다.</li>
</ul>
"""

_README_JA = f"""
<h2 style="color:{TOKENS["--text-primary"]}; margin-top:0;">NEXUS Remapper &amp; Workspace Orchestrator</h2>
<p style="color:{_MUTED};">Windows 11 64-bit 汎用補助 HID ハブ &amp; マルチモニター ウィンドウオーケストレーター (Darkroom Filament v1.1)</p>
<hr style="border:1px solid {_BORDER};">
<h3 style="color:{_DANGER};">1. 緊急脱出セーフガード (Panic Exit)</h3>
<p>フックやインターセプションの誤動作で入力がロックされた場合、<b>メインキーボードの <code>ESC + F12</code></b> を同時押しすると
すべてのカーネル/ユーザーフックを即座に解除して安全終了します。</p>
<h3 style="color:{_GOLD};">2. クイックスタート (Listen モード → リマップ &amp; ショートカット録音)</h3>
<ul>
  <li><b>ハードウェア ハブ</b> でメインキーボード/マウスが <code>Protected</code> で保護されていることを確認し、補助デバイスに別名(Alias)を設定できます。</li>
  <li><b>マッピング マトリックス</b> の <b>Listen モード</b> を有効にして補助キーパッドやダイヤルを操作すると、物理キーキャップ表示のカードが自動生成されます。</li>
  <li>ショートカット(<code>KEY_COMBO</code>)では <b>REC</b> ボタンからキーの組み合わせを直接録音できます。</li>
</ul>
<h3 style="color:{_ORANGE};">3. ロータリーダイヤル動的加速 &amp; マルチジェスチャー</h3>
<ul>
  <li>回転速度(<code>dt</code>)に応じてズーム/ホイールの加速倍率(<code>1.0x〜3.0x</code>)がリアルタイムに変化します。</li>
  <li>通常のクリックに加え、<b>ダブルクリック</b> および <b>長押し(0.45秒以上)</b> を独立したイベントとして割り当て可能です。</li>
</ul>
<h3 style="color:{_GOLD};">4. カスタムレイヤー &amp; トリガー条件 (フォーカス / プロセス指定)</h3>
<ul>
  <li><b>マッピング レイヤー</b> で <b>フォーカスモード</b>(複数 <code>.exe</code>) または <b>プロセス指定モード</b>(単一 <code>.exe</code>) を選択して作成できます。</li>
  <li>モード間の重複登録はブロックされ、2つ以上のプロセス指定アプリが同時実行されると選択ポップアップが表示されます。</li>
</ul>
<h3 style="color:{_ORANGE};">5. マルチモニター配置プリセット &amp; 2D ミニマップ / DWM 枠補正</h3>
<ul>
  <li><b>ワークスペース プリセット</b> で保存した配置は <code>rcWork</code> 基準の相対比率(<code>0.0〜1.0</code>)で記録され、2D ミニマップで即座に確認できます。</li>
  <li><b>設定</b> の <code>DWM 透明シャドウ枠補正</code> を有効にすると Windows 11 特有の 7px の隙間を自動補正します。</li>
</ul>
"""

_README_EN = f"""
<h2 style="color:{TOKENS["--text-primary"]}; margin-top:0;">NEXUS Remapper &amp; Workspace Orchestrator</h2>
<p style="color:{_MUTED};">Windows 11 64-bit Universal Auxiliary HID Hub &amp; Multi-Monitor Workspace Orchestrator (Darkroom Filament v1.1)</p>
<hr style="border:1px solid {_BORDER};">
<h3 style="color:{_DANGER};">1. Emergency Panic Exit Safeguard</h3>
<p>If a hook or driver ever locks input unexpectedly, press <b><code>ESC + F12</code> on your primary keyboard</b> simultaneously
to immediately unhook all kernel/user engines and exit safely.</p>
<h3 style="color:{_GOLD};">2. Quick Start (Listen Mode → Remap &amp; Shortcut Recorder)</h3>
<ul>
  <li>Verify in <b>Hardware Hub</b> that your primary keyboard/mouse remain <code>Protected</code>. Click the edit icon to assign custom aliases to auxiliary devices.</li>
  <li>Enable <b>Listen Mode</b> in <b>Mapping Matrix</b> and operate an auxiliary keypad or dial to auto-create a card with physical keycap labels (<code>NUM7</code>, <code>DIAL CW</code>, etc.).</li>
  <li>For <code>KEY_COMBO</code> actions, click <b>REC</b> to capture key combinations directly.</li>
</ul>
<h3 style="color:{_ORANGE};">3. Rotary Dial Dynamic Velocity &amp; Multi-Gesture</h3>
<ul>
  <li>Zoom and scroll actions dynamically scale speed (<code>1.0x ~ 3.0x</code>) based on dial turn velocity (<code>dt</code>).</li>
  <li>Supports <b>Double-Click (<code>DIAL_DOUBLE_CLICK</code>)</b> and <b>Long-Press (<code>DIAL_LONG_PRESS</code>, &ge; 0.45s)</b> in addition to single click.</li>
</ul>
<h3 style="color:{_GOLD};">4. Custom Layers &amp; Trigger Modes (Focus / Process-Assigned)</h3>
<ul>
  <li>Create layers in <b>Mapping Layer</b> using either <b>Focus Mode</b> (multiple <code>.exe</code>) or <b>Process-Assigned Mode</b> (single <code>.exe</code> active while running).</li>
  <li>Cross-mode duplicate bindings are blocked automatically, and concurrent process layers open a dedicated selection dialog.</li>
</ul>
<h3 style="color:{_ORANGE};">5. Multi-Monitor Layout Presets, 2D Minimap &amp; DWM Frame Compensation</h3>
<ul>
  <li>Snapshots in <b>Workspace Presets</b> store normalized <code>0.0 ~ 1.0</code> ratios relative to each monitor's <code>rcWork</code> and render live on the 2D Blueprint Minimap.</li>
  <li>Enable <code>DWM Invisible Shadow Border Compensation</code> in <b>Settings</b> to eliminate Windows 11's 7px invisible frame gap for flush tiling.</li>
</ul>
"""

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ko": {
        "nav_0": "Hardware Hub",
        "nav_1": "Workspace Presets",
        "nav_2": "Mapping Layer",
        "nav_3": "Mapping Matrix",
        "nav_4": "Settings",
        "nav_5": "Read Me",
        "nav_header": "Workspace",
        "panic_short": "비상 탈출: ESC + F12",
        "hide_to_tray": "트레이로 숨기기",
        "bypass_on": "Bypass",
        "bypass_off": "Live Sync",
        "tray_show": "콘솔 열기",
        "tray_bypass": "리매핑 일시 정지 (Bypass)",
        "tray_quit": "완전 종료",
        "common_cancel": "취소",
        "common_close": "닫기",
        # Hardware Hub
        "hub_title": "Hardware Hub",
        "hub_all": "전체",
        "hub_scan": "스캔",
        "hub_listen_off": "새 장치 Listen 등록",
        "hub_listen_on": "Listen 대기 중 — 장치 조작",
        "signal_monitor_title": "Signal Monitor",
        "signal_monitor_clear": "비우기",
        "signal_monitor_hint": "등록된 보조 키패드나 다이얼(Consumer Control 0x0C)을 조작하면 원시 패킷 및 표준 InputEvent가 실시간 표시됩니다.",
        "signal_monitor_placeholder": "수신된 입력 신호 대기 중",
        # Workspace Presets
        "ws_topo_title": "Display Topology",
        "snapshot_btn": "스냅샷 저장",
        "ws_presets_title": "Layout Presets",
        "ws_export": "내보내기",
        "ws_import": "가져오기",
        "ws_auto_launch": "미실행 앱 자동 실행 후 정렬",
        "ws_apply_btn": "선택 레이아웃 적용",
        "ws_delete_btn": "삭제",
        "ws_inspector_title": "Inspector & Blueprint",
        "ws_focus_label": "정렬 후 최종 포커스 메인 앱:",
        "ws_detail_placeholder": "좌측에서 프리셋을 선택하면 2D 미니맵과 모니터별 창 비율 좌표(0.0 ~ 1.0)가 표시됩니다.",
        # Mapping Layer
        "layer_title": "Custom Layers",
        "layer_add": "+ 새 레이어",
        "layer_rename": "이름 변경",
        "layer_delete": "삭제",
        "layer_export": "레이어 내보내기",
        "layer_import": "레이어 불러오기",
        "layer_bind_hint": "선택된 레이어에 대상 .exe를 바인딩하면 해당 프로그램 창이 포커스될 때 레이어가 자동 전환되며, 매칭 앱이 없으면 default로 복귀합니다.",
        "layer_bound_label": "바인딩된 프로세스 (.exe)",
        "layer_add_exe": "추가",
        "layer_rem_exe": "해제",
        "layer_running_label": "실행 중인 프로세스",
        "layer_refresh_proc": "새로고침",
        "layer_bind_btn": "← 선택 프로세스 바인딩",
        "layer_mode_label": "트리거 모드",
        "layer_mode_focus": "포커스 모드",
        "layer_mode_process": "프로세스 지정 모드",
        "layer_mode_focus_desc": "포커스 모드 (복수 .exe)",
        "layer_mode_process_desc": "프로세스 지정 모드 (단일 .exe)",
        "layer_mode_focus_tag": "포커스",
        "layer_mode_process_tag": "프로세스 지정",
        "layer_bind_hint_process": "프로세스 지정 모드에서는 단 하나의 .exe만 지정할 수 있습니다. 해당 프로그램이 실행 중이면 창 포커스와 무관하게 이 레이어가 자동 활성화됩니다.",
        "layer_create_title": "새 레이어 생성",
        "layer_create_name_label": "레이어 이름",
        "layer_create_name_placeholder": "예: cad, photo, media",
        "layer_create_mode_label": "발동 조건 선택",
        "layer_create_confirm": "생성",
        "layer_create_ok": "생성",
        "layer_create_cancel": "취소",
        "conflict_dialog_title": "프로세스 지정 레이어 충돌 선택",
        "conflict_dialog_header": "동시 실행 레이어 선택",
        "conflict_dialog_desc": "2개 이상의 프로세스 지정 레이어 대상 프로그램이 동시에 실행 중입니다.\n활성화할 레이어를 선택하세요.",
        "conflict_dialog_apply": "선택 레이어 적용",
        "conflict_dialog_close": "닫기",
        # Mapping Matrix
        "matrix_title": "Mapping Matrix",
        "matrix_all_devices": "전체 장치",
        "listen_mode": "Listen Mode",
        "listen_on": "Listen ON",
        "clear_mappings": "목록 초기화",
        "export_matrix": "내보내기",
        "import_matrix": "불러오기",
        "matrix_listen_banner": "Listen Mode 활성 — 보조 키패드 버튼이나 로터리 다이얼을 조작하면 매핑 카드가 생성됩니다",
        "matrix_empty_hint": "등록된 매핑 카드가 없습니다.\nListen Mode를 켠 뒤 보조 키패드나 다이얼을 조작하면 여기에 매핑 카드가 자동 생성됩니다.",
        # Settings
        "settings_title": "Engine & Preferences",
        "prefer_kernel": "1순위 Interception 커널 드라이버 우선 사용 (미설치/차단 시 User Fallback 자동 전환)",
        "minimize_tray": "창 닫기(X) 시 종료하지 않고 시스템 트레이 백그라운드로 최소화",
        "auto_switch_layer": "활성 창(.exe) 전환 시 바인딩된 사용자 정의 레이어로 자동 전환 (미매칭 시 default 복귀)",
        "compensate_dwm": "Windows 11 DWM 투명 그림자 테두리(약 7px) 자동 보정 — 빈틈없는 타일링 정렬",
        "run_at_startup": "Windows 시작 시 자동 실행 (HKCU\\...\\Run 레지스트리 등록)",
        "start_minimized": "자동 실행 시 창을 띄우지 않고 시스템 트레이로 바로 시작 (--minimized)",
        "bypass_remapping": "리매핑 일시 정지 (Bypass — 보조 장치 입력을 원본 그대로 통과)",
        "ui_language": "UI 언어",
        "config_path": "config.json 경로",
        "open_folder": "폴더 열기",
        "backup_config": "전체 설정 백업",
        "restore_config": "전체 설정 복원",
        "save_now": "설정 저장",
        "log_title": "Activity Log",
        "readme_html": _README_KO,
    },
    "ja": {
        "nav_0": "ハードウェア ハブ",
        "nav_1": "ワークスペース プリセット",
        "nav_2": "マッピング レイヤー",
        "nav_3": "マッピング マトリックス",
        "nav_4": "設定",
        "nav_5": "ガイド",
        "nav_header": "ワークスペース",
        "panic_short": "緊急脱出: ESC + F12",
        "hide_to_tray": "トレイに隠す",
        "bypass_on": "Bypass",
        "bypass_off": "Live Sync",
        "tray_show": "コンソールを開く",
        "tray_bypass": "リマップ一時停止 (Bypass)",
        "tray_quit": "完全終了",
        "common_cancel": "キャンセル",
        "common_close": "閉じる",
        # Hardware Hub
        "hub_title": "ハードウェア ハブ",
        "hub_all": "すべて",
        "hub_scan": "スキャン",
        "hub_listen_off": "新規デバイス Listen 登録",
        "hub_listen_on": "Listen 待機中 — 操作",
        "signal_monitor_title": "リアルタイム信号モニター",
        "signal_monitor_clear": "クリア",
        "signal_monitor_hint": "登録された補助キーパッドやダイヤル(0x0C)を操作すると生パケットと InputEvent が表示されます。",
        "signal_monitor_placeholder": "入力信号を待機中",
        # Workspace Presets
        "ws_topo_title": "ディスプレイ構成",
        "snapshot_btn": "配置スナップショット保存",
        "ws_presets_title": "保存済みプリセット",
        "ws_export": "出力",
        "ws_import": "読込",
        "ws_auto_launch": "未起動アプリを自動起動して整列",
        "ws_apply_btn": "選択レイアウト適用",
        "ws_delete_btn": "削除",
        "ws_inspector_title": "プリセット詳細 & ミニマップ",
        "ws_focus_label": "整列後にフォーカスするアプリ:",
        "ws_detail_placeholder": "左からプリセットを選択すると 2D ミニマップと比率座標(0.0〜1.0)が表示されます。",
        # Mapping Layer
        "layer_title": "カスタム レイヤー",
        "layer_add": "+ 新規レイヤー",
        "layer_rename": "名前変更",
        "layer_delete": "削除",
        "layer_export": "レイヤー出力",
        "layer_import": "レイヤー読込",
        "layer_bind_hint": "レイヤーに .exe を紐付けると、対象アプリにフォーカスした際に自動切替されます（未一致時は default）。",
        "layer_bound_label": "紐付け済みプロセス (.exe)",
        "layer_add_exe": "追加",
        "layer_rem_exe": "解除",
        "layer_running_label": "現在実行中のプロセス",
        "layer_refresh_proc": "更新",
        "layer_bind_btn": "← 選択プロセスを紐付け",
        "layer_mode_label": "トリガーモード",
        "layer_mode_focus": "フォーカスモード",
        "layer_mode_process": "プロセス指定モード",
        "layer_mode_focus_desc": "フォーカスモード (複数 .exe)",
        "layer_mode_process_desc": "プロセス指定モード (単一 .exe)",
        "layer_mode_focus_tag": "フォーカス",
        "layer_mode_process_tag": "プロセス指定",
        "layer_bind_hint_process": "プロセス指定モードでは単一の .exe のみ指定できます。対象アプリが起動中であればフォーカスに関係なくこのレイヤーが自動で有効になります。",
        "layer_create_title": "新規レイヤー作成",
        "layer_create_name_label": "レイヤー名",
        "layer_create_name_placeholder": "例: cad, photo, media",
        "layer_create_mode_label": "トリガー条件",
        "layer_create_confirm": "作成",
        "layer_create_ok": "作成",
        "layer_create_cancel": "キャンセル",
        "conflict_dialog_title": "プロセス指定レイヤー競合選択",
        "conflict_dialog_header": "同時起動レイヤー選択",
        "conflict_dialog_desc": "2つ以上のプロセス指定レイヤー対象アプリが同時に起動しています。\n有効にするレイヤーを選択してください。",
        "conflict_dialog_apply": "選択レイヤー適用",
        "conflict_dialog_close": "閉じる",
        # Mapping Matrix
        "matrix_title": "マッピング マトリックス",
        "matrix_all_devices": "すべてのデバイス",
        "listen_mode": "Listen モード",
        "listen_on": "Listen 中",
        "clear_mappings": "一覧をクリア",
        "export_matrix": "出力",
        "import_matrix": "読込",
        "matrix_listen_banner": "Listen モード有効 — 補助キーパッドまたはダイヤルを操作するとカードが生成されます",
        "matrix_empty_hint": "登録されたマッピングカードがありません。\nListen モードを有効にして補助キーパッドやダイヤルを操作してください。",
        # Settings
        "settings_title": "エンジンおよびシステム設定",
        "prefer_kernel": "Interception カーネルドライバーを優先使用 (未導入時は User Fallback へ自動切替)",
        "minimize_tray": "ウィンドウを閉じる(X)時に終了せずシステムトレイへ最小化",
        "auto_switch_layer": "アクティブウィンドウ(.exe)切替時に紐付いたレイヤーへ自動切替 (未一致時は default)",
        "compensate_dwm": "Windows 11 DWM 透明シャドウ枠(約 7px)を自動補正 — 隙間なく整列",
        "run_at_startup": "Windows 起動時に自動実行 (HKCU\\...\\Run レジストリ登録)",
        "start_minimized": "自動起動時にウィンドウを表示せずトレイで開始 (--minimized)",
        "bypass_remapping": "リマップ一時停止 (Bypass — 補助デバイスの入力をそのまま通過)",
        "ui_language": "UI 言語",
        "config_path": "config.json パス",
        "open_folder": "フォルダを開く",
        "backup_config": "全設定バックアップ",
        "restore_config": "全設定復元",
        "save_now": "保存",
        "log_title": "アクティビティ ログ",
        "readme_html": _README_JA,
    },
    "en": {
        "nav_0": "Hardware Hub",
        "nav_1": "Workspace Presets",
        "nav_2": "Mapping Layer",
        "nav_3": "Mapping Matrix",
        "nav_4": "Settings",
        "nav_5": "Read Me",
        "nav_header": "Workspace",
        "panic_short": "Panic Exit: ESC + F12",
        "hide_to_tray": "Minimize to Tray",
        "bypass_on": "Bypass",
        "bypass_off": "Live Sync",
        "tray_show": "Open Console",
        "tray_bypass": "Pause Remapping (Bypass)",
        "tray_quit": "Quit",
        "common_cancel": "Cancel",
        "common_close": "Close",
        # Hardware Hub
        "hub_title": "Hardware Hub",
        "hub_all": "All",
        "hub_scan": "Scan",
        "hub_listen_off": "Listen & Register Device",
        "hub_listen_on": "Listening — Operate Device",
        "signal_monitor_title": "Signal Monitor",
        "signal_monitor_clear": "Clear",
        "signal_monitor_hint": "Operate a registered keypad or rotary dial (0x0C) to inspect raw HID packets and InputEvents in real time.",
        "signal_monitor_placeholder": "Waiting for incoming HID signals",
        # Workspace Presets
        "ws_topo_title": "Display Topology",
        "snapshot_btn": "Save Snapshot",
        "ws_presets_title": "Layout Presets",
        "ws_export": "Export",
        "ws_import": "Import",
        "ws_auto_launch": "Auto-launch missing apps before arranging",
        "ws_apply_btn": "Apply Layout",
        "ws_delete_btn": "Delete",
        "ws_inspector_title": "Inspector & Blueprint",
        "ws_focus_label": "Final Focus App after Arrange:",
        "ws_detail_placeholder": "Select a preset on the left to preview the 2D minimap and normalized window ratios (0.0 ~ 1.0).",
        # Mapping Layer
        "layer_title": "Custom Layers",
        "layer_add": "+ New Layer",
        "layer_rename": "Rename",
        "layer_delete": "Delete",
        "layer_export": "Export Layer",
        "layer_import": "Import Layer",
        "layer_bind_hint": "Bind target .exe processes to a layer for automatic switching on window focus (unmatched apps return to default).",
        "layer_bound_label": "Bound Processes (.exe)",
        "layer_add_exe": "Add",
        "layer_rem_exe": "Remove",
        "layer_running_label": "Running Processes",
        "layer_refresh_proc": "Refresh",
        "layer_bind_btn": "← Bind Selected Process",
        "layer_mode_label": "Trigger Mode",
        "layer_mode_focus": "Focus Mode",
        "layer_mode_process": "Process-Assigned Mode",
        "layer_mode_focus_desc": "Focus Mode (Multiple .exe)",
        "layer_mode_process_desc": "Process-Assigned Mode (Single .exe)",
        "layer_mode_focus_tag": "Focus",
        "layer_mode_process_tag": "Process",
        "layer_bind_hint_process": "Process-Assigned Mode allows binding only one .exe. This layer stays active automatically while that process is running, regardless of window focus.",
        "layer_create_title": "Create New Layer",
        "layer_create_name_label": "Layer Name",
        "layer_create_name_placeholder": "e.g. cad, photo, media",
        "layer_create_mode_label": "Trigger Condition",
        "layer_create_confirm": "Create",
        "layer_create_ok": "Create",
        "layer_create_cancel": "Cancel",
        "conflict_dialog_title": "Select Active Process Layer",
        "conflict_dialog_header": "Concurrent Process Layers",
        "conflict_dialog_desc": "Multiple apps bound to Process-Assigned layers are running simultaneously.\nSelect which layer to activate.",
        "conflict_dialog_apply": "Apply Selected",
        "conflict_dialog_close": "Close",
        # Mapping Matrix
        "matrix_title": "Mapping Matrix",
        "matrix_all_devices": "All Devices",
        "listen_mode": "Listen Mode",
        "listen_on": "Listen ON",
        "clear_mappings": "Clear List",
        "export_matrix": "Export",
        "import_matrix": "Import",
        "matrix_listen_banner": "Listen Mode active — Press a keypad button or turn a dial to create a mapping card",
        "matrix_empty_hint": "No mapping cards yet.\nEnable Listen Mode and operate an auxiliary keypad or dial to create cards here.",
        # Settings
        "settings_title": "Engine & Preferences",
        "prefer_kernel": "Prefer Interception Kernel Driver (auto-fallback to User Fallback if blocked)",
        "minimize_tray": "Minimize to System Tray instead of quitting when closing window (X)",
        "auto_switch_layer": "Auto-switch to bound custom layer when active .exe changes (fallback: default)",
        "compensate_dwm": "Compensate Windows 11 DWM Invisible Shadow Frame (~7px) for flush tiling",
        "run_at_startup": "Launch automatically on Windows startup (HKCU\\...\\Run)",
        "start_minimized": "Start minimized in System Tray on auto-start (--minimized)",
        "bypass_remapping": "Pause Remapping (Bypass — pass auxiliary inputs through natively)",
        "ui_language": "UI Language",
        "config_path": "config.json Path",
        "open_folder": "Open Folder",
        "backup_config": "Backup All",
        "restore_config": "Restore All",
        "save_now": "Save Now",
        "log_title": "Activity Log",
        "readme_html": _README_EN,
    },
}


def tr(lang: str, key: str) -> str:
    """언어 코드(`ko`/`ja`/`en`)에 해당하는 번역 문자열을 반환한다."""
    table = TRANSLATIONS.get(lang, TRANSLATIONS["ko"])
    return table.get(key, TRANSLATIONS["ko"].get(key, key))
