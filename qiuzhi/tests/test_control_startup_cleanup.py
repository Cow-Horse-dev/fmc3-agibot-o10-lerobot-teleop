from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_SRC = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/control.py"
)


def test_control_source_disconnects_teleop_when_startup_fails():
    source = CONTROL_SRC.read_text(encoding="utf-8")

    assert "def _disconnect_best_effort(" in source
    assert "startup_attempted: bool = False" in source
    assert "startup_complete = False" in source
    assert "teleop_startup_attempted = True" in source
    assert "_disconnect_best_effort(" in source
    assert "teleop," in source
    assert '"teleoperator",' in source
    assert "startup_attempted=teleop_startup_attempted" in source


def test_control_source_configures_rerun_blueprint_from_robot_cameras():
    source = CONTROL_SRC.read_text(encoding="utf-8")

    assert "from .utils.rerun_control_display import configure_control_rerun_display" in source
    assert "configure_control_rerun_display(robot)" in source


def test_o10_robot_sources_apply_realsense_camera_controls():
    package_root = (
        REPO_ROOT
        / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
        / "lerobot_play/robots"
    )
    sources = [
        package_root / "pico_follower_single_arm_agibot_o10/airbot_pico_follower_single_arm_agibot_o10.py",
        package_root / "pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py",
    ]

    for source_path in sources:
        source = source_path.read_text(encoding="utf-8")
        assert "from lerobot_play.utils.realsense_controls import apply_realsense_controls" in source
        assert "apply_realsense_controls(" in source
