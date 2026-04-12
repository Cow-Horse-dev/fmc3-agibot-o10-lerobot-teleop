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
    ) -> None:
        self.feature_names = tuple(feature_names)
        self.path = Path(path).expanduser() if path is not None else None
        self.label = label

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
        joint_values = payload.get("joint_values", payload)
        if isinstance(joint_values, dict):
            return self.normalize(
                [joint_values[feature_name] for feature_name in self.feature_names]
            )
        if isinstance(joint_values, list):
            return self.normalize(joint_values)

        raise ValueError(f"Unsupported {self.label} format: {type(joint_values).__name__}")

    def save(
        self,
        joint_values: Sequence[float],
        *,
        description: str | None = None,
    ) -> list[float]:
        normalized_joint_values = self.normalize(joint_values)
        if self.path is None:
            return normalized_joint_values

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {}
        if self.path.exists():
            existing_payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(existing_payload, dict):
                payload.update(
                    {
                        key: value
                        for key, value in existing_payload.items()
                        if key not in {"feature_names", "joint_values"}
                    }
                )

        if description is not None:
            payload["description"] = description

        payload.update(
            {
            "feature_names": list(self.feature_names),
            "joint_values": {
                feature_name: normalized_joint_values[index]
                for index, feature_name in enumerate(self.feature_names)
            },
            },
        )
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return normalized_joint_values
