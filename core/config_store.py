"""`config.json` 영구 저장소 및 매핑 규칙 관리 모듈.

개발 환경(`__file__`)과 PyInstaller 단일 `.exe` 패키징 환경(`sys.frozen`) 모두에서
실행 파일 기준 상대 경로의 `config.json`을 UTF-8로 안전하게 읽고 쓴다.
"""

from __future__ import annotations

import json
import sys
import uuid
import winreg
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.actions import ActionSpec, ActionType
from core.context_watcher import DEFAULT_PROCESS_PROFILES
from core.events import InputEvent, normalize_binding_event_type


def get_app_base_dir() -> Path:
    """실행 환경(`sys.frozen` 여부)에 따라 기준 디렉터리를 반환한다."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_config_path(filename: str = "config.json") -> Path:
    """`config.json`의 절대 경로를 반환한다."""
    return get_app_base_dir() / filename


WINDOWS_RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_RUN_VALUE_NAME = "NEXUS_Remapper"


def build_startup_command(minimized: bool = False) -> str:
    """`.exe` 및 `.py` 실행 환경 모두에 대응하는 Windows 시작 프로그램 명령 문자열을 생성한다."""
    flag = " --minimized" if minimized else ""
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}"{flag}'
    py_exe = Path(sys.executable).resolve()
    main_py = (get_app_base_dir() / "main.py").resolve()
    return f'"{py_exe}" "{main_py}"{flag}'


def is_windows_startup_enabled(
    value_name: str = WINDOWS_RUN_VALUE_NAME,
    subkey: str = WINDOWS_RUN_SUBKEY,
) -> bool:
    """`HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run` 등록 여부를 조회한다."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, value_name)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_windows_startup(
    enabled: bool,
    minimized: bool = False,
    value_name: str = WINDOWS_RUN_VALUE_NAME,
    subkey: str = WINDOWS_RUN_SUBKEY,
) -> str:
    """Windows 시작 시 자동 실행 레지스트리를 등록하거나 해제한다."""
    if enabled:
        cmd = build_startup_command(minimized=minimized)
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, cmd)
        return cmd

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, value_name)
    except FileNotFoundError:
        pass
    return ""


@dataclass
class MappingRule:
    """단일 물리 입력(`device_id`, `event_type`, `code`)과 액션 간 매핑 규칙."""

    device_id: str
    event_type: str
    code: int | str
    action: ActionSpec
    rule_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    device_name: str = ""
    profile: str = "*"
    layer: str = "default"
    label: str = ""
    enabled: bool = True

    @property
    def trigger_key(self) -> str:
        """디바이스·정규화 이벤트·코드 조합 식별 문자열을 반환한다."""
        code_str = (
            f"0x{self.code:04X}" if isinstance(self.code, int) else str(self.code)
        )
        norm_type = normalize_binding_event_type(self.event_type)
        return f"{self.device_id}|{norm_type}|{code_str}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "event_type": self.event_type,
            "code": self.code,
            "profile": self.profile,
            "layer": self.layer,
            "label": self.label,
            "enabled": self.enabled,
            "action": self.action.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MappingRule:
        action_raw = data.get("action", {})
        action = (
            ActionSpec.from_dict(action_raw)
            if isinstance(action_raw, dict)
            else ActionSpec(ActionType.NONE)
        )
        return cls(
            rule_id=str(data.get("rule_id") or uuid.uuid4().hex[:10]),
            device_id=str(data["device_id"]),
            device_name=str(data.get("device_name", "")),
            event_type=str(data["event_type"]),
            code=data["code"],
            profile=str(data.get("profile", "*")),
            layer=str(data.get("layer", "default")),
            label=str(data.get("label", "")),
            enabled=bool(data.get("enabled", True)),
            action=action,
        )


@dataclass
class LayerConfig:
    """사용자 정의 레이어 및 자동 전환 대상 프로세스(`.exe`) 바인딩 정보."""

    name: str
    processes: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "processes": list(self.processes),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerConfig:
        procs = [
            str(p).strip()
            for p in data.get("processes", [])
            if str(p).strip()
        ]
        return cls(
            name=str(data["name"]).strip(),
            processes=procs,
            description=str(data.get("description", "")),
        )


def create_default_config() -> dict[str, Any]:
    """초기 `config.json` 기본 스키마를 생성한다."""
    return {
        "version": 1,
        "settings": {
            "prefer_kernel_engine": True,
            "active_layer": "default",
            "layers": ["default", "bim", "media"],
            "selected_topology": "__auto__",
            "auto_launch_missing_apps": False,
            "compensate_dwm_frame": True,
            "minimize_to_tray": True,
            "auto_switch_layer": True,
            "run_at_startup": False,
            "start_minimized": False,
            "bypass_remapping": False,
            "language": "ko",
        },
        "layer_configs": [
            {"name": "default", "processes": [], "description": "기본 폴백 레이어"},
            {
                "name": "bim",
                "processes": ["Revit.exe", "acad.exe"],
                "description": "CAD/BIM 작업 레이어",
            },
            {
                "name": "media",
                "processes": ["MinimalMediaPlayer.exe"],
                "description": "미디어 제어 레이어",
            },
        ],
        "process_profiles": dict(DEFAULT_PROCESS_PROFILES),
        "devices": [],
        "mappings": [],
        "topology_labels": {},
        "layout_presets": [],
    }


class ConfigStore:
    """`config.json` 입출력 및 매핑 규칙·사용자 정의 레이어 관리를 담당하는 저장소."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or get_config_path()
        self.data: dict[str, Any] = create_default_config()
        self.mappings: list[MappingRule] = []
        self.layer_configs: list[LayerConfig] = [
            LayerConfig.from_dict(item) for item in self.data["layer_configs"]
        ]

    def _sync_layers_to_data(self) -> None:
        # "default" 레이어는 항상 첫 번째 기본 레이어로 보장
        if not any(lc.name == "default" for lc in self.layer_configs):
            self.layer_configs.insert(
                0, LayerConfig(name="default", processes=[], description="기본 폴백 레이어")
            )
        self.data["layer_configs"] = [lc.to_dict() for lc in self.layer_configs]
        self.settings["layers"] = [lc.name for lc in self.layer_configs]

    def load(self) -> dict[str, Any]:
        """`config.json`을 로드한다. 파일이 없으면 기본 설정을 생성해 저장한다."""
        if not self.config_path.is_file():
            self.data = create_default_config()
            self.mappings = []
            self.layer_configs = [
                LayerConfig.from_dict(item) for item in self.data["layer_configs"]
            ]
            self.save()
            return self.data

        with self.config_path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)

        defaults = create_default_config()
        merged = {**defaults, **loaded}
        merged["settings"] = {**defaults["settings"], **loaded.get("settings", {})}
        merged["process_profiles"] = {
            **defaults["process_profiles"],
            **loaded.get("process_profiles", {}),
        }
        self.data = merged
        self.mappings = [
            MappingRule.from_dict(item) for item in merged.get("mappings", [])
        ]

        # 구버전 config.json(settings.layers만 존재하는 경우) 자동 마이그레이션
        raw_layers = loaded.get("layer_configs")
        if isinstance(raw_layers, list) and raw_layers:
            self.layer_configs = [
                LayerConfig.from_dict(item)
                for item in raw_layers
                if isinstance(item, dict) and item.get("name")
            ]
        else:
            self.layer_configs = [
                LayerConfig(name=str(name))
                for name in merged["settings"].get("layers", ["default"])
                if str(name).strip()
            ]
        self._sync_layers_to_data()
        return self.data

    def save(self) -> None:
        """현재 메모리 상태를 `config.json`에 UTF-8 JSON으로 영구 저장한다."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._sync_layers_to_data()
        self.data["mappings"] = [m.to_dict() for m in self.mappings]
        with self.config_path.open("w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)

    # ── 사용자 정의 레이어 & 프로세스(.exe) 바인딩 관리 ───────────────────────

    def list_layers(self) -> list[str]:
        """등록된 모든 레이어 이름 목록을 반환한다."""
        return [lc.name for lc in self.layer_configs]

    def get_layer_config(self, name: str) -> LayerConfig | None:
        """이름으로 `LayerConfig`를 조회한다."""
        for lc in self.layer_configs:
            if lc.name == name:
                return lc
        return None

    def create_layer(
        self,
        name: str,
        processes: list[str] | None = None,
        description: str = "",
    ) -> LayerConfig:
        """새 사용자 정의 레이어를 생성한다."""
        clean = name.strip()
        if not clean or clean == "*":
            raise ValueError("Invalid layer name")
        if self.get_layer_config(clean) is not None:
            raise ValueError(f"Layer '{clean}' already exists")

        norm_procs = self._normalize_process_list(processes or [])
        lc = LayerConfig(name=clean, processes=norm_procs, description=description)
        self.layer_configs.append(lc)
        self._sync_layers_to_data()
        return lc

    def rename_layer(self, old_name: str, new_name: str) -> bool:
        """레이어 이름을 변경하고 소속 매핑 규칙의 `layer` 필드를 함께 이관한다."""
        clean_new = new_name.strip()
        if not clean_new or clean_new == "*" or old_name == "default":
            return False
        if self.get_layer_config(clean_new) is not None:
            return False
        lc = self.get_layer_config(old_name)
        if lc is None:
            return False

        lc.name = clean_new
        for rule in self.mappings:
            if rule.layer == old_name:
                rule.layer = clean_new
        if self.settings.get("active_layer") == old_name:
            self.settings["active_layer"] = clean_new
        self._sync_layers_to_data()
        return True

    def delete_layer(self, name: str, delete_rules: bool = True) -> bool:
        """사용자 정의 레이어를 삭제한다(`default` 레이어는 삭제 불가)."""
        if name == "default":
            return False
        before = len(self.layer_configs)
        self.layer_configs = [lc for lc in self.layer_configs if lc.name != name]
        if len(self.layer_configs) == before:
            return False

        if delete_rules:
            self.mappings = [m for m in self.mappings if m.layer != name]
        else:
            for m in self.mappings:
                if m.layer == name:
                    m.layer = "default"
        if self.settings.get("active_layer") == name:
            self.settings["active_layer"] = "default"
        self._sync_layers_to_data()
        return True

    @staticmethod
    def _normalize_process_list(processes: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for p in processes:
            clean = p.strip()
            if not clean:
                continue
            low = clean.lower()
            if low not in seen:
                seen.add(low)
                result.append(clean)
        return result

    def set_layer_processes(self, layer_name: str, processes: list[str]) -> bool:
        """특정 레이어에 자동 전환용 `.exe` 프로세스 목록을 바인딩한다."""
        lc = self.get_layer_config(layer_name)
        if lc is None:
            return False
        norm_procs = self._normalize_process_list(processes)
        bound_low = {p.lower() for p in norm_procs}
        # 동일 .exe가 다른 레이어에 중복 바인딩되지 않도록 정리
        for other in self.layer_configs:
            if other.name != layer_name:
                other.processes = [
                    p for p in other.processes if p.lower() not in bound_low
                ]
        lc.processes = norm_procs
        self._sync_layers_to_data()
        return True

    def get_layer_bindings(self) -> dict[str, list[str]]:
        """`{layer_name: [exe1, exe2, ...]}` 매핑 딕셔너리를 반환한다."""
        return {lc.name: list(lc.processes) for lc in self.layer_configs}

    def resolve_layer_for_process(self, process_name: str) -> str:
        """프로세스명(`.exe`)에 바인딩된 레이어명을 반환한다(없으면 `default`)."""
        if not process_name:
            return "default"
        target = process_name.strip().lower()
        for lc in self.layer_configs:
            if any(p.lower() == target for p in lc.processes):
                return lc.name
        return "default"

    def export_layer_to_file(self, layer_name: str, file_path: Path) -> int:
        """선택된 단일 레이어의 프로세스 바인딩 및 매핑 규칙을 `.json`으로 내보낸다."""
        lc = self.get_layer_config(layer_name)
        if lc is None:
            raise ValueError(f"Unknown layer: {layer_name}")
        rules = [r.to_dict() for r in self.mappings if r.layer == layer_name]
        payload = {
            "format": "nexus_layer_bundle",
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "layer": lc.to_dict(),
            "mappings": rules,
        }
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return len(rules)

    def import_layer_from_file(
        self, file_path: Path, mode: str = "merge"
    ) -> tuple[str, int]:
        """단일 레이어 번들 `.json` 파일을 불러와 레이어 정의와 매핑 규칙을 복원한다."""
        with file_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict) or "layer" not in raw:
            raise ValueError("Invalid layer bundle JSON: missing 'layer' field")

        lc = LayerConfig.from_dict(raw["layer"])
        existing = self.get_layer_config(lc.name)
        if existing is None:
            self.layer_configs.append(lc)
        elif mode == "replace":
            existing.processes = list(lc.processes)
            existing.description = lc.description
        else:
            merged_procs = self._normalize_process_list(existing.processes + lc.processes)
            existing.processes = merged_procs

        imported_rules = [
            MappingRule.from_dict({**item, "layer": lc.name})
            for item in raw.get("mappings", [])
        ]
        if mode == "replace":
            self.mappings = [m for m in self.mappings if m.layer != lc.name]
            self.mappings.extend(imported_rules)
        else:
            for incoming in imported_rules:
                idx = next(
                    (
                        i
                        for i, cur in enumerate(self.mappings)
                        if cur.rule_id == incoming.rule_id
                        or (
                            cur.trigger_key == incoming.trigger_key
                            and cur.profile == incoming.profile
                            and cur.layer == incoming.layer
                        )
                    ),
                    None,
                )
                if idx is not None:
                    self.mappings[idx] = incoming
                else:
                    self.mappings.append(incoming)

        self.save()
        return lc.name, len(imported_rules)

    @property
    def settings(self) -> dict[str, Any]:
        return self.data.setdefault("settings", {})

    def upsert_mapping(self, rule: MappingRule) -> None:
        """동일 `rule_id`가 있으면 갱신하고 없으면 추가한다."""
        for idx, existing in enumerate(self.mappings):
            if existing.rule_id == rule.rule_id:
                self.mappings[idx] = rule
                return
        self.mappings.append(rule)

    def remove_mapping(self, rule_id: str) -> bool:
        """`rule_id`에 해당하는 매핑 규칙을 제거한다."""
        before = len(self.mappings)
        self.mappings = [m for m in self.mappings if m.rule_id != rule_id]
        return len(self.mappings) < before

    def remove_mappings(self, rule_ids: list[str]) -> int:
        """여러 `rule_id`에 해당하는 매핑 규칙을 일괄 제거하고 삭제 건수를 반환한다."""
        target = set(rule_ids)
        before = len(self.mappings)
        self.mappings = [m for m in self.mappings if m.rule_id not in target]
        return before - len(self.mappings)

    def find_matching_rule(
        self,
        event: InputEvent,
        active_profile: str,
        active_layer: str,
    ) -> MappingRule | None:
        """우선순위(프로파일+레이어 -> 프로파일+공통 -> 공통+레이어 -> 전역)로 매핑을 조회한다."""
        ev_key = event.binding_key
        candidates = [
            m for m in self.mappings if m.enabled and m.trigger_key == ev_key
        ]
        if not candidates:
            return None

        search_order = [
            (active_profile, active_layer),
            (active_profile, "*"),
            ("*", active_layer),
            ("*", "*"),
        ]
        for target_prof, target_layer in search_order:
            for m in candidates:
                if m.profile == target_prof and m.layer == target_layer:
                    return m
        return None

    def export_mappings_to_file(
        self,
        file_path: Path,
        devices_snapshot: list[dict[str, Any]] | None = None,
        layer_filter: str | None = None,
        profile_filter: str | None = None,
    ) -> int:
        """현재 매핑 매트릭스를 별도 `.json` 파일로 내보낸다(Export)."""
        rules = list(self.mappings)
        if layer_filter:
            rules = [r for r in rules if r.layer == layer_filter]
        if profile_filter:
            rules = [r for r in rules if r.profile == profile_filter]

        payload = {
            "format": "nexus_mapping_matrix",
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "devices": list(
                devices_snapshot
                if devices_snapshot is not None
                else self.data.get("devices", [])
            ),
            "mappings": [r.to_dict() for r in rules],
        }
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return len(rules)

    def import_mappings_from_file(
        self,
        file_path: Path,
        mode: str = "merge",
    ) -> tuple[int, list[dict[str, Any]]]:
        """외부 `.json` 파일에서 매핑 매트릭스를 불러온다(Import: `merge` 또는 `replace`)."""
        with file_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)

        if not isinstance(raw, dict) or "mappings" not in raw:
            raise ValueError("Invalid mapping matrix JSON: missing 'mappings' field")

        imported_rules = [
            MappingRule.from_dict(item) for item in raw.get("mappings", [])
        ]
        imported_devices = [
            d for d in raw.get("devices", []) if isinstance(d, dict) and d.get("device_id")
        ]

        if mode == "replace":
            self.mappings = imported_rules
        elif mode == "merge":
            for incoming in imported_rules:
                matched_idx = next(
                    (
                        idx
                        for idx, cur in enumerate(self.mappings)
                        if cur.rule_id == incoming.rule_id
                        or (
                            cur.trigger_key == incoming.trigger_key
                            and cur.profile == incoming.profile
                            and cur.layer == incoming.layer
                        )
                    ),
                    None,
                )
                if matched_idx is not None:
                    self.mappings[matched_idx] = incoming
                else:
                    self.mappings.append(incoming)
        else:
            raise ValueError(f"Unsupported import mode: {mode}")

        self.save()
        return len(imported_rules), imported_devices

    def backup_to_file(self, file_path: Path) -> None:
        """전체 `config.json` 상태를 지정된 백업 파일로 UTF-8 JSON 저장한다."""
        self.save()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)

    def restore_from_file(self, file_path: Path) -> dict[str, Any]:
        """전체 설정 백업 파일로부터 `config.json`을 검증·복원하고 재로드한다."""
        with file_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict) or "settings" not in raw or "mappings" not in raw:
            raise ValueError("Invalid full config backup JSON")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=2)
        return self.load()
