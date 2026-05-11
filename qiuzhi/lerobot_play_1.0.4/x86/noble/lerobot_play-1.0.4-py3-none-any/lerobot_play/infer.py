#!/usr/bin/env python3
"""
AIRBOT Play 推理子系统

支持4种具身模型推理：ACT, DP, PI0, SmolVLA
支持同步和异步推理模式
"""

import argparse
import json
import os
import sys
import time
import threading
import tempfile
from dataclasses import fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
import draccus

from lerobot.cameras.configs import Cv2Rotation
from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.act.modeling_act import ACTPolicy
from lerobot.policies.diffusion.modeling_diffusion import DiffusionPolicy
from lerobot.policies.pi0.modeling_pi0 import PI0Policy
from lerobot.policies.pi05.modeling_pi05 import PI05Policy
from lerobot.policies.groot.modeling_groot import GrootPolicy
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.utils.control_utils import init_keyboard_listener
from lerobot.utils.utils import log_say, init_logging
from lerobot.utils.visualization_utils import init_rerun
from lerobot.scripts.lerobot_record import record_loop
from lerobot.processor import make_default_processors

# 异步推理相关导入
from lerobot.async_inference.configs import RobotClientConfig
from lerobot.async_inference.helpers import visualize_action_queue_size

from .async_inference.robot_client import RobotClient
from .robots.airbot_play_follower.config_play_follower import AirbotPlayFollowerConfig
from .robots.airbot_ptk_follower.config_PTK_follower import AirbotPTKFollowerConfig
from .robots.airbot_tok2_follower.config_TOK2_follower import AirbotTOK2FollowerConfig
from .robots.airbot_tok4_follower.config_TOK4_follower import AirbotTOK4FollowerConfig
from .robots.quest3_follower.config_quest3_follower import Quest3FollowerConfig
from .robots.pico_follower.config_pico_follower import PicoFollowerConfig
from .robots.pico_follower_single_arm_agibot_o10.config_pico_follower_single_arm_agibot_o10 import (
    PicoFollowerSingleArmAgibotO10Config,
)
from .robots.pico_follower_dual_arm_agibot_o10.config_pico_follower_dual_arm_agibot_o10 import (
    PicoFollowerDualArmAgibotO10Config,
)
from .robots.utils import make_robot_from_config
from .utils.policy_preprocessor import load_observation_rename_map
from .utils.runtime_helpers import build_dataset_features
from .utils.camera_config_parser import parse_camera_configs


SUPPORTED_POLICIES = ("act", "diffusion", "pi0", "pi05", "smolvla", "groot")
O10_ROBOT_TYPES = (
    "pico_follower_single_arm_agibot_o10",
    "pico_follower_dual_arm_agibot_o10",
)
POLICIES_WITHOUT_O10_TACTILE = ("pi0", "pi05")
PEFT_ADAPTER_CONFIG_FILE = "adapter_config.json"
PEFT_ADAPTER_WEIGHT_FILES = ("adapter_model.safetensors", "adapter_model.bin")
PALIGEMMA_TOKENIZER_ENV = "ARM_HAND_TELEOP_PALIGEMMA_TOKENIZER"
DEFAULT_PALIGEMMA_TOKENIZER_PATHS = (
    "~/workspace/models/paligemma-tokenizer",
    "/home/phl/FermiBotNas/models/paligemma-tokenizer",
)


def _parse_cameras(cameras_obj: dict) -> dict:
    """解析相机配置，与 record.py 保持一致"""
    return parse_camera_configs(cameras_obj)


def _validate_model_path(model_path: str) -> bool:
    """验证模型路径有效性"""
    model_path = os.path.expanduser(model_path)
    if not os.path.exists(model_path):
        raise ValueError(f"Model path does not exist: {model_path}")

    # 检查是否为有效的模型目录
    if not os.path.isdir(model_path):
        raise ValueError(f"Model path is not a directory: {model_path}")

    config_path = os.path.join(model_path, "config.json")
    if not os.path.exists(config_path):
        raise ValueError(f"config.json not found in model directory: {model_path}")

    weight_candidates = [
        "pytorch_model.bin",
        "model.safetensors",
        *PEFT_ADAPTER_WEIGHT_FILES,
    ]
    if not any(os.path.exists(os.path.join(model_path, file)) for file in weight_candidates):
        print(
            "Warning: no model or PEFT adapter weight file was found "
            f"in model directory: {model_path}"
        )

    return True


def _get_default_save_path(policy_type: str) -> str:
    """获取默认保存路径"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    home_dir = os.path.expanduser("~")
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    return os.path.join(
        home_dir,
        ".cache",
        "huggingface",
        "lerobot",
        f"{policy_type}_infer_{date_str}_{timestamp_ms}",
    )


def _create_save_directory(save_path: str) -> str:
    """创建保存目录"""
    return os.path.expanduser(save_path)


def _parse_cli_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="AIRBOT Play/PTK inference entrypoint")

    parser.add_argument(
        "--yaml", type=str, default=None, help="Path to inference YAML config file"
    )

    # 必需参数
    parser.add_argument(
        "--policy",
        type=str,
        required=False,
        choices=SUPPORTED_POLICIES,
        help="Policy type",
    )
    parser.add_argument(
        "--task_description",
        type=str,
        required=False,
        help="Task description for inference",
    )
    parser.add_argument(
        "--model_path", type=str, required=False, help="Path to the model directory"
    )

    # 可选参数
    parser.add_argument(
        "--save_data", action="store_true", default=False, help="Save inference results"
    )
    parser.add_argument(
        "--display_data",
        action="store_true",
        default=False,
        help="Visualize inference data with Rerun",
    )
    parser.add_argument(
        "--async_infer",
        action="store_true",
        default=False,
        help="Use async inference",
    )
    parser.add_argument(
        "--num_episodes", type=int, default=1, help="Number of inference episodes"
    )
    parser.add_argument(
        "--episode_time_sec",
        type=int,
        default=100,
        help="Duration of each episode in seconds",
    )
    parser.add_argument("--fps", type=int, default=30, help="Inference FPS")
    parser.add_argument("--device", type=str, default="cuda", help="Compute device")
    parser.add_argument(
        "--server_address",
        type=str,
        default="localhost:8080",
        help="Server address for async inference",
    )
    parser.add_argument(
        "--save_path",
        type=str,
        default=None,
        help="Custom save path for inference results",
    )
    parser.add_argument(
        "--actions_per_chunk",
        type=int,
        default=None,
        help="Async inference actions requested from each policy chunk",
    )
    parser.add_argument(
        "--chunk_size_threshold",
        type=float,
        default=None,
        help="Async inference queue fullness threshold for sending observations",
    )
    parser.add_argument(
        "--debug_visualize_queue_size",
        action="store_true",
        default=False,
        help="Plot async action queue size when inference stops",
    )

    # 机器人配置参数（与 record.py 保持一致）
    parser.add_argument(
        "--robot.type",
        dest="robot_type",
        type=str,
        default="airbot_PTK_follower",
        choices=[
            "airbot_play_follower",
            "airbot_PTK_follower",
            "airbot_TOK2_follower",
            "airbot_TOK4_follower",
            "quest3_follower",
            "pico_follower",
            "pico_follower_single_arm_agibot_o10",
            "pico_follower_dual_arm_agibot_o10",
        ],
        help="Robot type: airbot_play_follower (single arm) or airbot_PTK_follower (dual arm)",
    )
    parser.add_argument(
        "--robot.port",
        dest="robot_port",
        type=str,
        default="can0",
        help="Robot port (for airbot_play_follower)",
    )
    parser.add_argument(
        "--robot.left_arm_port",
        dest="robot_left_arm_port",
        type=str,
        default="can0",
        help="Left arm port (for airbot_PTK_follower)",
    )
    parser.add_argument(
        "--robot.right_arm_port",
        dest="robot_right_arm_port",
        type=str,
        default="can1",
        help="Right arm port (for airbot_PTK_follower)",
    )
    parser.add_argument(
        "--robot.id", dest="robot_id", type=str, default="PTK_follower", help="Robot ID"
    )
    parser.add_argument(
        "--robot.cameras",
        dest="robot_cameras",
        type=str,
        default=None,
        help="Camera configuration as JSON string",
    )
    parser.add_argument(
        "--robot.handedness",
        dest="robot_handedness",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--robot.channel_mode",
        dest="robot_channel_mode",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--robot.device_id",
        dest="robot_device_id",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--robot.canfd_id",
        dest="robot_canfd_id",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--robot.channel_id",
        dest="robot_channel_id",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--robot.reset_poses_path",
        dest="robot_reset_poses_path",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--robot.reset_gesture",
        dest="robot_reset_gesture",
        type=str,
        default=None,
    )

    return parser.parse_args()


def _load_yaml(path: str) -> dict:
    with open(Path(path).expanduser(), encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _load_config(cli: argparse.Namespace) -> dict:
    if cli.yaml:
        cfg = _load_yaml(cli.yaml)

        infer_cfg = cfg.setdefault("infer", {})
        if cli.policy is not None:
            infer_cfg["policy"] = cli.policy
        if cli.task_description is not None:
            infer_cfg["task_description"] = cli.task_description
        if cli.model_path is not None:
            infer_cfg["model_path"] = cli.model_path
        if cli.save_data:
            infer_cfg["save_data"] = True
        if cli.display_data:
            infer_cfg["display_data"] = True
        if cli.async_infer:
            infer_cfg["async_infer"] = True
        if cli.num_episodes != 1:
            infer_cfg["num_episodes"] = cli.num_episodes
        if cli.episode_time_sec != 100:
            infer_cfg["episode_time_sec"] = cli.episode_time_sec
        if cli.fps != 30:
            infer_cfg["fps"] = cli.fps
        if cli.device != "cuda":
            infer_cfg["device"] = cli.device
        if cli.server_address != "localhost:8080":
            infer_cfg["server_address"] = cli.server_address
        if cli.save_path is not None:
            infer_cfg["save_path"] = cli.save_path
        if cli.actions_per_chunk is not None:
            infer_cfg["actions_per_chunk"] = cli.actions_per_chunk
        if cli.chunk_size_threshold is not None:
            infer_cfg["chunk_size_threshold"] = cli.chunk_size_threshold
        if cli.debug_visualize_queue_size:
            infer_cfg["debug_visualize_queue_size"] = True

        robot_cfg = cfg.setdefault("robot", {})
        if cli.robot_type != "airbot_PTK_follower":
            robot_cfg["type"] = cli.robot_type
        if cli.robot_port != "can0":
            robot_cfg["port"] = cli.robot_port
        if cli.robot_left_arm_port != "can0":
            robot_cfg["left_arm_port"] = cli.robot_left_arm_port
        if cli.robot_right_arm_port != "can1":
            robot_cfg["right_arm_port"] = cli.robot_right_arm_port
        if cli.robot_id != "PTK_follower":
            robot_cfg["id"] = cli.robot_id
        if cli.robot_cameras is not None:
            robot_cfg["cameras"] = yaml.safe_load(cli.robot_cameras)
        if cli.robot_handedness is not None:
            robot_cfg["handedness"] = cli.robot_handedness
        if cli.robot_channel_mode is not None:
            robot_cfg["channel_mode"] = cli.robot_channel_mode
        if cli.robot_device_id is not None:
            robot_cfg["device_id"] = cli.robot_device_id
        if cli.robot_canfd_id is not None:
            robot_cfg["canfd_id"] = cli.robot_canfd_id
        if cli.robot_channel_id is not None:
            robot_cfg["channel_id"] = cli.robot_channel_id
        if cli.robot_reset_poses_path is not None:
            robot_cfg["reset_poses_path"] = cli.robot_reset_poses_path
        if cli.robot_reset_gesture is not None:
            robot_cfg["reset_gesture"] = cli.robot_reset_gesture

        return cfg

    return {
        "infer": {
            "policy": cli.policy,
            "task_description": cli.task_description,
            "model_path": cli.model_path,
            "save_data": cli.save_data,
            "display_data": cli.display_data,
            "async_infer": cli.async_infer,
            "num_episodes": cli.num_episodes,
            "episode_time_sec": cli.episode_time_sec,
            "fps": cli.fps,
            "device": cli.device,
            "server_address": cli.server_address,
            "save_path": cli.save_path,
            "actions_per_chunk": cli.actions_per_chunk,
            "chunk_size_threshold": cli.chunk_size_threshold
            if cli.chunk_size_threshold is not None
            else 0.5,
            "debug_visualize_queue_size": cli.debug_visualize_queue_size,
        },
        "robot": {
            "type": cli.robot_type,
            "port": cli.robot_port,
            "left_arm_port": cli.robot_left_arm_port,
            "right_arm_port": cli.robot_right_arm_port,
            "id": cli.robot_id,
            "cameras": yaml.safe_load(cli.robot_cameras)
            if cli.robot_cameras is not None
            else None,
            "handedness": cli.robot_handedness,
            "channel_mode": cli.robot_channel_mode,
            "device_id": cli.robot_device_id,
            "canfd_id": cli.robot_canfd_id,
            "channel_id": cli.robot_channel_id,
            "reset_poses_path": cli.robot_reset_poses_path,
            "reset_gesture": cli.robot_reset_gesture,
        },
    }


def _config_to_args(cfg: dict) -> argparse.Namespace:
    infer_cfg = cfg.get("infer", {})
    robot_cfg = cfg.get("robot", {})

    robot_cameras = robot_cfg.get("cameras")

    return argparse.Namespace(
        yaml=None,
        policy=infer_cfg.get("policy"),
        task_description=infer_cfg.get("task_description"),
        model_path=infer_cfg.get("model_path"),
        save_data=bool(infer_cfg.get("save_data", False)),
        display_data=bool(infer_cfg.get("display_data", False)),
        async_infer=bool(infer_cfg.get("async_infer", False)),
        num_episodes=int(infer_cfg.get("num_episodes", 1)),
        episode_time_sec=int(infer_cfg.get("episode_time_sec", 100)),
        fps=int(infer_cfg.get("fps", 30)),
        device=infer_cfg.get("device", "cuda"),
        server_address=infer_cfg.get("server_address", "localhost:8080"),
        save_path=infer_cfg.get("save_path"),
        actions_per_chunk=int(infer_cfg.get("actions_per_chunk", 0) or 0),
        chunk_size_threshold=float(infer_cfg.get("chunk_size_threshold", 0.5)),
        debug_visualize_queue_size=bool(
            infer_cfg.get("debug_visualize_queue_size", False)
        ),
        robot_type=robot_cfg.get("type", "airbot_PTK_follower"),
        robot_port=robot_cfg.get("port", "can0"),
        robot_left_arm_port=robot_cfg.get("left_arm_port", "can0"),
        robot_right_arm_port=robot_cfg.get("right_arm_port", "can1"),
        robot_id=robot_cfg.get("id", "PTK_follower"),
        robot_cameras=json.dumps(robot_cameras) if robot_cameras is not None else None,
        robot_handedness=robot_cfg.get("handedness"),
        robot_channel_mode=robot_cfg.get("channel_mode"),
        robot_device_id=robot_cfg.get("device_id"),
        robot_canfd_id=robot_cfg.get("canfd_id"),
        robot_channel_id=robot_cfg.get("channel_id"),
        robot_reset_poses_path=robot_cfg.get("reset_poses_path"),
        robot_reset_gesture=robot_cfg.get("reset_gesture"),
        robot_gripper_gesture=robot_cfg.get("gripper_gesture"),
        robot_left=robot_cfg.get("left", {}),
        robot_right=robot_cfg.get("right", {}),
        robot_enable_hand=robot_cfg.get("enable_hand", True),
        robot_allow_camera_read_failures=robot_cfg.get("allow_camera_read_failures", False),
        robot_include_eef_pose=robot_cfg.get("include_eef_pose", True),
        robot_action_control_mode=robot_cfg.get("action_control_mode", "joint"),
        robot_hand_action_mode=robot_cfg.get("hand_action_mode", "dexterous_10d"),
        robot_tactile_mode=robot_cfg.get("tactile_mode", "none"),
    )


def _validate_args(args: argparse.Namespace) -> None:
    """验证命令行参数"""
    if not args.policy:
        raise ValueError("infer.policy is required")
    if args.policy not in SUPPORTED_POLICIES:
        raise ValueError(f"Unsupported policy type: {args.policy}")
    if not args.task_description:
        raise ValueError("infer.task_description is required")
    if not args.model_path:
        raise ValueError("infer.model_path is required")
    if args.num_episodes <= 0:
        raise ValueError("infer.num_episodes must be positive")
    if args.episode_time_sec <= 0:
        raise ValueError("infer.episode_time_sec must be positive")
    if args.fps <= 0:
        raise ValueError("infer.fps must be positive")
    if args.actions_per_chunk < 0:
        raise ValueError("infer.actions_per_chunk must be non-negative")
    if not 0.0 <= args.chunk_size_threshold <= 1.0:
        raise ValueError("infer.chunk_size_threshold must be in [0, 1]")
    args.model_path = os.path.expanduser(args.model_path)
    if args.save_path:
        args.save_path = os.path.expanduser(args.save_path)

    # 验证异步推理支持
    if args.async_infer and args.policy not in SUPPORTED_POLICIES:
        raise ValueError(f"Async inference not supported for policy: {args.policy}")

    # 验证模型路径
    _validate_model_path(args.model_path)

    # 验证相机配置
    if args.robot_cameras:
        try:
            cameras_config = json.loads(args.robot_cameras)
            _parse_cameras(cameras_config)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid camera configuration: {e}")


def _apply_policy_robot_schema_defaults(args: argparse.Namespace) -> None:
    """Apply policy-specific robot schema defaults before constructing hardware."""
    if (
        args.policy in POLICIES_WITHOUT_O10_TACTILE
        and args.robot_type in O10_ROBOT_TYPES
        and args.robot_tactile_mode != "none"
    ):
        log_say(
            f"{args.policy} inference on Agibot O10 uses visual + proprioception only; "
            f"overriding robot.tactile_mode={args.robot_tactile_mode!r} to 'none'."
        )
        args.robot_tactile_mode = "none"


def _feature_shape(feature: Any) -> tuple[int, ...]:
    shape = feature.get("shape") if isinstance(feature, dict) else getattr(feature, "shape")
    return tuple(int(dim) for dim in shape)


def _policy_feature_names(features: dict[str, Any], feature_type: str) -> set[str]:
    return {
        name
        for name, feature in features.items()
        if str(getattr(feature, "type", "")).split(".")[-1] == feature_type
        or (
            isinstance(feature, dict)
            and str(feature.get("type", "")).split(".")[-1] == feature_type
        )
    }


def _validate_policy_robot_feature_compatibility(
    policy_or_config: Any,
    robot_features: dict[str, dict],
    model_path: str,
    observation_rename_map: dict[str, str] | None = None,
) -> None:
    """Fail early when the checkpoint schema does not match this robot run."""
    policy_config = getattr(policy_or_config, "config", policy_or_config)
    policy_input_features = getattr(policy_config, "input_features", {}) or {}
    policy_output_features = getattr(policy_config, "output_features", {}) or {}
    policy_type = getattr(policy_config, "type", None)

    def _allows_vla_padding(key: str, policy_dim: int, robot_dim: int) -> bool:
        if policy_type not in {"pi0", "pi05"} or robot_dim > policy_dim:
            return False
        max_dim_name = "max_state_dim" if key == "observation.state" else "max_action_dim"
        return policy_dim == getattr(policy_config, max_dim_name, None)

    mismatches: list[str] = []
    for key in ("observation.state", "action"):
        policy_features = policy_input_features if key == "observation.state" else policy_output_features
        if key not in policy_features or key not in robot_features:
            continue

        policy_dim = _feature_shape(policy_features[key])[0]
        robot_dim = _feature_shape(robot_features[key])[0]
        if policy_dim != robot_dim and not _allows_vla_padding(key, policy_dim, robot_dim):
            mismatches.append(f"{key}: model expects {policy_dim}D, robot exposes {robot_dim}D")

    expected_image_keys = _policy_feature_names(policy_input_features, "VISUAL")
    robot_image_keys = {
        key
        for key, feature in robot_features.items()
        if feature.get("dtype") in {"image", "video"}
    }
    if observation_rename_map:
        robot_image_keys = {
            observation_rename_map.get(key, key)
            for key in robot_image_keys
        }
    missing_image_keys = sorted(expected_image_keys - robot_image_keys)
    if missing_image_keys:
        mismatches.append(
            "image keys: model expects missing robot observations "
            f"{missing_image_keys}; robot exposes {sorted(robot_image_keys)}"
        )

    if mismatches:
        details = "\n  - ".join(mismatches)
        raise ValueError(
            "Policy checkpoint features do not match the current robot inference schema "
            f"for {model_path}:\n  - {details}\n"
            "Use a checkpoint fine-tuned on a dataset recorded with the same "
            "hand_action_mode, tactile_mode, action_control_mode, and camera keys."
        )


def _load_policy_config(model_path: str, device: str | None) -> PreTrainedConfig:
    config = PreTrainedConfig.from_pretrained(model_path)
    if device:
        config.device = device
    return config


def _load_policy_config_lenient(model_path: str, device: str | None) -> PreTrainedConfig:
    try:
        return _load_policy_config(model_path, device)
    except Exception as original_error:
        config_path = Path(model_path).expanduser() / "config.json"
        if not config_path.exists():
            raise

        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        policy_type = raw_config.get("type")
        if not policy_type:
            raise

        try:
            config_class = PreTrainedConfig.get_choice_class(policy_type)
        except Exception:
            raise original_error

        if not is_dataclass(config_class):
            raise original_error

        valid_fields = {field.name for field in fields(config_class)}
        filtered_config = {
            key: value
            for key, value in raw_config.items()
            if key != "type" and key in valid_fields
        }
        dropped_fields = sorted(set(raw_config) - valid_fields - {"type"})
        if not dropped_fields:
            raise original_error

        log_say(
            f"Ignoring unsupported {policy_type} config fields for inference: "
            f"{dropped_fields}"
        )

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as file:
            json.dump(filtered_config, file)
            filtered_config_path = file.name

        try:
            with draccus.config_type("json"):
                config = draccus.parse(config_class, filtered_config_path, args=[])
        finally:
            os.unlink(filtered_config_path)

        if device:
            config.device = device
        return config


def _is_local_peft_adapter_path(model_path: str) -> bool:
    model_path = os.path.expanduser(model_path)
    if not os.path.isdir(model_path):
        return False

    has_adapter_config = os.path.exists(
        os.path.join(model_path, PEFT_ADAPTER_CONFIG_FILE)
    )
    has_adapter_weights = any(
        os.path.exists(os.path.join(model_path, file))
        for file in PEFT_ADAPTER_WEIGHT_FILES
    )
    return has_adapter_config and has_adapter_weights


def _load_base_policy(policy_type: str, model_path: str, device: str | None = None):
    config_path = Path(model_path).expanduser() / "config.json"
    from_pretrained_kwargs = {}
    if device is not None and config_path.exists():
        from_pretrained_kwargs["config"] = _load_policy_config_lenient(model_path, device)

    if policy_type == "act":
        return ACTPolicy.from_pretrained(model_path, **from_pretrained_kwargs)
    if policy_type == "diffusion":
        return DiffusionPolicy.from_pretrained(model_path, **from_pretrained_kwargs)
    if policy_type == "pi0":
        return PI0Policy.from_pretrained(model_path, **from_pretrained_kwargs)
    if policy_type == "pi05":
        return PI05Policy.from_pretrained(model_path, **from_pretrained_kwargs)
    if policy_type == "groot":
        return GrootPolicy.from_pretrained(model_path, **from_pretrained_kwargs)
    if policy_type == "smolvla":
        return SmolVLAPolicy.from_pretrained(model_path, **from_pretrained_kwargs)
    raise ValueError(f"Unsupported policy type: {policy_type}")


def _set_policy_device(policy, device: str | None) -> None:
    if not device:
        return

    policy.to(device)
    policy_config = getattr(policy, "config", None)
    if policy_config is not None and hasattr(policy_config, "device"):
        policy_config.device = device


def _policy_device(policy) -> str:
    policy_config = getattr(policy, "config", None)
    return getattr(policy_config, "device", "unknown")


def _ensure_lerobot_policy_config(policy, base_policy) -> None:
    policy_config = getattr(policy, "config", None)
    if policy_config is None or not hasattr(policy_config, "input_features"):
        policy.config = base_policy.config


def _load_peft_policy(policy_type: str, adapter_path: str):
    try:
        from peft import PeftConfig, PeftModel
    except ImportError as exc:
        raise RuntimeError(
            "PEFT/LoRA adapter checkpoint detected, but package 'peft' is not installed."
        ) from exc

    peft_config = PeftConfig.from_pretrained(adapter_path)
    base_model_path = getattr(peft_config, "base_model_name_or_path", None)
    if not base_model_path:
        raise ValueError(
            "PEFT adapter_config.json does not contain base_model_name_or_path; "
            "cannot load the base policy for inference."
        )

    log_say(
        f"Detected PEFT adapter at {adapter_path}; "
        f"loading base {policy_type} policy from {base_model_path}"
    )
    base_policy = _load_base_policy(policy_type, base_model_path)
    policy = PeftModel.from_pretrained(base_policy, adapter_path, config=peft_config)
    _ensure_lerobot_policy_config(policy, base_policy)
    return policy


def _validate_policy_type_matches_checkpoint(
    policy_type: str,
    policy_config: PreTrainedConfig,
    model_path: str,
) -> None:
    if policy_config.type != policy_type:
        raise ValueError(
            f"infer.policy is {policy_type!r}, but checkpoint at {model_path} "
            f"has config type {policy_config.type!r}."
        )


def _load_observation_rename_map(model_path: str) -> dict[str, str]:
    return load_observation_rename_map(model_path, logger=log_say)


def _resolve_local_paligemma_tokenizer_path() -> str | None:
    configured_path = os.environ.get(PALIGEMMA_TOKENIZER_ENV)
    candidate_paths = (
        (configured_path,)
        if configured_path
        else DEFAULT_PALIGEMMA_TOKENIZER_PATHS
    )

    for candidate_path in candidate_paths:
        if not candidate_path:
            continue
        tokenizer_path = Path(candidate_path).expanduser()
        if tokenizer_path.is_dir():
            return str(tokenizer_path)

    return None


def _build_policy_preprocessor_overrides(
    policy_type: str,
    device: str,
    observation_rename_map: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {
        "device_processor": {"device": str(device)}
    }

    if observation_rename_map is not None:
        overrides["rename_observations_processor"] = {
            "rename_map": observation_rename_map
        }

    if policy_type in {"pi0", "pi05"}:
        tokenizer_path = _resolve_local_paligemma_tokenizer_path()
        if tokenizer_path:
            overrides["tokenizer_processor"] = {
                "tokenizer_name": tokenizer_path
            }
            log_say(f"Using local PaliGemma tokenizer at {tokenizer_path}")

    return overrides


def _load_and_validate_policy_config(
    policy_type: str,
    model_path: str,
    device: str | None,
    robot_features: dict[str, dict],
) -> PreTrainedConfig:
    policy_config = _load_policy_config_lenient(model_path, device)
    _validate_policy_type_matches_checkpoint(policy_type, policy_config, model_path)
    _validate_policy_robot_feature_compatibility(
        policy_config,
        robot_features,
        model_path,
        observation_rename_map=_load_observation_rename_map(model_path),
    )
    return policy_config


def _load_policy(policy_type: str, model_path: str, device: str):
    """加载策略模型并放到指定 device。

    lerobot 上游 PreTrainedPolicy.from_pretrained 会按保存时的 config.device
    做 policy.to(config.device)，yaml 里 infer.device 原本不起作用。这里显式
    覆盖：from_pretrained 之后再把 policy 移到 device，并同步 config.device
    让后续 make_pre_post_processors 的 device_processor 与实际一致。
    """
    log_say(f"Loading {policy_type} policy from {model_path} (target device: {device})")
    start_time = time.time()

    try:
        if _is_local_peft_adapter_path(model_path):
            policy = _load_peft_policy(policy_type, model_path)
        else:
            policy = _load_base_policy(policy_type, model_path, device)

        _set_policy_device(policy, device)

        load_time = time.time() - start_time
        log_say(
            f"Policy loaded successfully in {load_time:.2f} seconds on {_policy_device(policy)}"
        )
        return policy

    except Exception as e:
        raise RuntimeError(f"Failed to load policy: {e}")


def _reset_to_training_start(robot, model_path: str) -> None:
    """从模型的训练数据集中读取第一帧 state，复位臂和手到该姿态。"""
    from lerobot_play.utils.agibot_o10 import (
        AGIBOT_O10_ARM_FEATURE_NAMES,
        AGIBOT_O10_HAND_FEATURE_NAMES,
    )

    train_config_path = os.path.join(model_path, "train_config.json")
    if not os.path.exists(train_config_path):
        log_say("No train_config.json found, skipping dataset-based reset")
        return

    with open(train_config_path) as f:
        train_cfg = json.load(f)

    dataset_cfg = train_cfg.get("dataset", {})
    dataset_root = dataset_cfg.get("root")
    repo_id = dataset_cfg.get("repo_id", "").split("/")[-1]
    if not dataset_root or not os.path.isdir(dataset_root):
        log_say(f"Training dataset not found at {dataset_root}, skipping reset")
        return

    try:
        ds = LeRobotDataset(repo_id, root=dataset_root, episodes=[0])
        state = ds[0]["observation.state"].tolist()
    except Exception as exc:
        log_say(f"Failed to load training dataset for reset: {exc}")
        return

    arm_dof = len(AGIBOT_O10_ARM_FEATURE_NAMES)
    hand_dof = len(AGIBOT_O10_HAND_FEATURE_NAMES)
    arm_target = state[:arm_dof]
    hand_target = state[arm_dof:arm_dof + hand_dof]

    robot.reset_arm_joint_pos = arm_target
    robot.reset_hand_joint_pos = hand_target
    log_say("Resetting to training dataset episode 0 start pose")
    robot.reset_zero()


def _should_reset_to_training_start(robot) -> bool:
    """Whether infer startup should override the configured reset pose.

    Dual-arm Agibot O10 recording/inference is standardized around the configured
    JSON reset pose. Its robot implementation consumes per-side reset targets
    (`left_reset_*` / `right_reset_*`), so the generic single-arm dataset-based
    override is not the correct startup path there.
    """
    return getattr(robot, "name", None) != "pico_follower_dual_arm_agibot_o10"


def _reset_robot_for_inference_start(robot, model_path: str) -> None:
    if _should_reset_to_training_start(robot):
        _reset_to_training_start(robot, model_path)
        return

    log_say("Resetting to configured reset pose for inference startup")
    robot.return_zero()


def _create_robot_config(args: argparse.Namespace):
    """创建机器人配置"""
    camera_config = {}
    if args.robot_cameras:
        camera_config = _parse_cameras(json.loads(args.robot_cameras))

    if args.robot_type == "airbot_play_follower":
        return AirbotPlayFollowerConfig(
            can_port=args.robot_port,
            id=args.robot_id,
            cameras=camera_config,
        )
    elif args.robot_type == "airbot_PTK_follower":
        return AirbotPTKFollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
            cameras=camera_config,
        )
    elif args.robot_type == "airbot_TOK2_follower":
        return AirbotTOK2FollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
            cameras=camera_config,
        )
    elif args.robot_type == "airbot_TOK4_follower":
        return AirbotTOK4FollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
            cameras=camera_config,
        )
    elif args.robot_type == "quest3_follower":
        return Quest3FollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
            cameras=camera_config,
        )
    elif args.robot_type == "pico_follower":
        return PicoFollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
            cameras=camera_config,
        )
    elif args.robot_type == "pico_follower_single_arm_agibot_o10":
        return PicoFollowerSingleArmAgibotO10Config(
            port=args.robot_port,
            handedness=args.robot_handedness or "right",
            channel_mode=args.robot_channel_mode or "multiChannel",
            device_id=1 if args.robot_device_id is None else args.robot_device_id,
            canfd_id=0 if args.robot_canfd_id is None else args.robot_canfd_id,
            channel_id=args.robot_channel_id,
            reset_poses_path=args.robot_reset_poses_path,
            reset_gesture=args.robot_reset_gesture,
            gripper_gesture=args.robot_gripper_gesture,
            enable_hand=args.robot_enable_hand,
            allow_camera_read_failures=args.robot_allow_camera_read_failures,
            include_eef_pose=args.robot_include_eef_pose,
            action_control_mode=args.robot_action_control_mode,
            hand_action_mode=args.robot_hand_action_mode,
            tactile_mode=args.robot_tactile_mode,
            id=args.robot_id,
            cameras=camera_config,
        )
    elif args.robot_type == "pico_follower_dual_arm_agibot_o10":
        return PicoFollowerDualArmAgibotO10Config(
            left=args.robot_left,
            right=args.robot_right,
            enable_hand=args.robot_enable_hand,
            allow_camera_read_failures=args.robot_allow_camera_read_failures,
            include_eef_pose=args.robot_include_eef_pose,
            action_control_mode=args.robot_action_control_mode,
            hand_action_mode=args.robot_hand_action_mode,
            tactile_mode=args.robot_tactile_mode,
            id=args.robot_id,
            cameras=camera_config,
        )
    else:
        raise ValueError(f"Unsupported robot type: {args.robot_type}")


def _create_dataset(robot, fps: int, save_path: str) -> LeRobotDataset:
    """创建数据集"""
    dataset_root = Path(save_path).expanduser()
    dataset_features = build_dataset_features(
        robot, use_videos=bool(getattr(robot, "cameras", {}))
    )

    return LeRobotDataset.create(
        repo_id=dataset_root.name,
        fps=fps,
        features=dataset_features,
        root=str(dataset_root),
        robot_type=robot.name,
        use_videos=bool(getattr(robot, "cameras", {})),
        image_writer_threads=4,
    )


class _NullDataset:
    """Stub dataset for inference runs that don't save data.

    record_loop only reads .fps/.features and conditionally calls .add_frame;
    using a stub avoids LeRobotDataset.create() spinning up image writer
    threads that fight the inference loop for CPU/IO.
    """

    def __init__(self, features: dict, fps: int):
        self.features = features
        self.fps = fps
        self.meta = type("_Meta", (), {"stats": {}})()

    def add_frame(self, frame): pass
    def save_episode(self): pass
    def wait_all_async_tasks(self): pass
    def finalize(self): pass


def _run_sync_inference(args: argparse.Namespace) -> Dict[str, Any]:
    """运行同步推理"""
    log_say("Starting synchronous inference")
    start_time = time.time()

    # 创建机器人配置
    robot_config = _create_robot_config(args)
    robot = make_robot_from_config(robot_config)
    (
        teleop_action_processor,
        robot_action_processor,
        robot_observation_processor,
    ) = make_default_processors()
    dataset = None
    save_path = None
    save_dataset = bool(args.save_data or args.save_path)

    if save_dataset:
        if args.save_path:
            save_path = args.save_path
        else:
            save_path = _get_default_save_path(args.policy)
        save_path = _create_save_directory(save_path)
        dataset = _create_dataset(robot, args.fps, save_path)
    else:
        dataset = _NullDataset(
            features=build_dataset_features(
                robot, use_videos=bool(getattr(robot, "cameras", {}))
            ),
            fps=args.fps,
        )

    _load_and_validate_policy_config(
        args.policy,
        args.model_path,
        args.device,
        dataset.features,
    )

    # 加载策略
    policy = _load_policy(args.policy, args.model_path, args.device)

    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=policy.config,
        pretrained_path=args.model_path,
        dataset_stats=dataset.meta.stats,
        # The inference device is automatically set to match the detected hardware, overriding any previous device settings from training to ensure compatibility.
        preprocessor_overrides=_build_policy_preprocessor_overrides(
            args.policy,
            str(policy.config.device),
        ),
    )

    # 初始化键盘监听和可视化
    events = {
        "start": False,
        "exit_early": False,
        "rerecord_episode": False,
        "stop_recording": False,
    }
    if args.display_data:
        _, events = init_keyboard_listener()
        init_rerun(session_name="inference")

    # 连接机器人
    robot.connect()
    _reset_robot_for_inference_start(robot, args.model_path)

    try:
        episodes_completed = 0
        for episode_idx in range(args.num_episodes):
            if events.get("stop_recording"):
                log_say(
                    f"stop_recording set before episode {episode_idx + 1}; ending inference"
                )
                break

            log_say(
                f"Running inference episode {episode_idx + 1} of {args.num_episodes}"
            )

            # 运行推理
            record_loop(
                robot=robot,
                events=events,
                fps=args.fps,
                policy=policy,
                preprocessor=preprocessor,  # Pass the pre and post policy processors
                postprocessor=postprocessor,
                dataset=dataset,
                control_time_s=args.episode_time_sec,
                single_task=args.task_description,
                display_data=args.display_data,
                teleop_action_processor=teleop_action_processor,
                robot_action_processor=robot_action_processor,
                robot_observation_processor=robot_observation_processor,
            )

            # 保存数据
            dataset.save_episode()
            episodes_completed += 1

            # 机器人归零
            is_last_episode = episode_idx >= args.num_episodes - 1
            if events.get("stop_recording"):
                log_say("stop_recording set; skipping post-episode reset and ending")
                break
            if not is_last_episode:
                log_say("Resetting robot to zero position")
                robot.return_zero()

        execution_time = time.time() - start_time
        log_say(
            f"Synchronous inference completed in {execution_time:.2f} seconds "
            f"({episodes_completed}/{args.num_episodes} episodes)"
        )

        avg_episode_time = (
            execution_time / episodes_completed if episodes_completed else 0.0
        )

        return {
            "status": "success",
            "policy": args.policy,
            "task": args.task_description,
            "episodes_completed": episodes_completed,
            "data_saved": save_dataset,
            "execution_time": execution_time,
            "save_path": save_path if save_dataset else None,
            "performance_stats": {
                "total_time": execution_time,
                "avg_episode_time": avg_episode_time,
            },
        }

    finally:
        if save_dataset and dataset is not None:
            try:
                dataset.wait_all_async_tasks()
            except Exception as exc:
                log_say(f"Warning: failed to wait for dataset tasks: {exc}")
            try:
                dataset.finalize()
            except Exception as exc:
                log_say(f"Warning: failed to finalize dataset: {exc}")

        try:
            robot.disconnect()
        except Exception as exc:
            log_say(f"Warning: failed to disconnect robot: {exc}")

        for cam in getattr(robot, "cameras", {}).values():
            try:
                cam.disconnect()
            except Exception as exc:
                log_say(f"Warning: failed to disconnect camera: {exc}")


def _run_async_inference(args: argparse.Namespace) -> Dict[str, Any]:
    """运行异步推理"""
    log_say("Starting asynchronous inference")
    start_time = time.time()

    # 创建机器人配置
    robot_config = _create_robot_config(args)
    robot = make_robot_from_config(robot_config)
    robot_features = build_dataset_features(
        robot,
        use_videos=bool(getattr(robot, "cameras", {})),
    )
    _load_and_validate_policy_config(
        args.policy,
        args.model_path,
        args.device,
        robot_features,
    )

    # 创建客户端配置
    client_cfg = RobotClientConfig(
        robot=robot_config,
        server_address=args.server_address,
        policy_device=args.device,
        policy_type=args.policy,
        pretrained_name_or_path=args.model_path,
        chunk_size_threshold=args.chunk_size_threshold,
        actions_per_chunk=args.actions_per_chunk
        or (100 if args.policy == "act" else 50),
        debug_visualize_queue_size=args.debug_visualize_queue_size,
    )
    client_cfg.display_data = args.display_data

    if args.display_data:
        init_rerun(session_name="inference")

    # 创建并启动客户端
    client = RobotClient(client_cfg)
    client_robot = getattr(client, "robot", None)
    if client_robot is not None:
        _reset_robot_for_inference_start(client_robot, args.model_path)

    if not client.start():
        raise RuntimeError("Failed to start RobotClient")

    action_receiver_thread = None

    try:
        # 启动动作接收线程
        action_receiver_thread = threading.Thread(
            target=client.receive_actions, daemon=True
        )
        action_receiver_thread.start()

        # 运行控制循环
        for episode_idx in range(args.num_episodes):
            log_say(
                f"Running async inference episode {episode_idx + 1} of {args.num_episodes}"
            )

            try:
                client.control_loop(
                    args.task_description,
                    control_time_s=args.episode_time_sec,
                )
            except KeyboardInterrupt:
                log_say("Inference interrupted by user")
                break

            # 机器人归零
            if episode_idx < args.num_episodes - 1:  # 不是最后一轮
                log_say("Resetting robot to zero position")
                client.clear_action_queue(advance_action_watermark=True)
                # 异步推理的归零需要特殊处理
                time.sleep(2)  # 等待动作完成

        execution_time = time.time() - start_time
        log_say(f"Asynchronous inference completed in {execution_time:.2f} seconds")

        return {
            "status": "success",
            "policy": args.policy,
            "task": args.task_description,
            "episodes_completed": args.num_episodes,
            "data_saved": False,  # 异步推理暂不支持数据保存
            "execution_time": execution_time,
            "save_path": None,
            "performance_stats": {
                "total_time": execution_time,
                "avg_episode_time": execution_time / args.num_episodes,
            },
        }

    except KeyboardInterrupt:
        log_say("Inference interrupted by user")

    finally:
        # 清理资源
        client.stop()
        if action_receiver_thread is not None:
            action_receiver_thread.join(timeout=5.0)
        if args.debug_visualize_queue_size:
            visualize_action_queue_size(client.action_queue_size)


def main():
    """主函数"""
    init_logging()

    try:
        # 解析命令行参数
        cli_args = _parse_cli_args()
        cfg = _load_config(cli_args)
        args = _config_to_args(cfg)
        _apply_policy_robot_schema_defaults(args)

        # 验证参数
        _validate_args(args)

        log_say(f"Starting inference with policy: {args.policy}")
        log_say(f"Task description: {args.task_description}")
        log_say(f"Model path: {args.model_path}")
        log_say(f"Async inference: {args.async_infer}")
        log_say(f"Number of episodes: {args.num_episodes}")

        # 运行推理
        if args.async_infer:
            result = _run_async_inference(args)
        else:
            result = _run_sync_inference(args)

        # 输出结果
        print(json.dumps(result, indent=2))

    except Exception as e:
        error_result = {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "suggestion": "Please check your configuration and try again",
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
