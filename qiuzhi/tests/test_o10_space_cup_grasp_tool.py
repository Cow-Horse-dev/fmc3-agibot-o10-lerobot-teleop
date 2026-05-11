import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "tools" / "o10_space_cup_grasp.py"


def _load_tool_module():
    spec = importlib.util.spec_from_file_location("o10_space_cup_grasp_tool", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeHand:
    def __init__(self):
        self.writes = []

    def write_active_joint_angles(self, joint_angles):
        self.writes.append(list(joint_angles))


def test_four_finger_linked_cylindrical_pose_moves_non_thumb_flexion_together():
    tool = _load_tool_module()
    open_pose = [-0.03, 1.51, -0.5, 0.0, 0.5, 0.5, 0.0, 1.48, 0.0, 1.48]
    closed_pose = [-0.03, 1.51, -0.7, 0.0, 0.7, 0.7, 0.0, 1.48, 0.0, 1.48]

    linked_open = tool.build_four_finger_linked_pose(open_pose)
    linked_closed = tool.build_four_finger_linked_pose(closed_pose)

    assert linked_open[:3] == pytest.approx(open_pose[:3])
    assert linked_closed[:3] == pytest.approx(closed_pose[:3])
    assert [
        linked_open[index] for index in tool.NON_THUMB_FLEXION_INDICES
    ] == pytest.approx([0.5] * 4)
    assert [
        linked_closed[index] for index in tool.NON_THUMB_FLEXION_INDICES
    ] == pytest.approx([0.7] * 4)


@pytest.mark.parametrize(
    ("handedness", "tripod_open", "expected_thumb_yaw", "expected_thumb_pitch"),
    [
        ("left", [-0.03, 1.51, -0.5, 0.0, 0.5, 0.5, 0.0, 1.48, 0.0, 1.48], 1.51, -0.5),
        ("right", [0.03, -1.51, 0.5, 0.0, 0.5, 0.5, 0.0, 1.48, 0.0, 1.48], -1.51, 0.5),
    ],
)
def test_perpendicular_initial_open_pose_straightens_four_fingers_and_keeps_thumb_opposed(
    handedness,
    tripod_open,
    expected_thumb_yaw,
    expected_thumb_pitch,
):
    tool = _load_tool_module()

    ready_open = tool.build_perpendicular_open_pose(tripod_open, handedness)

    assert ready_open[0] == pytest.approx(tripod_open[0])
    assert ready_open[1] == pytest.approx(expected_thumb_yaw)
    assert ready_open[2] == pytest.approx(expected_thumb_pitch)
    assert [ready_open[index] for index in tool.NON_THUMB_YAW_INDICES] == pytest.approx([0.0] * 3)
    assert [
        ready_open[index] for index in tool.NON_THUMB_FLEXION_INDICES
    ] == pytest.approx([0.0] * 4)


def test_space_press_and_release_closes_then_opens_hand():
    tool = _load_tool_module()
    keyboard = SimpleNamespace(Key=SimpleNamespace(space=object()))
    hand = _FakeHand()
    open_pose = [0.1] * 10
    closed_pose = [0.9] * 10
    controller = tool.SpaceCupGraspController(hand, open_pose, closed_pose)

    controller.on_press(keyboard.Key.space, keyboard)
    controller.on_release(keyboard.Key.space, keyboard)

    assert hand.writes == [closed_pose, open_pose]


def test_default_space_tool_gesture_is_cylindrical(monkeypatch):
    tool = _load_tool_module()
    monkeypatch.setattr(tool.sys, "argv", ["o10_space_cup_grasp.py"])

    args = tool.parse_args()

    assert args.gesture == "cylindrical"
