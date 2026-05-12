from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def _resolve_config_path(path: str | Path, base_path: str | Path | None = None) -> Path:
    config_path = Path(path).expanduser()
    if config_path.is_absolute():
        return config_path

    if config_path.exists():
        return config_path

    if base_path is not None:
        base = Path(base_path).expanduser()
        if base.is_file():
            base = base.parent
        for parent in (base, *base.parents):
            candidate = parent / config_path
            if candidate.exists():
                return candidate

    for parent in Path(__file__).resolve().parents:
        candidate = parent / config_path
        if candidate.exists():
            return candidate

    return config_path


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).expanduser().open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _profile_map(profile: dict[str, Any], section: str) -> dict[str, str]:
    mapping = profile.get(section, {})
    if isinstance(mapping, list):
        return {str(name): str(name) for name in mapping}
    if isinstance(mapping, dict):
        return {str(target): str(source) for target, source in mapping.items()}
    return {}


def _materialize_section(
    shared_config: dict[str, Any],
    profile: dict[str, Any],
    section: str,
    inline_overrides: dict[str, Any],
) -> dict[str, Any]:
    shared_section = shared_config.get(section, {})
    materialized: dict[str, Any] = {}

    for target_name, source_name in _profile_map(profile, section).items():
        if source_name not in shared_section:
            raise KeyError(f"Shared camera config is missing {section}.{source_name}")
        materialized[target_name] = deepcopy(shared_section[source_name])

    for target_name, override in (inline_overrides or {}).items():
        if target_name in materialized and isinstance(override, dict):
            materialized[target_name] = _deep_update(materialized[target_name], override)
        else:
            materialized[target_name] = deepcopy(override)

    return materialized


def apply_shared_camera_config(
    config: dict[str, Any],
    *,
    base_path: str | Path | None = None,
) -> dict[str, Any]:
    materialized_config = deepcopy(config)
    robot_config = materialized_config.get("robot")
    if not isinstance(robot_config, dict):
        return materialized_config

    shared_path = robot_config.get("camera_config_path")
    profile_name = robot_config.get("camera_profile")
    if not shared_path or not profile_name:
        return materialized_config

    resolved_shared_path = _resolve_config_path(shared_path, base_path=base_path)
    shared_config = _load_yaml(resolved_shared_path)
    profile = (shared_config.get("profiles") or {}).get(profile_name)
    if not isinstance(profile, dict):
        raise KeyError(f"Shared camera config is missing profiles.{profile_name}")

    robot_config["cameras"] = _materialize_section(
        shared_config,
        profile,
        "cameras",
        robot_config.get("cameras") or {},
    )
    robot_config["camera_controls"] = _materialize_section(
        shared_config,
        profile,
        "camera_controls",
        robot_config.get("camera_controls") or {},
    )
    return materialized_config


def load_yaml_with_shared_camera_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    config = _load_yaml(config_path)
    return apply_shared_camera_config(config, base_path=config_path)
