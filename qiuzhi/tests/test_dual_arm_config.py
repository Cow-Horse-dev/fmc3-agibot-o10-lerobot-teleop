import sys
import types
from pathlib import Path

import pytest
import yaml


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

from lerobot_play.utils.shared_camera_config import load_yaml_with_shared_camera_config


def _load_config(path: str) -> dict:
    return load_yaml_with_shared_camera_config(path)


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


@pytest.mark.parametrize(
    "config_path",
    [
        "configs/left_arm/o10_left_control.yaml",
        "configs/left_arm/o10_left_record.yaml",
        "configs/left_arm/o10_left_infer.yaml",
        "configs/right_arm/o10_right_control.yaml",
        "configs/right_arm/o10_right_record.yaml",
        "configs/right_arm/o10_right_infer.yaml",
        "configs/right_arm/o10_right_infer_cpu.yaml",
        "configs/dual_arm/o10_dual_control.yaml",
        "configs/dual_arm/o10_dual_record.yaml",
        "configs/dual_arm/o10_dual_infer.yaml",
    ],
)
def test_o10_top_camera_configs_rotate_physical_camera_upright(config_path):
    config = _load_config(config_path)

    top_camera = config["robot"]["cameras"]["top"]

    assert (
        top_camera["index_or_path"]
        == "/dev/v4l/by-id/usb-LRCP_500W_LRCP_500W_200901010001-video-index0"
    )
    assert top_camera["rotation"] == "ROTATE_180"


def test_dual_record_yaml_keeps_local_preview_disabled():
    with open("configs/dual_arm/o10_dual_record.yaml") as f:
        config = yaml.safe_load(f)

    assert config["run"]["display_data"] is False


def test_left_control_yaml_parses():
    config = _load_config("configs/left_arm/o10_left_control.yaml")
    assert config["teleop"]["type"] == "pico_leader_single_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_single_arm_agibot_o10"
    assert config["robot"]["allow_camera_read_failures"] is True
    assert config["robot"]["port"] == "can0"
    assert config["teleop"]["handedness"] == "left"
    assert config["teleop"]["controller_side"] == "right"
    assert config["teleop"]["wrist_pose_source"] == "left"
    assert config["robot"]["enable_hand"] is True
    assert set(config["robot"]["cameras"]) == {"top", "left_wrist"}
    assert config["robot"]["cameras"]["left_wrist"]["serial_number_or_name"] == "260322276846"


def test_right_control_yaml_parses():
    config = _load_config("configs/right_arm/o10_right_control.yaml")
    assert config["teleop"]["type"] == "pico_leader_single_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_single_arm_agibot_o10"
    assert config["robot"]["allow_camera_read_failures"] is True
    assert config["robot"]["port"] == "can1"
    assert config["teleop"]["handedness"] == "right"
    assert config["teleop"]["controller_side"] == "left"
    assert config["teleop"]["wrist_pose_source"] == "right"
    assert set(config["robot"]["cameras"]) == {"top", "right_wrist"}
    assert config["robot"]["cameras"]["right_wrist"]["serial_number_or_name"] == "260322273018"


@pytest.mark.parametrize(
    ("config_path", "camera_key"),
    [
        ("configs/right_arm/o10_right_control.yaml", "right_wrist"),
        ("configs/right_arm/o10_right_record.yaml", "right_wrist"),
        ("configs/right_arm/o10_right_infer.yaml", "right"),
        ("configs/right_arm/o10_right_infer_cpu.yaml", "right"),
        ("configs/dual_arm/o10_dual_control.yaml", "right_wrist"),
        ("configs/dual_arm/o10_dual_record.yaml", "right_wrist"),
        ("configs/dual_arm/o10_dual_infer.yaml", "right_wrist"),
    ],
)
def test_right_wrist_realsense_configs_use_manual_exposure(config_path, camera_key):
    config = _load_config(config_path)

    controls = config["robot"]["camera_controls"][camera_key]

    assert controls["auto_exposure"] is False
    assert controls["exposure_us"] == 14000
    assert controls["gain"] == 16


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
    assert config["robot"]["left"]["gripper_gesture"] == "tripod"
    assert config["robot"]["right"]["gripper_gesture"] == "pinch"


def test_dual_infer_yaml_enables_display_at_15hz():
    with open("configs/dual_arm/o10_dual_infer.yaml") as f:
        config = yaml.safe_load(f)

    assert config["infer"]["display_data"] is True
    assert config["infer"]["fps"] == 15


def test_dual_record_yaml_keeps_left_trigger_mode_and_original_gestures():
    with open("configs/dual_arm/o10_dual_record.yaml") as f:
        config = yaml.safe_load(f)

    assert config["teleop"]["arm_trigger_mode"] == "left"
    assert config["teleop"]["left"]["trigger_gesture"] == "tripod"
    assert config["teleop"]["right"]["trigger_gesture"] == "pinch"
    assert config["teleop"]["left"]["gripper_gesture"] == "tripod"
    assert config["teleop"]["right"]["gripper_gesture"] == "pinch"
    assert config["robot"]["left"]["gripper_gesture"] == "tripod"
    assert config["robot"]["right"]["gripper_gesture"] == "pinch"


@pytest.mark.parametrize(
    "config_path",
    [
        "configs/left_arm/o10_left_control.yaml",
        "configs/left_arm/o10_left_record.yaml",
    ],
)
def test_left_arm_control_and_record_configs_keep_original_trigger_gesture(config_path):
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["teleop"]["trigger_gesture"] == "pinch"
    assert config["teleop"]["reset_gesture"] == "pinch"
    assert "hand_action_mode" not in config["teleop"]
    assert "gripper_gesture" not in config["teleop"]
    assert "hand_action_mode" not in config["robot"]
    assert "gripper_gesture" not in config["robot"]
    assert config["robot"]["reset_gesture"] == "pinch"


def test_left_arm_infer_config_keeps_original_reset_gesture():
    with open("configs/left_arm/o10_left_infer.yaml") as f:
        config = yaml.safe_load(f)

    assert config["robot"]["reset_gesture"] == "pinch"
    assert "hand_action_mode" not in config["robot"]
    assert "gripper_gesture" not in config["robot"]


@pytest.mark.parametrize(
    "config_path",
    [
        "configs/right_arm/o10_right_control.yaml",
        "configs/right_arm/o10_right_record.yaml",
    ],
)
def test_right_arm_control_and_record_configs_use_cylindrical_gripper_1d(config_path):
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["teleop"]["hand_action_mode"] == "gripper_1d"
    assert config["teleop"]["trigger_gesture"] == "cylindrical"
    assert config["teleop"]["gripper_gesture"] == "cylindrical"
    assert config["teleop"]["reset_gesture"] == "cylindrical"
    assert config["robot"]["hand_action_mode"] == "gripper_1d"
    assert config["robot"]["gripper_gesture"] == "cylindrical"
    assert config["robot"]["reset_gesture"] == "cylindrical"


@pytest.mark.parametrize(
    "config_path",
    [
        "configs/right_arm/o10_right_infer.yaml",
        "configs/right_arm/o10_right_infer_cpu.yaml",
        "configs/right_arm/o10_right_replay.yaml",
    ],
)
def test_right_arm_infer_and_replay_configs_use_cylindrical_gripper_1d(config_path):
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["robot"]["hand_action_mode"] == "gripper_1d"
    assert config["robot"]["gripper_gesture"] == "cylindrical"
    assert config["robot"]["reset_gesture"] == "cylindrical"


def test_dual_arm_wrist_camera_rotations_are_no_rotation():
    dual_record = _load_config("configs/dual_arm/o10_dual_record.yaml")
    dual_control = _load_config("configs/dual_arm/o10_dual_control.yaml")

    left_record = _load_config("configs/left_arm/o10_left_record.yaml")
    right_record = _load_config("configs/right_arm/o10_right_record.yaml")

    assert (
        dual_record["robot"]["cameras"]["left_wrist"]["rotation"]
        == left_record["robot"]["cameras"]["left"]["rotation"]
        == "NO_ROTATION"
    )
    assert (
        dual_record["robot"]["cameras"]["right_wrist"]["rotation"]
        == right_record["robot"]["cameras"]["right_wrist"]["rotation"]
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
    config = _load_config("configs/left_arm/o10_left_record.yaml")
    assert "dataset" in config
    assert "run" in config
    assert config["robot"]["port"] == "can0"
    assert config["robot"]["include_eef_pose"] is False
    assert config["robot"]["tactile_mode"] == "none"
    assert config["teleop"]["controller_side"] == "right"
    assert config["teleop"]["wrist_pose_source"] == "left"
    assert "left" in config["robot"]["cameras"]
    assert "right" not in config["robot"]["cameras"]


def test_right_record_yaml_records_raw_130d_tactile_separately():
    config = _load_config("configs/right_arm/o10_right_record.yaml")

    assert config["robot"]["port"] == "can1"
    assert config["robot"]["include_eef_pose"] is False
    assert config["robot"]["tactile_mode"] == "130d"
    assert config["teleop"]["controller_side"] == "left"
    assert config["teleop"]["wrist_pose_source"] == "right"
    assert "right_wrist" in config["robot"]["cameras"]
    assert "right" not in config["robot"]["cameras"]


def test_single_arm_realsense_rotations_are_no_rotation():
    left_control_config = _load_config("configs/left_arm/o10_left_control.yaml")
    left_record_config = _load_config("configs/left_arm/o10_left_record.yaml")
    left_infer_config = _load_config("configs/left_arm/o10_left_infer.yaml")
    control_config = _load_config("configs/right_arm/o10_right_control.yaml")
    record_config = _load_config("configs/right_arm/o10_right_record.yaml")
    infer_config = _load_config("configs/right_arm/o10_right_infer.yaml")

    left_control_rotation = left_control_config["robot"]["cameras"]["left_wrist"]["rotation"]
    left_record_rotation = left_record_config["robot"]["cameras"]["left"]["rotation"]
    left_infer_rotation = left_infer_config["robot"]["cameras"]["left"]["rotation"]
    control_rotation = control_config["robot"]["cameras"]["right_wrist"]["rotation"]
    record_rotation = record_config["robot"]["cameras"]["right_wrist"]["rotation"]
    infer_rotation = infer_config["robot"]["cameras"]["right"]["rotation"]

    assert left_control_rotation == left_record_rotation == left_infer_rotation == "NO_ROTATION"
    assert control_rotation == record_rotation == infer_rotation == "NO_ROTATION"
