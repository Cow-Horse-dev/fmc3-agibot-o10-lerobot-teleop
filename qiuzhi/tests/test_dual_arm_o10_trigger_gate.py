import importlib.util
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
MODULE_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "teleoperators"
    / "pico_leader_dual_arm_agibot_o10"
    / "pico_leader_dual_arm_agibot_o10.py"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


def _install_stub_module(monkeypatch, name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _trigger_gesture_hand_pos(gesture_name: str, handedness: str, state_key: str) -> list[float]:
    from lerobot_play.utils.o10_hand_control import trigger_gesture_hand_pos

    return trigger_gesture_hand_pos(None, gesture_name, handedness, state_key)


def _gripper_value_to_hand_joints(
    gripper_value: float,
    gesture_name: str,
    handedness: str,
) -> list[float]:
    from lerobot_play.utils.o10_hand_control import gripper_value_to_hand_joints

    return gripper_value_to_hand_joints(gripper_value, gesture_name, handedness)


def _load_dual_arm_module(monkeypatch):
    class FakeArmKdlNumerical:
        def __init__(self, *args, **kwargs):
            pass

    class FakePicoLeaderSingleArmEEF:
        pass

    class FakeOnlineVariableStepLPF:
        def __init__(self, *args, **kwargs):
            self.value = 0.0

        def sample(self, now):
            return self.value

        def update(self, now, value):
            self.value = value

    class FakeAgibotO10GloveTeleoperator:
        pass

    class FakePersistentJointTargetStore:
        pass

    class FakePicoLeaderDualArmAgibotO10Config:
        pass

    _install_stub_module(
        monkeypatch,
        "mmk2_kdl_py",
        ArmKdlNumerical=FakeArmKdlNumerical,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.pico_leader_single_arm_eef",
        PicoLeaderSingleArmEEF=FakePicoLeaderSingleArmEEF,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.lpf",
        OnlineVariableStepLPF=FakeOnlineVariableStepLPF,
    )
    _install_stub_module(
        monkeypatch,
        "lerobot_play.teleoperators.pico_leader_single_arm_agibot_o10.agibot_o10_hand",
        AgibotO10GloveTeleoperator=FakeAgibotO10GloveTeleoperator,
    )
    def _fake_load_reset_poses(path, side, gesture):
        return [], []

    _install_stub_module(
        monkeypatch,
        "lerobot_play.utils.joint_target_store",
        PersistentJointTargetStore=FakePersistentJointTargetStore,
        load_reset_poses=_fake_load_reset_poses,
    )
    _install_stub_module(
        monkeypatch,
        "test_dual_arm_config_module",
        PicoLeaderDualArmAgibotO10Config=FakePicoLeaderDualArmAgibotO10Config,
    )

    spec = importlib.util.spec_from_file_location(
        "test_dual_arm_o10_trigger_gate_module",
        MODULE_PATH,
        submodule_search_locations=[str(MODULE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "test_dual_arm_o10_trigger_gate_module"
    monkeypatch.setitem(
        sys.modules,
        "test_dual_arm_o10_trigger_gate_module.config_pico_leader_dual_arm_agibot_o10",
        sys.modules["test_dual_arm_config_module"],
    )
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("side", ["left", "right"])
def test_trigger_gesture_hand_requires_left_trigger_in_left_mode(monkeypatch, side):
    module = _load_dual_arm_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.config = SimpleNamespace(
        hand_mode="trigger_gesture",
        trigger_gesture="pinch",
        arm_trigger_mode="left",
    )
    teleop.startflag = True
    teleop.ctrl = {
        "LTr": False,
        "RTr": False,
        "LG": True,
        "RG": True,
        "leftGrip": 0.0,
        "rightGrip": 0.0,
    }
    teleop.left_lpfs = [SimpleNamespace(sample=lambda now: 0.0) for _ in range(6)]
    teleop.right_lpfs = [SimpleNamespace(sample=lambda now: 0.0) for _ in range(6)]
    teleop.left_hand_teleoperator = None
    teleop.right_hand_teleoperator = None
    open_state = _trigger_gesture_hand_pos(
        "pinch",
        side,
        "open",
    )
    setattr(teleop, f"{side}_commanded_hand_joint_pos", open_state.copy())
    setattr(teleop, f"{side}_hand_state_lock", None)
    teleop._get_commanded_hand_joint_pos = (
        lambda requested_side: getattr(teleop, f"{requested_side}_commanded_hand_joint_pos").copy()
    )
    teleop._set_commanded_hand_joint_pos = (
        lambda requested_side, joint_pos: setattr(
            teleop,
            f"{requested_side}_commanded_hand_joint_pos",
            joint_pos.copy(),
        )
    )

    disabled_state = teleop._get_side_joint_pos(side)
    assert disabled_state[6:] == pytest.approx(open_state)

    teleop.ctrl["LTr"] = True
    enabled_state = teleop._get_side_joint_pos(side)
    expected_closed = _trigger_gesture_hand_pos(
        "pinch",
        side,
        "closed",
    )
    assert enabled_state[6:] == pytest.approx(expected_closed)


@pytest.mark.parametrize("side", ["left", "right"])
def test_arm_control_still_requires_left_trigger_in_left_mode(monkeypatch, side):
    module = _load_dual_arm_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.config = SimpleNamespace(
        hand_mode="trigger_gesture",
        trigger_gesture="pinch",
        arm_trigger_mode="left",
    )
    teleop.startflag = True
    teleop.ctrl = {
        "LTr": False,
        "RTr": True,
    }

    assert teleop._is_arm_control_enabled(side) is False

    teleop.ctrl["LTr"] = True
    assert teleop._is_arm_control_enabled(side) is True


def test_split_mode_maps_left_trigger_to_left_arm_and_right_trigger_to_right_arm(monkeypatch):
    module = _load_dual_arm_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.config = SimpleNamespace(
        hand_mode="trigger_gesture",
        trigger_gesture="pinch",
        arm_trigger_mode="split",
    )
    teleop.startflag = True
    teleop.ctrl = {
        "LTr": True,
        "RTr": False,
    }

    assert teleop._is_arm_control_enabled("left") is True
    assert teleop._is_arm_control_enabled("right") is False

    teleop.ctrl = {
        "LTr": False,
        "RTr": True,
    }
    assert teleop._is_arm_control_enabled("left") is False
    assert teleop._is_arm_control_enabled("right") is True


@pytest.mark.parametrize(
    ("left_trigger", "right_trigger", "expected"),
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, True),
    ],
)
def test_both_mode_requires_both_triggers(monkeypatch, left_trigger, right_trigger, expected):
    module = _load_dual_arm_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.config = SimpleNamespace(
        hand_mode="trigger_gesture",
        trigger_gesture="pinch",
        arm_trigger_mode="both",
    )
    teleop.startflag = True
    teleop.ctrl = {
        "LTr": left_trigger,
        "RTr": right_trigger,
    }

    assert teleop._is_arm_control_enabled("left") is expected
    assert teleop._is_arm_control_enabled("right") is expected


@pytest.mark.parametrize("side", ["left", "right"])
def test_trigger_gesture_grip_button_forces_closed_pose(monkeypatch, side):
    module = _load_dual_arm_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.config = SimpleNamespace(
        hand_mode="trigger_gesture",
        trigger_gesture="pinch",
        arm_trigger_mode="left",
    )
    teleop.startflag = True
    teleop.ctrl = {
        "LTr": True,
        "RTr": False,
        "LG": False,
        "RG": False,
        "leftGrip": 0.0,
        "rightGrip": 0.0,
    }
    teleop.left_lpfs = [SimpleNamespace(sample=lambda now: 0.0) for _ in range(6)]
    teleop.right_lpfs = [SimpleNamespace(sample=lambda now: 0.0) for _ in range(6)]
    teleop.left_hand_teleoperator = None
    teleop.right_hand_teleoperator = None
    setattr(
        teleop,
        f"{side}_commanded_hand_joint_pos",
        _trigger_gesture_hand_pos("pinch", side, "open"),
    )
    teleop._get_commanded_hand_joint_pos = (
        lambda requested_side: getattr(teleop, f"{requested_side}_commanded_hand_joint_pos").copy()
    )
    teleop._set_commanded_hand_joint_pos = (
        lambda requested_side, joint_pos: setattr(
            teleop,
            f"{requested_side}_commanded_hand_joint_pos",
            joint_pos.copy(),
        )
    )

    button_key = "LG" if side == "left" else "RG"
    teleop.ctrl[button_key] = True

    state = teleop._get_side_joint_pos(side)
    expected_closed = _trigger_gesture_hand_pos(
        "pinch",
        side,
        "closed",
    )
    assert state[6:] == pytest.approx(expected_closed)


def test_space_key_closes_left_cylindrical_grasp(monkeypatch):
    module = _load_dual_arm_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.config = SimpleNamespace(
        hand_mode="trigger_gesture",
        trigger_gesture="pinch",
        arm_trigger_mode="split",
        left={"trigger_gesture": "cylindrical"},
        right={"trigger_gesture": "pinch"},
    )
    teleop.startflag = True
    teleop.ctrl = {
        "LTr": True,
        "RTr": False,
        "LG": False,
        "RG": False,
        "leftGrip": 0.0,
        "rightGrip": 0.0,
    }
    teleop.left_lpfs = [SimpleNamespace(sample=lambda now: 0.0) for _ in range(6)]
    teleop.left_hand_teleoperator = None

    open_cylindrical_grasp = _trigger_gesture_hand_pos(
        "cylindrical",
        "left",
        "open",
    )
    teleop.left_commanded_hand_joint_pos = open_cylindrical_grasp.copy()
    teleop._get_commanded_hand_joint_pos = (
        lambda requested_side: getattr(teleop, f"{requested_side}_commanded_hand_joint_pos").copy()
    )
    teleop._set_commanded_hand_joint_pos = (
        lambda requested_side, joint_pos: setattr(
            teleop,
            f"{requested_side}_commanded_hand_joint_pos",
            joint_pos.copy(),
        )
    )

    open_state = teleop._get_side_joint_pos("left")
    assert open_state[6:] == pytest.approx(open_cylindrical_grasp)

    space_key = object()

    def on_press(key):
        if key is space_key:
            teleop.ctrl["leftGrip"] = 1.0

    keyboard_listener = SimpleNamespace(on_press=on_press)
    keyboard_listener.on_press(space_key)

    closed_state = teleop._get_side_joint_pos("left")
    expected_closed_cylindrical_grasp = _trigger_gesture_hand_pos(
        "cylindrical",
        "left",
        "closed",
    )
    assert closed_state[6:] == pytest.approx(expected_closed_cylindrical_grasp)


@pytest.mark.parametrize("side", ["left", "right"])
def test_trigger_gesture_grip_axis_sets_continuous_gripper_value(monkeypatch, side):
    module = _load_dual_arm_module(monkeypatch)
    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.config = SimpleNamespace(
        hand_mode="trigger_gesture",
        trigger_gesture="pinch",
        arm_trigger_mode="left",
    )
    teleop.startflag = True
    teleop.ctrl = {
        "LTr": True,
        "RTr": False,
        "LG": False,
        "RG": False,
        "leftGrip": 0.0,
        "rightGrip": 0.0,
    }
    teleop.left_lpfs = [SimpleNamespace(sample=lambda now: 0.0) for _ in range(6)]
    teleop.right_lpfs = [SimpleNamespace(sample=lambda now: 0.0) for _ in range(6)]
    teleop.left_hand_teleoperator = None
    teleop.right_hand_teleoperator = None
    setattr(
        teleop,
        f"{side}_commanded_hand_joint_pos",
        _trigger_gesture_hand_pos("pinch", side, "open"),
    )
    teleop._get_commanded_hand_joint_pos = (
        lambda requested_side: getattr(teleop, f"{requested_side}_commanded_hand_joint_pos").copy()
    )
    teleop._set_commanded_hand_joint_pos = (
        lambda requested_side, joint_pos: setattr(
            teleop,
            f"{requested_side}_commanded_hand_joint_pos",
            joint_pos.copy(),
        )
    )

    grip_key = "leftGrip" if side == "left" else "rightGrip"
    teleop.ctrl[grip_key] = 0.5

    state = teleop._get_side_joint_pos(side)
    expected_half_closed = _gripper_value_to_hand_joints(
        0.5,
        "pinch",
        side,
    )
    assert state[6:] == pytest.approx(expected_half_closed)


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
    }
    ctrl.update(overrides)
    return ctrl


def _make_dual_arm_teleop(module, *, startflag: bool, ctrl: dict):
    teleop = object.__new__(module.PicoLeaderDualArmAgibotO10)
    teleop.stop_event = _OneLoopStopEvent()
    teleop.pause_event = _NoopPauseEvent()
    teleop.is_connected = True
    teleop.config = SimpleNamespace(arm_trigger_mode="left")
    teleop.ctrl = ctrl
    teleop.startflag = startflag
    teleop.left_info = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    teleop.right_info = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    teleop.reset_pose = lambda: None
    teleop._control_arm_with_wrist = lambda side, pose_info: None
    return teleop


def test_dual_arm_enable_reset_buttons_use_left_controller_xy(monkeypatch):
    module = _load_dual_arm_module(monkeypatch)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    start_teleop = _make_dual_arm_teleop(
        module,
        startflag=False,
        ctrl=_build_ctrl(X=True, A=True),
    )
    start_teleop.handle_pose_data()
    assert start_teleop.startflag is True

    ignored_start_teleop = _make_dual_arm_teleop(
        module,
        startflag=False,
        ctrl=_build_ctrl(A=True),
    )
    ignored_start_teleop.handle_pose_data()
    assert ignored_start_teleop.startflag is False

    reset_calls = {"count": 0}
    reset_teleop = _make_dual_arm_teleop(
        module,
        startflag=True,
        ctrl=_build_ctrl(Y=True, B=True),
    )
    reset_teleop.reset_pose = lambda: reset_calls.__setitem__(
        "count", reset_calls["count"] + 1
    )
    reset_teleop.handle_pose_data()
    assert reset_teleop.startflag is False
    assert reset_calls["count"] == 1

    ignored_reset_calls = {"count": 0}
    ignored_reset_teleop = _make_dual_arm_teleop(
        module,
        startflag=True,
        ctrl=_build_ctrl(B=True),
    )
    ignored_reset_teleop.reset_pose = lambda: ignored_reset_calls.__setitem__(
        "count", ignored_reset_calls["count"] + 1
    )
    ignored_reset_teleop.handle_pose_data()
    assert ignored_reset_teleop.startflag is True
    assert ignored_reset_calls["count"] == 0
