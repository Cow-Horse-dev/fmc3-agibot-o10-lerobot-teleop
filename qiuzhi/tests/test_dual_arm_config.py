import pytest
import yaml


def test_dual_control_yaml_parses():
    with open("configs/o10_dual_control.yaml") as f:
        config = yaml.safe_load(f)
    assert config["teleop"]["type"] == "pico_leader_dual_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_dual_arm_agibot_o10"
    assert config["robot"]["left"]["port"] == "can1"
    assert config["robot"]["right"]["port"] == "can0"
    assert config["teleop"]["left"]["handedness"] == "left"
    assert config["teleop"]["right"]["handedness"] == "right"


def test_left_control_yaml_parses():
    with open("configs/o10_left_control.yaml") as f:
        config = yaml.safe_load(f)
    assert config["teleop"]["type"] == "pico_leader_single_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_single_arm_agibot_o10"
    assert config["robot"]["port"] == "can1"
    assert config["teleop"]["handedness"] == "left"


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


def test_dual_record_yaml_has_dataset_section():
    with open("configs/o10_dual_record.yaml") as f:
        config = yaml.safe_load(f)
    assert "dataset" in config
    assert "run" in config
    assert config["robot"]["type"] == "pico_follower_dual_arm_agibot_o10"


def test_left_record_yaml_has_dataset_section():
    with open("configs/o10_left_record.yaml") as f:
        config = yaml.safe_load(f)
    assert "dataset" in config
    assert "run" in config
    assert config["robot"]["port"] == "can1"
