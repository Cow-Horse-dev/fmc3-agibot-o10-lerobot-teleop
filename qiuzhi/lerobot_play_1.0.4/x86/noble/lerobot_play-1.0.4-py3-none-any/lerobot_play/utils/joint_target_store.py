from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence


class PersistentJointTargetStore:
    def __init__(
        self,
        feature_names: Sequence[str],
        path: str | Path | None,
        label: str,
        group_key: str | None = None,
    ) -> None:
        self.feature_names = tuple(feature_names)
        self.path = Path(path).expanduser() if path is not None else None
        self.label = label
        self.group_key = group_key

    @property
    def has_path(self) -> bool:
        return self.path is not None

    def normalize(self, joint_values: Sequence[float]) -> list[float]:
        if len(joint_values) != len(self.feature_names):
            raise ValueError(
                f"{self.label} expects {len(self.feature_names)} joint values, "
                f"got {len(joint_values)}"
            )
        return [float(value) for value in joint_values]

    def load(self) -> list[float] | None:
        if self.path is None or not self.path.exists():
            return None

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if self.group_key is not None:
            groups = payload.get("groups") if isinstance(payload, dict) else None
            if isinstance(groups, dict):
                payload = groups.get(self.group_key)
                if payload is None:
                    return None

        joint_values = payload.get("joint_values", payload)
        if isinstance(joint_values, dict):
            return self.normalize(
                [joint_values[feature_name] for feature_name in self.feature_names]
            )
        if isinstance(joint_values, list):
            return self.normalize(joint_values)

        raise ValueError(f"Unsupported {self.label} format: {type(joint_values).__name__}")

    def save(self, joint_values: Sequence[float]) -> list[float]:
        normalized_joint_values = self.normalize(joint_values)
        if self.path is None:
            return normalized_joint_values

        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "feature_names": list(self.feature_names),
            "joint_values": {
                feature_name: normalized_joint_values[index]
                for index, feature_name in enumerate(self.feature_names)
            },
        }
        if self.group_key is None:
            payload = entry
        else:
            payload = {}
            if self.path.exists():
                existing_payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(existing_payload, dict):
                    payload = existing_payload
            groups = payload.setdefault("groups", {})
            if not isinstance(groups, dict):
                payload["groups"] = {}
                groups = payload["groups"]
            groups[self.group_key] = entry
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return normalized_joint_values
