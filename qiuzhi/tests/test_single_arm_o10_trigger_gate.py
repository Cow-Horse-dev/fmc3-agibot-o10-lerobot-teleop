import importlib.util
import sys
import types
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
EEF_MODULE_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "teleoperators"
    / "pico_leader_single_arm_eef"
    / "pico_leader_single_arm_eef.py"
)
AGIBOT_MODULE_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "teleoperators"
    / "pico_leader_single_arm_agibot_o10"
    / "pico_leader_single_arm_agibot_o10.py"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


def _install_stub_module(monkeypatch, name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_single_arm_eef_module(monkeypatch):
    class FakeTeleoperator:
        def __init__(self, config):
            self.config = config

    class FakePicoLeaderSingleArmEEFConfig:
        pass

    class FakeOnlineVariableStepLPF:
        def __init__(self, *args, **kwargs):
            self.value = 0.0

        def sample(self, now):
            return self.value

        def update(self, now, value):
            self.value = value

    class FakeArmKdlNumerical:
        def __init__(self, *args, **kwargs):
            pass

    class FakeUdexrealTeleoperator:
        def __init__(self, *args, **kwargs):
            pass

    class FakeRotation:
        @staticmethod
        def from_matrix(matrix):
            return types.SimpleNamespace(as_quat=lambda: [0.0, 0.0, 0.0, 1.0])

    _install_stub_module(
        monkeypatch,
        "airbot_hardware_py",
    )
    _install_stub_module(
        monkeypatch,
        "airbot_state_machine",
        robotic_arm=object(),
    )
    _install_stub_module(
        monkeypatch,
        "lerobot.cameras.utils",
        make_cameras_from_configs=lambda configs: {},
    )
    _install_stub_module(
        monkeypatch,
        "lerobot.utils.errors",
        DeviceAlreadyConnectedError=RuntimeError,
        DeviceNotConnectedError=RuntimeError,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play._compat",
        Teleoperator=FakeTeleoperator,
        preload_lerobot_processor=lambda: None,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef",
        pico_webrtc=types.SimpleNamespace(__file__="/tmp/pico_webrtc.py"),
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.config_pico_leader_single_arm_eef",
        PicoLeaderSingleArmEEFConfig=FakePicoLeaderSingleArmEEFConfig,
    )
    _install_stub_module(
        monkeypatch,
        "pkg_resources",
    )
    _install_stub_module(
        monkeypatch,
        "zmq",
    )
    _install_stub_module(
        monkeypatch,
        "test_single_arm_eef_module.lpf",
        OnlineVariableStepLPF=FakeOnlineVariableStepLPF,
    )
    _install_stub_module(
        monkeypatch,
        "test_single_arm_eef_module.udexreal_hand",
        UdexrealTeleoperator=FakeUdexrealTeleoperator,
    )
    _install_stub_module(
        monkeypatch,
        "mmk2_kdl_py",
        ArmKdlNumerical=FakeArmKdlNumerical,
    )
    _install_stub_module(
        monkeypatch,
        "scipy",
    )
    _install_stub_module(
        monkeypatch,
        "scipy.spatial",
    )
    _install_stub_module(
        monkeypatch,
        "scipy.spatial.transform",
        Rotation=FakeRotation,
    )

    spec = importlib.util.spec_from_file_location(
        "test_single_arm_eef_module",
        EEF_MODULE_PATH,
        submodule_search_locations=[str(EEF_MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_single_arm_eef_module"
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_single_arm_agibot_module(monkeypatch):
    parent_module = _load_single_arm_eef_module(monkeypatch)

    class FakeAgibotO10GloveTeleoperator:
        def __init__(self, *args, **kwargs):
            pass

    class FakePersistentJointTargetStore:
        def __init__(self, *args, **kwargs):
            pass

        def normalize(self, joint_pos):
            return list(joint_pos)

    class FakePicoLeaderSingleArmAgibotO10Config:
        pass

    def _fake_load_reset_poses(path, side, gesture):
        return [], []

    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.pico_leader_single_arm_eef",
        PicoLeaderSingleArmEEF=parent_module.PicoLeaderSingleArmEEF,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.utils.joint_target_store",
        PersistentJointTargetStore=FakePersistentJointTargetStore,
        load_reset_poses=_fake_load_reset_poses,
    )
    _install_stub_module(
        monkeypatch,
        "test_single_arm_agibot_module.agibot_o10_hand",
        AgibotO10GloveTeleoperator=FakeAgibotO10GloveTeleoperator,
    )
    _install_stub_module(
        monkeypatch,
        "test_single_arm_agibot_module.config_pico_leader_single_arm_agibot_o10",
        PicoLeaderSingleArmAgibotO10Config=FakePicoLeaderSingleArmAgibotO10Config,
    )

    spec = importlib.util.spec_from_file_location(
        "test_single_arm_agibot_module",
        AGIBOT_MODULE_PATH,
        submodule_search_locations=[str(AGIBOT_MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_single_arm_agibot_module"
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _OneLoopStopEvent:
    def __init__(self):
        self._checks = 0

    def is_set(self):
        self._checks += 1
        return self._checks >= 3


class _NoopPauseEvent:
    def wait(self):
        return None


def _build_ctrl(**overrides):
    ctrl = {
        "A": False,
        "B": False,
        "X": False,
        "Y": False,
        "LTr": False,
        "RTr": False,
        "LG": False,
        "RG": False,
        "leftGrip": 0.0,
        "rightGrip": 0.0,
    }
    ctrl.update(overrides)
    return ctrl


def test_default_pose_treats_zero_norm_quaternion_as_invalid(monkeypatch):
    module = _load_single_arm_eef_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderSingleArmEEF)

    assert teleop._is_default_pose([0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 0.0]) is True


def _make_single_arm_eef_teleop(
    module,
    handedness: str,
    *,
    controller_side: str | None = None,
    wrist_pose_source: str | None = None,
    startflag: bool,
    ctrl: dict,
):
    teleop = object.__new__(module.PicoLeaderSingleArmEEF)
    teleop.stop_event = _OneLoopStopEvent()
    teleop.pause_event = _NoopPauseEvent()
    teleop._is_connected = True
    teleop.handedness = handedness
    teleop.controller_side = controller_side or handedness
    teleop.wrist_pose_source = wrist_pose_source or "auto"
    teleop.ctrl = ctrl
    teleop.startflag = startflag
    teleop.pose = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    teleop.active_pose_source = handedness
    teleop._last_default_pose_warning_time = 0.0
    teleop.arm_init = False
    teleop.reset_pose = lambda: None
    teleop._is_default_pose = lambda pose: True
    return teleop


@pytest.mark.parametrize(
    ("handedness", "controller_side", "matching_start_button", "opposite_start_button"),
    [
        ("left", "left", "X", "A"),
        ("right", "right", "A", "X"),
        ("left", "right", "A", "X"),
        ("right", "left", "X", "A"),
    ],
)
def test_single_arm_start_button_uses_controller_side(
    monkeypatch, handedness, controller_side, matching_start_button, opposite_start_button
):
    module = _load_single_arm_eef_module(monkeypatch)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    matching_teleop = _make_single_arm_eef_teleop(
        module,
        handedness,
        controller_side=controller_side,
        startflag=False,
        ctrl=_build_ctrl(**{matching_start_button: True}),
    )
    matching_teleop.handle_pose_data()
    assert matching_teleop.startflag is True

    opposite_teleop = _make_single_arm_eef_teleop(
        module,
        handedness,
        controller_side=controller_side,
        startflag=False,
        ctrl=_build_ctrl(**{opposite_start_button: True}),
    )
    opposite_teleop.handle_pose_data()
    assert opposite_teleop.startflag is False


@pytest.mark.parametrize(
    ("handedness", "controller_side", "matching_reset_button", "opposite_reset_button"),
    [
        ("left", "left", "Y", "B"),
        ("right", "right", "B", "Y"),
        ("left", "right", "B", "Y"),
        ("right", "left", "Y", "B"),
    ],
)
def test_single_arm_reset_button_uses_controller_side(
    monkeypatch, handedness, controller_side, matching_reset_button, opposite_reset_button
):
    module = _load_single_arm_eef_module(monkeypatch)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    matching_reset_calls = {"count": 0}
    matching_teleop = _make_single_arm_eef_teleop(
        module,
        handedness,
        controller_side=controller_side,
        startflag=True,
        ctrl=_build_ctrl(**{matching_reset_button: True}),
    )
    matching_teleop.reset_pose = lambda: matching_reset_calls.__setitem__(
        "count", matching_reset_calls["count"] + 1
    )
    matching_teleop.handle_pose_data()
    assert matching_teleop.startflag is False
    assert matching_reset_calls["count"] == 1

    opposite_reset_calls = {"count": 0}
    opposite_teleop = _make_single_arm_eef_teleop(
        module,
        handedness,
        controller_side=controller_side,
        startflag=True,
        ctrl=_build_ctrl(**{opposite_reset_button: True}),
    )
    opposite_teleop.reset_pose = lambda: opposite_reset_calls.__setitem__(
        "count", opposite_reset_calls["count"] + 1
    )
    opposite_teleop.handle_pose_data()
    assert opposite_teleop.startflag is True
    assert opposite_reset_calls["count"] == 0


@pytest.mark.parametrize(
    ("handedness", "controller_side", "matching_trigger", "opposite_trigger"),
    [
        ("left", "left", "LTr", "RTr"),
        ("right", "right", "RTr", "LTr"),
        ("left", "right", "RTr", "LTr"),
        ("right", "left", "LTr", "RTr"),
    ],
)
def test_single_arm_arm_control_requires_controller_side_trigger_gate(
    monkeypatch, handedness, controller_side, matching_trigger, opposite_trigger
):
    module = _load_single_arm_eef_module(monkeypatch)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    opposite_trigger_called = {"value": False}
    opposite_teleop = _make_single_arm_eef_teleop(
        module,
        handedness,
        controller_side=controller_side,
        startflag=True,
        ctrl=_build_ctrl(**{opposite_trigger: True}),
    )
    opposite_teleop._is_default_pose = (
        lambda pose: opposite_trigger_called.__setitem__("value", True) or True
    )
    opposite_teleop.handle_pose_data()
    assert opposite_trigger_called["value"] is False

    matching_trigger_called = {"value": False}
    matching_teleop = _make_single_arm_eef_teleop(
        module,
        handedness,
        controller_side=controller_side,
        startflag=True,
        ctrl=_build_ctrl(**{matching_trigger: True}),
    )
    matching_teleop._is_default_pose = (
        lambda pose: matching_trigger_called.__setitem__("value", True) or True
    )
    matching_teleop.handle_pose_data()
    assert matching_trigger_called["value"] is True


@pytest.mark.parametrize(
    ("handedness", "controller_side", "matching_trigger", "opposite_trigger"),
    [
        ("left", "left", "LTr", "RTr"),
        ("right", "right", "RTr", "LTr"),
        ("left", "right", "RTr", "LTr"),
        ("right", "left", "LTr", "RTr"),
    ],
)
def test_single_arm_hand_control_requires_controller_side_trigger_gate(
    monkeypatch, handedness, controller_side, matching_trigger, opposite_trigger
):
    module = _load_single_arm_agibot_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderSingleArmAgibotO10)
    teleop.handedness = handedness
    teleop.controller_side = controller_side
    teleop.startflag = True
    teleop.ctrl = _build_ctrl(**{opposite_trigger: True})

    assert teleop._is_hand_control_enabled() is False

    teleop.ctrl = _build_ctrl(**{matching_trigger: True})
    assert teleop._is_hand_control_enabled() is True


def test_single_arm_trigger_gesture_accepts_cylindrical(monkeypatch):
    module = _load_single_arm_agibot_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderSingleArmAgibotO10)
    teleop.handedness = "right"
    teleop.config = types.SimpleNamespace(
        trigger_gesture="cylindrical",
        reset_poses_path=None,
    )

    assert teleop._get_trigger_gesture_hand_pos("open") == pytest.approx(
        [0.03, -1.51, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
    assert teleop._get_trigger_gesture_hand_pos("closed") == pytest.approx(
        [0.03, -1.51, 0.7, 0.0, 0.7, 0.7, 0.0, 0.7, 0.0, 0.7]
    )


@pytest.mark.parametrize(
    ("handedness", "controller_side", "wrist_pose_source", "matching_grip", "matching_grip_axis", "opposite_grip", "opposite_grip_axis"),
    [
        ("left", "right", "left", "LG", "leftGrip", "RG", "rightGrip"),
        ("right", "left", "right", "RG", "rightGrip", "LG", "leftGrip"),
    ],
)
def test_single_arm_trigger_gesture_grasp_uses_wrist_pose_source(
    monkeypatch,
    handedness,
    controller_side,
    wrist_pose_source,
    matching_grip,
    matching_grip_axis,
    opposite_grip,
    opposite_grip_axis,
):
    module = _load_single_arm_agibot_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderSingleArmAgibotO10)
    teleop.handedness = handedness
    teleop.controller_side = controller_side
    teleop.wrist_pose_source = wrist_pose_source

    teleop.ctrl = _build_ctrl(**{opposite_grip: True})
    assert teleop._is_trigger_gesture_grasp_pressed() is False

    teleop.ctrl = _build_ctrl(**{opposite_grip_axis: 1.0})
    assert teleop._is_trigger_gesture_grasp_pressed() is False

    teleop.ctrl = _build_ctrl(**{matching_grip: True})
    assert teleop._is_trigger_gesture_grasp_pressed() is True

    teleop.ctrl = _build_ctrl(**{matching_grip_axis: 0.2})
    assert teleop._is_trigger_gesture_grasp_pressed() is True
