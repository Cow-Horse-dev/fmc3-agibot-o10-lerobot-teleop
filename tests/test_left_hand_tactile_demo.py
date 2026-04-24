#!/usr/bin/env python3
"""左手触觉实时打印 demo。

用途：
- 连接左手 OmniHand O10
- 循环读取触觉
- 你用手按左手不同区域时，终端实时打印数值变化

示例：
    python tests/test_left_hand_tactile_demo.py
    python tests/test_left_hand_tactile_demo.py --mode 80d
    python tests/test_left_hand_tactile_demo.py --mode 130d --interval 0.2
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_ROOT))

from lerobot_play.utils.agibot_o10 import AgibotO10Hand


TACTILE_REGION_NAMES = (
    "thumb",
    "index",
    "middle",
    "ring",
    "little",
    "palm",
    "dorsum",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="左手触觉实时打印 demo")
    parser.add_argument(
        "--mode",
        choices=("7d", "80d", "130d"),
        default="7d",
        help="7d 打印区域均值，80d 打印五指点阵，130d 打印全手点阵",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="打印周期，单位秒，默认 0.1",
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=1,
        help="OmniHand device_id，默认 1",
    )
    parser.add_argument(
        "--canfd-id",
        type=int,
        default=0,
        help="OmniHand canfd_id，默认 0",
    )
    parser.add_argument(
        "--channel-id",
        type=int,
        default=None,
        help="multiChannel 模式下左手默认是 0；不传就自动使用左手默认值",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="关闭单行刷新，改为每次都换行打印",
    )
    return parser.parse_args()


def format_7d(values: list[float]) -> str:
    short_names = ("T", "I", "M", "R", "L", "P", "D")
    pairs = [
        f"{short_name}:{value:5.1f}"
        for short_name, value in zip(short_names, values, strict=True)
    ]
    return " ".join(pairs)


def format_dense(values: list[float], preview_count: int = 12) -> str:
    head = " ".join(f"{value:5.1f}" for value in values[:preview_count])
    peak = max(values) if values else 0.0
    total = sum(values)
    return (
        f"count={len(values):3d}  max={peak:6.1f}  sum={total:8.1f}  "
        f"first[{preview_count}]={head}"
    )


def read_tactile(hand: AgibotO10Hand, mode: str) -> list[float]:
    if mode == "7d":
        return hand.read_tactile_avg()
    if mode == "80d":
        return hand.read_tactile_fingertip()
    return hand.read_tactile_full()


def main() -> int:
    args = parse_args()
    hand = AgibotO10Hand(
        handedness="left",
        channel_mode="multiChannel",
        device_id=args.device_id,
        canfd_id=args.canfd_id,
        channel_id=args.channel_id,
    )

    print("Connecting left hand tactile demo...")
    hand.connect()
    print(
        "Connected. Press Ctrl+C to stop. "
        "Try pressing thumb/index/middle/ring/little/palm/dorsum on the left hand."
    )

    try:
        while True:
            values = read_tactile(hand, args.mode)
            timestamp = time.strftime("%H:%M:%S")
            if args.mode == "7d":
                line = format_7d(values)
            else:
                line = format_dense(values)
            output = f"[{timestamp}] {args.mode} {line}"
            if args.no_refresh:
                print(output, flush=True)
            else:
                terminal_width = shutil.get_terminal_size((120, 20)).columns
                clipped = output[: max(1, terminal_width - 1)]
                print("\r" + clipped.ljust(max(1, terminal_width - 1)), end="", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopping tactile demo...")
    finally:
        hand.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
