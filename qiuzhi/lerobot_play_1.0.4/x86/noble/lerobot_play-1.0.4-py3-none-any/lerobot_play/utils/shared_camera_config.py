from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CAMERA_REFERENCE_KEYS = ("shared_wrist_camera", "wrist_camera", "camera_ref")


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


@dataclass(frozen=True)
class CameraReference:
    source_name: str
    overrides: dict[str, Any]


class SharedCameraRegistry:
    """Registry for reusable physical camera definitions.

    The O10 YAML files declare scene-specific camera keys, while this registry
    owns the physical wrist camera parameters and optional hardware controls.
    """

    def __init__(self, config: dict[str, Any]):
        self._config = deepcopy(config)

    def resolve_camera(self, source_name: str) -> dict[str, Any]:
        wrist_cameras = self._config.get("wrist_cameras", {})
        if source_name in wrist_cameras:
            defaults = self._config.get("wrist_camera_defaults", {})
            return _deep_update(defaults, wrist_cameras[source_name])

        legacy_cameras = self._config.get("cameras", {})
        if source_name in legacy_cameras:
            return deepcopy(legacy_cameras[source_name])

        available = ", ".join(sorted(wrist_cameras)) or "<none>"
        raise KeyError(
            f"Shared camera config is missing wrist_cameras.{source_name}; "
            f"available wrist cameras: {available}"
        )

    def parse_reference(self, camera_config: Any) -> CameraReference | None:
        if isinstance(camera_config, str):
            return CameraReference(source_name=camera_config, overrides={})

        if not isinstance(camera_config, dict):
            return None

        source_name = next(
            (
                str(camera_config[key])
                for key in CAMERA_REFERENCE_KEYS
                if camera_config.get(key)
            ),
            None,
        )
        if not source_name:
            return None

        overrides = {
            key: deepcopy(value)
            for key, value in camera_config.items()
            if key not in CAMERA_REFERENCE_KEYS
        }
        return CameraReference(source_name=source_name, overrides=overrides)

    def materialize_cameras(
        self,
        cameras: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        materialized: dict[str, Any] = {}
        camera_sources: dict[str, str] = {}

        for target_name, camera_config in (cameras or {}).items():
            reference = self.parse_reference(camera_config)
            if reference is None:
                materialized[target_name] = deepcopy(camera_config)
                continue

            materialized[target_name] = _deep_update(
                self.resolve_camera(reference.source_name),
                reference.overrides,
            )
            camera_sources[target_name] = reference.source_name

        return materialized, camera_sources

    def materialize_camera_controls(
        self,
        camera_sources: dict[str, str],
        inline_overrides: dict[str, Any],
    ) -> dict[str, Any]:
        shared_controls = self._config.get("camera_controls", {})
        materialized: dict[str, Any] = {}

        for target_name, source_name in camera_sources.items():
            if source_name in shared_controls:
                materialized[target_name] = deepcopy(shared_controls[source_name])

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
    if not shared_path:
        return materialized_config
    if robot_config.get("camera_profile"):
        raise ValueError(
            "robot.camera_profile is no longer used. Declare robot.cameras in the "
            "scene YAML and use left_wrist/right_wrist references for shared wrist cameras."
        )

    resolved_shared_path = _resolve_config_path(shared_path, base_path=base_path)
    shared_config = _load_yaml(resolved_shared_path)
    registry = SharedCameraRegistry(shared_config)

    robot_config["cameras"], camera_sources = registry.materialize_cameras(
        robot_config.get("cameras") or {}
    )
    robot_config["camera_controls"] = registry.materialize_camera_controls(
        camera_sources,
        robot_config.get("camera_controls") or {},
    )
    return materialized_config


def load_yaml_with_shared_camera_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    config = _load_yaml(config_path)
    return apply_shared_camera_config(config, base_path=config_path)
