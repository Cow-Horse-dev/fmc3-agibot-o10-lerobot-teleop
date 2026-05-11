from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from lerobot.datasets.utils import INFO_PATH
from lerobot.utils.constants import HF_LEROBOT_HOME

from .agibot_o10 import AGIBOT_O10_ARM_FEATURE_NAMES, AGIBOT_O10_HAND_FEATURE_NAMES


@dataclass(frozen=True, slots=True)
class DatasetTarget:
    repo_id: str
    root: Path


def dataset_root_from_repo_id(repo_id: str, root: str | Path | None = None) -> Path:
    if root is None:
        return HF_LEROBOT_HOME / repo_id

    root_path = Path(root).expanduser()
    if root_path.name == repo_id:
        return root_path

    return root_path / repo_id


def is_incomplete_dataset_root(dataset_root: Path) -> bool:
    if not dataset_root.exists():
        return False

    entries = {
        path.relative_to(dataset_root).as_posix() for path in dataset_root.rglob("*")
    }
    return entries.issubset({"meta", INFO_PATH})


def prepare_dataset_root_for_recording(
    repo_id: str, root: str | Path | None = None
) -> Path:
    dataset_root = dataset_root_from_repo_id(repo_id, root)
    if not dataset_root.exists():
        return dataset_root

    if is_incomplete_dataset_root(dataset_root):
        import shutil

        shutil.rmtree(dataset_root)
        return dataset_root

    raise FileExistsError(
        f"Dataset directory already exists: {dataset_root}\n"
        "Please use a new dataset.repo_id or remove the existing dataset before recording again."
    )


def resolve_dataset_target(
    repo_id: str | None = None,
    root: str | Path | None = None,
    path: str | Path | None = None,
    default_repo_id: str | None = None,
) -> DatasetTarget:
    if path is not None:
        dataset_root = Path(path).expanduser()
        return DatasetTarget(repo_id=repo_id or dataset_root.name, root=dataset_root)

    resolved_repo_id = repo_id or default_repo_id
    if resolved_repo_id is None:
        raise ValueError("A dataset repo_id or dataset path is required.")

    return DatasetTarget(
        repo_id=resolved_repo_id,
        root=dataset_root_from_repo_id(resolved_repo_id, root),
    )


def normalize_task_name(task_name: str | None) -> str:
    normalized = str(task_name or "").strip().lower()
    if not normalized:
        return "task"

    normalized = re.sub(r"\s+", "_", normalized, flags=re.UNICODE)
    normalized = re.sub(r"[^\w-]+", "_", normalized, flags=re.UNICODE)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "task"


def build_task_date_repo_id(task_name: str | None, date_format: str = "%Y%m%d") -> str:
    return f"{normalize_task_name(task_name)}_{datetime.now().strftime(date_format)}"


def resolve_record_dataset_target(
    repo_id: str | None,
    root: str | Path | None,
    task_name: str | None,
    auto_name_from_task_date: bool = False,
    date_format: str = "%Y%m%d",
) -> DatasetTarget:
    if not auto_name_from_task_date:
        return resolve_dataset_target(repo_id=repo_id, root=root)

    base_repo_id = build_task_date_repo_id(task_name, date_format=date_format)
    candidate_repo_id = base_repo_id
    suffix = 2

    while dataset_root_from_repo_id(candidate_repo_id, root).exists():
        candidate_repo_id = f"{base_repo_id}_{suffix}"
        suffix += 1

    return resolve_dataset_target(repo_id=candidate_repo_id, root=root)


def validate_o10_tactile_mode(mode: str | None) -> str:
    normalized = str(mode or "none").strip().lower()
    if normalized in {"none", "130d"}:
        return normalized
    raise ValueError(
        f"Unsupported O10 tactile_mode={mode!r}. Supported values are 'none' and '130d'."
    )


def _is_dataset_feature_spec(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and "dtype" in value
        and "shape" in value
    )


def _normalise_shape(shape: Any) -> tuple[int, ...]:
    if isinstance(shape, tuple):
        return shape
    if isinstance(shape, list):
        return tuple(int(item) for item in shape)
    return (int(shape),)


def _normalise_dataset_feature_spec(spec: dict[str, Any]) -> dict[str, Any]:
    feature = dict(spec)
    feature["shape"] = _normalise_shape(feature["shape"])
    if "names" in feature and feature["names"] is not None:
        feature["names"] = list(feature["names"])
    return feature


def _hw_to_dataset_features(
    hw_features: dict[str, Any], prefix: str, use_videos: bool
) -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {}
    scalar_features = {
        key: value for key, value in hw_features.items() if value is float
    }
    camera_features = {
        key: value
        for key, value in hw_features.items()
        if isinstance(value, tuple)
    }
    dataset_feature_specs = {
        key: value
        for key, value in hw_features.items()
        if _is_dataset_feature_spec(value)
    }

    if scalar_features and prefix == "action":
        features["action"] = {
            "dtype": "float32",
            "shape": (len(scalar_features),),
            "names": list(scalar_features),
        }

    if scalar_features and prefix == "observation":
        features["observation.state"] = {
            "dtype": "float32",
            "shape": (len(scalar_features),),
            "names": list(scalar_features),
        }

    for key, shape in camera_features.items():
        features[f"{prefix}.images.{key}"] = {
            "dtype": "video" if use_videos else "image",
            "shape": shape,
            "names": ["height", "width", "channels"],
        }

    for key, spec in dataset_feature_specs.items():
        dataset_key = key if key.startswith(f"{prefix}.") else f"{prefix}.{key}"
        features[dataset_key] = _normalise_dataset_feature_spec(spec)

    return features


def build_dataset_features(robot, use_videos: bool) -> dict[str, Any]:
    action_features = _hw_to_dataset_features(robot.action_features, "action", use_videos)
    observation_features = _hw_to_dataset_features(
        robot.observation_features, "observation", use_videos
    )
    return {**action_features, **observation_features}


@dataclass(frozen=True, slots=True)
class ReplayActionLayout:
    min_length: int
    builder: Callable[[list[float]], dict[str, Any]]


def _build_single_arm_action_with_eef(values: list[float]) -> dict[str, Any]:
    return {
        "joints": values[0:6],
        "eef": values[6],
    }


def _build_dual_arm_action_with_eef(values: list[float]) -> dict[str, Any]:
    return {
        "left_joints": values[0:6],
        "left_eef": values[6],
        "right_joints": values[7:13],
        "right_eef": values[13],
    }


def _build_agibot_o10_joint_action(values: list[float]) -> dict[str, Any]:
    arm_joint_count = len(AGIBOT_O10_ARM_FEATURE_NAMES)
    hand_joint_count = len(AGIBOT_O10_HAND_FEATURE_NAMES)
    hand_start = arm_joint_count
    hand_end = hand_start + hand_joint_count
    return {
        "joints": values[:arm_joint_count],
        "hand_joints": values[hand_start:hand_end],
    }


def _build_dual_arm_agibot_o10_joint_action(values: list[float]) -> dict[str, Any]:
    side_joint_count = len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES)
    action: dict[str, Any] = {}
    for side_index, side in enumerate(("left", "right")):
        side_values = values[side_index * side_joint_count : (side_index + 1) * side_joint_count]
        for feature_index, feature_name in enumerate(
            (*AGIBOT_O10_ARM_FEATURE_NAMES, *AGIBOT_O10_HAND_FEATURE_NAMES)
        ):
            action[f"{side}.{feature_name}"] = side_values[feature_index]
    return action


_REPLAY_ACTION_LAYOUTS: dict[str, ReplayActionLayout] = {
    "airbot_play_follower": ReplayActionLayout(7, _build_single_arm_action_with_eef),
    "airbot_PTK_follower": ReplayActionLayout(14, _build_dual_arm_action_with_eef),
    "airbot_TOK2_follower": ReplayActionLayout(14, _build_dual_arm_action_with_eef),
    "airbot_TOK4_follower": ReplayActionLayout(14, _build_dual_arm_action_with_eef),
    "quest3_follower": ReplayActionLayout(14, _build_dual_arm_action_with_eef),
    "pico_follower": ReplayActionLayout(14, _build_dual_arm_action_with_eef),
    "pico_follower_single_arm_agibot_o10": ReplayActionLayout(
        len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES),
        _build_agibot_o10_joint_action,
    ),
    "pico_follower_dual_arm_agibot_o10": ReplayActionLayout(
        2 * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES)),
        _build_dual_arm_agibot_o10_joint_action,
    ),
}


def decode_replay_action(
    robot_type: str,
    action_values: Sequence[Any],
    action_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    values = [float(value) for value in action_values]
    if action_names is not None:
        if len(values) < len(action_names):
            raise ValueError(
                f"Action for {robot_type} must contain at least {len(action_names)} values, "
                f"got {len(values)}"
            )
        return {
            feature_name: values[index]
            for index, feature_name in enumerate(action_names)
        }

    if robot_type not in _REPLAY_ACTION_LAYOUTS:
        raise ValueError(f"Unsupported robot type: {robot_type}")

    layout = _REPLAY_ACTION_LAYOUTS[robot_type]
    if len(values) < layout.min_length:
        raise ValueError(
            f"Action for {robot_type} must contain at least {layout.min_length} values, "
            f"got {len(values)}"
        )

    return layout.builder(values)
