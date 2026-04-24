import importlib.util
import sys
from pathlib import Path


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

CONFIG_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "teleoperators"
    / "pico_leader_single_arm_agibot_o10"
    / "config_pico_leader_single_arm_agibot_o10.py"
)

spec = importlib.util.spec_from_file_location(
    "single_arm_o10_config_test_module",
    CONFIG_PATH,
)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

PicoLeaderSingleArmAgibotO10Config = module.PicoLeaderSingleArmAgibotO10Config


def test_single_arm_o10_config_accepts_trigger_gesture_hand_mode():
    config = PicoLeaderSingleArmAgibotO10Config(
        hand_mode="trigger_gesture",
        trigger_gesture="pinch",
    )

    assert config.hand_mode == "trigger_gesture"
    assert config.trigger_gesture == "pinch"
