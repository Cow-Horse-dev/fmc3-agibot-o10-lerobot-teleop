from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD_SRC = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/record.py"
)


def test_record_source_supports_dual_arm_o10_types():
    source = RECORD_SRC.read_text(encoding="utf-8")

    assert 'elif robot_type == "pico_follower_dual_arm_agibot_o10":' in source
    assert 'elif teleop_type == "pico_leader_dual_arm_agibot_o10":' in source
    assert 'robot.name == "pico_follower_dual_arm_agibot_o10"' in source
    assert 'teleop.name == "pico_leader_dual_arm_agibot_o10"' in source


def test_record_source_accepts_intelrealsense_alias():
    source = RECORD_SRC.read_text(encoding="utf-8")

    assert "from .utils.camera_config_parser import parse_camera_configs" in source
    assert "return parse_camera_configs(cameras_obj)" in source


def test_record_source_rehydrates_single_arm_teleop_when_episode_starts():
    source = RECORD_SRC.read_text(encoding="utf-8")

    start = source.index(
        'elif (\n'
        '                teleop.name == "pico_leader_single_arm_eef"\n'
        '                or teleop.name == "pico_leader_single_arm_agibot_o10"\n'
        "            ):"
    )
    end = source.index(
        '            elif teleop.name == "pico_leader_dual_arm_agibot_o10":',
        start,
    )
    block = source[start:end]

    enable_zero_mode_index = block.index("_set_single_arm_zero_mode(teleop, True)")
    sync_index = block.index("_sync_teleop_to_robot_reset(teleop)")
    disable_zero_mode_index = block.index("_set_single_arm_zero_mode(teleop, False)")

    assert enable_zero_mode_index < sync_index < disable_zero_mode_index


def test_record_source_rehydrates_dual_arm_teleop_when_episode_starts():
    source = RECORD_SRC.read_text(encoding="utf-8")

    start = source.index(
        '                print_green(\n'
        '                    f"Episode {recorded + 1} started. Keyboard controls the recording flow; VR controls both arms and both hands."\n'
        "                )"
    )
    end = source.index("            else:", start)
    block = source[start:end]

    enable_zero_mode_index = block.index("_set_dual_arm_zero_mode(teleop, True)")
    sync_index = block.index("_sync_teleop_to_robot_reset(teleop)")
    disable_zero_mode_index = block.index("_set_dual_arm_zero_mode(teleop, False)")

    assert enable_zero_mode_index < sync_index < disable_zero_mode_index
