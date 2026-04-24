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

    assert "_release_teleop_waiting_state_for_recording(teleop)" in block


def test_record_source_rehydrates_dual_arm_teleop_when_episode_starts():
    source = RECORD_SRC.read_text(encoding="utf-8")

    start = source.index(
        '                print_green(\n'
        '                    f"Episode {recorded + 1} started. Keyboard controls the recording flow; VR controls both arms and both hands."\n'
        "                )"
    )
    end = source.index("            else:", start)
    block = source[start:end]

    assert "_release_teleop_waiting_state_for_recording(teleop)" in block


def test_record_source_prepares_o10_teleop_waiting_state_after_initial_reset():
    source = RECORD_SRC.read_text(encoding="utf-8")

    start = source.index(
        '        elif (\n'
        '            robot.name == "pico_follower_single_arm_eef"\n'
        '            or robot.name == "pico_follower_single_arm_agibot_o10"\n'
        "        ):"
    )
    end = source.index('        recorded = 0', start)
    block = source[start:end]

    assert "_prepare_teleop_waiting_state_after_reset(teleop)" in block
    assert 'robot.name == "pico_follower_dual_arm_agibot_o10"' in block


def test_record_source_uses_gentle_waiting_reset_for_mid_episode_and_post_episode_resets():
    source = RECORD_SRC.read_text(encoding="utf-8")

    y_reset_start = source.index('            if events.get("reset_robot"):')
    y_reset_end = source.index('            if events.get("discard_episode"):', y_reset_start)
    y_reset_block = source[y_reset_start:y_reset_end]
    assert "_prepare_teleop_waiting_state_after_reset(teleop)" in y_reset_block

    post_episode_start = source.index('            if robot.name == "airbot_play_follower":')
    post_episode_end = source.index('            if events["rerecord_episode"]:', post_episode_start)
    post_episode_block = source[post_episode_start:post_episode_end]
    assert "_prepare_teleop_waiting_state_after_reset(teleop" in post_episode_block
