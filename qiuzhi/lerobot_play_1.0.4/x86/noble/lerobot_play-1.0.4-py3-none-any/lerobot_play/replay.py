#!/usr/bin/env python3
"""
AIRBOT Play 数据回放子系统

支持两种机器人类型的数据回放：airbot_play_follower 和 airbot_PTK_follower
支持本地数据集回放
"""

import argparse
import time
from typing import Dict, Any

import yaml

from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import log_say, init_logging

from .utils.lerobot_dataset import LeRobotDataset
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
from .utils.runtime_helpers import decode_replay_action, resolve_dataset_target


def _parse_cli_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="AIRBOT Play/PTK data replay entrypoint"
    )
    parser.add_argument(
        "--yaml",
        type=str,
        default=None,
        help="Path to replay YAML config file",
    )

    # 必需参数
    parser.add_argument(
        "--dataset.repo_id",
        dest="repo_id",
        type=str,
        required=False,
        help="Dataset repository ID. Optional when --dataset.root points to a local dataset directory.",
    )
    parser.add_argument(
        "--dataset.root",
        dest="dataset_root",
        type=str,
        required=False,
        help="Local dataset directory to replay",
    )

    # 可选参数
    parser.add_argument(
        "--episode_index",
        type=int,
        default=0,
        help="Episode index to replay (default: 0)",
    )
    parser.add_argument("--fps", type=int, default=30, help="Replay FPS (default: 30)")

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

    return parser.parse_args()


def _load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _load_config(cli: argparse.Namespace) -> dict:
    if cli.yaml:
        cfg = _load_yaml(cli.yaml)

        if cli.repo_id is not None or cli.dataset_root is not None:
            dataset_cfg = cfg.setdefault("dataset", {})
            if cli.repo_id is not None:
                dataset_cfg["repo_id"] = cli.repo_id
            if cli.dataset_root is not None:
                dataset_cfg["root"] = cli.dataset_root

        replay_cfg = cfg.setdefault("replay", {})
        if cli.episode_index != 0:
            replay_cfg["episode_index"] = cli.episode_index
        if cli.fps != 30:
            replay_cfg["fps"] = cli.fps

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

        return cfg

    return {
        "dataset": {
            "repo_id": cli.repo_id,
            "root": cli.dataset_root,
        },
        "replay": {
            "episode_index": cli.episode_index,
            "fps": cli.fps,
        },
        "robot": {
            "type": cli.robot_type,
            "port": cli.robot_port,
            "left_arm_port": cli.robot_left_arm_port,
            "right_arm_port": cli.robot_right_arm_port,
            "id": cli.robot_id,
            "handedness": cli.robot_handedness,
            "channel_mode": cli.robot_channel_mode,
            "device_id": cli.robot_device_id,
            "canfd_id": cli.robot_canfd_id,
            "channel_id": cli.robot_channel_id,
        },
    }


def _config_to_args(cfg: dict) -> argparse.Namespace:
    dataset_cfg = cfg.get("dataset", {})
    replay_cfg = cfg.get("replay", {})
    robot_cfg = cfg.get("robot", {})

    return argparse.Namespace(
        yaml=None,
        repo_id=dataset_cfg.get("repo_id"),
        dataset_root=dataset_cfg.get("root"),
        episode_index=int(replay_cfg.get("episode_index", 0)),
        fps=int(replay_cfg.get("fps", 30)),
        robot_type=robot_cfg.get("type", "airbot_PTK_follower"),
        robot_port=robot_cfg.get("port", "can0"),
        robot_left_arm_port=robot_cfg.get("left_arm_port", "can0"),
        robot_right_arm_port=robot_cfg.get("right_arm_port", "can1"),
        robot_id=robot_cfg.get("id", "PTK_follower"),
        robot_handedness=robot_cfg.get("handedness"),
        robot_channel_mode=robot_cfg.get("channel_mode"),
        robot_device_id=robot_cfg.get("device_id"),
        robot_canfd_id=robot_cfg.get("canfd_id"),
        robot_channel_id=robot_cfg.get("channel_id"),
        robot_arm_reset_joints_path=robot_cfg.get("arm_reset_joints_path"),
        robot_hand_reset_joints_path=robot_cfg.get("hand_reset_joints_path"),
    )


def _validate_args(args: argparse.Namespace) -> None:
    """验证命令行参数"""
    # 检查数据集路径是否存在
    import os

    if not args.dataset_root:
        raise ValueError("dataset.root is required")

    dataset_target = resolve_dataset_target(repo_id=args.repo_id, path=args.dataset_root)
    args.repo_id = dataset_target.repo_id
    args.dataset_root = str(dataset_target.root)

    if not os.path.exists(args.dataset_root):
        raise ValueError(f"Dataset root directory does not exist: {args.dataset_root}")

    # 检查数据集是否包含指定轮次
    try:
        dataset = LeRobotDataset(
            args.repo_id, root=args.dataset_root, episodes=[args.episode_index]
        )
        if args.episode_index >= dataset.meta.total_episodes:
            raise ValueError(
                f"Episode {args.episode_index} not found. Dataset has {dataset.meta.total_episodes} episodes."
            )
    except Exception as e:
        raise ValueError(f"Failed to load dataset: {e}")


def _create_robot_config(args: argparse.Namespace):
    """创建机器人配置"""
    if args.robot_type == "airbot_play_follower":
        return AirbotPlayFollowerConfig(
            can_port=args.robot_port,
            id=args.robot_id,
        )
    elif args.robot_type == "airbot_PTK_follower":
        return AirbotPTKFollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
        )
    elif args.robot_type == "airbot_TOK2_follower":
        return AirbotTOK2FollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
        )
    elif args.robot_type == "airbot_TOK4_follower":
        return AirbotTOK4FollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
        )
    elif args.robot_type == "quest3_follower":
        return Quest3FollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
        )
    elif args.robot_type == "pico_follower":
        return PicoFollowerConfig(
            left_arm_port=args.robot_left_arm_port,
            right_arm_port=args.robot_right_arm_port,
            id=args.robot_id,
        )
    elif args.robot_type == "pico_follower_single_arm_agibot_o10":
        return PicoFollowerSingleArmAgibotO10Config(
            port=args.robot_port,
            handedness=args.robot_handedness or "right",
            channel_mode=args.robot_channel_mode or "multiChannel",
            device_id=1 if args.robot_device_id is None else args.robot_device_id,
            canfd_id=0 if args.robot_canfd_id is None else args.robot_canfd_id,
            channel_id=args.robot_channel_id,
            arm_reset_joints_path=args.robot_arm_reset_joints_path,
            hand_reset_joints_path=args.robot_hand_reset_joints_path,
            id=args.robot_id,
        )
    else:
        raise ValueError(f"Unsupported robot type: {args.robot_type}")


def _replay_episode(
    robot, dataset, episode_index: int, fps: int, robot_type: str
) -> Dict[str, Any]:
    """回放指定轮次的数据"""
    log_say(f"Starting replay of episode {episode_index}")
    start_time = time.time()

    # 获取动作数据
    actions = dataset.hf_dataset.select_columns("action")
    num_frames = dataset.num_frames
    progress_interval = max(1, num_frames // 10) if num_frames > 0 else 1

    log_say(f"Replaying {num_frames} frames at {fps} FPS")

    try:
        for idx in range(num_frames):
            t0 = time.perf_counter()

            # 获取动作张量
            action_tensor = actions[idx]["action"]
            action_dict = decode_replay_action(robot_type, action_tensor)

            # 发送动作到机器人
            robot.send_action(action_dict)

            # 控制回放速度
            precise_sleep(1.0 / fps - (time.perf_counter() - t0))

            # 显示进度
            if idx % progress_interval == 0 or idx == num_frames - 1:
                progress = (idx + 1) / num_frames * 100
                log_say(f"Replay progress: {progress:.1f}% ({idx + 1}/{num_frames})")

        execution_time = time.time() - start_time
        log_say(f"Replay completed in {execution_time:.2f} seconds")

        return {
            "status": "success",
            "robot_type": robot_type,
            "episode_index": episode_index,
            "frames_replayed": num_frames,
            "execution_time": execution_time,
            "avg_fps": num_frames / execution_time,
        }

    except Exception as e:
        log_say(f"Replay failed: {e}")
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "robot_type": robot_type,
            "episode_index": episode_index,
        }


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

        log_say(f"Starting replay with robot type: {args.robot_type}")
        log_say(f"Dataset: {args.repo_id}")
        log_say(f"Dataset root: {args.dataset_root}")
        log_say(f"Episode index: {args.episode_index}")
        log_say(f"Replay FPS: {args.fps}")

        # 创建机器人配置
        robot_config = _create_robot_config(args)
        robot = make_robot_from_config(robot_config)

        # 连接机器人
        robot.connect()
        log_say("Robot connected successfully")

        # 加载数据集
        dataset = LeRobotDataset(
            args.repo_id, root=args.dataset_root, episodes=[args.episode_index]
        )
        log_say(
            f"Dataset loaded: {dataset.num_frames} frames in episode {args.episode_index}"
        )

        # 回放数据
        result = _replay_episode(
            robot, dataset, args.episode_index, args.fps, args.robot_type
        )

        # 机器人归零
        if result["status"] == "success":
            log_say("Returning robot to zero position")

            if robot.name == "airbot_play_follower":
                robot.reset_zero()
            elif robot.name == "airbot_PTK_follower":
                robot.reset_init()
            elif robot.name == "airbot_TOK4_follower":
                robot.reset_zero()
            elif robot.name == "airbot_TOK2_follower":
                robot.reset_zero()
            elif robot.name == "quest3_follower":
                robot.reset_zero()
            elif robot.name == "pico_follower":
                robot.reset_zero()
            elif robot.name == "pico_follower_single_arm_agibot_o10":
                robot.reset_zero()

        # 输出结果
        import json

        print(json.dumps(result, indent=2))

    except Exception as e:
        error_result = {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "suggestion": "Please check your configuration and dataset",
        }
        import json

        print(json.dumps(error_result, indent=2))
        import sys

        sys.exit(1)

    finally:
        # 清理资源
        try:
            robot.disconnect()
            log_say("Robot disconnected")
        except:
            pass


if __name__ == "__main__":
    main()
