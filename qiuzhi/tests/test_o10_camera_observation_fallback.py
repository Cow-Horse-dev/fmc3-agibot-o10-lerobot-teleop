import importlib.util
import sys
import time
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


def _install_stub_module(monkeypatch, name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _install_common_robot_stubs(monkeypatch):
    class FakeArm:
        def init(self, *args, **kwargs):
            return True

        def uninit(self):
            return None

        def enable(self):
            return None

        def set_param(self, *args, **kwargs):
            return None

    class FakeRobot:
        def __init__(self, config):
            self.config = config

    class FakeArmKdlNumerical:
        def __init__(self, *args, **kwargs):
            pass

        def forward_kinematics(self, joints):
            return np.eye(4)

    class FakePersistentJointTargetStore:
        def __init__(self, *args, **kwargs):
            pass

        def normalize(self, joint_pos):
            return list(joint_pos)

    class FakeAgibotO10Hand:
        def __init__(self, *args, **kwargs):
            pass

    arm_feature_names = tuple(f"joint{index}.pos" for index in range(1, 7))
    hand_feature_names = tuple(f"hand_joint_{index}.pos" for index in range(10))
    gripper_feature_names = ("gripper.pos",)
    eef_delta_feature_names = (
        "delta_pose.x",
        "delta_pose.y",
        "delta_pose.z",
        "delta_orientation.roll",
        "delta_orientation.pitch",
        "delta_orientation.yaw",
    )
    pose_feature_names = tuple(
        ("pose.x", "pose.y", "pose.z", "quaternion.qx", "quaternion.qy", "quaternion.qz", "quaternion.qw")
    )

    _install_stub_module(
        monkeypatch,
        "airbot_hardware_py",
        Play=types.SimpleNamespace(create=lambda *args, **kwargs: FakeArm()),
        MotorType=types.SimpleNamespace(OD=object(), DM=object(), NA=object()),
        EEFType=types.SimpleNamespace(NA=object()),
        MotorControlMode=types.SimpleNamespace(PVT=object()),
        create_asio_executor=lambda *args, **kwargs: types.SimpleNamespace(
            get_io_context=lambda: object()
        ),
    )
    _install_stub_module(
        monkeypatch,
        "lerobot.cameras.utils",
        make_cameras_from_configs=lambda configs: {},
    )
    _install_stub_module(
        monkeypatch,
        "lerobot.robots.robot",
        Robot=FakeRobot,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot.utils.errors",
        DeviceAlreadyConnectedError=RuntimeError,
        DeviceNotConnectedError=RuntimeError,
    )
    _install_stub_module(
        monkeypatch,
        "mmk2_kdl_py",
        ArmKdlNumerical=FakeArmKdlNumerical,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.utils.agibot_o10",
        AGIBOT_O10_ARM_FEATURE_NAMES=arm_feature_names,
        AGIBOT_O10_EEF_DELTA_FEATURE_NAMES=eef_delta_feature_names,
        AGIBOT_O10_GRIPPER_FEATURE_NAMES=gripper_feature_names,
        AGIBOT_O10_HAND_FEATURE_NAMES=hand_feature_names,
        AGIBOT_O10_POSE_FEATURE_NAMES=pose_feature_names,
        AgibotO10Hand=FakeAgibotO10Hand,
        agibot_o10_eef_absolute_pose_to_matrix=lambda eef_pose: np.eye(4),
        agibot_o10_gripper_value_from_hand_joints=lambda *args, **kwargs: 0.0,
        agibot_o10_hand_joints_from_gripper_value=lambda *args, **kwargs: [0.0] * len(hand_feature_names),
        agibot_o10_action_feature_types=lambda: {
            name: float for name in (*arm_feature_names, *hand_feature_names, *pose_feature_names)
        },
        agibot_o10_joint_action_feature_types=lambda: {
            name: float for name in (*arm_feature_names, *hand_feature_names)
        },
        agibot_o10_eef_absolute_action_feature_types=lambda: {
            name: float for name in (*pose_feature_names, *hand_feature_names)
        },
        agibot_o10_eef_absolute_gripper_action_feature_types=lambda: {
            name: float for name in (*pose_feature_names, *gripper_feature_names)
        },
        agibot_o10_eef_delta_action_feature_types=lambda: {
            name: float for name in (*eef_delta_feature_names, *hand_feature_names)
        },
        agibot_o10_gripper_action_feature_types=lambda: {
            name: float for name in (*arm_feature_names, *gripper_feature_names)
        },
        agibot_o10_eef_delta_gripper_action_feature_types=lambda: {
            name: float for name in (*eef_delta_feature_names, *gripper_feature_names)
        },
        agibot_o10_gripper_state_feature_types=lambda: {
            name: float for name in (*arm_feature_names, *gripper_feature_names)
        },
        build_agibot_o10_joint_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*arm_feature_names, *hand_feature_names), values, strict=True)
        },
        build_agibot_o10_eef_delta_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*eef_delta_feature_names, *hand_feature_names), values, strict=True)
        },
        build_agibot_o10_eef_absolute_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*pose_feature_names, *hand_feature_names), values, strict=True)
        },
        build_agibot_o10_gripper_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*arm_feature_names, *gripper_feature_names), values, strict=True)
        },
        build_agibot_o10_eef_delta_gripper_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*eef_delta_feature_names, *gripper_feature_names), values, strict=True)
        },
        build_agibot_o10_eef_absolute_gripper_action_dict=lambda values: {
            name: float(value)
            for name, value in zip((*pose_feature_names, *gripper_feature_names), values, strict=True)
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
        PersistentJointTargetStore=FakePersistentJointTargetStore,
        load_reset_poses=lambda *args, **kwargs: (None, None),
    )


def _load_single_arm_module(monkeypatch):
    _install_common_robot_stubs(monkeypatch)

    class FakePicoFollowerSingleArmAgibotO10Config:
        pass

    _install_stub_module(
        monkeypatch,
        "test_single_arm_robot_module.config_pico_follower_single_arm_agibot_o10",
        PicoFollowerSingleArmAgibotO10Config=FakePicoFollowerSingleArmAgibotO10Config,
    )

    spec = importlib.util.spec_from_file_location(
        "test_single_arm_robot_module",
        SINGLE_MODULE_PATH,
        submodule_search_locations=[str(SINGLE_MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_single_arm_robot_module"
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_dual_arm_module(monkeypatch):
    _install_common_robot_stubs(monkeypatch)

    class FakePicoFollowerDualArmAgibotO10Config:
        pass

    _install_stub_module(
        monkeypatch,
        "test_dual_arm_robot_module.config_pico_follower_dual_arm_agibot_o10",
        PicoFollowerDualArmAgibotO10Config=FakePicoFollowerDualArmAgibotO10Config,
    )

    spec = importlib.util.spec_from_file_location(
        "test_dual_arm_robot_module",
        DUAL_MODULE_PATH,
        submodule_search_locations=[str(DUAL_MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_dual_arm_robot_module"
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _ColorCamera:
    def __init__(self, reads):
        self._reads = list(reads)

    def async_read(self, timeout_ms=200):
        result = self._reads.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _TimeoutRecordingCamera:
    def __init__(self):
        self.timeout_ms_calls = []

    def async_read(self, timeout_ms=200):
        self.timeout_ms_calls.append(timeout_ms)
        raise TimeoutError("camera timeout")


class _SlowColorCamera:
    def __init__(self, value: int, sleep_s: float):
        self.value = value
        self.sleep_s = sleep_s

    def async_read(self, timeout_ms=200):
        time.sleep(self.sleep_s)
        return np.full((2, 4, 3), self.value, dtype=np.uint8)


class _ConnectCamera:
    def __init__(self, exc: Exception | None = None):
        self.exc = exc
        self.connected = False

    def connect(self):
        if self.exc is not None:
            raise self.exc
        self.connected = True

    def disconnect(self):
        self.connected = False


class _ShutdownArm:
    def __init__(self):
        self.disabled = False
        self.uninitialized = False

    def disable(self):
        self.disabled = True

    def uninit(self):
        self.uninitialized = True


class _DepthCamera:
    def __init__(self, reads):
        self._reads = list(reads)

    def async_read_color_and_depth(self, timeout_ms=200):
        result = self._reads.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_single_arm_camera_timeout_reuses_cached_depth_frames_when_allowed(monkeypatch):
    module = _load_single_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerSingleArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(
        include_eef_pose=False,
        tactile_mode="none",
        allow_camera_read_failures=True,
        cameras={"wrist": SimpleNamespace(height=2, width=3, use_depth=True)},
    )
    robot.hand = None
    robot.cameras = {
        "wrist": _DepthCamera(
            [
                (
                    np.full((2, 3, 3), 7, dtype=np.uint8),
                    np.arange(6, dtype=np.uint16).reshape(2, 3),
                ),
                TimeoutError("camera timeout"),
            ]
        )
    }
    robot.get_joint_pos = lambda: (
        [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
        [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
    )

    first_obs = robot.get_observation()
    second_obs = robot.get_observation()

    np.testing.assert_array_equal(first_obs["wrist"], second_obs["wrist"])
    np.testing.assert_array_equal(first_obs["wrist_depth"], second_obs["wrist_depth"])
    assert second_obs["wrist_depth"].shape == (2, 3, 1)
    assert second_obs["wrist_depth"].dtype == np.uint16


def test_single_arm_skips_camera_connect_failures_when_allowed(monkeypatch):
    good_camera = _ConnectCamera()
    bad_camera = _ConnectCamera(ConnectionError("missing wrist camera"))
    module = _load_single_arm_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "make_cameras_from_configs",
        lambda configs: {"top": good_camera, "wrist": bad_camera},
    )

    robot = module.PicoFollowerSingleArmAgibotO10(
        SimpleNamespace(
            port="can0",
            handedness="left",
            enable_hand=False,
            allow_camera_read_failures=True,
            channel_mode="multiChannel",
            device_id=1,
            canfd_id=0,
            channel_id=None,
            cameras={
                "top": SimpleNamespace(height=2, width=3, use_depth=False),
                "wrist": SimpleNamespace(height=2, width=3, use_depth=False),
            },
        )
    )

    assert robot.cameras == {"top": good_camera}
    assert good_camera.connected is True


def test_single_arm_camera_timeout_still_raises_when_fallback_is_disabled(monkeypatch):
    module = _load_single_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerSingleArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(
        include_eef_pose=False,
        tactile_mode="none",
        allow_camera_read_failures=False,
        cameras={"top": SimpleNamespace(height=2, width=3, use_depth=False)},
    )
    robot.hand = None
    robot.cameras = {"top": _ColorCamera([TimeoutError("camera timeout")])}
    robot.get_joint_pos = lambda: (
        [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
        [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
    )

    with pytest.raises(TimeoutError, match="camera timeout"):
        robot.get_observation()


def test_single_arm_camera_reads_run_in_parallel(monkeypatch):
    module = _load_single_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerSingleArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(
        include_eef_pose=False,
        tactile_mode="none",
        allow_camera_read_failures=True,
        camera_read_timeout_ms=100,
        cameras={
            "top": SimpleNamespace(height=2, width=4, use_depth=False),
            "wrist": SimpleNamespace(height=2, width=4, use_depth=False),
        },
    )
    robot.hand = None
    robot.cameras = {
        "top": _SlowColorCamera(1, 0.05),
        "wrist": _SlowColorCamera(2, 0.05),
    }
    robot.get_joint_pos = lambda: (
        [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
        [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
    )

    start = time.perf_counter()
    obs = robot.get_observation()
    elapsed_s = time.perf_counter() - start

    assert elapsed_s < 0.09
    assert int(obs["top"][0, 0, 0]) == 1
    assert int(obs["wrist"][0, 0, 0]) == 2


def test_single_arm_safe_shutdown_disconnects_connected_cameras(monkeypatch):
    module = _load_single_arm_module(monkeypatch)
    camera = _ConnectCamera()
    camera.connect()
    robot = object.__new__(module.PicoFollowerSingleArmAgibotO10)
    robot.arm = _ShutdownArm()
    robot.hand = None
    robot.cameras = {"top": camera}

    robot._safe_shutdown()

    assert camera.connected is False
    assert robot.arm.disabled is True
    assert robot.arm.uninitialized is True


def test_single_arm_return_zero_times_out_instead_of_looping_forever(monkeypatch, caplog):
    module = _load_single_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerSingleArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(
        enable_hand=False,
        arm_joints_num=7,
        reset_timeout_s=0.01,
    )
    robot.arm = _NeverArrivingArm()
    robot.hand = None
    robot.reset_arm_joint_pos = [0.0] * 6
    robot.reset_hand_joint_pos = [0.0] * 10

    with caplog.at_level("WARNING"):
        robot.return_zero()

    assert robot.arm.pvt_calls > 0
    assert "Timed out resetting Agibot O10" in caplog.text


def test_dual_arm_skips_camera_connect_failures_when_allowed(monkeypatch):
    good_camera = _ConnectCamera()
    bad_camera = _ConnectCamera(ConnectionError("missing wrist camera"))
    module = _load_dual_arm_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "make_cameras_from_configs",
        lambda configs: {"top": good_camera, "wrist": bad_camera},
    )

    robot = module.PicoFollowerDualArmAgibotO10(
        SimpleNamespace(
            left={"port": "can0", "handedness": "left"},
            right={"port": "can1", "handedness": "right"},
            enable_hand=False,
            allow_camera_read_failures=True,
            include_eef_pose=False,
            tactile_mode="none",
            arm_joints_num=7,
            cameras={
                "top": SimpleNamespace(height=2, width=3, use_depth=False),
                "wrist": SimpleNamespace(height=2, width=3, use_depth=False),
            },
        )
    )

    robot.connect()

    assert robot.cameras == {"top": good_camera}
    assert good_camera.connected is True
    assert bad_camera.connected is False


def test_dual_arm_camera_timeout_returns_zero_frame_when_allowed(monkeypatch):
    module = _load_dual_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(
        include_eef_pose=False,
        tactile_mode="none",
        enable_hand=False,
        allow_camera_read_failures=True,
        cameras={"top": SimpleNamespace(height=2, width=4, use_depth=False)},
    )
    robot.cameras = {"top": _ColorCamera([TimeoutError("camera timeout")])}
    robot.get_joint_pos = lambda: {
        "left": [
            [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
            [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
        ],
        "right": [
            [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
            [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
        ],
    }

    obs = robot.get_observation()

    assert obs["top"].shape == (2, 4, 3)
    assert obs["top"].dtype == np.uint8
    assert np.count_nonzero(obs["top"]) == 0


def test_dual_arm_camera_fallback_uses_short_configured_read_timeout(monkeypatch):
    module = _load_dual_arm_module(monkeypatch)
    camera = _TimeoutRecordingCamera()
    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(
        include_eef_pose=False,
        tactile_mode="none",
        enable_hand=False,
        allow_camera_read_failures=True,
        camera_read_timeout_ms=35,
        cameras={"top": SimpleNamespace(height=2, width=4, use_depth=False)},
    )
    robot.cameras = {"top": camera}
    robot.get_joint_pos = lambda: {
        "left": [
            [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
            [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
        ],
        "right": [
            [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
            [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
        ],
    }

    robot.get_observation()

    assert camera.timeout_ms_calls == [35]


def test_dual_arm_camera_reads_run_in_parallel(monkeypatch):
    module = _load_dual_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(
        include_eef_pose=False,
        tactile_mode="none",
        enable_hand=False,
        allow_camera_read_failures=True,
        camera_read_timeout_ms=100,
        cameras={
            "top": SimpleNamespace(height=2, width=4, use_depth=False),
            "left_wrist": SimpleNamespace(height=2, width=4, use_depth=False),
            "right_wrist": SimpleNamespace(height=2, width=4, use_depth=False),
        },
    )
    robot.cameras = {
        "top": _SlowColorCamera(1, 0.05),
        "left_wrist": _SlowColorCamera(2, 0.05),
        "right_wrist": _SlowColorCamera(3, 0.05),
    }
    robot.get_joint_pos = lambda: {
        "left": [
            [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
            [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
        ],
        "right": [
            [0.0] * len(module.AGIBOT_O10_ARM_FEATURE_NAMES),
            [0.0] * len(module.AGIBOT_O10_HAND_FEATURE_NAMES),
        ],
    }

    start = time.perf_counter()
    obs = robot.get_observation()
    elapsed_s = time.perf_counter() - start

    assert elapsed_s < 0.11
    assert int(obs["top"][0, 0, 0]) == 1
    assert int(obs["left_wrist"][0, 0, 0]) == 2
    assert int(obs["right_wrist"][0, 0, 0]) == 3


class _NeverArrivingArm:
    def __init__(self):
        self.pvt_calls = 0

    def state(self):
        return SimpleNamespace(pos=[1.0] * 6)

    def pvt(self, *args, **kwargs):
        self.pvt_calls += 1


def test_dual_arm_return_zero_times_out_instead_of_looping_forever(monkeypatch, caplog):
    module = _load_dual_arm_module(monkeypatch)
    robot = object.__new__(module.PicoFollowerDualArmAgibotO10)
    robot._is_connected = True
    robot.config = SimpleNamespace(
        enable_hand=False,
        arm_joints_num=7,
        reset_timeout_s=0.01,
    )
    robot.left_arm = _NeverArrivingArm()
    robot.right_arm = _NeverArrivingArm()
    robot.left_reset_arm_joint_pos = [0.0] * 6
    robot.right_reset_arm_joint_pos = [0.0] * 6
    robot.left_reset_hand_joint_pos = [0.0] * 10
    robot.right_reset_hand_joint_pos = [0.0] * 10

    with caplog.at_level("WARNING"):
        robot.return_zero()

    assert robot.left_arm.pvt_calls > 0
    assert robot.right_arm.pvt_calls > 0
    assert "Timed out resetting dual-arm O10" in caplog.text
