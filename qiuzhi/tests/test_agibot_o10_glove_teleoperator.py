import importlib.util
from pathlib import Path
import sys
import time


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

AGIBOT_O10_HAND_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "teleoperators"
    / "pico_leader_single_arm_agibot_o10"
    / "agibot_o10_hand.py"
)

spec = importlib.util.spec_from_file_location(
    "agibot_o10_hand_test_module",
    AGIBOT_O10_HAND_PATH,
)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

AgibotO10GloveTeleoperator = module.AgibotO10GloveTeleoperator


def test_select_role_name_prefers_matching_handedness():
    teleoperator = AgibotO10GloveTeleoperator(handedness="right")

    selected_role = teleoperator._select_role_name(["UDXST4688L", "UDXST4688R"])

    assert selected_role == "UDXST4688R"


def test_select_role_name_rejects_explicit_opposite_handedness():
    teleoperator = AgibotO10GloveTeleoperator(handedness="right")

    selected_role = teleoperator._select_role_name(["UDXST4688L"])

    assert selected_role is None


def test_has_hand_data_respects_max_age():
    teleoperator = AgibotO10GloveTeleoperator(handedness="right")
    teleoperator.last_update_time = time.time() - 1.0

    assert teleoperator.has_hand_data()
    assert not teleoperator.has_hand_data(max_age_s=0.2)


def test_update_hand_data_stores_pre_mapped_values_verbatim():
    teleoperator = AgibotO10GloveTeleoperator(handedness="right")
    sample = [0.10, -0.20, 0.30, 0.0, 0.5, 0.5, 0.0, 0.5, 0.0, 0.5]
    teleoperator.update_hand_data(sample)
    assert teleoperator.get_hand_data() == sample


def test_teleoperator_owns_an_o10_hand_mapper_with_matching_handedness():
    teleoperator = AgibotO10GloveTeleoperator(handedness="left")
    assert teleoperator.mapper.handedness == "left"
