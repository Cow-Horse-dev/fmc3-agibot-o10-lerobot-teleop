import sys
import types

import pytest
import yaml


def test_dual_control_yaml_parses():
    with open("configs/dual_arm/o10_dual_control.yaml") as f:
        config = yaml.safe_load(f)
    assert config["teleop"]["type"] == "pico_leader_dual_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_dual_arm_agibot_o10"
    assert config["robot"]["allow_camera_read_failures"] is True
    assert config["teleop"]["hand_action_mode"] == "gripper_1d"
    assert config["robot"]["hand_action_mode"] == "gripper_1d"
    assert config["teleop"]["left"]["gripper_gesture"] == "tripod"
    assert config["teleop"]["right"]["gripper_gesture"] == "pinch"
    assert config["robot"]["left"]["gripper_gesture"] == "tripod"
    assert config["robot"]["right"]["gripper_gesture"] == "pinch"
    assert config["robot"]["left"]["port"] == "can0"
    assert config["robot"]["right"]["port"] == "can1"
    assert config["teleop"]["left"]["handedness"] == "left"
    assert config["teleop"]["right"]["handedness"] == "right"


def test_dual_record_yaml_keeps_local_preview_disabled():
    with open("configs/dual_arm/o10_dual_record.yaml") as f:
        config = yaml.safe_load(f)

    assert config["run"]["display_data"] is False


def test_left_control_yaml_parses():
    with open("configs/left_arm/o10_left_control.yaml") as f:
        config = yaml.safe_load(f)
    assert config["teleop"]["type"] == "pico_leader_single_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_single_arm_agibot_o10"
    assert config["robot"]["allow_camera_read_failures"] is True
    assert config["robot"]["port"] == "can1"
    assert config["teleop"]["handedness"] == "left"
    assert config["teleop"]["controller_side"] == "left"
    assert config["teleop"]["wrist_pose_source"] == "left"
    assert config["robot"]["enable_hand"] is True
    assert set(config["robot"]["cameras"]) == {"top", "left_wrist"}
    assert config["robot"]["cameras"]["left_wrist"]["serial_number_or_name"] == "260322276846"


def test_right_control_yaml_parses():
    with open("configs/right_arm/o10_right_control.yaml") as f:
        config = yaml.safe_load(f)
    assert config["teleop"]["type"] == "pico_leader_single_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_single_arm_agibot_o10"
    assert config["robot"]["allow_camera_read_failures"] is True
    assert config["robot"]["port"] == "can0"
    assert config["teleop"]["handedness"] == "right"
    assert config["teleop"]["controller_side"] == "right"
    assert config["teleop"]["wrist_pose_source"] == "right"
    assert set(config["robot"]["cameras"]) == {"top", "right_wrist"}
    assert config["robot"]["cameras"]["right_wrist"]["serial_number_or_name"] == "260322273018"


def test_dual_arm_feature_dimensions():
    import sys
    sys.path.insert(0, "qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any")
    from lerobot_play.utils.agibot_o10 import (
        AGIBOT_O10_ARM_FEATURE_NAMES,
        AGIBOT_O10_HAND_FEATURE_NAMES,
        AGIBOT_O10_POSE_FEATURE_NAMES,
    )
    action_dim = 2 * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES))
    state_dim = 2 * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES) + len(AGIBOT_O10_POSE_FEATURE_NAMES))
    assert action_dim == 32
    assert state_dim == 46


def test_dual_arm_joint_only_state_dimension_is_32():
    import sys
    sys.path.insert(0, "qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any")
    from lerobot_play.utils.agibot_o10 import (
        AGIBOT_O10_ARM_FEATURE_NAMES,
        AGIBOT_O10_HAND_FEATURE_NAMES,
    )

    state_dim = 2 * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES))

    assert state_dim == 32


def test_dual_record_yaml_has_dataset_section():
    with open("configs/dual_arm/o10_dual_record.yaml") as f:
        config = yaml.safe_load(f)
    assert "dataset" in config
    assert "run" in config
    assert config["robot"]["type"] == "pico_follower_dual_arm_agibot_o10"
    assert config["robot"]["allow_camera_read_failures"] is True
    assert config["robot"]["include_eef_pose"] is False
    assert config["robot"]["action_control_mode"] == "joint"
    assert config["robot"]["tactile_mode"] == "none"


def test_dual_infer_yaml_uses_gripper_state_without_eef_pose():
    with open("configs/dual_arm/o10_dual_infer.yaml") as f:
        config = yaml.safe_load(f)

    assert config["robot"]["hand_action_mode"] == "gripper_1d"
    assert config["robot"]["include_eef_pose"] is False
    assert config["robot"]["tactile_mode"] == "none"


def test_dual_record_yaml_keeps_left_trigger_mode_and_tripod_left_hand():
    with open("configs/dual_arm/o10_dual_record.yaml") as f:
        config = yaml.safe_load(f)

    assert config["teleop"]["arm_trigger_mode"] == "left"
    assert config["teleop"]["left"]["trigger_gesture"] == "tripod"
    assert config["teleop"]["right"]["trigger_gesture"] == "pinch"


def test_dual_arm_wrist_camera_rotations_are_no_rotation():
    with open("configs/dual_arm/o10_dual_record.yaml") as f:
        dual_record = yaml.safe_load(f)
    with open("configs/dual_arm/o10_dual_control.yaml") as f:
        dual_control = yaml.safe_load(f)

    with open("configs/left_arm/o10_left_record.yaml") as f:
        left_record = yaml.safe_load(f)
    with open("configs/right_arm/o10_right_record.yaml") as f:
        right_record = yaml.safe_load(f)

    assert (
        dual_record["robot"]["cameras"]["left_wrist"]["rotation"]
        == left_record["robot"]["cameras"]["left"]["rotation"]
        == "NO_ROTATION"
    )
    assert (
        dual_record["robot"]["cameras"]["right_wrist"]["rotation"]
        == right_record["robot"]["cameras"]["right"]["rotation"]
        == "NO_ROTATION"
    )
    assert dual_control["robot"]["cameras"]["left_wrist"]["rotation"] == "NO_ROTATION"
    assert dual_control["robot"]["cameras"]["right_wrist"]["rotation"] == "NO_ROTATION"


def test_dual_replay_yaml_builds_o10_dual_robot_config():
    sys.path.insert(0, "qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any")
    dataset_module = types.ModuleType("lerobot_play.utils.lerobot_dataset")
    dataset_module.LeRobotDataset = object
    sys.modules.setdefault("lerobot_play.utils.lerobot_dataset", dataset_module)
    from lerobot_play.replay import _config_to_args, _create_robot_config
    from lerobot_play.robots.pico_follower_dual_arm_agibot_o10.config_pico_follower_dual_arm_agibot_o10 import (
        PicoFollowerDualArmAgibotO10Config,
    )

    with open("configs/dual_arm/o10_dual_replay.yaml") as f:
        config = yaml.safe_load(f)

    robot_config = _create_robot_config(_config_to_args(config))

    assert isinstance(robot_config, PicoFollowerDualArmAgibotO10Config)
    assert robot_config.left["port"] == "can0"
    assert robot_config.right["port"] == "can1"
    assert robot_config.enable_hand is True


def test_left_record_yaml_has_dataset_section():
    with open("configs/left_arm/o10_left_record.yaml") as f:
        config = yaml.safe_load(f)
    assert "dataset" in config
    assert "run" in config
    assert config["robot"]["port"] == "can0"
    assert config["robot"]["include_eef_pose"] is False
    assert config["robot"]["tactile_mode"] == "none"
    assert config["teleop"]["controller_side"] == "left"
    assert config["teleop"]["wrist_pose_source"] == "left"
    assert "left" in config["robot"]["cameras"]
    assert "right" not in config["robot"]["cameras"]


def test_right_record_yaml_uses_joint_only_state_without_tactile():
    with open("configs/right_arm/o10_right_record.yaml") as f:
        config = yaml.safe_load(f)

    assert config["robot"]["port"] == "can1"
    assert config["robot"]["include_eef_pose"] is False
    assert config["robot"]["tactile_mode"] == "none"
    assert config["teleop"]["controller_side"] == "right"
    assert config["teleop"]["wrist_pose_source"] == "right"
    assert "right" in config["robot"]["cameras"]


def test_single_arm_realsense_rotations_are_no_rotation():
    with open("configs/left_arm/o10_left_control.yaml") as f:
        left_control_config = yaml.safe_load(f)
    with open("configs/left_arm/o10_left_record.yaml") as f:
        left_record_config = yaml.safe_load(f)
    with open("configs/left_arm/o10_left_infer.yaml") as f:
        left_infer_config = yaml.safe_load(f)
    with open("configs/right_arm/o10_right_control.yaml") as f:
        control_config = yaml.safe_load(f)
    with open("configs/right_arm/o10_right_record.yaml") as f:
        record_config = yaml.safe_load(f)
    with open("configs/right_arm/o10_right_infer.yaml") as f:
        infer_config = yaml.safe_load(f)

    left_control_rotation = left_control_config["robot"]["cameras"]["left_wrist"]["rotation"]
    left_record_rotation = left_record_config["robot"]["cameras"]["left"]["rotation"]
    left_infer_rotation = left_infer_config["robot"]["cameras"]["left"]["rotation"]
    control_rotation = control_config["robot"]["cameras"]["right_wrist"]["rotation"]
    record_rotation = record_config["robot"]["cameras"]["right"]["rotation"]
    infer_rotation = infer_config["robot"]["cameras"]["right"]["rotation"]

    assert left_control_rotation == left_record_rotation == left_infer_rotation == "NO_ROTATION"
    assert control_rotation == record_rotation == infer_rotation == "NO_ROTATION"
