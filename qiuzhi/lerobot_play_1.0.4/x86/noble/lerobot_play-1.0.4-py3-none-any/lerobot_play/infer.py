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
from datetime import datetime
from typing import Dict, Any, Optional

import shutil
import yaml

from lerobot.cameras.configs import ColorMode, Cv2Rotation
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from lerobot.policies.factory import make_pre_post_processors
from lerobot.utils.utils import log_say, init_logging
from lerobot.utils.visualization_utils import init_rerun
from lerobot.processor import make_default_processors

# 异步推理相关导入
from lerobot.async_inference.configs import RobotClientConfig
from lerobot.async_inference.helpers import visualize_action_queue_size

from .robots.airbot_play_follower.config_play_follower import AirbotPlayFollowerConfig
from .robots.airbot_ptk_follower.config_PTK_follower import AirbotPTKFollowerConfig
from .robots.airbot_tok2_follower.config_TOK2_follower import AirbotTOK2FollowerConfig
from .robots.airbot_tok4_follower.config_TOK4_follower import AirbotTOK4FollowerConfig
from .robots.quest3_follower.config_quest3_follower import Quest3FollowerConfig
from .robots.pico_follower.config_pico_follower import PicoFollowerConfig
from .robots.pico_follower_single_arm_agibot_o10.config_pico_follower_single_arm_agibot_o10 import (
    PicoFollowerSingleArmAgibotO10Config,
)
from .robots.utils import make_robot_from_config
from .utils.control_utils import init_keyboard_listener
from .utils.lerobot_dataset import LeRobotDataset
from .utils.lerobot_record import record_loop
from .utils.runtime_helpers import (
    build_dataset_features,
    is_incomplete_dataset_root,
    prepare_dataset_root_for_recording,
    resolve_dataset_target,
)


def _parse_cameras(cameras_obj: dict) -> dict:
    """解析相机配置，与 record.py 保持一致"""
    parsed: dict = {}
    for name, cfg in (cameras_obj or {}).items():
        cam_type = cfg.get("type")
        if cam_type == "opencv":
            parsed[name] = OpenCVCameraConfig(
                index_or_path=cfg.get("index_or_path", cfg.get("camera_index")),
                fps=int(cfg.get("fps", 30)),
                width=int(cfg.get("width", 640)),
                height=int(cfg.get("height", 480)),
                rotation=Cv2Rotation[cfg.get("rotation", "NO_ROTATION")],
            )
        elif cam_type == "realsense":
            parsed[name] = RealSenseCameraConfig(
                serial_number_or_name=str(cfg.get("serial_number_or_name", "")),
                fps=int(cfg.get("fps", 30)),
                width=int(cfg.get("width", 640)),
                height=int(cfg.get("height", 480)),
                color_mode=ColorMode[cfg.get("color_mode", "RGB")],
                use_depth=bool(cfg.get("use_depth", False)),
                rotation=Cv2Rotation[cfg.get("rotation", "NO_ROTATION")],
            )
        else:
            raise ValueError(f"Unsupported camera type: {cam_type}")
    return parsed


def _load_camera_config(cameras_value: Any) -> dict:
    if not cameras_value:
        return {}

    if isinstance(cameras_value, dict):
        return cameras_value

    if isinstance(cameras_value, str):
        try:
            return json.loads(cameras_value)
        except json.JSONDecodeError:
            loaded = yaml.safe_load(cameras_value)
            return loaded or {}

    raise ValueError(f"Unsupported camera configuration value: {type(cameras_value)}")


def _validate_model_path(model_path: str) -> bool:
    """验证模型路径有效性"""
    if not os.path.exists(model_path):
        raise ValueError(f"Model path does not exist: {model_path}")

    # 检查是否为有效的模型目录
    if not os.path.isdir(model_path):
        raise ValueError(f"Model path is not a directory: {model_path}")

    # 检查是否包含必要的模型文件
    required_files = ["config.json", "pytorch_model.bin"]
    for file in required_files:
        if not os.path.exists(os.path.join(model_path, file)):
            print(f"Warning: {file} not found in model directory")

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


def _parse_cli_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="AIRBOT Play/PTK inference entrypoint")
    parser.add_argument(
        "--yaml",
        type=str,
        default=None,
        help="Path to inference YAML config file",
    )

    # 必需参数
    parser.add_argument(
        "--policy",
        type=str,
        required=False,
        choices=["act", "diffusion", "pi0", "pi05", "smolvla", "groot"],
        help="Policy type. Required unless --yaml is provided.",
    )
    parser.add_argument(
        "--task_description",
        type=str,
        required=False,
        help="Task description for inference. Required unless --yaml is provided.",
    )
    parser.add_argument(
        "--model_path",
        type=str,
        required=False,
        help="Path to the model directory. Required unless --yaml is provided.",
    )

    # 可选参数
    parser.add_argument(
        "--save_data", action="store_true", default=False, help="Save inference results"
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
        help="Handedness for single-arm Agibot O10 follower",
    )
    parser.add_argument(
        "--robot.channel_mode",
        dest="robot_channel_mode",
        type=str,
        default=None,
        help="Agibot O10 channel mode",
    )
    parser.add_argument(
        "--robot.device_id",
        dest="robot_device_id",
        type=int,
        default=None,
        help="Agibot O10 device id",
    )
    parser.add_argument(
        "--robot.canfd_id",
        dest="robot_canfd_id",
        type=int,
        default=None,
        help="Agibot O10 CANFD id",
    )
    parser.add_argument(
        "--robot.channel_id",
        dest="robot_channel_id",
        type=int,
        default=None,
        help="Agibot O10 channel id",
    )

    return parser.parse_args()


def _load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _load_config(cli: argparse.Namespace) -> dict:
    if cli.yaml:
        return _load_yaml(cli.yaml)

    return {
        "infer": {
            "policy": cli.policy,
            "task_description": cli.task_description,
            "model_path": cli.model_path,
            "save_data": cli.save_data,
            "async_infer": cli.async_infer,
            "num_episodes": cli.num_episodes,
            "episode_time_sec": cli.episode_time_sec,
            "fps": cli.fps,
            "device": cli.device,
            "server_address": cli.server_address,
            "save_path": cli.save_path,
        },
        "robot": {
            "type": cli.robot_type,
            "port": cli.robot_port,
            "left_arm_port": cli.robot_left_arm_port,
            "right_arm_port": cli.robot_right_arm_port,
            "id": cli.robot_id,
            "cameras": cli.robot_cameras,
            "handedness": cli.robot_handedness,
            "channel_mode": cli.robot_channel_mode,
            "device_id": cli.robot_device_id,
            "canfd_id": cli.robot_canfd_id,
            "channel_id": cli.robot_channel_id,
        },
    }


def _config_to_args(cfg: dict) -> argparse.Namespace:
    infer_cfg = cfg.get("infer", {})
    robot_cfg = cfg.get("robot", {})

    return argparse.Namespace(
        yaml=None,
        policy=infer_cfg.get("policy"),
        task_description=infer_cfg.get("task_description"),
        model_path=infer_cfg.get("model_path"),
        save_data=bool(infer_cfg.get("save_data", False)),
        async_infer=bool(infer_cfg.get("async_infer", False)),
        num_episodes=int(infer_cfg.get("num_episodes", 1)),
        episode_time_sec=int(infer_cfg.get("episode_time_sec", 100)),
        fps=int(infer_cfg.get("fps", 30)),
        device=infer_cfg.get("device", "cuda"),
        server_address=infer_cfg.get("server_address", "localhost:8080"),
        save_path=infer_cfg.get("save_path"),
        robot_type=robot_cfg.get("type", "airbot_PTK_follower"),
        robot_port=robot_cfg.get("port", "can0"),
        robot_left_arm_port=robot_cfg.get("left_arm_port", "can0"),
        robot_right_arm_port=robot_cfg.get("right_arm_port", "can1"),
        robot_id=robot_cfg.get("id", "PTK_follower"),
        robot_cameras=robot_cfg.get("cameras"),
        robot_handedness=robot_cfg.get("handedness"),
        robot_channel_mode=robot_cfg.get("channel_mode"),
        robot_device_id=robot_cfg.get("device_id"),
        robot_canfd_id=robot_cfg.get("canfd_id"),
        robot_channel_id=robot_cfg.get("channel_id"),
    )


def _validate_args(args: argparse.Namespace) -> None:
    """验证命令行参数"""
    for required_field in ["policy", "task_description", "model_path"]:
        if not getattr(args, required_field, None):
            raise ValueError(f"{required_field} is required")

    # 验证异步推理支持
    if args.async_infer and args.policy not in [
        "act",
        "diffusion",
        "smolvla",
        "pi0",
        "pi05",
        "groot",
    ]:
        raise ValueError(f"Async inference not supported for policy: {args.policy}")

    # 验证模型路径
    _validate_model_path(args.model_path)

    # 验证相机配置
    if args.robot_cameras:
        try:
            cameras_config = _load_camera_config(args.robot_cameras)
            _parse_cameras(cameras_config)
        except ValueError as e:
            raise ValueError(f"Invalid camera configuration: {e}")


def _load_policy(policy_type: str, model_path: str, device: str):
    """加载策略模型"""
    log_say(f"Loading {policy_type} policy from {model_path}")
    start_time = time.time()

    try:
        if policy_type == "act":
            from lerobot.policies.act.modeling_act import ACTPolicy

            policy = ACTPolicy.from_pretrained(model_path)
        elif policy_type == "diffusion":
            from lerobot.policies.diffusion.modeling_diffusion import DiffusionPolicy

            policy = DiffusionPolicy.from_pretrained(model_path)
        elif policy_type == "pi0":
            from lerobot.policies.pi0.modeling_pi0 import PI0Policy

            policy = PI0Policy.from_pretrained(model_path)
        elif policy_type == "pi05":
            from lerobot.policies.pi05.modeling_pi05 import PI05Policy

            policy = PI05Policy.from_pretrained(model_path)
        elif policy_type == "groot":
            from lerobot.policies.groot.modeling_groot import GrootPolicy

            policy = GrootPolicy.from_pretrained(model_path)
        elif policy_type == "smolvla":
            from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

            policy = SmolVLAPolicy.from_pretrained(model_path)
        else:
            raise ValueError(f"Unsupported policy type: {policy_type}")

        if hasattr(policy, "config") and hasattr(policy.config, "device"):
            policy.config.device = device
        if hasattr(policy, "to"):
            policy.to(device)

        load_time = time.time() - start_time
        log_say(f"Policy loaded successfully in {load_time:.2f} seconds")
        return policy

    except Exception as e:
        raise RuntimeError(f"Failed to load policy: {e}")


def _create_robot_config(args: argparse.Namespace):
    """创建机器人配置"""
    camera_config = {}
    if args.robot_cameras:
        camera_config = _parse_cameras(_load_camera_config(args.robot_cameras))

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
            id=args.robot_id,
            cameras=camera_config,
        )
    else:
        raise ValueError(f"Unsupported robot type: {args.robot_type}")


def _create_dataset(robot, fps: int, repo_id: str, dataset_root: str) -> LeRobotDataset:
    """创建数据集"""
    use_videos = bool(robot.cameras)
    dataset_features = build_dataset_features(robot, use_videos=use_videos)

    return LeRobotDataset.create(
        repo_id=repo_id,
        fps=fps,
        features=dataset_features,
        root=dataset_root,
        robot_type=robot.name,
        use_videos=use_videos,
        image_writer_threads=4,
    )


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
    save_target = None
    dataset = None
    robot_connected = False

    try:
        # 加载策略
        policy = _load_policy(args.policy, args.model_path, args.device)

        save_target = resolve_dataset_target(
            path=args.save_path or _get_default_save_path(args.policy)
        )
        had_incomplete_dataset = is_incomplete_dataset_root(save_target.root)
        prepare_dataset_root_for_recording(
            repo_id=save_target.repo_id,
            root=save_target.root,
        )
        if had_incomplete_dataset:
            log_say(f"Removed stale incomplete inference dataset: {save_target.root}")
        if args.save_data:
            log_say(f"Inference data will be saved to: {save_target.root}")

        # 创建数据集
        dataset = _create_dataset(
            robot,
            args.fps,
            repo_id=save_target.repo_id,
            dataset_root=str(save_target.root),
        )

        preprocessor, postprocessor = make_pre_post_processors(
            policy_cfg=policy.config,
            pretrained_path=args.model_path,
            dataset_stats=dataset.meta.stats,
            # The inference device is automatically set to match the detected hardware, overriding any previous device settings from training to ensure compatibility.
            preprocessor_overrides={
                "device_processor": {"device": str(policy.config.device)}
            },
        )

        # 初始化键盘监听和可视化
        _, events = init_keyboard_listener()
        if args.save_data:
            init_rerun(session_name="inference")

        # 连接机器人
        robot.connect()
        robot_connected = True

        for episode_idx in range(args.num_episodes):
            log_say(
                f"Running inference episode {episode_idx + 1} of {args.num_episodes}"
            )

            # 运行推理
            record_loop(
                robot=robot,
                events=events,
                fps=args.fps,
                policy=policy,
                preprocessor=preprocessor,
                postprocessor=postprocessor,
                dataset=dataset,
                control_time_s=args.episode_time_sec,
                single_task=args.task_description,
                display_data=False,
                teleop_action_processor=teleop_action_processor,
                robot_action_processor=robot_action_processor,
                robot_observation_processor=robot_observation_processor,
            )

            dataset.save_episode()

            if episode_idx < args.num_episodes - 1:
                log_say("Resetting robot to zero position")
                robot.return_zero()

        execution_time = time.time() - start_time
        log_say(f"Synchronous inference completed in {execution_time:.2f} seconds")

        return {
            "status": "success",
            "policy": args.policy,
            "task": args.task_description,
            "episodes_completed": args.num_episodes,
            "data_saved": args.save_data,
            "execution_time": execution_time,
            "save_path": str(save_target.root) if args.save_data else None,
            "performance_stats": {
                "total_time": execution_time,
                "avg_episode_time": execution_time / args.num_episodes,
            },
        }

    finally:
        # 清理资源
        for cam in getattr(robot, "cameras", {}).values():
            try:
                cam.disconnect()
            except Exception:
                pass
        if dataset is not None:
            try:
                dataset.wait_all_async_tasks()
            except Exception as exc:
                log_say(f"Warning: failed to wait for dataset tasks: {exc}")
            try:
                dataset.finalize()
            except Exception as exc:
                log_say(f"Warning: failed to finalize dataset: {exc}")
        if robot_connected:
            try:
                robot.disconnect()
            except Exception as exc:
                log_say(f"Warning: failed to disconnect robot: {exc}")
        if not args.save_data and save_target is not None:
            shutil.rmtree(save_target.root, ignore_errors=True)


def _run_async_inference(args: argparse.Namespace) -> Dict[str, Any]:
    """运行异步推理"""
    from .async_inference.robot_client import RobotClient

    log_say("Starting asynchronous inference")
    start_time = time.time()

    # 创建机器人配置
    robot_config = _create_robot_config(args)

    # 创建客户端配置
    client_cfg = RobotClientConfig(
        robot=robot_config,
        server_address=args.server_address,
        policy_device=args.device,
        policy_type=args.policy,
        pretrained_name_or_path=args.model_path,
        chunk_size_threshold=0.5,
        actions_per_chunk=100 if args.policy == "act" else 50,
        debug_visualize_queue_size=False,
    )

    # 创建并启动客户端
    client = RobotClient(client_cfg)

    if not client.start():
        raise RuntimeError("Failed to start RobotClient")

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
                client.control_loop(args.task_description)
            except KeyboardInterrupt:
                log_say("Inference interrupted by user")
                break

            # 机器人归零
            if episode_idx < args.num_episodes - 1:  # 不是最后一轮
                log_say("Resetting robot to zero position")
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
        client.stop()
        # action_receiver_thread.join()
        # (Optionally) plot the action queue size
        visualize_action_queue_size(client.action_queue_size)

    finally:
        # 清理资源
        client.stop()
        # action_receiver_thread.join(timeout=5.0)
        visualize_action_queue_size(client.action_queue_size)


def main():
    """主函数"""
    init_logging()

    try:
        # 解析命令行参数
        cli_args = _parse_cli_args()
        cfg = _load_config(cli_args)
        args = _config_to_args(cfg)

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
