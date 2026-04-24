from pathlib import Path
import sys
import types

import pytest


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
fake_mmk2_kdl = types.ModuleType("mmk2_kdl_py")
fake_mmk2_kdl.ArmKdlNumerical = object

sys.modules.setdefault("airbot_hardware_py", fake_airbot_hardware)
sys.modules.setdefault("mmk2_kdl_py", fake_mmk2_kdl)

from lerobot_play.infer import (
    _config_to_args,
    _create_dataset,
    _create_robot_config,
    _create_save_directory,
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
