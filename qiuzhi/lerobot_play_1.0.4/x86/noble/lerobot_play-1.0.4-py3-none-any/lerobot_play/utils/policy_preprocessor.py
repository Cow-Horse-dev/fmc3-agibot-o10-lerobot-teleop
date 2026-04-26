from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path


def load_observation_rename_map(
    model_path: str,
    logger: Callable[[str], None] | None = None,
) -> dict[str, str]:
    processor_path = Path(model_path).expanduser() / "policy_preprocessor.json"
    if not processor_path.exists():
        return {}

    try:
        with processor_path.open(encoding="utf-8") as file:
            processor_config = json.load(file)
    except Exception as exc:
        if logger is not None:
            logger(f"Warning: failed to read policy_preprocessor.json: {exc}")
        return {}

    for step in processor_config.get("steps", []):
        if step.get("registry_name") == "rename_observations_processor":
            rename_map = step.get("config", {}).get("rename_map", {})
            return dict(rename_map) if isinstance(rename_map, dict) else {}

    return {}
