"""경량 다국어(한국어 / 日本語 / English) 내장 사전 모듈 — 6개 전체 페이지 대응."""

from __future__ import annotations

LANGUAGE_LABELS: dict[str, str] = {
    "ko": "한국어",
    "ja": "日本語",
    "en": "English",
}

_README_KO = """
<h2 style="color:#00FFCC; margin-top:0;">NEXUS Remapper &amp; Workspace Orchestrator — 가이드</h2>
<p style="color:#94A3B8;">Windows 11 64-bit 범용 보조 HID 허브 및 다중 모니터 창 오케스트레이터 (Precision Architectural HUD v2.0)</p>
<hr style="border:1px solid #25252E;">
<h3 style="color:#F97316;">1. 비상 탈출 안전장치 (Panic Exit)</h3>
<p>훅 또는 인터셉션 오작동으로 입력이 잠긴 경우, <b>메인 키보드의 <code>ESC + F12</code></b>를 동시에 누르면
모든 커널/유저 모드 훅을 즉시 해제하고 안전 종료합니다.</p>
<h3 style="color:#00FFCC;">2. 빠른 시작 (Listen Mode → 리매핑 &amp; 단축키 녹화)</h3>
<ul>
  <li><b>[HARDWARE HUB]</b>에서 내장 키보드/마우스가 <code>Protected</code>로 보호되어 있는지 확인하고, 연필 아이콘으로 보조 장치 별칭(Alias)을 지정할 수 있습니다.</li>
  <li><b>[MAPPING MATRIX]</b>의 <b>[Listen Mode]</b>를 켜고 보조 키패드나 다이얼을 조작하면 물리 키캡 라벨(<code>NUM7</code>, <code>DIAL CW</code> 등)로 카드가 자동 생성됩니다.</li>
  <li>단축키(<code>KEY_COMBO</code>) 액션에서는 <b>[REC]</b> 버튼을 눌러 원하는 키 조합을 직접 녹화할 수 있습니다.</li>
</ul>
<h3 style="color:#A855F7;">3. 로터리 다이얼 가속 곡선 &amp; 멀티 제스처</h3>
<ul>
  <li>다이얼 회전 속도(<code>dt</code>)에 따라 줌/휠 가속 배율(<code>1.0x ~ 3.0x</code>)이 실시간 동적 적용됩니다.</li>
  <li>다이얼 클릭 외에 <b>더블 클릭(<code>DIAL_DOUBLE_CLICK</code>)</b>과 <b>길게 누르기(<code>DIAL_LONG_PRESS</code>, 0.45초 이상)</b> 제스처를 지원합니다.</li>
</ul>
<h3 style="color:#A855F7;">4. 사용자 정의 레이어 &amp; 프로세스(.exe) 자동 전환</h3>
<ul>
  <li><b>[MAPPING LAYER]</b>에서 원하는 레이어를 무제한 생성하고 실행 중인 <code>.exe</code>를 바인딩할 수 있습니다.</li>
  <li>해당 앱으로 포커스가 이동하면 <code>SetWinEventHook</code>이 무부하로 감지해 레이어를 자동 전환하며, 매칭 앱이 없으면 <code>default</code>로 복귀합니다.</li>
</ul>
<h3 style="color:#00FFCC;">5. 다중 모니터 창 배치 프리셋 &amp; 2D 미니맵 / DWM 테두리 보정</h3>
<ul>
  <li><b>[WORKSPACE PRESETS]</b>에서 스냅샷을 저장하면 <code>rcWork</code> 기준 <code>0.0 ~ 1.0</code> 상대 비율로 저장되며, 우측 2D 블루프린트 미니맵에서 창 배치를 즉시 미리 볼 수 있습니다.</li>
  <li><b>[SETTINGS]</b>의 <code>DWM 투명 그림자 테두리 보정</code>을 켜면 Windows 11 창 외곽 7px 오차를 자동 보정해 완벽한 타일링을 구현합니다.</li>
</ul>
"""

_README_JA = """
<h2 style="color:#00FFCC; margin-top:0;">NEXUS Remapper &amp; Workspace Orchestrator — ガイド</h2>
<p style="color:#94A3B8;">Windows 11 64-bit 汎用補助 HID ハブ &amp; マルチモニター ウィンドウオーケストレーター (v2.0)</p>
<hr style="border:1px solid #25252E;">
<h3 style="color:#F97316;">1. 緊急脱出セーフガード (Panic Exit)</h3>
<p>フックやインターセプションの誤動作で入力がロックされた場合、<b>メインキーボードの <code>ESC + F12</code></b> を同時押しすると
すべてのカーネル/ユーザーフックを即座に解除して安全終了します。</p>
<h3 style="color:#00FFCC;">2. クイックスタート (Listen モード → リマップ &amp; ショートカット録音)</h3>
<ul>
  <li><b>[ハードウェア ハブ]</b> でメインキーボード/マウスが <code>Protected</code> で保護されていることを確認し、補助デバイスに分かりやすい別名(Alias)を設定できます。</li>
  <li><b>[マッピング マトリックス]</b> の <b>[Listen モード]</b> を有効にして補助キーパッドやダイヤルを操作すると、物理キーキャップ表示のカードが自動生成されます。</li>
  <li>ショートカット(<code>KEY_COMBO</code>)では <b>[REC]</b> ボタンからキーの組み合わせを直接録音できます。</li>
</ul>
<h3 style="color:#A855F7;">3. ロータリーダイヤル動的加速 &amp; マルチジェスチャー</h3>
<ul>
  <li>回転速度(<code>dt</code>)に応じてズーム/ホイールの加速倍率(<code>1.0x〜3.0x</code>)がリアルタイムに変化します。</li>
  <li>通常のクリックに加え、<b>ダブルクリック</b> および <b>長押し(0.45秒以上)</b> を独立したイベントとして割り当て可能です。</li>
</ul>
<h3 style="color:#A855F7;">4. カスタムレイヤー &amp; プロセス(.exe)自動切替</h3>
<ul>
  <li><b>[マッピング レイヤー]</b> で無制限にレイヤーを作成し、実行中の <code>.exe</code> を紐付けられます。</li>
  <li>対象アプリにフォーカスが移ると <code>SetWinEventHook</code> により低負荷で自動切替され、一致しない場合は <code>default</code> へ戻ります。</li>
</ul>
<h3 style="color:#00FFCC;">5. マルチモニター配置プリセット &amp; 2D ミニマップ / DWM 枠補正</h3>
<ul>
  <li><b>[ワークスペース プリセット]</b> で保存した配置は <code>rcWork</code> 基準の相対比率(<code>0.0〜1.0</code>)で記録され、2D ミニマップで即座に確認できます。</li>
  <li><b>[設定]</b> の <code>DWM 透明シャドウ枠補正</code> を有効にすると Windows 11 特有の 7px の隙間を自動補正します。</li>
</ul>
"""

_README_EN = """
<h2 style="color:#00FFCC; margin-top:0;">NEXUS Remapper &amp; Workspace Orchestrator — Guide</h2>
<p style="color:#94A3B8;">Windows 11 64-bit Universal Auxiliary HID Hub &amp; Multi-Monitor Workspace Orchestrator (v2.0)</p>
<hr style="border:1px solid #25252E;">
<h3 style="color:#F97316;">1. Emergency Panic Exit Safeguard</h3>
<p>If a hook or driver ever locks input unexpectedly, press <b><code>ESC + F12</code> on your primary keyboard</b> simultaneously
to immediately unhook all kernel/user engines and exit safely.</p>
<h3 style="color:#00FFCC;">2. Quick Start (Listen Mode → Remap &amp; Shortcut Recorder)</h3>
<ul>
  <li>Verify in <b>[HARDWARE HUB]</b> that your primary keyboard/mouse remain <code>Protected</code>. Click the edit icon to assign custom aliases to auxiliary devices.</li>
  <li>Enable <b>[Listen Mode]</b> in <b>[MAPPING MATRIX]</b> and operate an auxiliary keypad or dial to auto-create a card with physical keycap labels (<code>NUM7</code>, <code>DIAL CW</code>, etc.).</li>
  <li>For <code>KEY_COMBO</code> actions, click <b>[REC]</b> to capture key combinations directly.</li>
</ul>
<h3 style="color:#A855F7;">3. Rotary Dial Dynamic Velocity &amp; Multi-Gesture</h3>
<ul>
  <li>Zoom and scroll actions dynamically scale speed (<code>1.0x ~ 3.0x</code>) based on dial turn velocity (<code>dt</code>).</li>
  <li>Supports <b>Double-Click (<code>DIAL_DOUBLE_CLICK</code>)</b> and <b>Long-Press (<code>DIAL_LONG_PRESS</code>, &ge; 0.45s)</b> in addition to single click.</li>
</ul>
<h3 style="color:#A855F7;">4. Custom Layers &amp; Auto-Switch by Active .exe</h3>
<ul>
  <li>Create unlimited custom layers in <b>[MAPPING LAYER]</b> and bind one or more running <code>.exe</code> processes.</li>
  <li><code>SetWinEventHook</code> switches layers with zero CPU polling on focus change and falls back to <code>default</code> when unmatched.</li>
</ul>
<h3 style="color:#00FFCC;">5. Multi-Monitor Layout Presets, 2D Minimap &amp; DWM Frame Compensation</h3>
<ul>
  <li>Snapshots in <b>[WORKSPACE PRESETS]</b> store normalized <code>0.0 ~ 1.0</code> ratios relative to each monitor's <code>rcWork</code> and render live on the 2D Blueprint Minimap.</li>
  <li>Enable <code>DWM Invisible Shadow Border Compensation</code> in <b>[SETTINGS]</b> to eliminate Windows 11's 7px invisible frame gap for flush tiling.</li>
</ul>
"""

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ko": {
        "nav_0": "HARDWARE HUB",
        "nav_1": "WORKSPACE PRESETS",
        "nav_2": "MAPPING LAYER",
        "nav_3": "MAPPING MATRIX",
        "nav_4": "SETTINGS",
        "nav_5": "READ ME",
        "nav_header": "NAVIGATION",
        "panic_short": "비상 탈출: ESC + F12",
        "hide_to_tray": "트레이로 숨기기",
        "bypass_on": "BYPASS ON",
        "bypass_off": "ACTIVE",
        "tray_show": "콘솔 열기",
        "tray_bypass": "리매핑 일시 정지 (Bypass)",
        "tray_quit": "완전 종료",
        # Hardware Hub
        "hub_title": "HARDWARE HUB",
        "hub_all": "전체",
        "hub_scan": "스캔",
        "hub_listen_off": "새 장치 Listen 등록 (OFF)",
        "hub_listen_on": "Listen 대기 중 — 보조 장치를 조작하세요",
        "signal_monitor_title": "REAL-TIME SIGNAL MONITOR",
        "signal_monitor_clear": "모니터 비우기",
        "signal_monitor_hint": "등록된 보조 키패드나 다이얼(Consumer Control 0x0C)을 조작하면 원시 패킷 및 표준 InputEvent가 실시간 표시됩니다.",
        "signal_monitor_placeholder": "수신된 입력 신호 대기 중...",
        # Workspace Presets
        "ws_topo_title": "DISPLAY TOPOLOGY & SNAPSHOT",
        "snapshot_btn": "현재 창 배치 스냅샷 저장",
        "ws_presets_title": "SAVED LAYOUT PRESETS",
        "ws_export": "내보내기(.json)",
        "ws_import": "가져오기(.json)",
        "ws_auto_launch": "미실행 앱 자동 실행 후 정렬",
        "ws_apply_btn": "선택 레이아웃 즉시 적용",
        "ws_delete_btn": "삭제",
        "ws_inspector_title": "PRESET INSPECTOR & 2D BLUEPRINT",
        "ws_focus_label": "정렬 후 최종 포커스 메인 앱:",
        "ws_detail_placeholder": "좌측에서 프리셋을 선택하면 2D 미니맵과 모니터별 창 비율 좌표(0.0 ~ 1.0)가 표시됩니다.",
        # Mapping Layer
        "layer_title": "CUSTOM LAYERS",
        "layer_add": "+ 새 레이어",
        "layer_rename": "이름 변경",
        "layer_delete": "삭제",
        "layer_export": "레이어 내보내기(.json)",
        "layer_import": "레이어 불러오기(.json)",
        "layer_bind_hint": "선택된 레이어에 대상 .exe를 바인딩하면 해당 프로그램 창이 포커스될 때 레이어가 자동 전환되며, 매칭 앱이 없으면 default로 복귀합니다.",
        "layer_bound_label": "바인딩된 프로세스 (.exe)",
        "layer_add_exe": "추가",
        "layer_rem_exe": "해제",
        "layer_running_label": "현재 실행 중인 프로세스",
        "layer_refresh_proc": "새로고침",
        "layer_bind_btn": "← 선택 프로세스를 레이어에 바인딩",
        # Mapping Matrix
        "matrix_title": "MAPPING MATRIX",
        "matrix_all_devices": "전체 장치",
        "listen_mode": "Listen Mode",
        "listen_on": "Listen ON",
        "clear_mappings": "목록 초기화",
        "export_matrix": "내보내기",
        "import_matrix": "불러오기",
        "matrix_listen_banner": "LISTEN MODE ACTIVE — 보조 키패드 버튼이나 로터리 다이얼을 조작하면 매핑 카드가 즉시 생성됩니다",
        "matrix_empty_hint": "등록된 매핑 카드가 없습니다.\n상단 또는 좌측의 [Listen Mode]를 켠 뒤 보조 키패드나 다이얼을 조작하면\n여기에 모듈형 매핑 카드가 자동으로 생성됩니다.",
        # Settings
        "settings_title": "ENGINE & SYSTEM PREFERENCES",
        "prefer_kernel": "1순위 Interception 커널 드라이버 우선 사용 (미설치/차단 시 USER FALLBACK 자동 전환)",
        "minimize_tray": "창 닫기(X) 시 종료하지 않고 시스템 트레이 백그라운드로 최소화",
        "auto_switch_layer": "활성 창(.exe) 전환 시 바인딩된 사용자 정의 레이어로 자동 전환 (미매칭 시 default 복귀)",
        "compensate_dwm": "Windows 11 DWM 투명 그림자 테두리(약 7px) 자동 보정 — 빈틈없는 타일링 정렬",
        "run_at_startup": "Windows 시작 시 자동 실행 (HKCU\\...\\Run 레지스트리 등록)",
        "start_minimized": "자동 실행 시 창을 띄우지 않고 시스템 트레이로 바로 시작 (--minimized)",
        "bypass_remapping": "리매핑 일시 정지 (Bypass — 보조 장치 입력을 원본 그대로 통과)",
        "ui_language": "UI 언어 (Language):",
        "config_path": "config.json 경로:",
        "open_folder": "폴더 열기",
        "backup_config": "전체 설정 백업",
        "restore_config": "전체 설정 복원",
        "save_now": "설정 즉시 저장",
        "log_title": "SYSTEM & ENGINE ACTIVITY LOG",
        "readme_html": _README_KO,
    },
    "ja": {
        "nav_0": "ハードウェア ハブ",
        "nav_1": "ワークスペース プリセット",
        "nav_2": "マッピング レイヤー",
        "nav_3": "マッピング マトリックス",
        "nav_4": "設定 (SETTINGS)",
        "nav_5": "ガイド (READ ME)",
        "nav_header": "ナビゲーション",
        "panic_short": "緊急脱出: ESC + F12",
        "hide_to_tray": "トレイに隠す",
        "bypass_on": "一時停止 (BYPASS)",
        "bypass_off": "稼働中 (ACTIVE)",
        "tray_show": "コンソールを開く",
        "tray_bypass": "リマップ一時停止 (Bypass)",
        "tray_quit": "完全終了",
        # Hardware Hub
        "hub_title": "ハードウェア ハブ",
        "hub_all": "すべて",
        "hub_scan": "スキャン",
        "hub_listen_off": "新規デバイス Listen 登録 (OFF)",
        "hub_listen_on": "Listen 待機中 — 補助デバイスを操作してください",
        "signal_monitor_title": "リアルタイム信号モニター",
        "signal_monitor_clear": "クリア",
        "signal_monitor_hint": "登録された補助キーパッドやダイヤル(0x0C)を操作すると生パケットと InputEvent が表示されます。",
        "signal_monitor_placeholder": "入力信号を待機中...",
        # Workspace Presets
        "ws_topo_title": "ディスプレイ構成 & スナップショット",
        "snapshot_btn": "現在のウィンドウ配置を保存",
        "ws_presets_title": "保存済みレイアウト プリセット",
        "ws_export": "エクスポート",
        "ws_import": "インポート",
        "ws_auto_launch": "未起動アプリを自動起動して整列",
        "ws_apply_btn": "選択レイアウトを適用",
        "ws_delete_btn": "削除",
        "ws_inspector_title": "プリセット詳細 & 2D ミニマップ",
        "ws_focus_label": "整列後にフォーカスするアプリ:",
        "ws_detail_placeholder": "左からプリセットを選択すると 2D ミニマップと比率座標(0.0〜1.0)が表示されます。",
        # Mapping Layer
        "layer_title": "カスタム レイヤー",
        "layer_add": "+ 新規レイヤー",
        "layer_rename": "名前変更",
        "layer_delete": "削除",
        "layer_export": "レイヤー出力(.json)",
        "layer_import": "レイヤー読込(.json)",
        "layer_bind_hint": "レイヤーに .exe を紐付けると、対象アプリにフォーカスした際に自動切替されます（未一致時は default）。",
        "layer_bound_label": "紐付け済みプロセス (.exe)",
        "layer_add_exe": "追加",
        "layer_rem_exe": "解除",
        "layer_running_label": "現在実行中のプロセス",
        "layer_refresh_proc": "更新",
        "layer_bind_btn": "← 選択プロセスをレイヤーに紐付け",
        # Mapping Matrix
        "matrix_title": "マッピング マトリックス",
        "matrix_all_devices": "すべてのデバイス",
        "listen_mode": "Listen モード",
        "listen_on": "Listen 中",
        "clear_mappings": "一覧をクリア",
        "export_matrix": "エクスポート",
        "import_matrix": "インポート",
        "matrix_listen_banner": "LISTEN MODE ACTIVE — 補助キーパッドまたはダイヤルを操作するとカードが自動生成されます",
        "matrix_empty_hint": "登録されたマッピングカードがありません。\n[Listen モード] を有効にして補助キーパッドやダイヤルを操作してください。",
        # Settings
        "settings_title": "エンジンおよびシステム設定",
        "prefer_kernel": "Interception カーネルドライバーを優先使用 (未導入時は USER FALLBACK へ自動切替)",
        "minimize_tray": "ウィンドウを閉じる(X)時に終了せずシステムトレイへ最小化",
        "auto_switch_layer": "アクティブウィンドウ(.exe)切替時に紐付いたレイヤーへ自動切替 (未一致時は default)",
        "compensate_dwm": "Windows 11 DWM 透明シャドウ枠(約 7px)を自動補正 — 隙間なく整列",
        "run_at_startup": "Windows 起動時に自動実行 (HKCU\\...\\Run レジストリ登録)",
        "start_minimized": "自動起動時にウィンドウを表示せずトレイで開始 (--minimized)",
        "bypass_remapping": "リマップ一時停止 (Bypass — 補助デバイスの入力をそのまま通過)",
        "ui_language": "UI 言語 (Language):",
        "config_path": "config.json パス:",
        "open_folder": "フォルダを開く",
        "backup_config": "全設定バックアップ",
        "restore_config": "全設定復元",
        "save_now": "今すぐ保存",
        "log_title": "システム・エンジン ログ",
        "readme_html": _README_JA,
    },
    "en": {
        "nav_0": "HARDWARE HUB",
        "nav_1": "WORKSPACE PRESETS",
        "nav_2": "MAPPING LAYER",
        "nav_3": "MAPPING MATRIX",
        "nav_4": "SETTINGS",
        "nav_5": "READ ME",
        "nav_header": "NAVIGATION",
        "panic_short": "PANIC EXIT: ESC + F12",
        "hide_to_tray": "Minimize to Tray",
        "bypass_on": "BYPASS ON",
        "bypass_off": "ACTIVE",
        "tray_show": "Open Console",
        "tray_bypass": "Pause Remapping (Bypass)",
        "tray_quit": "Quit",
        # Hardware Hub
        "hub_title": "HARDWARE HUB",
        "hub_all": "All",
        "hub_scan": "Scan",
        "hub_listen_off": "Listen & Register Device (OFF)",
        "hub_listen_on": "Listening — Operate an auxiliary device",
        "signal_monitor_title": "REAL-TIME SIGNAL MONITOR",
        "signal_monitor_clear": "Clear",
        "signal_monitor_hint": "Operate a registered keypad or rotary dial (0x0C) to inspect raw HID packets and InputEvents in real time.",
        "signal_monitor_placeholder": "Waiting for incoming HID signals...",
        # Workspace Presets
        "ws_topo_title": "DISPLAY TOPOLOGY & SNAPSHOT",
        "snapshot_btn": "Save Window Snapshot",
        "ws_presets_title": "SAVED LAYOUT PRESETS",
        "ws_export": "Export (.json)",
        "ws_import": "Import (.json)",
        "ws_auto_launch": "Auto-launch missing apps before arranging",
        "ws_apply_btn": "Apply Selected Layout",
        "ws_delete_btn": "Delete",
        "ws_inspector_title": "PRESET INSPECTOR & 2D BLUEPRINT",
        "ws_focus_label": "Final Focus App after Arrange:",
        "ws_detail_placeholder": "Select a preset on the left to preview the 2D minimap and normalized window ratios (0.0 ~ 1.0).",
        # Mapping Layer
        "layer_title": "CUSTOM LAYERS",
        "layer_add": "+ New Layer",
        "layer_rename": "Rename",
        "layer_delete": "Delete",
        "layer_export": "Export Layer (.json)",
        "layer_import": "Import Layer (.json)",
        "layer_bind_hint": "Bind target .exe processes to a layer for automatic switching on window focus (unmatched apps return to default).",
        "layer_bound_label": "Bound Processes (.exe)",
        "layer_add_exe": "Add",
        "layer_rem_exe": "Remove",
        "layer_running_label": "Running Processes",
        "layer_refresh_proc": "Refresh",
        "layer_bind_btn": "← Bind Selected Process to Layer",
        # Mapping Matrix
        "matrix_title": "MAPPING MATRIX",
        "matrix_all_devices": "All Devices",
        "listen_mode": "Listen Mode",
        "listen_on": "Listen ON",
        "clear_mappings": "Clear List",
        "export_matrix": "Export",
        "import_matrix": "Import",
        "matrix_listen_banner": "LISTEN MODE ACTIVE — Press a keypad button or turn a dial to create a mapping card",
        "matrix_empty_hint": "No mapping cards yet.\nEnable [Listen Mode] and operate an auxiliary keypad or dial\nto automatically generate modular mapping cards here.",
        # Settings
        "settings_title": "ENGINE & SYSTEM PREFERENCES",
        "prefer_kernel": "Prefer Interception Kernel Driver (auto-fallback to USER FALLBACK if blocked)",
        "minimize_tray": "Minimize to System Tray instead of quitting when closing window (X)",
        "auto_switch_layer": "Auto-switch to bound custom layer when active .exe changes (fallback: default)",
        "compensate_dwm": "Compensate Windows 11 DWM Invisible Shadow Frame (~7px) for flush tiling",
        "run_at_startup": "Launch automatically on Windows startup (HKCU\\...\\Run)",
        "start_minimized": "Start minimized in System Tray on auto-start (--minimized)",
        "bypass_remapping": "Pause Remapping (Bypass — pass auxiliary inputs through natively)",
        "ui_language": "UI Language:",
        "config_path": "config.json Path:",
        "open_folder": "Open Folder",
        "backup_config": "Backup All",
        "restore_config": "Restore All",
        "save_now": "Save Now",
        "log_title": "SYSTEM & ENGINE ACTIVITY LOG",
        "readme_html": _README_EN,
    },
}


def tr(lang: str, key: str) -> str:
    """언어 코드(`ko`/`ja`/`en`)에 해당하는 번역 문자열을 반환한다."""
    table = TRANSLATIONS.get(lang, TRANSLATIONS["ko"])
    return table.get(key, TRANSLATIONS["ko"].get(key, key))
