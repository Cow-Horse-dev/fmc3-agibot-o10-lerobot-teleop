from __future__ import annotations

import importlib
import importlib.util
import math
import os
import sys
from pathlib import Path
from typing import Sequence


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

_ROBOT_HAND_ANGLE_LIMITS = {
    "left": [-60, 100, -49, 12, 90, 90, -10, 90, -10, 90],
    "right": [60, -100, 49, -12, 90, 90, 10, 90, 10, 90],
}

_GLOVE_HAND_ANGLE_LIMITS = {
    "left": [37, 30, 58, 30, 79, 81, 20, 81, 30, 100],
    "right": [37, 30, 60, 30, 81, 81, 20, 81, 30, 100],
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


def default_channel_id_for_handedness(handedness: str) -> int:
    return 0 if normalize_handedness(handedness) == "left" else 1


def agibot_o10_hand_feature_types() -> dict[str, type]:
    return {name: float for name in AGIBOT_O10_HAND_FEATURE_NAMES}


def agibot_o10_joint_action_feature_types() -> dict[str, type]:
    return {
        **{name: float for name in AGIBOT_O10_ARM_FEATURE_NAMES},
        **agibot_o10_hand_feature_types(),
    }


def agibot_o10_action_feature_types() -> dict[str, type]:
    return {
        **agibot_o10_joint_action_feature_types(),
        **{name: float for name in AGIBOT_O10_POSE_FEATURE_NAMES},
    }


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


def extract_ude_glove_angles(finger_data: Sequence[object], handedness: str) -> list[float]:
    mapping = _UDE_GLOVE_INDEX_MAP[normalize_handedness(handedness)]
    values: list[float] = []
    for finger_index, axis in mapping:
        values.append(float(getattr(finger_data[finger_index], axis)))
    return values


def map_glove_angles_to_agibot_o10(handedness: str, glove_angles: Sequence[float]) -> list[float]:
    side = normalize_handedness(handedness)
    if len(glove_angles) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
        raise ValueError(
            f"Agibot O10 glove angles must have {len(AGIBOT_O10_HAND_FEATURE_NAMES)} values, "
            f"got {len(glove_angles)}"
        )

    robot_limits = _ROBOT_HAND_ANGLE_LIMITS[side]
    glove_limits = _GLOVE_HAND_ANGLE_LIMITS[side]
    thumb_roll_offset = 10 if side == "left" else -10

    joints: list[float] = []
    for index, data in enumerate(glove_angles):
        clamped = min(abs(float(data)), glove_limits[index])
        angle_deg = (clamped / glove_limits[index]) * robot_limits[index]
        if index == 0:
            angle_deg += thumb_roll_offset
        joints.append(int(round(angle_deg)) * math.pi / 180)

    return joints


def glove_vec_to_agibot_o10_joint_angles(
    finger_data: Sequence[object], handedness: str
) -> list[float]:
    return map_glove_angles_to_agibot_o10(
        handedness,
        extract_ude_glove_angles(finger_data, handedness),
    )


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

    def disconnect(self) -> None:
        self._hand = None
        self._sdk = None
