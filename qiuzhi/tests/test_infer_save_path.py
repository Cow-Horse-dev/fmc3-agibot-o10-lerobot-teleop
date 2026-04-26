from pathlib import Path
import json
import sys
import types
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
    _validate_policy_type_matches_checkpoint,
    _validate_policy_robot_feature_compatibility,
    _validate_args,
    _validate_model_path,
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
