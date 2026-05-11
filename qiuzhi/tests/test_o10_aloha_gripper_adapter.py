import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
DUAL_ROBOT_MODULE_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "robots"
    / "pico_follower_dual_arm_agibot_o10"
    / "airbot_pico_follower_dual_arm_agibot_o10.py"
)
DUAL_TELEOP_MODULE_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "teleoperators"
    / "pico_leader_dual_arm_agibot_o10"
    / "pico_leader_dual_arm_agibot_o10.py"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))

from lerobot_play.utils import agibot_o10


ARM_FEATURE_NAMES = agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES
GRIPPER_FEATURE_NAME = "gripper.pos"


def _install_stub_module(monkeypatch, name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


class _FakeRobot:
    def __init__(self, config):
        self.config = config


class _FakeArm:
    def __init__(self):
        self.pvt_calls = []

    def pvt(self, joints, velocities, effort):
        self.pvt_calls.append((list(joints), list(velocities), list(effort)))


class _FakeHand:
    def __init__(self):
        self.writes = []

    def write_active_joint_angles(self, joints):
        self.writes.append(list(joints))


class _FakePicoLeaderSingleArmEEF:
    pass


def _expected_dual_aloha_feature_names() -> list[str]:
    return [
        *(f"left.{name}" for name in ARM_FEATURE_NAMES),
        f"left.{GRIPPER_FEATURE_NAME}",
        *(f"right.{name}" for name in ARM_FEATURE_NAMES),
        f"right.{GRIPPER_FEATURE_NAME}",
    ]


def _install_dual_robot_stubs(monkeypatch):
    _install_stub_module(
        monkeypatch,
        "airbot_hardware_py",
        Play=types.SimpleNamespace(create=lambda *args, **kwargs: _FakeArm()),
        MotorType=types.SimpleNamespace(OD=object(), DM=object(), NA=object()),
        EEFType=types.SimpleNamespace(NA=object()),
        MotorControlMode=types.SimpleNamespace(PVT=object()),
        create_asio_executor=lambda *args, **kwargs: types.SimpleNamespace(
            get_io_context=lambda: object()
        ),
    )
    _install_stub_module(monkeypatch, "lerobot.cameras.utils", make_cameras_from_configs=lambda configs: {})
    _install_stub_module(monkeypatch, "lerobot.robots.robot", Robot=_FakeRobot)
    _install_stub_module(monkeypatch, "lerobot.utils.errors", DeviceNotConnectedError=RuntimeError)
    _install_stub_module(monkeypatch, "mmk2_kdl_py", ArmKdlNumerical=lambda *args, **kwargs: object())
    _install_stub_module(
        monkeypatch,
        "lerobot_play.utils.camera_autodetect",
        resolve_auto_opencv_cameras=lambda *args, **kwargs: None,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.utils.joint_target_store",
        PersistentJointTargetStore=object,
        load_reset_poses=lambda *args, **kwargs: (None, None),
    )
    _install_stub_module(
        monkeypatch,
        "test_dual_o10_aloha.config_pico_follower_dual_arm_agibot_o10",
        PicoFollowerDualArmAgibotO10Config=object,
    )


def _load_dual_robot_module(monkeypatch):
    _install_dual_robot_stubs(monkeypatch)
    spec = importlib.util.spec_from_file_location(
        "test_dual_o10_aloha",
        DUAL_ROBOT_MODULE_PATH,
        submodule_search_locations=[str(DUAL_ROBOT_MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_dual_o10_aloha"
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_dual_teleop_module(monkeypatch):
    _install_stub_module(monkeypatch, "mmk2_kdl_py", ArmKdlNumerical=lambda *args, **kwargs: object())
    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.pico_leader_single_arm_eef",
        PicoLeaderSingleArmEEF=_FakePicoLeaderSingleArmEEF,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.lpf",
        OnlineVariableStepLPF=object,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_agibot_o10.agibot_o10_hand",
        AgibotO10GloveTeleoperator=object,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.robots.pico_follower_dual_arm_agibot_o10.airbot_pico_follower_dual_arm_agibot_o10",
        DUAL_ARM_ACTION_FEATURE_NAMES=tuple(
            [
                *(f"left.{name}" for name in ARM_FEATURE_NAMES),
                *(f"left.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES),
                *(f"right.{name}" for name in ARM_FEATURE_NAMES),
                *(f"right.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES),
            ]
        ),
        DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES=tuple(f"eef_{index}" for index in range(32)),
        DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES=tuple(_expected_dual_aloha_feature_names()),
        DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES=tuple(
            [
                *(f"left.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES),
                *(f"left.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES),
                *(f"right.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES),
                *(f"right.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES),
            ]
        ),
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.utils.joint_target_store",
        PersistentJointTargetStore=object,
        load_reset_poses=lambda *args, **kwargs: (None, None),
    )
    _install_stub_module(
        monkeypatch,
        "test_dual_o10_aloha_teleop.config_pico_leader_dual_arm_agibot_o10",
        PicoLeaderDualArmAgibotO10Config=object,
    )
    spec = importlib.util.spec_from_file_location(
        "test_dual_o10_aloha_teleop",
        DUAL_TELEOP_MODULE_PATH,
        submodule_search_locations=[str(DUAL_TELEOP_MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_dual_o10_aloha_teleop"
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_hand_gripper_adapter_round_trips_trigger_gesture_poses():
    open_pose = agibot_o10.get_agibot_o10_trigger_gesture_joint_angles("tripod", "left", "open")
    closed_pose = agibot_o10.get_agibot_o10_trigger_gesture_joint_angles("tripod", "left", "closed")
    midpoint = [(open_value + closed_value) / 2 for open_value, closed_value in zip(open_pose, closed_pose)]

    assert agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES == (GRIPPER_FEATURE_NAME,)
    assert agibot_o10.normalize_agibot_o10_hand_action_mode("gripper_1d") == "gripper_1d"
    assert agibot_o10.agibot_o10_hand_joints_from_gripper_value(0.0, "tripod", "left") == pytest.approx(open_pose)
    assert agibot_o10.agibot_o10_hand_joints_from_gripper_value(1.0, "tripod", "left") == pytest.approx(closed_pose)
    assert agibot_o10.agibot_o10_gripper_value_from_hand_joints(open_pose, "tripod", "left") == pytest.approx(0.0)
    assert agibot_o10.agibot_o10_gripper_value_from_hand_joints(closed_pose, "tripod", "left") == pytest.approx(1.0)
    assert agibot_o10.agibot_o10_gripper_value_from_hand_joints(midpoint, "tripod", "left") == pytest.approx(0.5)


@pytest.mark.parametrize("handedness", ["left", "right"])
def test_cylindrical_gripper_1d_mapping_uses_reset_pose_gesture(handedness):
    reset_poses_path = REPO_ROOT.parent / "configs" / "reset_poses" / "o10_dual_reset.json"
    open_pose = agibot_o10.get_agibot_o10_reset_pose_gesture_joint_angles(
        reset_poses_path,
        "cylindrical",
        handedness,
        "open",
    )
    closed_pose = agibot_o10.get_agibot_o10_reset_pose_gesture_joint_angles(
        reset_poses_path,
        "cylindrical",
        handedness,
        "closed",
    )

    assert agibot_o10.agibot_o10_hand_joints_from_gripper_value(
        0.0,
        "cylindrical",
        handedness,
        reset_poses_path=reset_poses_path,
    ) == pytest.approx(open_pose)
    assert agibot_o10.agibot_o10_hand_joints_from_gripper_value(
        1.0,
        "cylindrical",
        handedness,
        reset_poses_path=reset_poses_path,
    ) == pytest.approx(closed_pose)
    assert agibot_o10.agibot_o10_gripper_value_from_hand_joints(
        closed_pose,
        "cylindrical",
        handedness,
        reset_poses_path=reset_poses_path,
    ) == pytest.approx(1.0)


def test_gripper_adapter_uses_reset_pose_gesture_open_as_pregrasp(tmp_path):
    reset_poses_path = tmp_path / "o10_reset.json"
    custom_open = [-0.11, 1.2, -0.45, 0.03, 0.31, 0.42, 0.07, 1.1, 0.08, 1.2]
    custom_closed = [-0.11, 1.2, -0.65, 0.03, 0.61, 0.72, 0.07, 1.1, 0.08, 1.2]
    reset_poses_path.write_text(
        json.dumps(
            {
                "arm": {
                    "feature_names": list(agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES),
                    "left": {name: 0.0 for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES},
                },
                "gestures": {
                    "tripod": {
                        "left": {
                            "open": custom_open,
                            "closed": custom_closed,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    midpoint = [
        (open_value + closed_value) / 2
        for open_value, closed_value in zip(custom_open, custom_closed)
    ]

    assert agibot_o10.agibot_o10_hand_joints_from_gripper_value(
        0.0,
        "tripod",
        "left",
        reset_poses_path=reset_poses_path,
    ) == pytest.approx(custom_open)
    assert agibot_o10.agibot_o10_hand_joints_from_gripper_value(
        1.0,
        "tripod",
        "left",
        reset_poses_path=reset_poses_path,
    ) == pytest.approx(custom_closed)
    assert agibot_o10.agibot_o10_gripper_value_from_hand_joints(
        midpoint,
        "tripod",
        "left",
        reset_poses_path=reset_poses_path,
    ) == pytest.approx(0.5)


def test_dual_robot_gripper_mode_exposes_aloha_14d_features_without_eef_pose(monkeypatch):
    module = _load_dual_robot_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot.config = SimpleNamespace(
        action_control_mode="joint",
        hand_action_mode="gripper_1d",
        include_eef_pose=True,
        tactile_mode="none",
        cameras={},
    )
    robot.cameras = {}

    assert list(robot.action_features) == _expected_dual_aloha_feature_names()
    assert list(robot.observation_features) == _expected_dual_aloha_feature_names()
    assert not any("pose." in name or "quaternion." in name for name in robot.observation_features)


def test_dual_robot_gripper_mode_observation_compresses_hand_to_1d(monkeypatch):
    module = _load_dual_robot_module(monkeypatch)
    left_hand = agibot_o10.agibot_o10_hand_joints_from_gripper_value(1.0, "tripod", "left")
    right_hand = agibot_o10.agibot_o10_hand_joints_from_gripper_value(0.0, "pinch", "right")

    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot.config = SimpleNamespace(
        hand_action_mode="gripper_1d",
        include_eef_pose=True,
        tactile_mode="none",
        enable_hand=True,
        left={"handedness": "left", "gripper_gesture": "tripod"},
        right={"handedness": "right", "gripper_gesture": "pinch"},
        cameras={},
    )
    robot._is_connected = True
    robot.cameras = {}
    robot.get_joint_pos = lambda: {
        "left": ([1, 2, 3, 4, 5, 6], left_hand),
        "right": ([7, 8, 9, 10, 11, 12], right_hand),
    }

    obs = robot.get_observation()

    assert list(obs) == _expected_dual_aloha_feature_names()
    assert obs[f"left.{GRIPPER_FEATURE_NAME}"] == pytest.approx(1.0)
    assert obs[f"right.{GRIPPER_FEATURE_NAME}"] == pytest.approx(0.0)


def test_dual_robot_gripper_mode_send_action_expands_1d_gripper_to_hand_joints(monkeypatch):
    module = _load_dual_robot_module(monkeypatch)
    left_closed = agibot_o10.agibot_o10_hand_joints_from_gripper_value(1.0, "tripod", "left")
    right_open = agibot_o10.agibot_o10_hand_joints_from_gripper_value(0.0, "pinch", "right")

    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot.config = SimpleNamespace(
        action_control_mode="joint",
        hand_action_mode="gripper_1d",
        enable_hand=True,
        arm_joints_num=7,
        left={"handedness": "left", "gripper_gesture": "tripod"},
        right={"handedness": "right", "gripper_gesture": "pinch"},
    )
    robot._is_connected = True
    robot.left_arm = _FakeArm()
    robot.right_arm = _FakeArm()
    robot.left_hand = _FakeHand()
    robot.right_hand = _FakeHand()

    action = {
        **{f"left.{name}": float(index) for index, name in enumerate(ARM_FEATURE_NAMES, start=1)},
        f"left.{GRIPPER_FEATURE_NAME}": 1.0,
        **{f"right.{name}": float(index) for index, name in enumerate(ARM_FEATURE_NAMES, start=7)},
        f"right.{GRIPPER_FEATURE_NAME}": 0.0,
    }

    sent = robot.send_action(action)

    assert robot.left_arm.pvt_calls[-1][0] == pytest.approx([1, 2, 3, 4, 5, 6])
    assert robot.right_arm.pvt_calls[-1][0] == pytest.approx([7, 8, 9, 10, 11, 12])
    assert robot.left_hand.writes[-1] == pytest.approx(left_closed)
    assert robot.right_hand.writes[-1] == pytest.approx(right_open)
    assert list(sent) == _expected_dual_aloha_feature_names()


def test_dual_teleop_gripper_mode_get_action_outputs_aloha_14d(monkeypatch):
    module = _load_dual_teleop_module(monkeypatch)
    left_hand = agibot_o10.agibot_o10_hand_joints_from_gripper_value(1.0, "tripod", "left")
    right_hand = agibot_o10.agibot_o10_hand_joints_from_gripper_value(0.0, "pinch", "right")

    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.config = SimpleNamespace(
        action_control_mode="joint",
        hand_action_mode="gripper_1d",
        left={"handedness": "left", "trigger_gesture": "tripod"},
        right={"handedness": "right", "trigger_gesture": "pinch"},
    )
    teleop.get_joint_pos = lambda: [
        1, 2, 3, 4, 5, 6, *left_hand,
        7, 8, 9, 10, 11, 12, *right_hand,
    ]

    action = teleop.get_action()

    assert list(teleop.action_features) == _expected_dual_aloha_feature_names()
    assert list(action) == _expected_dual_aloha_feature_names()
    assert action[f"left.{GRIPPER_FEATURE_NAME}"] == pytest.approx(1.0)
    assert action[f"right.{GRIPPER_FEATURE_NAME}"] == pytest.approx(0.0)
