import importlib
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch


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


def _install_global_hardware_stubs() -> None:
    if "airbot_hardware_py" not in sys.modules:
        fake_airbot = types.ModuleType("airbot_hardware_py")
        fake_airbot.MotorType = SimpleNamespace(OD=1, DM=2, NA=3)
        fake_airbot.EEFType = SimpleNamespace(NA=0)
        fake_airbot.MotorControlMode = SimpleNamespace(PVT=1)
        fake_airbot.Play = SimpleNamespace(create=lambda *args, **kwargs: object())
        fake_airbot.create_asio_executor = lambda *_args, **_kwargs: SimpleNamespace(
            get_io_context=lambda: object()
        )
        sys.modules["airbot_hardware_py"] = fake_airbot

    if "mmk2_kdl_py" not in sys.modules:
        fake_kdl_module = types.ModuleType("mmk2_kdl_py")

        class FakeArmKdlNumerical:
            def __init__(self, *args, **kwargs):
                pass

        fake_kdl_module.ArmKdlNumerical = FakeArmKdlNumerical
        sys.modules["mmk2_kdl_py"] = fake_kdl_module


_install_global_hardware_stubs()

if "mcap" not in sys.modules:
    fake_mcap = types.ModuleType("mcap")
    fake_mcap_writer = types.ModuleType("mcap.writer")
    fake_mcap_writer.Writer = object
    fake_mcap_reader = types.ModuleType("mcap.reader")
    fake_mcap_reader.make_reader = lambda *args, **kwargs: None
    sys.modules["mcap"] = fake_mcap
    sys.modules["mcap.writer"] = fake_mcap_writer
    sys.modules["mcap.reader"] = fake_mcap_reader

from lerobot_play.utils.agibot_o10 import AGIBOT_O10_HAND_FEATURE_NAMES
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore


def _import_o10_robot_module(monkeypatch: pytest.MonkeyPatch):
    fake_airbot = types.ModuleType("airbot_hardware_py")
    fake_airbot.MotorType = SimpleNamespace(OD=1, DM=2, NA=3)
    fake_airbot.EEFType = SimpleNamespace(NA=0)
    fake_airbot.MotorControlMode = SimpleNamespace(PVT=1)
    fake_airbot.Play = SimpleNamespace(create=lambda *args, **kwargs: object())
    fake_airbot.create_asio_executor = lambda *_args, **_kwargs: SimpleNamespace(
        get_io_context=lambda: object()
    )

    fake_kdl_module = types.ModuleType("mmk2_kdl_py")

    class FakeArmKdlNumerical:
        def __init__(self, *args, **kwargs):
            pass

    fake_kdl_module.ArmKdlNumerical = FakeArmKdlNumerical

    monkeypatch.setitem(sys.modules, "airbot_hardware_py", fake_airbot)
    monkeypatch.setitem(sys.modules, "mmk2_kdl_py", fake_kdl_module)

    module_name = (
        "lerobot_play.robots.pico_follower_single_arm_agibot_o10."
        "airbot_pico_follower_single_arm_agibot_o10"
    )
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_o10_hand_reset_target_falls_back_to_zero_when_json_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    robot_module = _import_o10_robot_module(monkeypatch)
    robot_cls = robot_module.PicoFollowerSingleArmAgibotO10

    robot = object.__new__(robot_cls)
    robot.hand_reset_store = PersistentJointTargetStore(
        feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
        path=tmp_path / "missing_hand_reset.json",
        label="right hand reset joint target",
    )
    robot.hand_reset_joint_pos = []
    robot.hand_joints = []

    with caplog.at_level(logging.WARNING):
        robot._initialize_hand_reset_target()

    assert robot.hand_reset_joint_pos == [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)
    assert robot.hand_joints == [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)
    assert "Falling back to zero hand reset target" in caplog.text


def test_o10_return_zero_uses_persistent_hand_reset_target(
    monkeypatch: pytest.MonkeyPatch,
):
    robot_module = _import_o10_robot_module(monkeypatch)
    robot_cls = robot_module.PicoFollowerSingleArmAgibotO10
    reset_target = [round(index * 0.1, 3) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]
    hand_writes: list[list[float]] = []

    class FakeArm:
        def state(self):
            return SimpleNamespace(pos=[0.0] * 6)

        def pvt(self, joints, velocities, effort):
            return None

    class FakeHand:
        def write_active_joint_angles(self, joint_values):
            hand_writes.append(list(joint_values))

    robot = object.__new__(robot_cls)
    robot._is_connected = True
    robot.config = SimpleNamespace(arm_joints_num=7)
    robot.arm = FakeArm()
    robot.hand = FakeHand()
    robot.hand_reset_joint_pos = reset_target.copy()
    robot.hand_joints = []
    robot.is_arm_arrive = lambda *_args, **_kwargs: True

    robot.return_zero()

    assert hand_writes == [reset_target]
    assert robot.hand_joints == reset_target


def test_o10_connect_rolls_back_arm_and_cameras_when_hand_connect_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    robot_module = _import_o10_robot_module(monkeypatch)
    robot_cls = robot_module.PicoFollowerSingleArmAgibotO10
    call_order: list[str] = []

    class FakeArm:
        def init(self, io_context, arm_port, frequency):
            call_order.append("arm.init")
            return True

        def uninit(self):
            call_order.append("arm.uninit")

    class FakeHand:
        def connect(self):
            call_order.append("hand.connect")
            raise RuntimeError("hand connect failed")

        def disconnect(self):
            call_order.append("hand.disconnect")

    robot = object.__new__(robot_cls)
    robot._is_connected = False
    robot.io_context = object()
    robot.arm_port = "can0"
    robot.arm = FakeArm()
    robot.hand = FakeHand()
    robot.include_tactile_observation = False
    robot._connect_cameras = lambda: call_order.append("cameras.connect")
    robot._disconnect_cameras = lambda: call_order.append("cameras.disconnect")
    robot._initialize_hand_reset_target = lambda: call_order.append("reset.init")
    robot.enable_motors = lambda: call_order.append("motors.enable")
    robot.configure = lambda: call_order.append("configure")

    with pytest.raises(RuntimeError, match="hand connect failed"):
        robot.connect()

    assert call_order[:3] == ["cameras.connect", "arm.init", "hand.connect"]
    assert "arm.uninit" in call_order
    assert "cameras.disconnect" in call_order
    assert "motors.enable" not in call_order
    assert robot._is_connected is False


def test_control_disconnects_teleop_when_robot_connect_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    disconnect_calls = {"teleop": 0, "robot": 0}

    monkeypatch.setitem(sys.modules, "zmq", types.ModuleType("zmq"))
    fake_state_machine = types.ModuleType("airbot_state_machine")
    fake_state_machine.robotic_arm = object()
    monkeypatch.setitem(sys.modules, "airbot_state_machine", fake_state_machine)
    fake_scipy = types.ModuleType("scipy")
    fake_scipy_spatial = types.ModuleType("scipy.spatial")
    fake_scipy_transform = types.ModuleType("scipy.spatial.transform")
    fake_scipy_transform.Rotation = object
    monkeypatch.setitem(sys.modules, "scipy", fake_scipy)
    monkeypatch.setitem(sys.modules, "scipy.spatial", fake_scipy_spatial)
    monkeypatch.setitem(sys.modules, "scipy.spatial.transform", fake_scipy_transform)
    monkeypatch.setitem(
        sys.modules,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.pico_webrtc",
        types.ModuleType("lerobot_play.teleoperators.pico_leader_single_arm_eef.pico_webrtc"),
    )
    fake_udexreal_hand = types.ModuleType(
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.udexreal_hand"
    )
    fake_udexreal_hand.UdexrealTeleoperator = object
    monkeypatch.setitem(
        sys.modules,
        "lerobot_play.teleoperators.pico_leader_single_arm_eef.udexreal_hand",
        fake_udexreal_hand,
    )
    sys.modules.pop("lerobot_play.control", None)
    import lerobot_play.control as control_module

    class FakeTeleop:
        is_connected = False

        def connect(self):
            self.is_connected = True

        def disconnect(self):
            disconnect_calls["teleop"] += 1
            self.is_connected = False

    class FakeRobot:
        is_connected = False

        def connect(self):
            raise RuntimeError("robot connect failed")

        def disconnect(self):
            disconnect_calls["robot"] += 1

    monkeypatch.setattr(control_module, "init_logging", lambda: None)
    monkeypatch.setattr(control_module, "make_teleoperator_from_config", lambda cfg: FakeTeleop())
    monkeypatch.setattr(control_module, "make_robot_from_config", lambda cfg: FakeRobot())
    monkeypatch.setattr(
        control_module,
        "make_default_processors",
        lambda: (lambda value: value, lambda value: value[0], lambda value: value),
    )

    cfg = control_module.TeleoperateConfig(teleop=object(), robot=object(), display_data=False)

    with pytest.raises(RuntimeError, match="robot connect failed"):
        control_module.teleoperate(cfg)

    assert disconnect_calls["teleop"] == 1
    assert disconnect_calls["robot"] == 0


def test_record_loop_supports_policy_without_dataset(monkeypatch: pytest.MonkeyPatch):
    import lerobot.datasets.feature_utils as feature_utils
    import lerobot.datasets.utils as datasets_utils
    import lerobot.utils.utils as lerobot_utils
    import torch

    datasets_utils.build_dataset_frame = feature_utils.build_dataset_frame
    datasets_utils.combine_feature_dicts = feature_utils.combine_feature_dicts
    if not hasattr(lerobot_utils, "get_safe_torch_device"):
        lerobot_utils.get_safe_torch_device = lambda device: torch.device(device)

    fake_dataset_module = types.ModuleType("lerobot_play.utils.lerobot_dataset")
    fake_dataset_module.LeRobotDataset = object
    monkeypatch.setitem(
        sys.modules,
        "lerobot_play.utils.lerobot_dataset",
        fake_dataset_module,
    )
    sys.modules.pop("lerobot_play.utils.lerobot_record", None)
    import lerobot_play.utils.lerobot_record as record_module

    events = {"exit_early": False}
    sent_actions: list[dict[str, float]] = []

    class FakePolicy:
        config = SimpleNamespace(device="cpu", use_amp=False)

        def reset(self):
            return None

    class FakeProcessor:
        def reset(self):
            return None

    class FakeRobot:
        name = "fake_robot"
        robot_type = "fake_robot"
        cameras = {}

        def get_observation(self):
            return {"joint1.pos": 1.0, "joint2.pos": 2.0}

        def send_action(self, action):
            sent_actions.append(action)
            events["exit_early"] = True
            return action

    dataset_features = {
        "observation.state": {
            "dtype": "float32",
            "shape": (2,),
            "names": ["joint1.pos", "joint2.pos"],
        },
        "action": {
            "dtype": "float32",
            "shape": (2,),
            "names": ["joint1.pos", "joint2.pos"],
        },
    }

    monkeypatch.setattr(
        record_module,
        "predict_action",
        lambda **kwargs: torch.tensor([[0.3, 0.4]], dtype=torch.float32),
    )
    monkeypatch.setattr(record_module, "precise_sleep", lambda *_args, **_kwargs: None)

    record_module.record_loop(
        robot=FakeRobot(),
        events=events,
        fps=30,
        teleop_action_processor=lambda value: value,
        robot_action_processor=lambda value: value[0],
        robot_observation_processor=lambda value: value,
        dataset=None,
        dataset_features=dataset_features,
        policy=FakePolicy(),
        preprocessor=FakeProcessor(),
        postprocessor=FakeProcessor(),
        control_time_s=1,
        single_task="test task",
    )

    assert sent_actions == [pytest.approx({"joint1.pos": 0.3, "joint2.pos": 0.4})]


def test_sync_inference_without_save_skips_dataset_creation(monkeypatch: pytest.MonkeyPatch):
    import lerobot.datasets.feature_utils as feature_utils
    import lerobot.datasets.utils as datasets_utils
    import lerobot.utils.utils as lerobot_utils
    import torch

    datasets_utils.build_dataset_frame = feature_utils.build_dataset_frame
    datasets_utils.combine_feature_dicts = feature_utils.combine_feature_dicts
    if not hasattr(lerobot_utils, "get_safe_torch_device"):
        lerobot_utils.get_safe_torch_device = lambda device: torch.device(device)

    fake_dataset_module = types.ModuleType("lerobot_play.utils.lerobot_dataset")
    fake_dataset_module.LeRobotDataset = object
    monkeypatch.setitem(
        sys.modules,
        "lerobot_play.utils.lerobot_dataset",
        fake_dataset_module,
    )
    fake_control_utils = types.ModuleType("lerobot_play.utils.control_utils")
    fake_control_utils.init_keyboard_listener = lambda: (None, {"exit_early": False})
    monkeypatch.setitem(
        sys.modules,
        "lerobot_play.utils.control_utils",
        fake_control_utils,
    )
    sys.modules.pop("lerobot_play.utils.lerobot_record", None)
    sys.modules.pop("lerobot_play.infer", None)
    import lerobot_play.infer as infer_module

    created_dataset = {"called": False}
    record_loop_calls: list[dict] = []

    class FakePolicy:
        config = SimpleNamespace(device="cpu", use_amp=False)

    class FakeRobot:
        cameras = {}
        name = "fake_robot"
        connected = False
        disconnected = False

        def connect(self):
            self.connected = True

        def disconnect(self):
            self.disconnected = True

        def return_zero(self):
            return None

    fake_robot = FakeRobot()
    dataset_features = {
        "observation.state": {"dtype": "float32", "shape": (1,), "names": ["joint1.pos"]},
        "action": {"dtype": "float32", "shape": (1,), "names": ["joint1.pos"]},
    }
    processor_kwargs: dict[str, object] = {}

    monkeypatch.setattr(infer_module, "_create_robot_config", lambda args: object())
    monkeypatch.setattr(infer_module, "make_robot_from_config", lambda cfg: fake_robot)
    monkeypatch.setattr(
        infer_module,
        "make_default_processors",
        lambda: (lambda value: value, lambda value: value[0], lambda value: value),
    )
    monkeypatch.setattr(infer_module, "_load_policy", lambda *args: FakePolicy())
    monkeypatch.setattr(
        infer_module,
        "build_dataset_features",
        lambda robot, use_videos: dataset_features,
    )

    def _fail_create_dataset(*args, **kwargs):
        created_dataset["called"] = True
        raise AssertionError("dataset should not be created when save_data=false")

    def _fake_make_pre_post_processors(**kwargs):
        processor_kwargs.update(kwargs)
        return (object(), object())

    def _fake_record_loop(**kwargs):
        record_loop_calls.append(kwargs)
        assert kwargs["dataset"] is None
        assert kwargs["dataset_features"] == dataset_features

    monkeypatch.setattr(infer_module, "_create_dataset", _fail_create_dataset)
    monkeypatch.setattr(infer_module, "make_pre_post_processors", _fake_make_pre_post_processors)
    monkeypatch.setattr(infer_module, "record_loop", _fake_record_loop)
    monkeypatch.setattr(infer_module, "log_say", lambda *args, **kwargs: None)

    args = SimpleNamespace(
        policy="act",
        task_description="pick camera",
        model_path="~/workspace/fake_model",
        save_data=False,
        fps=30,
        num_episodes=1,
        episode_time_sec=1,
        device="cpu",
        save_path=None,
        robot_type="airbot_play_follower",
    )

    result = infer_module._run_sync_inference(args)

    assert result["data_saved"] is False
    assert result["save_path"] is None
    assert created_dataset["called"] is False
    assert len(record_loop_calls) == 1
    assert processor_kwargs["pretrained_path"] == args.model_path
    assert "dataset_stats" not in processor_kwargs
    assert fake_robot.connected is True
    assert fake_robot.disconnected is True
