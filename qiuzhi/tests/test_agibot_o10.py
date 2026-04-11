import importlib.util
import math
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
YUDIE_REFERENCE_PATH = (
    Path("/home/phl/workspace/yudie/AGIBOT/Omnihand_o10_yudie.py")
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))

from lerobot_play.utils import agibot_o10


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


def _load_yudie_reference_module():
    fake_sdk = types.ModuleType("omnihand_2025")
    fake_sdk.AgibotHandO10 = object
    fake_sdk.EFinger = object
    fake_sdk.EControlMode = object
    fake_sdk.EHandType = object

    original_module = sys.modules.get("omnihand_2025")
    sys.modules["omnihand_2025"] = fake_sdk

    try:
        spec = importlib.util.spec_from_file_location(
            "yudie_o10_reference",
            YUDIE_REFERENCE_PATH,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if original_module is None:
            sys.modules.pop("omnihand_2025", None)
        else:
            sys.modules["omnihand_2025"] = original_module


def _build_test_inputs(handedness: str, mapped_values: list[float]):
    finger_data = [Vec3() for _ in range(30)]
    raw_values = [0.0] * 30

    if handedness == "left":
        glove_targets = (
            (0, "z", 20),
            (0, "y", 3),
            (0, "x", 2),
            (3, "y", 7),
            (3, "x", 6),
            (6, "x", 10),
            (9, "y", 15),
            (9, "x", 14),
            (12, "y", 19),
            (12, "x", 18),
        )
    else:
        glove_targets = (
            (15, "z", 20),
            (15, "y", 3),
            (15, "x", 2),
            (18, "y", 7),
            (18, "x", 6),
            (21, "x", 10),
            (24, "y", 15),
            (24, "x", 14),
            (27, "y", 19),
            (27, "x", 18),
        )

    for value, (finger_index, axis, raw_index) in zip(mapped_values, glove_targets):
        setattr(finger_data[finger_index], axis, value)
        raw_values[raw_index] = value

    return finger_data, raw_values


def test_left_glove_mapping_matches_yudie_reference():
    reference_module = _load_yudie_reference_module()
    mapped_values = [12.0, -18.0, 64.0, 16.0, -92.0, 45.0, -5.0, 88.0, 33.0, -120.0]
    finger_data, raw_values = _build_test_inputs("left", mapped_values)

    actual = agibot_o10.glove_vec_to_agibot_o10_joint_angles(finger_data, "left")
    expected = reference_module.get_finger_data_for_AgibotHandO10hand_Angles(
        "left",
        raw_values,
    )

    assert actual == pytest.approx(expected, abs=1e-12)


def test_right_glove_mapping_matches_yudie_reference():
    reference_module = _load_yudie_reference_module()
    mapped_values = [-37.0, 21.0, -71.0, 30.0, 96.0, -75.0, 14.0, 82.0, -44.0, 99.0]
    finger_data, raw_values = _build_test_inputs("right", mapped_values)

    actual = agibot_o10.glove_vec_to_agibot_o10_joint_angles(finger_data, "right")
    expected = reference_module.get_finger_data_for_AgibotHandO10hand_Angles(
        "right",
        raw_values,
    )

    assert actual == pytest.approx(expected, abs=1e-12)


def test_build_agibot_o10_joint_action_dict_contains_only_arm_and_hand_joints():
    action = agibot_o10.build_agibot_o10_joint_action_dict(range(16))

    assert list(action.keys()) == [
        *agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES,
        *agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES,
    ]
    assert list(action.values()) == pytest.approx([float(i) for i in range(16)])


def test_build_agibot_o10_joint_action_dict_rejects_non_joint_lengths():
    with pytest.raises(ValueError, match="must contain 16 values"):
        agibot_o10.build_agibot_o10_joint_action_dict(range(23))


def test_sdk_import_error_mentions_qiuzhi_omnihand_root(monkeypatch):
    monkeypatch.delenv("QIUZHI_OMNIHAND_ROOT", raising=False)

    def fake_import_module(name: str):
        if name == "omnihand_2025":
            raise ModuleNotFoundError(name)
        raise AssertionError(f"Unexpected import attempted: {name}")

    monkeypatch.setattr(agibot_o10.importlib, "import_module", fake_import_module)

    with pytest.raises(ImportError) as exc_info:
        agibot_o10.import_omnihand_2025_module()

    assert "QIUZHI_OMNIHAND_ROOT" in str(exc_info.value)
