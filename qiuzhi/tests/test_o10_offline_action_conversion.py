import json
import sys
from pathlib import Path

import numpy as np
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

from lerobot_play.utils.agibot_o10 import (  # noqa: E402
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_EEF_DELTA_FEATURE_NAMES,
    AGIBOT_O10_GRIPPER_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AGIBOT_O10_POSE_FEATURE_NAMES,
    agibot_o10_eef_absolute_pose_to_matrix,
    agibot_o10_eef_delta_to_absolute_pose,
    agibot_o10_joint_action_to_eef_absolute_gripper_action,
    agibot_o10_pose_matrix_to_eef_absolute_pose,
    agibot_o10_resolve_eef_absolute_gripper_action_to_joints,
    agibot_o10_two_absolute_poses_to_eef_delta,
)


DATASET_ROOT = Path(
    "/home/phl/workspace/dataset/Robot/agi_arm_bot/without_tactile/"
    "use_the_right_arm_to_move_the_tissue_between_the_black_paper_and_the_yellow_paper_20260512_merged"
)


class FakeArmKdl:
    def forward_kinematics(self, joints):
        joints = [float(value) for value in joints]
        transform = _rotation_z(joints[5])
        transform[:3, 3] = [joints[0], joints[1], joints[2]]
        return transform

    def inverse_kinematics(self, target_pose, seed, force_calculate=False):
        target_pose = np.asarray(target_pose, dtype=float)
        yaw = float(np.arctan2(target_pose[1, 0], target_pose[0, 0]))
        return [[
            float(target_pose[0, 3]),
            float(target_pose[1, 3]),
            float(target_pose[2, 3]),
            0.0,
            0.0,
            yaw,
        ]]


def _rotation_z(yaw: float) -> np.ndarray:
    cos_yaw = np.cos(yaw)
    sin_yaw = np.sin(yaw)
    return np.array(
        [
            [cos_yaw, -sin_yaw, 0.0, 0.0],
            [sin_yaw, cos_yaw, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _action_dict(names, values):
    return {name: float(value) for name, value in zip(names, values, strict=True)}


def _assert_same_pose_matrix(left_pose, right_pose):
    left_matrix = agibot_o10_eef_absolute_pose_to_matrix(left_pose)
    right_matrix = agibot_o10_eef_absolute_pose_to_matrix(right_pose)
    assert left_matrix == pytest.approx(right_matrix, abs=1e-8)


def test_joint_gripper_action_round_trips_through_eef_absolute_without_hardware():
    arm_kdl = FakeArmKdl()
    joint_action = _action_dict(
        (*AGIBOT_O10_ARM_FEATURE_NAMES, *AGIBOT_O10_GRIPPER_FEATURE_NAMES),
        [0.12, -0.04, 0.31, 0.0, 0.0, 0.25, 0.7],
    )

    eef_action = agibot_o10_joint_action_to_eef_absolute_gripper_action(joint_action, arm_kdl)
    restored_action = agibot_o10_resolve_eef_absolute_gripper_action_to_joints(
        eef_action,
        arm_kdl,
        seed_joints=[0.0] * len(AGIBOT_O10_ARM_FEATURE_NAMES),
    )

    assert list(eef_action) == [*AGIBOT_O10_POSE_FEATURE_NAMES, *AGIBOT_O10_GRIPPER_FEATURE_NAMES]
    assert list(restored_action) == [*AGIBOT_O10_ARM_FEATURE_NAMES, *AGIBOT_O10_GRIPPER_FEATURE_NAMES]
    assert [restored_action[name] for name in AGIBOT_O10_ARM_FEATURE_NAMES] == pytest.approx(
        [joint_action[name] for name in AGIBOT_O10_ARM_FEATURE_NAMES]
    )
    assert restored_action[AGIBOT_O10_GRIPPER_FEATURE_NAMES[0]] == pytest.approx(0.7)


def test_absolute_pose_and_delta_pose_convert_both_directions_without_hardware():
    previous_matrix = np.eye(4)
    previous_matrix[:3, 3] = [0.1, -0.2, 0.3]
    current_matrix = _rotation_z(0.35)
    current_matrix[:3, 3] = [0.15, -0.18, 0.28]
    previous_pose = agibot_o10_pose_matrix_to_eef_absolute_pose(previous_matrix)
    current_pose = agibot_o10_pose_matrix_to_eef_absolute_pose(current_matrix)

    delta = agibot_o10_two_absolute_poses_to_eef_delta(previous_pose, current_pose)
    reconstructed_pose = agibot_o10_eef_delta_to_absolute_pose(previous_pose, delta)

    assert list(delta) == list(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    assert [delta[name] for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES[:3]] == pytest.approx(
        [0.05, 0.02, -0.02]
    )
    assert delta["delta_orientation.yaw"] == pytest.approx(0.35)
    _assert_same_pose_matrix(reconstructed_pose.values(), current_pose.values())


def test_local_merged_joint_dataset_can_be_read_and_converted_offline():
    info_path = DATASET_ROOT / "meta" / "info.json"
    parquet_path = DATASET_ROOT / "data" / "chunk-000" / "file-000.parquet"
    if not info_path.exists() or not parquet_path.exists():
        pytest.skip(f"local dataset is not available at {DATASET_ROOT}")

    pyarrow_parquet = pytest.importorskip("pyarrow.parquet")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    action_info = info["features"]["action"]
    assert action_info["names"] == [
        *AGIBOT_O10_ARM_FEATURE_NAMES,
        *AGIBOT_O10_GRIPPER_FEATURE_NAMES,
    ]

    table = pyarrow_parquet.read_table(str(parquet_path), columns=["action"])
    rows = table.slice(0, min(table.num_rows, 8)).to_pydict()["action"]
    assert rows

    arm_kdl = FakeArmKdl()
    for raw_action in rows:
        joint_action = _action_dict(action_info["names"], raw_action)
        eef_action = agibot_o10_joint_action_to_eef_absolute_gripper_action(
            joint_action,
            arm_kdl,
        )
        restored_action = agibot_o10_resolve_eef_absolute_gripper_action_to_joints(
            eef_action,
            arm_kdl,
            seed_joints=[0.0] * len(AGIBOT_O10_ARM_FEATURE_NAMES),
        )
        assert list(eef_action) == [
            *AGIBOT_O10_POSE_FEATURE_NAMES,
            *AGIBOT_O10_GRIPPER_FEATURE_NAMES,
        ]
        assert [restored_action[name] for name in action_info["names"]] == pytest.approx(
            [joint_action[name] for name in action_info["names"]],
            abs=1e-6,
        )


def test_joint_to_eef_absolute_requires_gripper_mode_action_shape():
    arm_kdl = FakeArmKdl()
    dexterous_action = _action_dict(
        (*AGIBOT_O10_ARM_FEATURE_NAMES, *AGIBOT_O10_HAND_FEATURE_NAMES),
        [0.0] * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES)),
    )

    with pytest.raises(ValueError, match="gripper.pos"):
        agibot_o10_joint_action_to_eef_absolute_gripper_action(dexterous_action, arm_kdl)
