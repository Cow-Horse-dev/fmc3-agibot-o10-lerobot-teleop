#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))

from lerobot_play.utils.o10_hand_pose_capture import (
    O10_HAND_POSE_KIND_FULL_RESET,
    O10_HAND_POSE_KIND_GRASP_PRESET,
    capture_glove_o10_hand_joint_pos,
    capture_robot_o10_hand_joint_pos,
    default_o10_hand_pose_description,
    default_o10_hand_pose_path,
    format_o10_hand_joint_report,
    save_o10_hand_joint_target,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="读取当前 O10 手关节并保存为 JSON。默认从机器人手当前关节读取。",
    )
    parser.add_argument(
        "--handedness",
        choices=("left", "right"),
        default="right",
        help="选择哪只手。默认: right",
    )
    parser.add_argument(
        "--pose-kind",
        choices=(O10_HAND_POSE_KIND_FULL_RESET, O10_HAND_POSE_KIND_GRASP_PRESET),
        default=O10_HAND_POSE_KIND_FULL_RESET,
        help="保存成哪种手型 JSON。默认: full_reset",
    )
    parser.add_argument(
        "--source",
        choices=("robot", "glove"),
        default="robot",
        help="从机器人手当前关节读取，还是从手套当前姿态读取。默认: robot",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 JSON 路径。不传时按 handedness + pose-kind 自动落到 configs/ 下。",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="写入 JSON 的 description。不传时自动按 pose-kind 生成。",
    )
    parser.add_argument(
        "--channel-mode",
        default="multiChannel",
        help="O10 手通道模式。默认: multiChannel",
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=1,
        help="OmniHand device_id。默认: 1",
    )
    parser.add_argument(
        "--canfd-id",
        type=int,
        default=0,
        help="USB-CANFD 适配器编号。默认: 0",
    )
    parser.add_argument(
        "--channel-id",
        type=int,
        default=None,
        help="O10 channel_id。不传时按 handedness 自动选择。",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="从手套读取时等待新鲜数据的超时秒数。默认: 2.0",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    output_path = (
        args.output.expanduser()
        if args.output is not None
        else default_o10_hand_pose_path(REPO_ROOT, args.handedness, args.pose_kind)
    )
    description = args.description or default_o10_hand_pose_description(
        args.handedness,
        args.pose_kind,
    )

    print("准备读取当前 O10 手关节...")
    print(f"  source: {args.source}")
    print(f"  handedness: {args.handedness}")
    print(f"  pose_kind: {args.pose_kind}")
    print(f"  output: {output_path}")

    if args.source == "robot":
        joint_values = capture_robot_o10_hand_joint_pos(
            handedness=args.handedness,
            channel_mode=args.channel_mode,
            device_id=args.device_id,
            canfd_id=args.canfd_id,
            channel_id=args.channel_id,
        )
    else:
        joint_values = capture_glove_o10_hand_joint_pos(
            handedness=args.handedness,
            timeout_s=args.timeout,
        )

    normalized_joint_values = save_o10_hand_joint_target(
        output_path,
        joint_values,
        description=description,
    )

    print(format_o10_hand_joint_report("已保存的 O10 手关节:", normalized_joint_values))
    print(f"JSON 已写入: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
