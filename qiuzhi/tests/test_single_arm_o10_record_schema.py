from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/robots/pico_follower_single_arm_agibot_o10/airbot_pico_follower_single_arm_agibot_o10.py"
)


def test_single_arm_observation_source_supports_optional_eef_pose_and_tactile():
    source = SRC_FILE.read_text(encoding="utf-8")

    assert "agibot_o10_joint_action_feature_types()" in source
    assert "if self.config.include_eef_pose:" in source
    assert "validate_o10_tactile_mode" in source
    assert 'tactile_mode == "130d"' in source
    assert 'tactile_mode == "7d"' not in source
    assert 'tactile_mode == "80d"' not in source
    assert "observation.tactile." in source
    assert 'if self.hand is not None and tactile_mode != "none":' in source
