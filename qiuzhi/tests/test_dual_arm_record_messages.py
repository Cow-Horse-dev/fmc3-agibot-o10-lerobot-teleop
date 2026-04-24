from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD_SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/record.py"
)
DUAL_TELEOP_SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/pico_leader_dual_arm_agibot_o10.py"
)


def test_dual_arm_record_source_uses_dynamic_trigger_mode_message():
    source = RECORD_SRC_FILE.read_text(encoding="utf-8")

    assert "_describe_dual_arm_trigger_mode(" in source
    assert (
        'print_green(\n                        _describe_dual_arm_trigger_mode('
        in source
    )


def test_dual_arm_teleop_source_overrides_single_arm_pose_source_log():
    source = DUAL_TELEOP_SRC_FILE.read_text(encoding="utf-8")

    assert "当前使用双臂 wrist pose 作为控臂输入" in source
    assert "当前使用 right wrist pose 作为控臂输入" not in source


def test_single_arm_record_source_uses_handedness_specific_control_hint():
    source = RECORD_SRC_FILE.read_text(encoding="utf-8")

    assert 'controller_side = getattr(' in source
    assert '"controller_side"' in source
    assert 'if controller_side == "right":' in source
    assert "A starts arm control, hold right trigger to move, B resets." in source
    assert "X starts arm control, hold left trigger to move, Y resets." in source
