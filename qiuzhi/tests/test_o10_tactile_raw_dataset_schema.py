import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


ARM_FEATURES = tuple(f"joint{index}.pos" for index in range(1, 7))
GRIPPER_FEATURES = ("gripper.pos",)
TACTILE_FULL_NAMES = tuple(
    f"tactile.{finger}_{index}"
    for finger in ("thumb", "index", "middle", "ring", "little")
    for index in range(16)
) + tuple(f"tactile.palm_{index}" for index in range(25)) + tuple(
    f"tactile.dorsum_{index}" for index in range(25)
)


def test_build_dataset_features_keeps_single_arm_130d_tactile_out_of_state():
    from lerobot_play.utils.runtime_helpers import build_dataset_features

    class Robot:
        action_features = {name: float for name in (*ARM_FEATURES, *GRIPPER_FEATURES)}
        observation_features = {
            **{name: float for name in (*ARM_FEATURES, *GRIPPER_FEATURES)},
            "observation.tactile.right_raw": {
                "dtype": "float32",
                "shape": (130,),
                "names": list(TACTILE_FULL_NAMES),
            },
            "right": (480, 640, 3),
        }

    features = build_dataset_features(Robot(), use_videos=True)

    assert features["observation.state"]["shape"] == (7,)
    assert features["observation.state"]["names"] == list((*ARM_FEATURES, *GRIPPER_FEATURES))
    assert features["observation.tactile.right_raw"]["shape"] == (130,)
    assert features["observation.tactile.right_raw"]["names"] == list(TACTILE_FULL_NAMES)
    assert features["action"]["shape"] == (7,)
    assert features["observation.images.right"]["dtype"] == "video"


def test_build_dataset_frame_packs_single_arm_tactile_raw_column():
    from lerobot.datasets.feature_utils import build_dataset_frame
    from lerobot_play.utils.runtime_helpers import build_dataset_features

    class Robot:
        action_features = {name: float for name in (*ARM_FEATURES, *GRIPPER_FEATURES)}
        observation_features = {
            **{name: float for name in (*ARM_FEATURES, *GRIPPER_FEATURES)},
            "observation.tactile.right_raw": {
                "dtype": "float32",
                "shape": (130,),
                "names": list(TACTILE_FULL_NAMES),
            },
        }

    features = build_dataset_features(Robot(), use_videos=False)
    values = {
        **{name: float(index) for index, name in enumerate((*ARM_FEATURES, *GRIPPER_FEATURES))},
        **{name: float(index) for index, name in enumerate(TACTILE_FULL_NAMES)},
    }

    frame = build_dataset_frame(features, values, prefix="observation")

    assert frame["observation.state"].shape == (7,)
    assert frame["observation.tactile.right_raw"].shape == (130,)
    assert frame["observation.tactile.right_raw"][129] == 129.0


def test_build_dataset_features_keeps_dual_arm_130d_tactile_out_of_state():
    from lerobot_play.utils.runtime_helpers import build_dataset_features

    state_names = tuple(f"{side}.{name}" for side in ("left", "right") for name in (*ARM_FEATURES, *GRIPPER_FEATURES))

    class Robot:
        action_features = {name: float for name in state_names}
        observation_features = {
            **{name: float for name in state_names},
            "observation.tactile.left_raw": {
                "dtype": "float32",
                "shape": (130,),
                "names": [f"left.{name}" for name in TACTILE_FULL_NAMES],
            },
            "observation.tactile.right_raw": {
                "dtype": "float32",
                "shape": (130,),
                "names": [f"right.{name}" for name in TACTILE_FULL_NAMES],
            },
        }

    features = build_dataset_features(Robot(), use_videos=False)

    assert features["observation.state"]["shape"] == (14,)
    assert features["observation.state"]["names"] == list(state_names)
    assert features["observation.tactile.left_raw"]["shape"] == (130,)
    assert features["observation.tactile.right_raw"]["shape"] == (130,)
    assert features["action"]["shape"] == (14,)


def test_build_dataset_features_rejects_legacy_tactile_modes():
    from lerobot_play.utils.runtime_helpers import validate_o10_tactile_mode

    assert validate_o10_tactile_mode("none") == "none"
    assert validate_o10_tactile_mode("130d") == "130d"
    with pytest.raises(ValueError, match="none.*130d"):
        validate_o10_tactile_mode("80d")
