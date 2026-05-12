from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


@dataclass(frozen=True)
class TaskProfile:
    profile_id: str
    adapter_path: Path
    task_description: str


class TaskProfileRegistry:
    def __init__(
        self,
        *,
        config_path: Path,
        profiles: dict[str, TaskProfile],
        default_profile_id: str,
        command_file: Path,
        base_model_path: Path | None = None,
    ) -> None:
        if default_profile_id not in profiles:
            raise ValueError(f"default_profile not found in profiles: {default_profile_id}")
        self.config_path = config_path
        self.profiles = dict(profiles)
        self.default_profile_id = default_profile_id
        self.command_file = command_file
        self.base_model_path = base_model_path
        self._task_to_profile_id = {
            profile.task_description: profile_id
            for profile_id, profile in self.profiles.items()
        }

    @classmethod
    def from_path(cls, config_path: str | os.PathLike[str]) -> "TaskProfileRegistry":
        path = Path(config_path).expanduser()
        with path.open(encoding="utf-8") as file:
            data = json.load(file) if path.suffix == ".json" else yaml.safe_load(file)

        if not isinstance(data, dict):
            raise ValueError(f"Multi-LoRA config must be a mapping: {path}")

        raw_profiles = data.get("profiles")
        if not isinstance(raw_profiles, dict) or not raw_profiles:
            raise ValueError(f"Multi-LoRA config must contain non-empty profiles: {path}")

        profiles: dict[str, TaskProfile] = {}
        for profile_id, raw_profile in raw_profiles.items():
            if not isinstance(raw_profile, dict):
                raise ValueError(f"Profile {profile_id!r} must be a mapping")
            adapter_path = _expand_path(raw_profile.get("adapter_path"), path.parent)
            task_description = raw_profile.get("task_description")
            if not task_description:
                raise ValueError(f"Profile {profile_id!r} is missing task_description")
            profiles[str(profile_id)] = TaskProfile(
                profile_id=str(profile_id),
                adapter_path=adapter_path,
                task_description=str(task_description),
            )

        default_profile_id = str(data.get("default_profile") or next(iter(profiles)))
        command_file = _expand_path(
            data.get("command_file") or "~/.cache/arm-hand-teleop/o10_lora_switch.json",
            path.parent,
        )
        base_model_path = (
            _expand_path(data["base_model_path"], path.parent)
            if data.get("base_model_path")
            else None
        )
        return cls(
            config_path=path,
            profiles=profiles,
            default_profile_id=default_profile_id,
            command_file=command_file,
            base_model_path=base_model_path,
        )

    @property
    def default_profile(self) -> TaskProfile:
        return self.profiles[self.default_profile_id]

    @property
    def effective_pretrained_path(self) -> Path:
        return self.default_profile.adapter_path

    def profile_for_id(self, profile_id: str) -> TaskProfile:
        try:
            return self.profiles[profile_id]
        except KeyError as exc:
            known = ", ".join(sorted(self.profiles))
            raise ValueError(f"Unknown LoRA task profile {profile_id!r}. Known: {known}") from exc

    def profile_for_task_description(self, task_description: str) -> TaskProfile:
        profile_id = self._task_to_profile_id.get(task_description)
        if profile_id is None:
            known = ", ".join(sorted(self._task_to_profile_id))
            raise ValueError(f"Unknown task description {task_description!r}. Known: {known}") from None
        return self.profile_for_id(profile_id)


class TaskSwitchCommandStore:
    def __init__(self, command_file: str | os.PathLike[str]) -> None:
        self.command_file = Path(command_file).expanduser()
        self._last_seen_mtime_ns: int | None = None

    def write(self, profile_id: str) -> None:
        self.command_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"profile_id": profile_id, "timestamp": time.time()}
        tmp_path = self.command_file.with_suffix(self.command_file.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.command_file)

    def read_latest_profile_id(self) -> str | None:
        if not self.command_file.exists():
            return None
        stat = self.command_file.stat()
        if self._last_seen_mtime_ns == stat.st_mtime_ns:
            return None
        self._last_seen_mtime_ns = stat.st_mtime_ns
        try:
            payload = json.loads(self.command_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        profile_id = payload.get("profile_id")
        return str(profile_id) if profile_id else None


class TaskSwitchCoordinator:
    def __init__(
        self,
        *,
        registry: TaskProfileRegistry,
        command_store: TaskSwitchCommandStore,
        initial_profile_id: str | None = None,
        switch_callback: Callable[[TaskProfile], None] | None = None,
    ) -> None:
        self.registry = registry
        self.command_store = command_store
        self.active_profile = registry.profile_for_id(initial_profile_id or registry.default_profile_id)
        self._pending_profile_id: str | None = None
        self._switch_callback = switch_callback

    def maybe_switch(self, *, is_switch_boundary: bool) -> TaskProfile:
        requested_profile_id = self.command_store.read_latest_profile_id()
        if requested_profile_id is not None:
            self.registry.profile_for_id(requested_profile_id)
            self._pending_profile_id = requested_profile_id

        if not is_switch_boundary or self._pending_profile_id is None:
            return self.active_profile

        if self._pending_profile_id == self.active_profile.profile_id:
            self._pending_profile_id = None
            return self.active_profile

        next_profile = self.registry.profile_for_id(self._pending_profile_id)
        if self._switch_callback is not None:
            self._switch_callback(next_profile)
        self.active_profile = next_profile
        self._pending_profile_id = None
        return self.active_profile


class SwitchablePeftPolicy:
    def __init__(self, policy: Any, registry: TaskProfileRegistry) -> None:
        self.policy = policy
        self.registry = registry
        self.active_profile = registry.default_profile

    def __getattr__(self, name: str) -> Any:
        return getattr(self.policy, name)

    def preload_remaining_adapters(self) -> None:
        for profile in self.registry.profiles.values():
            if profile.profile_id == self.active_profile.profile_id:
                continue
            self.policy.load_adapter(
                str(profile.adapter_path),
                adapter_name=profile.profile_id,
                is_trainable=False,
            )

    def switch_to_profile(self, profile_id: str) -> bool:
        profile = self.registry.profile_for_id(profile_id)
        if profile.profile_id == self.active_profile.profile_id:
            return False

        self.policy.set_adapter(profile.profile_id, inference_mode=True)
        self.active_profile = profile
        self._reset_runtime_state()
        return True

    def switch_to_task_description(self, task_description: str) -> bool:
        profile = self.registry.profile_for_task_description(task_description)
        return self.switch_to_profile(profile.profile_id)

    def _reset_runtime_state(self) -> None:
        if hasattr(self.policy, "reset"):
            self.policy.reset()
        if hasattr(self.policy, "init_rtc_processor"):
            self.policy.init_rtc_processor()


def is_multi_lora_config_path(model_path: str | os.PathLike[str]) -> bool:
    path = Path(model_path).expanduser()
    return path.is_file() and path.suffix in {".yaml", ".yml", ".json"}


def _expand_path(value: Any, base_dir: Path) -> Path:
    if value is None:
        raise ValueError("Path value is required")
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path
