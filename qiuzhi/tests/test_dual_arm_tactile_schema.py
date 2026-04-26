from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/robots/pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py"
)


def test_observation_features_source_references_dual_arm_tactile_feature_sets():
    source = SRC_FILE.read_text(encoding="utf-8")

    assert 'if tactile_mode == "7d":' in source
    assert "DUAL_ARM_TACTILE_AVG_FEATURE_NAMES" in source
    assert 'elif tactile_mode == "80d":' in source
    assert "DUAL_ARM_TACTILE_FINGERTIP_FEATURE_NAMES" in source
    assert 'elif tactile_mode == "130d":' in source
    assert "DUAL_ARM_TACTILE_FULL_FEATURE_NAMES" in source
    assert "return {**state_ft, **tactile_ft, **self._cameras_ft}" in source


def test_gripper_observation_source_uses_gripper_state_without_eef_pose_fields():
    source = SRC_FILE.read_text(encoding="utf-8")

    assert "DUAL_ARM_GRIPPER_STATE_FEATURE_NAMES" in source
    assert 'if self._hand_action_mode() == "gripper_1d":' in source
    assert 'if self._hand_action_mode() != "gripper_1d" and self.config.include_eef_pose:' in source
    assert "for idx, feat in enumerate(AGIBOT_O10_POSE_FEATURE_NAMES):" in source
