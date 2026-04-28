from pathlib import Path
import json
import pickle
import sys
import threading
import types
from queue import Queue
from types import SimpleNamespace

import numpy as np
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


fake_airbot_hardware = types.ModuleType("airbot_hardware_py")
fake_airbot_hardware.MotorType = SimpleNamespace(OD=object(), DM=object(), NA=object())
fake_airbot_hardware.EEFType = SimpleNamespace(NA=object())
fake_airbot_hardware.MotorControlMode = SimpleNamespace(PVT=object())
fake_airbot_hardware.create_asio_executor = lambda *args, **kwargs: SimpleNamespace(
    get_io_context=lambda: SimpleNamespace()
)
fake_airbot_hardware.Play = SimpleNamespace(
    create=lambda *args, **kwargs: SimpleNamespace(
        init=lambda *args, **kwargs: True,
        uninit=lambda *args, **kwargs: None,
        enable=lambda *args, **kwargs: None,
        disable=lambda *args, **kwargs: None,
        set_param=lambda *args, **kwargs: None,
        pvt=lambda *args, **kwargs: None,
        state=lambda: SimpleNamespace(pos=[0.0] * 6),
    )
)
fake_mmk2_kdl = types.ModuleType("mmk2_kdl_py")
fake_mmk2_kdl.ArmKdlNumerical = lambda *args, **kwargs: SimpleNamespace()

sys.modules.setdefault("airbot_hardware_py", fake_airbot_hardware)
sys.modules.setdefault("mmk2_kdl_py", fake_mmk2_kdl)

from lerobot_play.infer import (
    _apply_policy_robot_schema_defaults,
    _config_to_args,
    _create_dataset,
    _create_robot_config,
    _create_save_directory,
    _run_async_inference,
    _validate_policy_type_matches_checkpoint,
    _validate_policy_robot_feature_compatibility,
    _validate_args,
    _validate_model_path,
    _load_policy,
)


class _DummyRobot:
    name = "dummy_robot"
    cameras = {}
    action_features = {}
    observation_features = {}


def test_create_save_directory_leaves_new_dataset_path_uncreated(tmp_path):
    dataset_root = tmp_path / "diffusion_infer_123"

    returned_path = _create_save_directory(str(dataset_root))

    assert returned_path == str(dataset_root)
    assert not dataset_root.exists()


def test_create_save_directory_expands_user_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    returned_path = _create_save_directory("~/diffusion_infer_123")

    assert returned_path == str(tmp_path / "diffusion_infer_123")
    assert not Path(returned_path).exists()


def test_create_dataset_uses_dataset_root_directly(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("lerobot_play.infer.LeRobotDataset.create", fake_create)

    dataset_root = tmp_path / "diffusion_infer_123"
    robot = _DummyRobot()

    _create_dataset(robot, fps=15, save_path=str(dataset_root))

    assert captured["repo_id"] == "diffusion_infer_123"
    assert captured["root"] == str(dataset_root)


def test_validate_model_path_expands_user_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    model_root = tmp_path / "models" / "agi_arm_bot"
    model_root.mkdir(parents=True)
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    (model_root / "model.safetensors").write_text("weights", encoding="utf-8")

    assert _validate_model_path("~/models/agi_arm_bot") is True


@pytest.mark.parametrize(
    ("policy_type", "policy_class_name"),
    [
        ("pi0", "PI0Policy"),
        ("pi05", "PI05Policy"),
    ],
)
def test_load_policy_wraps_pi_peft_adapter(
    policy_type, policy_class_name, tmp_path, monkeypatch
):
    base_model_root = tmp_path / f"base_{policy_type}"
    base_model_root.mkdir()
    adapter_root = tmp_path / f"{policy_type}_lora"
    adapter_root.mkdir()
    (adapter_root / "adapter_config.json").write_text("{}", encoding="utf-8")
    (adapter_root / "adapter_model.safetensors").write_text("adapter", encoding="utf-8")
    (adapter_root / "config.json").write_text("{}", encoding="utf-8")

    loaded_paths = []
    wrapped_paths = []

    class DummyConfig:
        device = "cpu"

    class DummyPolicy:
        config = DummyConfig()

        def to(self, device):
            self.config.device = device
            return self

    class DummyWrappedPolicy:
        config = SimpleNamespace(peft_type="LORA")

        def __init__(self, base_policy):
            self.base_policy = base_policy

        def to(self, device):
            self.config.device = device
            return self

    class DummyPeftConfig:
        base_model_name_or_path = str(base_model_root)

    class DummyPeftModel:
        @staticmethod
        def from_pretrained(policy, adapter_path, config):
            wrapped_paths.append((policy, adapter_path, config))
            return DummyWrappedPolicy(policy)

    fake_peft = types.ModuleType("peft")
    fake_peft.PeftConfig = SimpleNamespace(
        from_pretrained=lambda adapter_path: DummyPeftConfig()
    )
    fake_peft.PeftModel = DummyPeftModel
    monkeypatch.setitem(sys.modules, "peft", fake_peft)

    def fake_from_pretrained(model_path):
        loaded_paths.append(model_path)
        return DummyPolicy()

    monkeypatch.setattr(
        f"lerobot_play.infer.{policy_class_name}.from_pretrained",
        fake_from_pretrained,
    )

    policy = _load_policy(policy_type, str(adapter_root), "cuda")

    assert isinstance(policy, DummyWrappedPolicy)
    assert loaded_paths == [str(base_model_root)]
    assert len(wrapped_paths) == 1
    assert isinstance(wrapped_paths[0][0], DummyPolicy)
    assert wrapped_paths[0][1] == str(adapter_root)
    assert isinstance(wrapped_paths[0][2], DummyPeftConfig)
    assert policy.config is wrapped_paths[0][0].config
    assert policy.config.device == "cuda"


def test_load_policy_filters_unknown_checkpoint_config_fields_for_pi0(tmp_path, monkeypatch):
    model_root = tmp_path / "pi0"
    model_root.mkdir()
    (model_root / "model.safetensors").write_text("weights", encoding="utf-8")
    (model_root / "config.json").write_text(
        json.dumps(
            {
                "type": "pi0",
                "device": "cpu",
                "n_obs_steps": 1,
                "chunk_size": 10,
                "n_action_steps": 10,
                "input_features": {
                    "observation.state": {"type": "STATE", "shape": [14]},
                    "observation.images.top": {"type": "VISUAL", "shape": [3, 224, 224]},
                },
                "output_features": {
                    "action": {"type": "ACTION", "shape": [14]},
                },
                "optimizer_foreach": False,
            }
        ),
        encoding="utf-8",
    )

    captured = {}

    class DummyPolicy:
        def __init__(self, config):
            self.config = config

        def to(self, device):
            self.config.device = device
            return self

    def fake_from_pretrained(model_path, **kwargs):
        captured["model_path"] = model_path
        captured["kwargs"] = kwargs
        return DummyPolicy(kwargs["config"])

    monkeypatch.setattr(
        "lerobot_play.infer.PI0Policy.from_pretrained",
        fake_from_pretrained,
    )

    policy = _load_policy("pi0", str(model_root), "cuda")

    assert captured["model_path"] == str(model_root)
    assert "config" in captured["kwargs"]
    assert not hasattr(captured["kwargs"]["config"], "optimizer_foreach")
    assert captured["kwargs"]["config"].type == "pi0"
    assert policy.config.device == "cuda"


def test_single_arm_o10_infer_passes_schema_fields_to_robot_config():
    args = _config_to_args(
        {
            "infer": {
                "policy": "diffusion",
                "task_description": "pick",
                "model_path": "/tmp/model",
            },
            "robot": {
                "type": "pico_follower_single_arm_agibot_o10",
                "port": "can0",
                "handedness": "left",
                "enable_hand": False,
                "allow_camera_read_failures": True,
                "include_eef_pose": False,
                "tactile_mode": "none",
                "cameras": {},
            },
        }
    )

    robot_config = _create_robot_config(args)

    assert robot_config.enable_hand is False
    assert robot_config.allow_camera_read_failures is True
    assert robot_config.include_eef_pose is False
    assert robot_config.tactile_mode == "none"


def test_dual_arm_o10_infer_passes_schema_fields_to_robot_config():
    args = _config_to_args(
        {
            "infer": {
                "policy": "diffusion",
                "task_description": "pick",
                "model_path": "/tmp/model",
            },
            "robot": {
                "type": "pico_follower_dual_arm_agibot_o10",
                "enable_hand": True,
                "allow_camera_read_failures": True,
                "include_eef_pose": False,
                "tactile_mode": "7d",
                "left": {"port": "can0", "handedness": "left"},
                "right": {"port": "can1", "handedness": "right"},
                "cameras": {},
            },
        }
    )

    robot_config = _create_robot_config(args)

    assert robot_config.enable_hand is True
    assert robot_config.allow_camera_read_failures is True
    assert robot_config.include_eef_pose is False
    assert robot_config.tactile_mode == "7d"
    assert robot_config.left == {"port": "can0", "handedness": "left"}
    assert robot_config.right == {"port": "can1", "handedness": "right"}


def test_dual_arm_o10_robot_factory_imports_runtime_class(monkeypatch):
    from lerobot_play.robots.pico_follower_dual_arm_agibot_o10.config_pico_follower_dual_arm_agibot_o10 import (
        PicoFollowerDualArmAgibotO10Config,
    )
    from lerobot_play.robots.utils import make_robot_from_config

    robot_config = PicoFollowerDualArmAgibotO10Config(
        left={"port": "can0", "handedness": "left"},
        right={"port": "can1", "handedness": "right"},
        enable_hand=False,
        cameras={},
    )

    robot = make_robot_from_config(robot_config)

    assert robot.name == "pico_follower_dual_arm_agibot_o10"


def test_pi0_dual_arm_o10_infer_forces_tactile_off_for_robot_schema():
    args = _config_to_args(
        {
            "infer": {
                "policy": "pi0",
                "task_description": "pick",
                "model_path": "/tmp/model",
            },
            "robot": {
                "type": "pico_follower_dual_arm_agibot_o10",
                "tactile_mode": "7d",
                "left": {"port": "can0", "handedness": "left"},
                "right": {"port": "can1", "handedness": "right"},
                "cameras": {},
            },
        }
    )

    _apply_policy_robot_schema_defaults(args)

    assert args.robot_tactile_mode == "none"


def test_diffusion_dual_arm_o10_infer_keeps_configured_tactile_schema():
    args = _config_to_args(
        {
            "infer": {
                "policy": "diffusion",
                "task_description": "pick",
                "model_path": "/tmp/model",
            },
            "robot": {
                "type": "pico_follower_dual_arm_agibot_o10",
                "tactile_mode": "7d",
                "left": {"port": "can0", "handedness": "left"},
                "right": {"port": "can1", "handedness": "right"},
                "cameras": {},
            },
        }
    )

    _apply_policy_robot_schema_defaults(args)

    assert args.robot_tactile_mode == "7d"


def test_validate_policy_robot_feature_compatibility_rejects_state_action_mismatch(tmp_path):
    policy = SimpleNamespace(
        config=SimpleNamespace(
            input_features={
                "observation.images.base_0_rgb": SimpleNamespace(shape=(3, 224, 224)),
                "observation.state": SimpleNamespace(shape=(32,)),
            },
            output_features={
                "action": SimpleNamespace(shape=(32,)),
            },
        )
    )
    robot_features = {
        "observation.images.base_0_rgb": {
            "dtype": "video",
            "shape": (480, 640, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.state": {
            "dtype": "float32",
            "shape": (14,),
            "names": [f"state_{index}" for index in range(14)],
        },
        "action": {
            "dtype": "float32",
            "shape": (14,),
            "names": [f"action_{index}" for index in range(14)],
        },
    }

    with pytest.raises(ValueError, match="observation.state"):
        _validate_policy_robot_feature_compatibility(
            policy,
            robot_features,
            str(tmp_path),
        )


def test_validate_policy_robot_feature_compatibility_allows_saved_camera_rename_map(tmp_path):
    policy = SimpleNamespace(
        config=SimpleNamespace(
            input_features={
                "observation.images.base_0_rgb": SimpleNamespace(shape=(3, 224, 224)),
                "observation.images.left_wrist_0_rgb": SimpleNamespace(shape=(3, 224, 224)),
                "observation.images.right_wrist_0_rgb": SimpleNamespace(shape=(3, 224, 224)),
                "observation.state": SimpleNamespace(shape=(14,)),
            },
            output_features={
                "action": SimpleNamespace(shape=(14,)),
            },
        )
    )
    robot_features = {
        "observation.images.top": {
            "dtype": "video",
            "shape": (480, 640, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.images.left_wrist": {
            "dtype": "video",
            "shape": (480, 640, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.images.right_wrist": {
            "dtype": "video",
            "shape": (480, 640, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.state": {
            "dtype": "float32",
            "shape": (14,),
            "names": [f"state_{index}" for index in range(14)],
        },
        "action": {
            "dtype": "float32",
            "shape": (14,),
            "names": [f"action_{index}" for index in range(14)],
        },
    }

    _validate_policy_robot_feature_compatibility(
        policy,
        robot_features,
        str(tmp_path),
        observation_rename_map={
            "observation.images.top": "observation.images.base_0_rgb",
            "observation.images.left_wrist": "observation.images.left_wrist_0_rgb",
            "observation.images.right_wrist": "observation.images.right_wrist_0_rgb",
        },
    )


def test_validate_policy_type_matches_checkpoint_rejects_wrong_policy_name(tmp_path):
    policy_config = SimpleNamespace(type="pi0")

    with pytest.raises(ValueError, match="checkpoint"):
        _validate_policy_type_matches_checkpoint("diffusion", policy_config, str(tmp_path))


def test_async_robot_client_sends_saved_observation_rename_map(tmp_path, monkeypatch):
    from lerobot_play.async_inference import robot_client as robot_client_module

    model_root = tmp_path / "model"
    model_root.mkdir()
    rename_map = {
        "observation.images.top": "observation.images.base_0_rgb",
        "observation.images.left_wrist": "observation.images.left_wrist_0_rgb",
        "observation.images.right_wrist": "observation.images.right_wrist_0_rgb",
    }
    (model_root / "policy_preprocessor.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "registry_name": "rename_observations_processor",
                        "config": {"rename_map": rename_map},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    fake_robot = SimpleNamespace(
        connect=lambda: None,
        observation_features={},
        action_features={},
    )
    monkeypatch.setattr(
        robot_client_module,
        "make_robot_from_config",
        lambda robot_config: fake_robot,
    )
    monkeypatch.setattr(
        robot_client_module,
        "map_robot_keys_to_lerobot_features",
        lambda robot: {"observation.images.top": {"dtype": "video"}},
    )

    client = robot_client_module.RobotClient(
        SimpleNamespace(
            robot=SimpleNamespace(),
            server_address="127.0.0.1:1",
            policy_type="pi0",
            pretrained_name_or_path=str(model_root),
            actions_per_chunk=50,
            policy_device="cpu",
            environment_dt=1 / 30,
            chunk_size_threshold=0.5,
            aggregate_fn=None,
            fps=30,
        )
    )

    assert client.policy_config.rename_map == rename_map


def test_async_raw_observation_renames_images_before_policy_resize():
    from lerobot.async_inference.helpers import raw_observation_to_observation

    raw_observation = {
        "joint": 0.1,
        "top": np.zeros((4, 4, 3), dtype=np.uint8),
    }
    lerobot_features = {
        "observation.state": {
            "dtype": "float32",
            "shape": (1,),
            "names": ["joint"],
        },
        "observation.images.top": {
            "dtype": "image",
            "shape": (4, 4, 3),
            "names": ["height", "width", "channels"],
        },
    }
    policy_image_features = {
        "observation.images.base_0_rgb": SimpleNamespace(shape=(3, 2, 2)),
    }

    observation = raw_observation_to_observation(
        raw_observation,
        lerobot_features,
        policy_image_features,
        observation_rename_map={
            "observation.images.top": "observation.images.base_0_rgb",
        },
    )

    assert "observation.images.base_0_rgb" in observation
    assert "observation.images.top" not in observation
    assert observation["observation.images.base_0_rgb"].shape == (1, 3, 2, 2)


def test_async_policy_server_uses_received_rename_map_in_action_prediction(monkeypatch):
    from lerobot.async_inference.configs import PolicyServerConfig
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot.async_inference.policy_server import PolicyServer

    captured: dict[str, object] = {}

    def fake_raw_observation_to_observation(
        raw_observation,
        lerobot_features,
        policy_image_features,
        observation_rename_map=None,
    ):
        captured["observation_rename_map"] = observation_rename_map
        return {"observation.state": "prepared"}

    monkeypatch.setattr(
        "lerobot.async_inference.policy_server.raw_observation_to_observation",
        fake_raw_observation_to_observation,
    )

    server = PolicyServer(PolicyServerConfig())
    server.lerobot_features = {}
    server.observation_rename_map = {
        "observation.images.top": "observation.images.base_0_rgb",
    }
    server.policy = SimpleNamespace(
        config=SimpleNamespace(image_features={}),
        predict_action_chunk=lambda observation: torch.zeros((1, 1, 1)),
    )
    server.preprocessor = lambda observation: observation
    server.postprocessor = lambda action: action
    server.actions_per_chunk = 1

    server._predict_action_chunk(
        TimedObservation(
            timestamp=0.0,
            timestep=0,
            observation={"top": np.zeros((4, 4, 3), dtype=np.uint8)},
        )
    )

    assert captured["observation_rename_map"] == server.observation_rename_map


def test_async_inference_runs_each_episode_for_configured_duration(tmp_path, monkeypatch):
    import lerobot_play.infer as infer_module

    model_root = tmp_path / "model"
    model_root.mkdir()
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    (model_root / "model.safetensors").write_text("weights", encoding="utf-8")

    control_calls = []

    class FakeRobot:
        name = "fake_robot"
        cameras = {}

    class FakeClient:
        def __init__(self, cfg):
            self.cfg = cfg
            self.action_queue_size = []
            self.stopped = False

        def start(self):
            return True

        def receive_actions(self):
            return None

        def control_loop(self, task, control_time_s=None):
            control_calls.append((task, control_time_s))
            return None, None

        def clear_action_queue(self, advance_action_watermark=False):
            return None

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(infer_module, "make_robot_from_config", lambda robot_config: FakeRobot())
    monkeypatch.setattr(
        infer_module,
        "build_dataset_features",
        lambda robot, use_videos: {
            "observation.state": {"dtype": "float32", "shape": (1,), "names": ["joint"]},
            "action": {"dtype": "float32", "shape": (1,), "names": ["joint"]},
        },
    )
    monkeypatch.setattr(
        infer_module,
        "_load_and_validate_policy_config",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(infer_module, "RobotClient", FakeClient)
    monkeypatch.setattr(infer_module, "visualize_action_queue_size", lambda *args, **kwargs: None)

    args = _config_to_args(
        {
            "infer": {
                "policy": "act",
                "task_description": "pick",
                "model_path": str(model_root),
                "num_episodes": 2,
                "episode_time_sec": 3,
                "fps": 30,
                "device": "cpu",
                "server_address": "localhost:8080",
            },
            "robot": {"cameras": {}},
        }
    )

    result = _run_async_inference(args)

    assert control_calls == [("pick", 3), ("pick", 3)]
    assert result["episodes_completed"] == 2


def test_async_robot_client_control_loop_duration_does_not_rewait_start_barrier():
    from lerobot_play.async_inference.robot_client import RobotClient

    barrier_waits = []
    client = object.__new__(RobotClient)
    client.start_barrier = SimpleNamespace(wait=lambda: barrier_waits.append("wait"))
    client.shutdown_event = SimpleNamespace(is_set=lambda: False)

    client.control_loop("pick", control_time_s=0)
    client.control_loop("pick", control_time_s=0)

    assert barrier_waits == ["wait"]


def test_async_robot_client_clear_action_queue_advances_stale_action_watermark():
    from lerobot.async_inference.helpers import TimedAction
    from lerobot_play.async_inference.robot_client import RobotClient

    client = object.__new__(RobotClient)
    client.action_queue = Queue()
    client.action_queue_lock = threading.Lock()
    client.action_queue_size = [2, 1]
    client.latest_action = 10
    client.latest_action_lock = threading.Lock()
    client.action_chunk_size = -1
    client.config = SimpleNamespace(actions_per_chunk=50)
    client.must_go = SimpleNamespace(set=lambda: None)

    client.clear_action_queue(advance_action_watermark=True)
    client._aggregate_action_queues(
        [
            TimedAction(timestamp=0.0, timestep=59, action=torch.tensor([1.0])),
            TimedAction(timestamp=0.0, timestep=61, action=torch.tensor([2.0])),
        ]
    )

    assert client.latest_action == 60
    assert client.action_queue_size == []
    assert client.action_queue.qsize() == 1
    assert client.action_queue.get_nowait().get_timestep() == 61


def test_lerobot_play_async_policy_server_loads_policy_through_project_loader(monkeypatch):
    from lerobot.async_inference.configs import PolicyServerConfig
    from lerobot.async_inference.helpers import RemotePolicyConfig
    from lerobot.transport import services_pb2
    from lerobot_play.async_inference.policy_server import PolicyServer

    loaded = []

    fake_policy = SimpleNamespace(
        config=SimpleNamespace(device="cpu"),
    )

    def fake_load_policy(policy_type, model_path, device):
        loaded.append((policy_type, model_path, device))
        fake_policy.config.device = device
        return fake_policy

    monkeypatch.setattr(
        "lerobot_play.async_inference.policy_server._load_policy",
        fake_load_policy,
    )
    monkeypatch.setattr(
        "lerobot_play.async_inference.policy_server.make_pre_post_processors",
        lambda *args, **kwargs: ("pre", "post"),
    )

    server = PolicyServer(PolicyServerConfig())
    server.shutdown_event.clear()
    policy_specs = RemotePolicyConfig(
        policy_type="pi0",
        pretrained_name_or_path="/tmp/pi0_lora",
        lerobot_features={"observation.state": {"dtype": "float32"}},
        actions_per_chunk=50,
        device="cuda",
        rename_map={"observation.images.top": "observation.images.base_0_rgb"},
    )
    request = services_pb2.PolicySetup(data=pickle.dumps(policy_specs))
    context = SimpleNamespace(peer=lambda: "test-client")

    server.SendPolicyInstructions(request, context)

    assert loaded == [("pi0", "/tmp/pi0_lora", "cuda")]
    assert server.policy is fake_policy
    assert server.preprocessor == "pre"
    assert server.postprocessor == "post"
    assert server.observation_rename_map == policy_specs.rename_map


def _minimal_valid_args(tmp_path):
    model_root = tmp_path / "model"
    model_root.mkdir()
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    return _config_to_args(
        {
            "infer": {
                "policy": "act",
                "task_description": "pick",
                "model_path": str(model_root),
                "num_episodes": 1,
                "episode_time_sec": 1,
                "fps": 1,
            },
            "robot": {"cameras": {}},
        }
    )


def test_validate_args_rejects_unknown_yaml_policy(tmp_path):
    args = _minimal_valid_args(tmp_path)
    args.policy = "unknown"

    with pytest.raises(ValueError, match="Unsupported policy type"):
        _validate_args(args)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("num_episodes", "infer.num_episodes must be positive"),
        ("episode_time_sec", "infer.episode_time_sec must be positive"),
        ("fps", "infer.fps must be positive"),
    ],
)
def test_validate_args_rejects_non_positive_runtime_values(tmp_path, field, message):
    args = _minimal_valid_args(tmp_path)
    setattr(args, field, 0)

    with pytest.raises(ValueError, match=message):
        _validate_args(args)
