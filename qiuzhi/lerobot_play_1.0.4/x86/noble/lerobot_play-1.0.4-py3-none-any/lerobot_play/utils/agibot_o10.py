from __future__ import annotations

import importlib
import importlib.util
import json
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Sequence


AGIBOT_O10_HAND_FEATURE_NAMES = (
    "thumb_cm_roll.pos",
    "thumb_cm_yaw.pos",
    "thumb_cm_pitch.pos",
    "index_mp_yaw.pos",
    "index_mp_pitch.pos",
    "middle_mp_pitch.pos",
    "ring_mp_yaw.pos",
    "ring_mp_pitch.pos",
    "pinky_mp_yaw.pos",
    "pinky_mp_pitch.pos",
)

AGIBOT_O10_ARM_FEATURE_NAMES = tuple(f"joint{i}.pos" for i in range(1, 7))
AGIBOT_O10_POSE_FEATURE_NAMES = (
    "pose.x",
    "pose.y",
    "pose.z",
    "quaternion.qx",
    "quaternion.qy",
    "quaternion.qz",
    "quaternion.qw",
)
AGIBOT_O10_EEF_DELTA_FEATURE_NAMES = (
    "delta_pose.x",
    "delta_pose.y",
    "delta_pose.z",
    "delta_orientation.roll",
    "delta_orientation.pitch",
    "delta_orientation.yaw",
)
AGIBOT_O10_GRIPPER_FEATURE_NAMES = ("gripper.pos",)
AGIBOT_O10_ACTION_CONTROL_MODES = ("joint", "eef_delta")
AGIBOT_O10_HAND_ACTION_MODES = ("dexterous_10d", "gripper_1d")

AGIBOT_O10_TRIGGER_GESTURES = {
    "pinch": {
        "right": {
            "open": [0.03, -1.51, 0.5, 0, 0.5, 1.48, 0, 1.48, 0, 1.48],
            "closed": [0.03, -1.51, 0.7, 0.0, 0.7, 1.48, 0, 1.48, 0, 1.48],
        },
        "left": {
            "open": [-0.03, 1.51, -0.5, 0, 0.5, 1.48, 0, 1.48, 0, 1.48],
            "closed": [-0.03, 1.51, -0.7, 0.0, 0.7, 1.48, 0, 1.48, 0, 1.48],
        },
    },
    "tripod": {
        "right": {
            "open": [0.03, -1.51, 0.5, 0, 0.5, 0.5, 0, 1.48, 0, 1.48],
            "closed": [0.03, -1.51, 0.7, 0.0, 0.7, 0.7, 0, 1.48, 0, 1.48],
        },
        "left": {
            "open": [-0.03, 1.51, -0.5, 0, 0.5, 0.5, 0, 1.48, 0, 1.48],
            "closed": [-0.03, 1.51, -0.7, 0.0, 0.7, 0.7, 0, 1.48, 0, 1.48],
        },
    },
    "cylindrical": {
        "right": {
            "open": [0.03, -1.51, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "closed": [0.03, -1.51, 0.7, 0.0, 0.7, 0.7, 0.0, 0.7, 0.0, 0.7],
        },
        "left": {
            "open": [-0.03, 1.51, -0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "closed": [-0.03, 1.51, -0.7, 0.0, 0.7, 0.7, 0.0, 0.7, 0.0, 0.7],
        },
    },
}

_UDE_GLOVE_INDEX_MAP = {
    "left": (
        (0, "z"),
        (0, "y"),
        (0, "x"),
        (3, "y"),
        (3, "x"),
        (6, "x"),
        (9, "y"),
        (9, "x"),
        (12, "y"),
        (12, "x"),
    ),
    "right": (
        (15, "z"),
        (15, "y"),
        (15, "x"),
        (18, "y"),
        (18, "x"),
        (21, "x"),
        (24, "y"),
        (24, "x"),
        (27, "y"),
        (27, "x"),
    ),
}


# --- O10HandMapper: glove deg → robot rad with EMA + hysteresis + 3-segment curve ---

@dataclass(frozen=True)
class O10ChannelParams:
    in_max: float
    in_low: float
    in_mid: float
    out_max: float
    out_low: float
    out_mid: float
    dead_band: float = 3.0


_O10_MAPPER_GLOVE_LIMIT_DEG = (37.0, 30.0, 60.0, 30.0, 81.0, 81.0, 20.0, 81.0, 30.0, 100.0)
_O10_MAPPER_ROBOT_LIMIT_DEG = (60.0, 100.0, 49.0, 12.0, 90.0, 90.0, 10.0, 90.0, 10.0, 90.0)
_O10_MAPPER_MIRROR_SIGN = {
    "left":  (-1, +1, -1, +1, +1, +1, -1, +1, -1, +1),
    "right": (+1, -1, +1, -1, +1, +1, +1, +1, +1, +1),
}
_O10_MAPPER_THUMB_ROLL_OFFSET_DEG = {"left": +10.0, "right": -10.0}
_O10_MAPPER_EMA_ALPHA = 0.35

_O10_MAPPER_IN_MAX_RATIO = 0.85
_O10_MAPPER_IN_LOW_BASE_DEG = 6.0
_O10_MAPPER_IN_LOW_RATIO = 0.30
_O10_MAPPER_IN_MID_RATIO = 0.55
_O10_MAPPER_OUT_LOW_RATIO = 0.04
_O10_MAPPER_OUT_MID_RATIO = 0.30
_O10_MAPPER_DEAD_BAND_DEG = 3.0


def _build_o10_default_channel_params() -> tuple[O10ChannelParams, ...]:
    params: list[O10ChannelParams] = []
    for glove_lim, robot_lim in zip(_O10_MAPPER_GLOVE_LIMIT_DEG, _O10_MAPPER_ROBOT_LIMIT_DEG):
        in_max = _O10_MAPPER_IN_MAX_RATIO * glove_lim
        in_low = min(_O10_MAPPER_IN_LOW_BASE_DEG, _O10_MAPPER_IN_LOW_RATIO * in_max)
        in_mid = _O10_MAPPER_IN_MID_RATIO * in_max
        out_max = robot_lim
        params.append(
            O10ChannelParams(
                in_max=in_max,
                in_low=in_low,
                in_mid=in_mid,
                out_max=out_max,
                out_low=_O10_MAPPER_OUT_LOW_RATIO * out_max,
                out_mid=_O10_MAPPER_OUT_MID_RATIO * out_max,
                dead_band=_O10_MAPPER_DEAD_BAND_DEG,
            )
        )
    return tuple(params)


O10_DEFAULT_CHANNEL_PARAMS = _build_o10_default_channel_params()


def _o10_channel_index_for_name(name: str) -> int:
    for candidate in (name, name + ".pos"):
        if candidate in AGIBOT_O10_HAND_FEATURE_NAMES:
            return AGIBOT_O10_HAND_FEATURE_NAMES.index(candidate)
    raise KeyError(f"Unknown O10 hand channel: {name!r}")


def _o10_apply_curve(params: O10ChannelParams, x: float) -> float:
    """Three-segment piecewise-linear curve with clamp to [0, out_max]."""
    if x <= 0.0:
        return 0.0
    if x >= params.in_max:
        return params.out_max
    if x <= params.in_low:
        return params.out_low * (x / params.in_low)
    if x <= params.in_mid:
        return params.out_low + (x - params.in_low) / (params.in_mid - params.in_low) * (
            params.out_mid - params.out_low
        )
    return params.out_mid + (x - params.in_mid) / (params.in_max - params.in_mid) * (
        params.out_max - params.out_mid
    )


class O10HandMapper:
    """Glove-deg → robot-rad mapper with EMA + hysteresis + 3-segment curve."""

    def __init__(
        self,
        handedness: str,
        params: Sequence[O10ChannelParams] | None = None,
        channel_overrides: Mapping[str, Mapping[str, float]] | None = None,
        ema_alpha: float = _O10_MAPPER_EMA_ALPHA,
    ) -> None:
        self.handedness = normalize_handedness(handedness)
        base = tuple(params) if params is not None else O10_DEFAULT_CHANNEL_PARAMS
        if len(base) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
            raise ValueError(
                f"O10HandMapper expects {len(AGIBOT_O10_HAND_FEATURE_NAMES)} channels, got {len(base)}"
            )
        if channel_overrides:
            mutable = list(base)
            for name, fields in channel_overrides.items():
                index = _o10_channel_index_for_name(name)
                mutable[index] = replace(mutable[index], **fields)
            base = tuple(mutable)
        self.params: tuple[O10ChannelParams, ...] = base
        self._mirror_sign: tuple[int, ...] = _O10_MAPPER_MIRROR_SIGN[self.handedness]
        self._thumb_roll_offset_deg: float = _O10_MAPPER_THUMB_ROLL_OFFSET_DEG[self.handedness]
        self._ema_alpha = float(ema_alpha)
        self._y_prev_raw: list[float] = [0.0] * len(self.params)
        self._anchor: list[float] = [0.0] * len(self.params)
        self._initialized: list[bool] = [False] * len(self.params)

    def reset(self) -> None:
        n = len(self.params)
        self._y_prev_raw = [0.0] * n
        self._anchor = [0.0] * n
        self._initialized = [False] * n

    def map(self, glove_deg: Sequence[float]) -> list[float]:
        if len(glove_deg) != len(self.params):
            raise ValueError(
                f"O10HandMapper.map expects {len(self.params)} values, got {len(glove_deg)}"
            )
        out: list[float] = []
        for i, raw in enumerate(glove_deg):
            params = self.params[i]
            x_abs = abs(float(raw))
            ema = self._ema_alpha * x_abs + (1.0 - self._ema_alpha) * self._y_prev_raw[i]
            self._y_prev_raw[i] = ema

            anchor = self._anchor[i]
            delta = ema - anchor
            if abs(delta) < params.dead_band:
                stable = anchor
            else:
                sign = 1.0 if delta > 0.0 else -1.0
                stable = ema - sign * params.dead_band
                self._anchor[i] = stable

            curve = _o10_apply_curve(params, stable)
            out_deg = self._mirror_sign[i] * curve
            if i == 0:
                out_deg += self._thumb_roll_offset_deg
            out.append(out_deg * math.pi / 180.0)
            self._initialized[i] = True
        return out


def _is_omnihand_root(candidate: Path) -> bool:
    candidate = candidate.expanduser()
    return (
        (candidate / "sdk_bootstrap.py").exists()
        or (candidate / "omnihand_2025" / "__init__.py").exists()
        or (candidate.name == "omnihand_2025" and (candidate / "__init__.py").exists())
    )


def _discover_omnihand_root() -> Path | None:
    search_bases: list[Path] = []
    for anchor in (Path(__file__).resolve(), Path.cwd().resolve()):
        search_bases.extend([anchor.parent, *anchor.parents])

    seen: set[Path] = set()
    for base in search_bases:
        for candidate in (
            base / "yudie",
            base / "yudie" / "omnihand_2025",
            base / "omnihand_2025",
        ):
            try:
                resolved = candidate.expanduser().resolve()
            except FileNotFoundError:
                continue

            if resolved in seen or not resolved.exists():
                continue
            seen.add(resolved)

            if _is_omnihand_root(resolved):
                return resolved

    return None


def normalize_handedness(handedness: str) -> str:
    normalized = handedness.lower()
    if normalized not in {"left", "right"}:
        raise ValueError(f"Unsupported handedness: {handedness}")
    return normalized


def normalize_trigger_gesture_name(gesture_name: str) -> str:
    normalized = gesture_name.lower()
    if normalized not in AGIBOT_O10_TRIGGER_GESTURES:
        supported = ", ".join(sorted(AGIBOT_O10_TRIGGER_GESTURES))
        raise ValueError(
            f"Unsupported Agibot O10 trigger gesture: {gesture_name}. "
            f"Supported gestures: {supported}"
        )
    return normalized


def normalize_trigger_gesture_state(state: str) -> str:
    normalized = state.lower()
    if normalized not in {"open", "closed"}:
        raise ValueError(f"Unsupported Agibot O10 trigger gesture state: {state}")
    return normalized


def get_agibot_o10_trigger_gesture_joint_angles(
    gesture_name: str,
    handedness: str,
    state: str,
) -> list[float]:
    """Return a copy of a predefined trigger-gesture hand pose."""
    gesture = AGIBOT_O10_TRIGGER_GESTURES[normalize_trigger_gesture_name(gesture_name)]
    side = normalize_handedness(handedness)
    state_key = normalize_trigger_gesture_state(state)
    return gesture[side][state_key].copy()


def get_agibot_o10_reset_pose_gesture_joint_angles(
    reset_poses_path: str | Path | None,
    gesture_name: str,
    handedness: str,
    state: str,
) -> list[float] | None:
    if not reset_poses_path:
        return None

    filepath = Path(reset_poses_path).expanduser()
    data = json.loads(filepath.read_text(encoding="utf-8"))
    gestures = data.get("gestures")
    if not isinstance(gestures, dict):
        raise ValueError(f"reset-poses JSON missing 'gestures' section: {filepath}")

    gesture_key = normalize_trigger_gesture_name(gesture_name)
    if gesture_key not in gestures:
        raise ValueError(
            f"gesture '{gesture_key}' not found (available: {list(gestures.keys())})"
        )
    side = normalize_handedness(handedness)
    gesture_section = gestures[gesture_key]
    if side not in gesture_section:
        raise ValueError(
            f"side '{side}' not found in gesture '{gesture_key}' "
            f"(available: {list(gesture_section.keys())})"
        )

    state_key = normalize_trigger_gesture_state(state)
    side_section = gesture_section[side]
    if state_key not in side_section:
        raise ValueError(
            f"state '{state_key}' not found in gesture '{gesture_key}' side '{side}' "
            f"(available: {list(side_section.keys())})"
        )
    return [float(value) for value in side_section[state_key]]


def normalize_agibot_o10_hand_action_mode(mode: str | None) -> str:
    normalized = (mode or "dexterous_10d").strip().lower()
    if normalized not in AGIBOT_O10_HAND_ACTION_MODES:
        expected = ", ".join(AGIBOT_O10_HAND_ACTION_MODES)
        raise ValueError(
            f"Unsupported Agibot O10 hand_action_mode {mode!r}; expected one of: {expected}"
        )
    return normalized


def agibot_o10_hand_joints_from_gripper_value(
    gripper_value: float,
    gesture_name: str,
    handedness: str,
    reset_poses_path: str | Path | None = None,
) -> list[float]:
    """Interpolate an O10 trigger-gesture hand pose from a 0..1 gripper value."""
    value = min(1.0, max(0.0, float(gripper_value)))
    open_pose = get_agibot_o10_reset_pose_gesture_joint_angles(
        reset_poses_path,
        gesture_name,
        handedness,
        "open",
    ) or get_agibot_o10_trigger_gesture_joint_angles(
        gesture_name,
        handedness,
        "open",
    )
    closed_pose = get_agibot_o10_reset_pose_gesture_joint_angles(
        reset_poses_path,
        gesture_name,
        handedness,
        "closed",
    ) or get_agibot_o10_trigger_gesture_joint_angles(
        gesture_name,
        handedness,
        "closed",
    )
    return [
        open_value + value * (closed_value - open_value)
        for open_value, closed_value in zip(open_pose, closed_pose, strict=True)
    ]


def agibot_o10_gripper_value_from_hand_joints(
    hand_joints: Sequence[float],
    gesture_name: str,
    handedness: str,
    reset_poses_path: str | Path | None = None,
) -> float:
    """Project a 10D O10 hand pose onto the configured open→closed gesture axis."""
    if len(hand_joints) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
        raise ValueError(
            f"Expected {len(AGIBOT_O10_HAND_FEATURE_NAMES)} hand joints, got {len(hand_joints)}"
        )

    open_pose = get_agibot_o10_reset_pose_gesture_joint_angles(
        reset_poses_path,
        gesture_name,
        handedness,
        "open",
    ) or get_agibot_o10_trigger_gesture_joint_angles(
        gesture_name,
        handedness,
        "open",
    )
    closed_pose = get_agibot_o10_reset_pose_gesture_joint_angles(
        reset_poses_path,
        gesture_name,
        handedness,
        "closed",
    ) or get_agibot_o10_trigger_gesture_joint_angles(
        gesture_name,
        handedness,
        "closed",
    )
    delta = [
        closed_value - open_value
        for open_value, closed_value in zip(open_pose, closed_pose, strict=True)
    ]
    denom = sum(value * value for value in delta)
    if denom <= 1e-12:
        return 0.0
    numer = sum(
        (float(joint_value) - open_value) * delta_value
        for joint_value, open_value, delta_value in zip(hand_joints, open_pose, delta, strict=True)
    )
    return min(1.0, max(0.0, numer / denom))


def default_channel_id_for_handedness(handedness: str) -> int:
    return 0 if normalize_handedness(handedness) == "left" else 1


def agibot_o10_hand_feature_types() -> dict[str, type]:
    return {name: float for name in AGIBOT_O10_HAND_FEATURE_NAMES}


def agibot_o10_gripper_feature_types() -> dict[str, type]:
    return {name: float for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES}


def agibot_o10_joint_action_feature_types() -> dict[str, type]:
    return {
        **{name: float for name in AGIBOT_O10_ARM_FEATURE_NAMES},
        **agibot_o10_hand_feature_types(),
    }


def agibot_o10_gripper_action_feature_types() -> dict[str, type]:
    return {
        **{name: float for name in AGIBOT_O10_ARM_FEATURE_NAMES},
        **agibot_o10_gripper_feature_types(),
    }


def agibot_o10_eef_delta_action_feature_types() -> dict[str, type]:
    return {
        **{name: float for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES},
        **agibot_o10_hand_feature_types(),
    }


def agibot_o10_eef_delta_gripper_action_feature_types() -> dict[str, type]:
    return {
        **{name: float for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES},
        **agibot_o10_gripper_feature_types(),
    }


def agibot_o10_action_feature_types() -> dict[str, type]:
    return {
        **agibot_o10_joint_action_feature_types(),
        **{name: float for name in AGIBOT_O10_POSE_FEATURE_NAMES},
    }


def agibot_o10_gripper_state_feature_types() -> dict[str, type]:
    return agibot_o10_gripper_action_feature_types()


def build_agibot_o10_joint_action_dict(joint_values: Sequence[float]) -> dict[str, float]:
    expected_joint_count = len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES)
    if len(joint_values) != expected_joint_count:
        raise ValueError(
            "Agibot O10 joint action must contain "
            f"{expected_joint_count} values, got {len(joint_values)}"
        )

    arm_joint_count = len(AGIBOT_O10_ARM_FEATURE_NAMES)
    arm_joint_values = joint_values[:arm_joint_count]
    hand_joint_values = joint_values[arm_joint_count:]

    return {
        **{
            feature_name: float(arm_joint_values[index])
            for index, feature_name in enumerate(AGIBOT_O10_ARM_FEATURE_NAMES)
        },
        **{
            feature_name: float(hand_joint_values[index])
            for index, feature_name in enumerate(AGIBOT_O10_HAND_FEATURE_NAMES)
        },
    }


def build_agibot_o10_gripper_action_dict(values: Sequence[float]) -> dict[str, float]:
    expected_value_count = len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    if len(values) != expected_value_count:
        raise ValueError(
            "Agibot O10 gripper action must contain "
            f"{expected_value_count} values, got {len(values)}"
        )

    arm_joint_count = len(AGIBOT_O10_ARM_FEATURE_NAMES)
    return {
        **{
            feature_name: float(values[index])
            for index, feature_name in enumerate(AGIBOT_O10_ARM_FEATURE_NAMES)
        },
        **{
            feature_name: float(values[arm_joint_count + index])
            for index, feature_name in enumerate(AGIBOT_O10_GRIPPER_FEATURE_NAMES)
        },
    }


def build_agibot_o10_eef_delta_action_dict(values: Sequence[float]) -> dict[str, float]:
    expected_value_count = len(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES)
    if len(values) != expected_value_count:
        raise ValueError(
            "Agibot O10 eef_delta action must contain "
            f"{expected_value_count} values, got {len(values)}"
        )

    delta_count = len(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    return {
        **{
            feature_name: float(values[index])
            for index, feature_name in enumerate(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        },
        **{
            feature_name: float(values[delta_count + index])
            for index, feature_name in enumerate(AGIBOT_O10_HAND_FEATURE_NAMES)
        },
    }


def build_agibot_o10_eef_delta_gripper_action_dict(values: Sequence[float]) -> dict[str, float]:
    expected_value_count = len(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES) + len(AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    if len(values) != expected_value_count:
        raise ValueError(
            "Agibot O10 eef_delta gripper action must contain "
            f"{expected_value_count} values, got {len(values)}"
        )

    delta_count = len(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    return {
        **{
            feature_name: float(values[index])
            for index, feature_name in enumerate(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        },
        **{
            feature_name: float(values[delta_count + index])
            for index, feature_name in enumerate(AGIBOT_O10_GRIPPER_FEATURE_NAMES)
        },
    }


def normalize_agibot_o10_action_control_mode(mode: str | None) -> str:
    normalized = (mode or "joint").strip().lower()
    if normalized not in AGIBOT_O10_ACTION_CONTROL_MODES:
        expected = ", ".join(AGIBOT_O10_ACTION_CONTROL_MODES)
        raise ValueError(
            f"Unsupported Agibot O10 action_control_mode {mode!r}; expected one of: {expected}"
        )
    return normalized


def extract_ude_glove_angles(finger_data: Sequence[object], handedness: str) -> list[float]:
    mapping = _UDE_GLOVE_INDEX_MAP[normalize_handedness(handedness)]
    values: list[float] = []
    for finger_index, axis in mapping:
        values.append(float(getattr(finger_data[finger_index], axis)))
    return values


def _run_sdk_bootstrap(bootstrap_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "_qiuzhi_omnihand_sdk_bootstrap",
        bootstrap_path,
    )
    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def _bootstrap_omnihand_root(root: Path) -> None:
    root = root.expanduser().resolve()
    os.environ.setdefault("QIUZHI_OMNIHAND_ROOT", str(root))

    candidate_roots = [root]
    if root.name == "omnihand_2025" and (root / "__init__.py").exists():
        candidate_roots.append(root.parent)

    for candidate_root in candidate_roots:
        bootstrap_path = candidate_root / "sdk_bootstrap.py"
        if bootstrap_path.exists():
            _run_sdk_bootstrap(bootstrap_path)
            return

    import_root = root.parent if root.name == "omnihand_2025" else root
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def import_omnihand_2025_module():
    try:
        return importlib.import_module("omnihand_2025")
    except (ImportError, ModuleNotFoundError) as first_error:
        root = os.environ.get("QIUZHI_OMNIHAND_ROOT")
        root_path = Path(root).expanduser() if root else _discover_omnihand_root()
        if root_path is None:
            raise ImportError(
                "Failed to import omnihand_2025. "
                "Please install the Agibot SDK, set QIUZHI_OMNIHAND_ROOT, "
                "or place the sibling yudie SDK checkout next to qiuzhi."
            ) from first_error

        if not root_path.exists():
            raise ImportError(
                f"QIUZHI_OMNIHAND_ROOT does not exist: {root_path}"
            ) from first_error

        _bootstrap_omnihand_root(root_path)

        try:
            return importlib.import_module("omnihand_2025")
        except (ImportError, ModuleNotFoundError) as second_error:
            raise ImportError(
                "Failed to import omnihand_2025 after applying "
                f"QIUZHI_OMNIHAND_ROOT={root_path}. "
                "Please make sure that directory exposes the omnihand_2025 package."
            ) from second_error


class AgibotO10Hand:
    def __init__(
        self,
        handedness: str = "right",
        channel_mode: str = "multiChannel",
        device_id: int = 1,
        canfd_id: int = 0,
        channel_id: int | None = None,
    ) -> None:
        self.handedness = normalize_handedness(handedness)
        self.channel_mode = channel_mode
        self.device_id = device_id
        self.canfd_id = canfd_id
        self.channel_id = (
            default_channel_id_for_handedness(self.handedness)
            if channel_id is None
            else channel_id
        )
        self._sdk = None
        self._hand = None
        self._tactile_cache_lock = threading.Lock()
        self._tactile_avg_cache: list[float] | None = None
        self._tactile_fingertip_cache: list[float] | None = None
        self._tactile_full_cache: list[float] | None = None
        self._tactile_last_update = 0.0

    def _refresh_tactile_caches(self) -> None:
        avg_result = []
        fingertip_result = []
        full_result = []

        tactile_fingers = self._get_tactile_fingers(self._sdk)
        for index, (_name, finger_enum) in enumerate(tactile_fingers):
            data = self._hand.get_tactile_sensor_data(finger_enum)
            values = [float(value) for value in data]
            avg_result.append(sum(values) / len(values) if values else 0.0)
            full_result.extend(values)
            if index < 5:
                fingertip_result.extend(values)

        with self._tactile_cache_lock:
            self._tactile_avg_cache = avg_result
            self._tactile_fingertip_cache = fingertip_result
            self._tactile_full_cache = full_result
            self._tactile_last_update = time.monotonic()

    def _read_tactile_with_cache(
        self,
        cache_name: str,
        *,
        max_cache_age_s: float = 0.2,
    ) -> list[float]:
        if self._hand is None:
            raise RuntimeError("Agibot O10 hand is not connected")

        now = time.monotonic()
        with self._tactile_cache_lock:
            cached = getattr(self, cache_name)
            last_update = self._tactile_last_update
            if cached is not None and now - last_update <= max_cache_age_s:
                return cached.copy()

        try:
            self._refresh_tactile_caches()
        except Exception:
            with self._tactile_cache_lock:
                cached = getattr(self, cache_name)
                if cached is not None:
                    return cached.copy()
            raise

        with self._tactile_cache_lock:
            cached = getattr(self, cache_name)
            return [] if cached is None else cached.copy()

    def connect(self) -> None:
        if self._hand is not None:
            raise RuntimeError("Agibot O10 hand already connected")

        if self.channel_mode != "multiChannel":
            raise ValueError(
                f"Unsupported Agibot O10 channel_mode: {self.channel_mode}. "
                "Phase 1 only supports multiChannel."
            )

        sdk = import_omnihand_2025_module()
        hand_type = (
            sdk.EHandType.LEFT if self.handedness == "left" else sdk.EHandType.RIGHT
        )

        try:
            self._hand = sdk.AgibotHandO10.create_hand(
                hand_type=hand_type,
                device_id=self.device_id,
                canfd_id=self.canfd_id,
                channel_id=self.channel_id,
            )
            self._sdk = sdk
            device_info = self._hand.get_device_info()
        except Exception as exc:
            self._hand = None
            self._sdk = None
            raise RuntimeError(
                "Failed to initialize Agibot O10 hand "
                f"(handedness={self.handedness}, device_id={self.device_id}, "
                f"canfd_id={self.canfd_id}, channel_id={self.channel_id}): {exc}"
            ) from exc

        if getattr(device_info, "device_id", 0) == 0:
            self._hand = None
            self._sdk = None
            raise RuntimeError(
                "Agibot O10 hand device is not ready: get_device_info().device_id == 0. "
                "Please check the USB-CANFD driver, CANFD channel selection and hand power."
            )

    def is_ready(self) -> bool:
        if self._hand is None:
            return False
        try:
            return getattr(self._hand.get_device_info(), "device_id", 0) != 0
        except Exception:
            return False

    def write_active_joint_angles(self, joint_angles: Sequence[float]) -> None:
        if self._hand is None:
            raise RuntimeError("Agibot O10 hand is not connected")
        if len(joint_angles) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
            raise ValueError(
                f"Expected {len(AGIBOT_O10_HAND_FEATURE_NAMES)} Agibot O10 joint angles, "
                f"got {len(joint_angles)}"
            )
        self._hand.set_all_active_joint_angles([float(angle) for angle in joint_angles])

    def read_active_joint_angles(self) -> list[float]:
        if self._hand is None:
            raise RuntimeError("Agibot O10 hand is not connected")
        return [float(angle) for angle in self._hand.get_all_active_joint_angles()]

    @staticmethod
    def _get_tactile_fingers(sdk):
        """返回 (name, EFinger) 列表，按固定顺序。"""
        return [
            ("thumb", sdk.EFinger.THUMB),
            ("index", sdk.EFinger.INDEX),
            ("middle", sdk.EFinger.MIDDLE),
            ("ring", sdk.EFinger.RING),
            ("little", sdk.EFinger.LITTLE),
            ("palm", sdk.EFinger.PALM),
            ("dorsum", sdk.EFinger.DORSUM),
        ]

    def read_tactile_avg(self) -> list[float]:
        """读取 7 区域触觉均值，返回 7D（每区域 1 个均值）。"""
        if self._hand is None:
            raise RuntimeError("Agibot O10 hand is not connected")
        result = []
        for _name, finger_enum in self._get_tactile_fingers(self._sdk):
            data = self._hand.get_tactile_sensor_data(finger_enum)
            avg = sum(data) / len(data) if data else 0.0
            result.append(float(avg))
        return result

    def read_tactile_avg_cached(self, *, max_cache_age_s: float = 0.2) -> list[float]:
        return self._read_tactile_with_cache(
            "_tactile_avg_cache", max_cache_age_s=max_cache_age_s
        )

    def read_tactile_fingertip(self) -> list[float]:
        """读取 5 指尖触觉全量，返回 80D（5 指 × 16 点）。"""
        if self._hand is None:
            raise RuntimeError("Agibot O10 hand is not connected")
        result = []
        for _name, finger_enum in self._get_tactile_fingers(self._sdk)[:5]:
            data = self._hand.get_tactile_sensor_data(finger_enum)
            result.extend([float(v) for v in data])
        return result

    def read_tactile_fingertip_cached(self, *, max_cache_age_s: float = 0.2) -> list[float]:
        return self._read_tactile_with_cache(
            "_tactile_fingertip_cache", max_cache_age_s=max_cache_age_s
        )

    def read_tactile_full(self) -> list[float]:
        """读取全手触觉，返回 130D（5 指 × 16 + 手掌 25 + 手背 25）。"""
        if self._hand is None:
            raise RuntimeError("Agibot O10 hand is not connected")
        result = []
        for _name, finger_enum in self._get_tactile_fingers(self._sdk):
            data = self._hand.get_tactile_sensor_data(finger_enum)
            result.extend([float(v) for v in data])
        return result

    def read_tactile_full_cached(self, *, max_cache_age_s: float = 0.2) -> list[float]:
        return self._read_tactile_with_cache(
            "_tactile_full_cache", max_cache_age_s=max_cache_age_s
        )

    def disconnect(self) -> None:
        self._hand = None
        self._sdk = None
