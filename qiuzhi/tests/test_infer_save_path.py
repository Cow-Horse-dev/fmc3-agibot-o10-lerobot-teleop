import json
import pickle
import sys
import threading
import types
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import numpy as np
import pytest
import torch
import yaml


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

import lerobot_play.infer as infer_module
from lerobot_play.infer import (
    _apply_policy_robot_schema_defaults,
    _build_policy_preprocessor_overrides,
    _config_to_args,
    _create_dataset,
    _create_robot_config,
    _create_save_directory,
    _run_async_inference,
    _reset_to_training_start,
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


def test_sync_inference_uses_project_record_loop():
    assert infer_module.record_loop.__module__ == "lerobot_play.utils.lerobot_record"


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


def test_build_policy_preprocessor_overrides_uses_local_paligemma_tokenizer_for_pi05(
    tmp_path, monkeypatch
):
    tokenizer_root = tmp_path / "paligemma-tokenizer"
    tokenizer_root.mkdir()
    monkeypatch.setenv("ARM_HAND_TELEOP_PALIGEMMA_TOKENIZER", str(tokenizer_root))

    overrides = _build_policy_preprocessor_overrides("pi05", "cuda")

    assert overrides["device_processor"] == {"device": "cuda"}
    assert overrides["tokenizer_processor"] == {
        "tokenizer_name": str(tokenizer_root)
    }


def test_build_policy_preprocessor_overrides_leaves_non_vla_tokenizer_unchanged(
    tmp_path, monkeypatch
):
    tokenizer_root = tmp_path / "paligemma-tokenizer"
    tokenizer_root.mkdir()
    monkeypatch.setenv("ARM_HAND_TELEOP_PALIGEMMA_TOKENIZER", str(tokenizer_root))

    overrides = _build_policy_preprocessor_overrides("act", "cuda")

    assert overrides == {"device_processor": {"device": "cuda"}}


def test_filter_norm_map_drops_feature_types_missing_from_runtime():
    norm_map = {
        "VISUAL": "IDENTITY",
        "STATE": "QUANTILES",
        "ACTION": "QUANTILES",
        "TACTILE": "MEAN_STD",
    }

    filtered = infer_module._filter_norm_map_for_supported_feature_types(
        norm_map,
        supported_feature_type_names={"VISUAL", "STATE", "ACTION"},
    )

    assert filtered == {
        "VISUAL": "IDENTITY",
        "STATE": "QUANTILES",
        "ACTION": "QUANTILES",
    }


def test_build_policy_processor_overrides_drop_legacy_tactile_norm_map_for_pi05():
    preprocessor_overrides = _build_policy_preprocessor_overrides("pi05", "cuda")
    postprocessor_overrides = infer_module._build_policy_postprocessor_overrides(
        "pi05",
        device="cuda",
    )

    assert "TACTILE" not in preprocessor_overrides["normalizer_processor"]["norm_map"]
    assert "TACTILE" not in postprocessor_overrides["unnormalizer_processor"]["norm_map"]


def test_trim_action_tensor_to_policy_action_dim_keeps_pi05_rtc_padding_internal():
    action_tensor = torch.arange(2 * 4, dtype=torch.float32).reshape(1, 2, 4)

    trimmed = infer_module._trim_action_tensor_to_action_dim(action_tensor, 2)

    assert trimmed.shape == (1, 2, 2)
    assert trimmed.tolist() == [[[0.0, 1.0], [4.0, 5.0]]]
    assert action_tensor.shape == (1, 2, 4)


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
                "tactile_mode": "130d",
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
    assert robot_config.tactile_mode == "130d"
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
                "tactile_mode": "130d",
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
                "tactile_mode": "130d",
                "left": {"port": "can0", "handedness": "left"},
                "right": {"port": "can1", "handedness": "right"},
                "cameras": {},
            },
        }
    )

    _apply_policy_robot_schema_defaults(args)

    assert args.robot_tactile_mode == "130d"


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


def test_validate_policy_robot_feature_compatibility_allows_vla_padded_state(tmp_path):
    policy = SimpleNamespace(
        config=SimpleNamespace(
            type="pi05",
            max_state_dim=32,
            max_action_dim=32,
            input_features={
                "observation.images.base_0_rgb": SimpleNamespace(shape=(3, 224, 224)),
                "observation.state": SimpleNamespace(shape=(32,)),
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
        },
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


def test_validate_policy_robot_feature_compatibility_allows_pi05_empty_camera_padding(tmp_path):
    policy = SimpleNamespace(
        config=SimpleNamespace(
            type="pi05",
            max_state_dim=32,
            max_action_dim=32,
            input_features={
                "observation.images.base_0_rgb": {
                    "type": "VISUAL",
                    "shape": (3, 480, 640),
                },
                "observation.images.right_wrist_0_rgb": {
                    "type": "VISUAL",
                    "shape": (3, 480, 640),
                },
                "observation.images.empty_camera_0": {
                    "type": "VISUAL",
                    "shape": (3, 224, 224),
                },
                "observation.state": {"type": "STATE", "shape": (7,)},
            },
            output_features={"action": {"type": "ACTION", "shape": (7,)}},
        )
    )
    robot_features = {
        "observation.images.top": {
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
            "shape": (7,),
            "names": [f"state_{index}" for index in range(7)],
        },
        "action": {
            "dtype": "float32",
            "shape": (7,),
            "names": [f"action_{index}" for index in range(7)],
        },
    }

    _validate_policy_robot_feature_compatibility(
        policy,
        robot_features,
        str(tmp_path),
        observation_rename_map={
            "observation.images.top": "observation.images.base_0_rgb",
            "observation.images.right_wrist": "observation.images.right_wrist_0_rgb",
        },
    )


def test_validate_policy_robot_feature_compatibility_allows_pi05_missing_left_camera_padding(tmp_path):
    policy = SimpleNamespace(
        config=SimpleNamespace(
            type="pi05",
            max_state_dim=32,
            max_action_dim=32,
            input_features={
                "observation.images.base_0_rgb": {
                    "type": "VISUAL",
                    "shape": (3, 224, 224),
                },
                "observation.images.left_wrist_0_rgb": {
                    "type": "VISUAL",
                    "shape": (3, 224, 224),
                },
                "observation.images.right_wrist_0_rgb": {
                    "type": "VISUAL",
                    "shape": (3, 224, 224),
                },
                "observation.images.empty_camera_0": {
                    "type": "VISUAL",
                    "shape": (3, 224, 224),
                },
                "observation.state": {"type": "STATE", "shape": (32,)},
            },
            output_features={"action": {"type": "ACTION", "shape": (7,)}},
        )
    )
    robot_features = {
        "observation.images.top": {
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
            "shape": (7,),
            "names": [f"state_{index}" for index in range(7)],
        },
        "action": {
            "dtype": "float32",
            "shape": (7,),
            "names": [f"action_{index}" for index in range(7)],
        },
    }

    _validate_policy_robot_feature_compatibility(
        policy,
        robot_features,
        str(tmp_path),
        observation_rename_map={
            "observation.images.top": "observation.images.base_0_rgb",
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


def test_async_inference_resets_robot_before_control_loop(tmp_path, monkeypatch):
    import lerobot_play.infer as infer_module

    model_root = tmp_path / "model"
    model_root.mkdir()
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    (model_root / "model.safetensors").write_text("weights", encoding="utf-8")

    events = []

    class FakeRobot:
        name = "pico_follower_dual_arm_agibot_o10"
        cameras = {}

        def return_zero(self):
            events.append("reset")

    class FakeClient:
        def __init__(self, cfg):
            self.robot = FakeRobot()
            self.action_queue_size = []

        def start(self):
            events.append("start")
            return True

        def receive_actions(self):
            return None

        def control_loop(self, task, control_time_s=None):
            events.append("control")
            return None, None

        def clear_action_queue(self, advance_action_watermark=False):
            return None

        def stop(self):
            return None

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
                "policy": "smolvla",
                "task_description": "pick",
                "model_path": str(model_root),
                "num_episodes": 1,
                "episode_time_sec": 1,
                "fps": 30,
                "device": "cpu",
                "server_address": "localhost:8080",
            },
            "robot": {"cameras": {}},
        }
    )

    _run_async_inference(args)

    assert events[:3] == ["reset", "start", "control"]


def test_reset_to_training_start_maps_gripper_state_to_hand_joints(tmp_path, monkeypatch):
    import lerobot_play.infer as infer_module

    model_root = tmp_path / "model"
    dataset_root = tmp_path / "dataset"
    model_root.mkdir()
    dataset_root.mkdir()
    (model_root / "train_config.json").write_text(
        json.dumps(
            {
                "dataset": {
                    "root": str(dataset_root),
                    "repo_id": "local/gripper_dataset",
                }
            }
        ),
        encoding="utf-8",
    )

    class FakeDataset:
        def __init__(self, repo_id, root, episodes):
            assert repo_id == "gripper_dataset"
            assert Path(root) == dataset_root
            assert episodes == [0]

        def __getitem__(self, index):
            assert index == 0
            return {
                "observation.state": np.array(
                    [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75],
                    dtype=np.float32,
                )
            }

    class FakeRobot:
        name = "pico_follower_single_arm_agibot_o10"

        def __init__(self):
            self.reset_arm_joint_pos = []
            self.reset_hand_joint_pos = []
            self.reset_called = False

        def _hand_action_mode(self):
            return "gripper_1d"

        def _gripper_value_to_hand_joints(self, gripper_value):
            return [float(gripper_value) + index for index in range(10)]

        def reset_zero(self):
            self.reset_called = True

    monkeypatch.setattr(infer_module, "LeRobotDataset", FakeDataset)
    robot = FakeRobot()

    _reset_to_training_start(robot, str(model_root))

    assert robot.reset_arm_joint_pos == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert robot.reset_hand_joint_pos == pytest.approx([0.75 + index for index in range(10)])
    assert robot.reset_called is True


def test_async_inference_uses_configured_queue_tuning(tmp_path, monkeypatch):
    import lerobot_play.infer as infer_module

    model_root = tmp_path / "model"
    model_root.mkdir()
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    (model_root / "model.safetensors").write_text("weights", encoding="utf-8")

    captured = {}

    class FakeRobot:
        name = "fake_robot"
        cameras = {}

    class FakeClient:
        def __init__(self, cfg):
            captured["cfg"] = cfg
            self.action_queue_size = []

        def start(self):
            return True

        def receive_actions(self):
            return None

        def control_loop(self, task, control_time_s=None):
            return None, None

        def clear_action_queue(self, advance_action_watermark=False):
            return None

        def stop(self):
            return None

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
                "policy": "smolvla",
                "task_description": "pick",
                "model_path": str(model_root),
                "num_episodes": 1,
                "episode_time_sec": 1,
                "fps": 30,
                "device": "cpu",
                "server_address": "localhost:8080",
                "actions_per_chunk": 40,
                "chunk_size_threshold": 0.6,
                "debug_visualize_queue_size": True,
            },
            "robot": {"cameras": {}},
        }
    )

    _run_async_inference(args)

    assert captured["cfg"].actions_per_chunk == 40
    assert captured["cfg"].chunk_size_threshold == 0.6
    assert captured["cfg"].debug_visualize_queue_size is True


def test_async_inference_initializes_rerun_when_display_data_enabled(
    tmp_path, monkeypatch
):
    import lerobot_play.infer as infer_module

    model_root = tmp_path / "model"
    model_root.mkdir()
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    (model_root / "model.safetensors").write_text("weights", encoding="utf-8")

    captured = {"rerun_sessions": []}

    class FakeRobot:
        name = "fake_robot"
        cameras = {}

    class FakeClient:
        def __init__(self, cfg):
            captured["cfg"] = cfg
            self.action_queue_size = []

        def start(self):
            return True

        def receive_actions(self):
            return None

        def control_loop(self, task, control_time_s=None):
            return None, None

        def clear_action_queue(self, advance_action_watermark=False):
            return None

        def stop(self):
            return None

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
    monkeypatch.setattr(
        infer_module,
        "init_rerun",
        lambda session_name: captured["rerun_sessions"].append(session_name),
    )
    monkeypatch.setattr(infer_module, "visualize_action_queue_size", lambda *args, **kwargs: None)

    args = _config_to_args(
        {
            "infer": {
                "policy": "pi05",
                "task_description": "pick",
                "model_path": str(model_root),
                "display_data": True,
                "num_episodes": 1,
                "episode_time_sec": 1,
                "fps": 15,
                "device": "cpu",
                "server_address": "localhost:8080",
            },
            "robot": {"cameras": {}},
        }
    )

    _run_async_inference(args)

    assert captured["rerun_sessions"] == ["inference"]
    assert getattr(captured["cfg"], "display_data", None) is True


def test_async_inference_does_not_visualize_queue_unless_debug_enabled(
    tmp_path, monkeypatch
):
    import lerobot_play.infer as infer_module

    model_root = tmp_path / "model"
    model_root.mkdir()
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    (model_root / "model.safetensors").write_text("weights", encoding="utf-8")

    visualize_calls = []

    class FakeRobot:
        name = "fake_robot"
        cameras = {}

    class FakeClient:
        def __init__(self, cfg):
            self.action_queue_size = [1, 2, 3]

        def start(self):
            return True

        def receive_actions(self):
            return None

        def control_loop(self, task, control_time_s=None):
            return None, None

        def clear_action_queue(self, advance_action_watermark=False):
            return None

        def stop(self):
            return None

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
    monkeypatch.setattr(
        infer_module,
        "visualize_action_queue_size",
        lambda queue_sizes: visualize_calls.append(queue_sizes),
    )

    args = _config_to_args(
        {
            "infer": {
                "policy": "act",
                "task_description": "pick",
                "model_path": str(model_root),
                "num_episodes": 1,
                "episode_time_sec": 1,
                "fps": 30,
                "device": "cpu",
                "server_address": "localhost:8080",
                "debug_visualize_queue_size": False,
            },
            "robot": {"cameras": {}},
        }
    )

    _run_async_inference(args)

    assert visualize_calls == []


def test_async_robot_client_stop_swallows_keyboard_interrupt_during_disconnect():
    from lerobot_play.async_inference.robot_client import RobotClient

    disconnect_calls = []

    class InterruptingRobot:
        is_connected = True

        def disconnect(self):
            disconnect_calls.append("disconnect")
            raise KeyboardInterrupt

    class FakeChannel:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    client = object.__new__(RobotClient)
    client.shutdown_event = threading.Event()
    client.robot = InterruptingRobot()
    client.channel = FakeChannel()
    client.logger = SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )

    client.stop()

    assert disconnect_calls == ["disconnect"]
    assert client.shutdown_event.is_set()
    assert client.channel.closed is True


def test_async_robot_client_control_loop_duration_does_not_rewait_start_barrier():
    from lerobot_play.async_inference.robot_client import RobotClient

    barrier_waits = []
    client = object.__new__(RobotClient)
    client.start_barrier = SimpleNamespace(wait=lambda: barrier_waits.append("wait"))
    client.shutdown_event = SimpleNamespace(is_set=lambda: False)

    client.control_loop("pick", control_time_s=0)
    client.control_loop("pick", control_time_s=0)

    assert barrier_waits == ["wait"]


def test_async_robot_client_logs_observation_to_rerun_when_display_enabled(
    monkeypatch,
):
    from lerobot_play.async_inference import robot_client as robot_client_module
    from lerobot_play.async_inference.robot_client import RobotClient

    logged = []

    class FakeRobot:
        def get_observation(self):
            return {
                "observation.state": np.array([1.0], dtype=np.float32),
                "observation.images.top": np.zeros((2, 2, 3), dtype=np.uint8),
            }

    client = object.__new__(RobotClient)
    client.robot = FakeRobot()
    client.latest_action_lock = threading.Lock()
    client.latest_action = 3
    client.action_queue_lock = threading.Lock()
    client.action_queue = Queue()
    client.must_go = threading.Event()
    client.must_go.set()
    client.config = SimpleNamespace(display_data=True)
    client.logger = SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    client.send_observation = lambda observation: True

    monkeypatch.setattr(
        robot_client_module,
        "log_rerun_data",
        lambda **kwargs: logged.append(kwargs),
        raising=False,
    )

    raw_observation = client.control_loop_observation("pick")

    assert logged == [{"observation": raw_observation}]
    assert raw_observation["task"] == "pick"


def test_async_inference_disconnects_schema_probe_robot_before_client(monkeypatch):
    from lerobot_play import infer as infer_module

    events = []

    class ProbeCamera:
        def disconnect(self):
            events.append("probe-camera-disconnect")

    probe_robot = SimpleNamespace(cameras={"top": ProbeCamera()})

    class FakeClient:
        def __init__(self, cfg):
            events.append("client-created")
            self.robot = None
            self.task_switch_coordinator = None
            self.action_queue_size = []

        def start(self):
            return True

        def receive_actions(self):
            return None

        def control_loop(self, task, control_time_s):
            return None

        def stop(self):
            events.append("client-stop")

    monkeypatch.setattr(infer_module, "_create_robot_config", lambda args: object())
    monkeypatch.setattr(infer_module, "make_robot_from_config", lambda config: probe_robot)
    monkeypatch.setattr(
        infer_module,
        "build_dataset_features",
        lambda robot, use_videos: {
            "observation.state": {"dtype": "float32", "shape": (7,), "names": []},
            "action": {"dtype": "float32", "shape": (7,), "names": []},
            "observation.images.top": {
                "dtype": "video",
                "shape": (480, 640, 3),
                "names": ["height", "width", "channels"],
            },
        },
    )
    monkeypatch.setattr(
        infer_module,
        "_load_and_validate_policy_config",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        infer_module,
        "_create_task_switch_coordinator",
        lambda model_path, policy=None, task_switch_config_path=None: None,
    )
    monkeypatch.setattr(infer_module, "RobotClient", FakeClient)

    args = SimpleNamespace(
        server_address="localhost:8080",
        device="cuda",
        policy="pi05",
        model_path="/tmp/model",
        chunk_size_threshold=0.8,
        actions_per_chunk=50,
        debug_visualize_queue_size=False,
        display_data=False,
        num_episodes=1,
        task_description="pick",
        episode_time_sec=0,
    )

    result = _run_async_inference(args)

    assert result["status"] == "success"
    assert events[:2] == ["probe-camera-disconnect", "client-created"]


def test_async_inference_uses_text_task_switch_config_for_fullft(tmp_path, monkeypatch):
    from lerobot_play import infer as infer_module

    task_switch_config = tmp_path / "tasks.yaml"
    task_switch_config.write_text(
        yaml.safe_dump(
            {
                "default_profile": "black_to_yellow",
                "command_file": str(tmp_path / "switch.json"),
                "profiles": {
                    "black_to_yellow": {
                        "task_description": "black to yellow",
                    },
                    "yellow_to_black": {
                        "task_description": "yellow to black",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    class FakeClient:
        def __init__(self, cfg):
            self.robot = None
            self.task_switch_coordinator = None
            self.action_queue_size = []

        def start(self):
            return True

        def receive_actions(self):
            return None

        def control_loop(self, task, control_time_s):
            captured["task"] = task
            captured["coordinator"] = self.task_switch_coordinator
            return None

        def stop(self):
            return None

    monkeypatch.setattr(infer_module, "_create_robot_config", lambda args: object())
    monkeypatch.setattr(infer_module, "make_robot_from_config", lambda config: SimpleNamespace(cameras={}))
    monkeypatch.setattr(
        infer_module,
        "build_dataset_features",
        lambda robot, use_videos: {
            "observation.state": {"dtype": "float32", "shape": (7,), "names": []},
            "action": {"dtype": "float32", "shape": (7,), "names": []},
        },
    )
    monkeypatch.setattr(infer_module, "_load_and_validate_policy_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(infer_module, "RobotClient", FakeClient)

    args = SimpleNamespace(
        server_address="localhost:8080",
        device="cuda",
        policy="pi05",
        model_path=str(tmp_path / "pretrained_model"),
        task_switch_config=str(task_switch_config),
        chunk_size_threshold=0.8,
        actions_per_chunk=50,
        debug_visualize_queue_size=False,
        display_data=False,
        num_episodes=1,
        task_description="fallback task",
        episode_time_sec=0,
    )

    result = _run_async_inference(args)

    assert result["status"] == "success"
    assert captured["task"] == "black to yellow"
    assert captured["coordinator"].active_profile.profile_id == "black_to_yellow"


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


def test_async_robot_client_ready_to_send_observation_before_first_chunk():
    from lerobot_play.async_inference.robot_client import RobotClient

    client = object.__new__(RobotClient)
    client.action_queue = Queue()
    client.action_queue_lock = threading.Lock()
    client.action_chunk_size = -1
    client._chunk_size_threshold = 0.5

    assert client._ready_to_send_observation() is True


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
    processor_call = {}

    def fake_make_pre_post_processors(*args, **kwargs):
        processor_call["args"] = args
        processor_call["kwargs"] = kwargs
        return "pre", "post"

    monkeypatch.setattr(
        "lerobot_play.async_inference.policy_server.make_pre_post_processors",
        fake_make_pre_post_processors,
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
    preprocessor_overrides = processor_call["kwargs"]["preprocessor_overrides"]
    postprocessor_overrides = processor_call["kwargs"]["postprocessor_overrides"]
    assert "TACTILE" not in preprocessor_overrides["normalizer_processor"]["norm_map"]
    assert "TACTILE" not in postprocessor_overrides["unnormalizer_processor"]["norm_map"]


def test_lerobot_play_async_policy_server_renames_observation_features_for_legacy_helper(
    monkeypatch,
):
    from lerobot.async_inference.configs import PolicyServerConfig
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot_play.async_inference.policy_server import PolicyServer

    captured: dict[str, object] = {}

    def legacy_raw_observation_to_observation(
        raw_observation,
        lerobot_features,
        policy_image_features,
    ):
        captured["raw_observation"] = raw_observation
        captured["lerobot_features"] = lerobot_features
        return {"observation.images.base_0_rgb": torch.zeros((1, 3, 2, 2))}

    monkeypatch.setattr(
        "lerobot.async_inference.policy_server.raw_observation_to_observation",
        legacy_raw_observation_to_observation,
    )

    server = PolicyServer(PolicyServerConfig())
    server.lerobot_features = {
        "observation.images.top": {
            "dtype": "video",
            "shape": (4, 4, 3),
            "names": ["height", "width", "channels"],
        },
    }
    server.observation_rename_map = {
        "observation.images.top": "observation.images.base_0_rgb",
    }
    server.policy = SimpleNamespace(
        config=SimpleNamespace(
            image_features={
                "observation.images.base_0_rgb": SimpleNamespace(shape=(3, 2, 2)),
            }
        ),
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

    assert "observation.images.base_0_rgb" in captured["lerobot_features"]
    assert "observation.images.top" not in captured["lerobot_features"]
    assert "base_0_rgb" in captured["raw_observation"]


def test_lerobot_play_async_policy_server_can_enable_rtc(monkeypatch):
    from lerobot.async_inference.configs import PolicyServerConfig
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot.policies.rtc.configuration_rtc import RTCConfig
    from lerobot_play.async_inference.policy_server import PolicyServer

    calls = []

    class FakePolicy:
        def __init__(self):
            self.config = SimpleNamespace(
                device="cpu",
                image_features={},
                rtc_config=RTCConfig(
                    enabled=True,
                    execution_horizon=4,
                    max_guidance_weight=8.0,
                    prefix_attention_schedule="EXP",
                ),
            )

        def predict_action_chunk(self, observation, **kwargs):
            calls.append(kwargs)
            return torch.arange(6, dtype=torch.float32).reshape(1, 3, 2)

    monkeypatch.setattr(
        "lerobot.async_inference.policy_server.raw_observation_to_observation",
        lambda *args, **kwargs: {"observation.state": torch.zeros(1)},
    )

    server = PolicyServer(PolicyServerConfig(fps=30, inference_latency=0.1))
    server.lerobot_features = {}
    server.observation_rename_map = {}
    server.policy = FakePolicy()
    server.preprocessor = lambda observation: observation
    server.postprocessor = lambda action: action
    server.actions_per_chunk = 3

    server._predict_action_chunk(
        TimedObservation(timestamp=0.0, timestep=0, observation={})
    )
    server._predict_action_chunk(
        TimedObservation(timestamp=0.1, timestep=1, observation={})
    )

    assert calls[0] == {}
    assert calls[1]["inference_delay"] == 3
    assert calls[1]["execution_horizon"] == 4
    assert calls[1]["prev_chunk_left_over"].shape == (1, 2, 2)


def test_lerobot_play_async_policy_server_trims_pi05_padding_before_postprocess(
    monkeypatch,
):
    from lerobot.async_inference.configs import PolicyServerConfig
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot.policies.rtc.configuration_rtc import RTCConfig
    from lerobot_play.async_inference.policy_server import PolicyServer

    postprocessed_shapes = []

    class FakePolicy:
        def __init__(self):
            self.config = SimpleNamespace(
                device="cpu",
                image_features={},
                rtc_config=RTCConfig(enabled=True),
            )

        def predict_action_chunk(self, observation, **kwargs):
            return torch.arange(8, dtype=torch.float32).reshape(1, 2, 4)

    monkeypatch.setattr(
        "lerobot.async_inference.policy_server.raw_observation_to_observation",
        lambda *args, **kwargs: {"observation.state": torch.zeros(1)},
    )

    server = PolicyServer(PolicyServerConfig())
    server.lerobot_features = {}
    server.observation_rename_map = {}
    server.policy = FakePolicy()
    server.preprocessor = lambda observation: observation
    server.postprocess_action_dim = 2

    def postprocess(action):
        postprocessed_shapes.append(tuple(action.shape))
        return action

    server.postprocessor = postprocess
    server.actions_per_chunk = 2

    action_chunk = server._predict_action_chunk(
        TimedObservation(timestamp=0.0, timestep=0, observation={})
    )

    assert postprocessed_shapes == [(1, 2), (1, 2)]
    assert server._rtc_previous_action_chunk.shape == (1, 2, 4)
    assert action_chunk[0].get_action().shape == (2,)


def test_lerobot_play_async_policy_server_pads_state_after_normalizer_preprocessor(
    monkeypatch,
):
    from lerobot.async_inference.configs import PolicyServerConfig
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot_play.async_inference.policy_server import PolicyServer

    captured = {}

    class FakePolicy:
        def __init__(self):
            self.config = SimpleNamespace(
                type="pi05",
                max_state_dim=32,
                input_features={
                    "observation.state": {"type": "STATE", "shape": (32,)},
                },
                image_features={},
            )

        def predict_action_chunk(self, observation, **kwargs):
            captured["policy_state"] = observation["observation.state"].clone()
            return torch.zeros((1, 1, 7), dtype=torch.float32)

    monkeypatch.setattr(
        "lerobot.async_inference.policy_server.raw_observation_to_observation",
        lambda *args, **kwargs: {
            "observation.state": torch.arange(7, dtype=torch.float32).reshape(1, 7),
        },
    )

    def preprocessor(observation):
        captured["preprocessor_state"] = observation["observation.state"].clone()
        state = observation["observation.state"]
        padded_observation = dict(observation)
        padded_observation["observation.state"] = torch.cat(
            (state, state.new_zeros((state.shape[0], 25))),
            dim=-1,
        )
        return padded_observation

    server = PolicyServer(PolicyServerConfig())
    server.lerobot_features = {}
    server.observation_rename_map = {}
    server.policy = FakePolicy()
    server.preprocessor = preprocessor
    server.postprocessor = lambda action: action
    server.actions_per_chunk = 1
    server.postprocess_action_dim = 7

    server._predict_action_chunk(
        TimedObservation(timestamp=0.0, timestep=0, observation={})
    )

    assert captured["preprocessor_state"].shape == (1, 7)
    assert torch.equal(
        captured["preprocessor_state"][0],
        torch.arange(7, dtype=torch.float32),
    )
    assert captured["policy_state"].shape == (1, 32)
    assert torch.equal(captured["policy_state"][0, :7], torch.arange(7, dtype=torch.float32))
    assert torch.equal(captured["policy_state"][0, 7:], torch.zeros(25, dtype=torch.float32))


def test_lerobot_play_async_policy_server_receive_observation_is_quiet_at_info(
    monkeypatch,
):
    from lerobot.async_inference.configs import PolicyServerConfig
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot.transport import services_pb2
    from lerobot.transport.utils import send_bytes_in_chunks
    from lerobot_play.async_inference.policy_server import PolicyServer

    info_messages = []
    monkeypatch.setattr(
        "lerobot.transport.utils.logging.info",
        lambda message, *args, **kwargs: info_messages.append(str(message)),
    )

    server = PolicyServer(PolicyServerConfig())
    timed_observation = TimedObservation(
        timestamp=0.0,
        timestep=1,
        observation={"joint": 0.1},
    )
    request_iterator = send_bytes_in_chunks(
        pickle.dumps(timed_observation),
        services_pb2.Observation,
        silent=True,
    )
    context = SimpleNamespace(peer=lambda: "test-client")

    server.SendObservations(request_iterator, context)

    assert not any("Starting receiver" in message for message in info_messages)
    assert server.observation_queue.get_nowait().get_timestep() == 1


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
