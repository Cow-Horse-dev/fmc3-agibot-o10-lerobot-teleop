import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
SINGLE_MODULE_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "robots"
    / "pico_follower_single_arm_agibot_o10"
    / "airbot_pico_follower_single_arm_agibot_o10.py"
)
DUAL_MODULE_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "robots"
    / "pico_follower_dual_arm_agibot_o10"
    / "airbot_pico_follower_dual_arm_agibot_o10.py"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


ARM_FEATURE_NAMES = tuple(f"joint{index}.pos" for index in range(1, 7))
HAND_FEATURE_NAMES = tuple(f"hand_joint_{index}.pos" for index in range(10))
GRIPPER_FEATURE_NAMES = ("gripper.pos",)
EEF_DELTA_FEATURE_NAMES = (
    "delta_pose.x",
    "delta_pose.y",
    "delta_pose.z",
    "delta_orientation.roll",
    "delta_orientation.pitch",
    "delta_orientation.yaw",
)
POSE_FEATURE_NAMES = (
    "pose.x",
    "pose.y",
    "pose.z",
    "quaternion.qx",
    "quaternion.qy",
    "quaternion.qz",
    "quaternion.qw",
)


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


class _FakeArmKdl:
    def __init__(self, solution):
        self.solution = list(solution)
        self.inverse_targets = []

    def forward_kinematics(self, joints):
        matrix = np.eye(4)
        matrix[0, 3] = float(joints[0])
        return matrix

    def inverse_kinematics(self, target_pose, seed, force_calculate=False):
        self.inverse_targets.append((np.array(target_pose), list(seed), force_calculate))
        return [self.solution]


def _install_common_stubs(monkeypatch):
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
    _install_stub_module(
        monkeypatch,
        "mmk2_kdl_py",
        ArmKdlNumerical=lambda *args, **kwargs: _FakeArmKdl([0.0] * 6),
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.utils.agibot_o10",
        AGIBOT_O10_ARM_FEATURE_NAMES=ARM_FEATURE_NAMES,
        AGIBOT_O10_HAND_FEATURE_NAMES=HAND_FEATURE_NAMES,
        AGIBOT_O10_GRIPPER_FEATURE_NAMES=GRIPPER_FEATURE_NAMES,
        AGIBOT_O10_EEF_DELTA_FEATURE_NAMES=EEF_DELTA_FEATURE_NAMES,
        AGIBOT_O10_POSE_FEATURE_NAMES=POSE_FEATURE_NAMES,
        AgibotO10Hand=_FakeHand,
        agibot_o10_gripper_value_from_hand_joints=lambda *args, **kwargs: 0.0,
        agibot_o10_hand_joints_from_gripper_value=lambda *args, **kwargs: [0.0] * len(HAND_FEATURE_NAMES),
        agibot_o10_joint_action_feature_types=lambda: {
            name: float for name in (*ARM_FEATURE_NAMES, *HAND_FEATURE_NAMES)
        },
        agibot_o10_action_feature_types=lambda: {
            name: float for name in (*ARM_FEATURE_NAMES, *HAND_FEATURE_NAMES, *POSE_FEATURE_NAMES)
        },
        agibot_o10_eef_delta_action_feature_types=lambda: {
            name: float for name in (*EEF_DELTA_FEATURE_NAMES, *HAND_FEATURE_NAMES)
        },
        agibot_o10_gripper_action_feature_types=lambda: {
            name: float for name in (*ARM_FEATURE_NAMES, *GRIPPER_FEATURE_NAMES)
        },
        agibot_o10_eef_delta_gripper_action_feature_types=lambda: {
            name: float for name in (*EEF_DELTA_FEATURE_NAMES, *GRIPPER_FEATURE_NAMES)
        },
        agibot_o10_gripper_state_feature_types=lambda: {
            name: float for name in (*ARM_FEATURE_NAMES, *GRIPPER_FEATURE_NAMES)
        },
        build_agibot_o10_joint_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*ARM_FEATURE_NAMES, *HAND_FEATURE_NAMES), values, strict=True)
        },
        build_agibot_o10_eef_delta_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*EEF_DELTA_FEATURE_NAMES, *HAND_FEATURE_NAMES), values, strict=True)
        },
        build_agibot_o10_gripper_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*ARM_FEATURE_NAMES, *GRIPPER_FEATURE_NAMES), values, strict=True)
        },
        build_agibot_o10_eef_delta_gripper_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*EEF_DELTA_FEATURE_NAMES, *GRIPPER_FEATURE_NAMES), values, strict=True)
        },
        normalize_agibot_o10_action_control_mode=lambda mode: (mode or "joint").strip().lower(),
        normalize_agibot_o10_hand_action_mode=lambda mode: (mode or "dexterous_10d").strip().lower(),
    )
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


def _load_single_arm_module(monkeypatch):
    _install_common_stubs(monkeypatch)

    _install_stub_module(
        monkeypatch,
        "test_single_o10_eef_delta.config_pico_follower_single_arm_agibot_o10",
        PicoFollowerSingleArmAgibotO10Config=object,
    )
    spec = importlib.util.spec_from_file_location(
        "test_single_o10_eef_delta",
        SINGLE_MODULE_PATH,
        submodule_search_locations=[str(SINGLE_MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_single_o10_eef_delta"
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_dual_arm_module(monkeypatch):
    _install_common_stubs(monkeypatch)

    _install_stub_module(
        monkeypatch,
        "test_dual_o10_eef_delta.config_pico_follower_dual_arm_agibot_o10",
        PicoFollowerDualArmAgibotO10Config=object,
    )
    spec = importlib.util.spec_from_file_location(
        "test_dual_o10_eef_delta",
        DUAL_MODULE_PATH,
        submodule_search_locations=[str(DUAL_MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_dual_o10_eef_delta"
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_single_arm_eef_delta_mode_exposes_delta_pose_and_hand_action_features(monkeypatch):
    module = _load_single_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerSingleArmAgibotO10)
    robot.config = SimpleNamespace(action_control_mode="eef_delta")

    assert list(robot.action_features) == [*EEF_DELTA_FEATURE_NAMES, *HAND_FEATURE_NAMES]


def test_dual_arm_eef_delta_mode_exposes_per_side_delta_pose_and_hand_action_features(monkeypatch):
    module = _load_dual_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot.config = SimpleNamespace(action_control_mode="eef_delta")

    expected = [
        *(f"left.{name}" for name in EEF_DELTA_FEATURE_NAMES),
        *(f"left.{name}" for name in HAND_FEATURE_NAMES),
        *(f"right.{name}" for name in EEF_DELTA_FEATURE_NAMES),
        *(f"right.{name}" for name in HAND_FEATURE_NAMES),
    ]
    assert list(robot.action_features) == expected


def test_single_arm_send_action_converts_eef_delta_to_joint_target(monkeypatch):
    module = _load_single_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerSingleArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(action_control_mode="eef_delta", enable_hand=True, arm_joints_num=7)
    robot.arm = _FakeArm()
    robot.hand = _FakeHand()
    robot.arm_kdl = _FakeArmKdl([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    robot.get_joint_pos = lambda: ([0.1, 0.0, 0.0, 0.0, 0.0, 0.0], [0.0] * 10)

    hand_values = [float(index) for index in range(10)]
    action = {
        **{name: 0.0 for name in EEF_DELTA_FEATURE_NAMES},
        **{name: value for name, value in zip(HAND_FEATURE_NAMES, hand_values, strict=True)},
    }

    sent_action = robot.send_action(action)

    assert robot.arm.pvt_calls[0][0] == pytest.approx([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert robot.hand.writes[0] == pytest.approx(hand_values)
    assert list(sent_action) == [*EEF_DELTA_FEATURE_NAMES, *HAND_FEATURE_NAMES]


def test_dual_arm_send_action_converts_each_side_eef_delta_to_joint_targets(monkeypatch):
    module = _load_dual_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(action_control_mode="eef_delta", enable_hand=True, arm_joints_num=7)
    robot.left_arm = _FakeArm()
    robot.right_arm = _FakeArm()
    robot.left_hand = _FakeHand()
    robot.right_hand = _FakeHand()
    robot.arm_kdl = _FakeArmKdl([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    robot.get_joint_pos = lambda: {
        "left": ([0.1, 0.0, 0.0, 0.0, 0.0, 0.0], [0.0] * 10),
        "right": ([0.2, 0.0, 0.0, 0.0, 0.0, 0.0], [0.0] * 10),
    }

    action = {}
    for side in ("left", "right"):
        action.update({f"{side}.{name}": 0.0 for name in EEF_DELTA_FEATURE_NAMES})
        action.update({f"{side}.{name}": float(index) for index, name in enumerate(HAND_FEATURE_NAMES)})

    sent_action = robot.send_action(action)

    assert robot.left_arm.pvt_calls[0][0] == pytest.approx([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert robot.right_arm.pvt_calls[0][0] == pytest.approx([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert robot.left_hand.writes[0] == pytest.approx([float(index) for index in range(10)])
    assert robot.right_hand.writes[0] == pytest.approx([float(index) for index in range(10)])
    assert list(sent_action) == [
        *(f"left.{name}" for name in EEF_DELTA_FEATURE_NAMES),
        *(f"left.{name}" for name in HAND_FEATURE_NAMES),
        *(f"right.{name}" for name in EEF_DELTA_FEATURE_NAMES),
        *(f"right.{name}" for name in HAND_FEATURE_NAMES),
    ]
