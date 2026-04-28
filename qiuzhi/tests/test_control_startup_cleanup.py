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
