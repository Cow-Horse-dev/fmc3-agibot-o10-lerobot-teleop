import importlib.util
from pathlib import Path
import sys


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


CONFIG_MODULE_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "robots"
    / "pico_follower_single_arm_agibot_o10"
    / "config_pico_follower_single_arm_agibot_o10.py"
)


def _load_config_class():
    spec = importlib.util.spec_from_file_location(
        "test_single_arm_o10_robot_config_module",
        CONFIG_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.PicoFollowerSingleArmAgibotO10Config


def test_single_arm_robot_config_accepts_enable_hand_false():
    config_class = _load_config_class()
    config = config_class(
        port="can1",
        handedness="left",
        enable_hand=False,
    )

    assert config.enable_hand is False
