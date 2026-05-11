#!/usr/bin/env python3
"""Smoke test for controlling an Agibot O10 arm with EEF delta actions.

Default mode is dry-run and does not connect to hardware:

    python tests/test_eef_delta_arm_control.py --hand right

To move a real arm, pass --execute explicitly. The delta is split across
multiple small eef_delta actions:

    python tests/test_eef_delta_arm_control.py --hand right --execute --dx 0.01
    python tests/test_eef_delta_arm_control.py --hand left --execute --dz 0.01
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


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


ARM_FEATURE_NAMES = tuple(f"joint{index}.pos" for index in range(1, 7))
HAND_FEATURE_NAMES = (
    "thumb_cm_roll.pos",
    "thumb_cm_yaw.pos",
    "thumb_cm_pitch.pos",
    "index_mp_yaw.pos",
    "index_mp_pitch.pos",
    "middle_mp_pitch.pos",
    "ring_mp_yaw.pos",
    "ring_mp_pitch.pos",
    "pinky_mp_yaw.pos",
    "pinky_mp_pitch.pos",
)
EEF_DELTA_FEATURE_NAMES = (
    "delta_pose.x",
    "delta_pose.y",
    "delta_pose.z",
    "delta_orientation.roll",
    "delta_orientation.pitch",
    "delta_orientation.yaw",
)


@dataclass(frozen=True)
class EefDelta:
    dx: float = 0.01
    dy: float = 0.0
    dz: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    def as_list(self) -> list[float]:
        return [self.dx, self.dy, self.dz, self.roll, self.pitch, self.yaw]

    def scaled(self, scale: float) -> "EefDelta":
        return EefDelta(*(value * scale for value in self.as_list()))


def default_port(handedness: str) -> str:
    return "can0" if handedness == "left" else "can1"


def build_eef_delta_action(
    delta: EefDelta,
    hand_joints: Sequence[float] | None = None,
) -> dict[str, float]:
    if hand_joints is None:
        hand_joints = [0.0] * len(HAND_FEATURE_NAMES)
    if len(hand_joints) != len(HAND_FEATURE_NAMES):
        raise ValueError(f"Expected {len(HAND_FEATURE_NAMES)} hand joints, got {len(hand_joints)}")

    action = {
        name: float(value)
        for name, value in zip(EEF_DELTA_FEATURE_NAMES, delta.as_list(), strict=True)
    }
    action.update(
        {
            name: float(value)
            for name, value in zip(HAND_FEATURE_NAMES, hand_joints, strict=True)
        }
    )
    return action


def split_delta(delta: EefDelta, steps: int) -> EefDelta:
    if steps <= 0:
        raise ValueError("--steps must be greater than 0")
    return delta.scaled(1.0 / steps)


def validate_delta(delta: EefDelta, max_translation: float, max_rotation: float) -> None:
    translation_norm = math.sqrt(delta.dx**2 + delta.dy**2 + delta.dz**2)
    rotation_norm = max(abs(delta.roll), abs(delta.pitch), abs(delta.yaw))
    if translation_norm > max_translation:
        raise ValueError(
            f"Translation delta norm {translation_norm:.4f} m exceeds "
            f"--max-translation {max_translation:.4f} m"
        )
    if rotation_norm > max_rotation:
        raise ValueError(
            f"Rotation delta {rotation_norm:.4f} rad exceeds "
            f"--max-rotation {max_rotation:.4f} rad"
        )


def print_joint_vector(title: str, names: Sequence[str], values: Sequence[float]) -> None:
    print(f"\n{title}:")
    for name, value in zip(names, values, strict=True):
        print(f"  {name:>25s}: {float(value):+.6f}")


def print_delta(title: str, delta: EefDelta) -> None:
    print(f"\n{title}:")
    for name, value in zip(EEF_DELTA_FEATURE_NAMES, delta.as_list(), strict=True):
        print(f"  {name:>25s}: {value:+.6f}")


def run_dry_run(args: argparse.Namespace) -> int:
    total_delta = EefDelta(args.dx, args.dy, args.dz, args.roll, args.pitch, args.yaw)
    validate_delta(total_delta, args.max_translation, args.max_rotation)
    per_step_delta = split_delta(total_delta, args.steps)
    action = build_eef_delta_action(per_step_delta)

    print("DRY RUN: no hardware connection and no arm movement.")
    print(f"Hand: {args.hand}")
    print(f"CAN port: {args.port or default_port(args.hand)}")
    print(f"Steps: {args.steps}, interval: {args.interval:.3f}s")
    print_delta("Requested total EEF delta", total_delta)
    print_delta("Per-step EEF delta sent to robot.send_action", per_step_delta)
    print("\nAction keys:")
    for key in action:
        print(f"  {key}")
    print("\nPass --execute to run this against the real arm.")
    return 0


def run_execute(args: argparse.Namespace) -> int:
    from lerobot_play.robots.pico_follower_single_arm_agibot_o10.airbot_pico_follower_single_arm_agibot_o10 import (
        PicoFollowerSingleArmAgibotO10,
    )
    from lerobot_play.robots.pico_follower_single_arm_agibot_o10.config_pico_follower_single_arm_agibot_o10 import (
        PicoFollowerSingleArmAgibotO10Config,
    )

    total_delta = EefDelta(args.dx, args.dy, args.dz, args.roll, args.pitch, args.yaw)
    validate_delta(total_delta, args.max_translation, args.max_rotation)
    per_step_delta = split_delta(total_delta, args.steps)
    port = args.port or default_port(args.hand)
    reset_poses_path = str(REPO_ROOT / "configs" / "reset_poses" / "o10_dual_reset.json")

    config = PicoFollowerSingleArmAgibotO10Config(
        port=port,
        handedness=args.hand,
        enable_hand=args.enable_hand,
        allow_camera_read_failures=True,
        cameras={},
        action_control_mode="eef_delta",
        hand_action_mode="dexterous_10d",
        reset_poses_path=reset_poses_path,
        reset_gesture=args.reset_gesture,
    )
    robot = PicoFollowerSingleArmAgibotO10(config)

    print(f"Connecting {args.hand} arm on {port} in eef_delta mode...")
    robot.connect()
    try:
        current_arm, current_hand = robot.get_joint_pos()
        print_joint_vector("Current arm joints", ARM_FEATURE_NAMES, current_arm[: len(ARM_FEATURE_NAMES)])
        if args.enable_hand:
            print_joint_vector("Current hand joints", HAND_FEATURE_NAMES, current_hand)

        action = build_eef_delta_action(per_step_delta, current_hand)
        print_delta("Requested total EEF delta", total_delta)
        print_delta("Per-step EEF delta", per_step_delta)
        print(f"\nSending {args.steps} eef_delta action(s)...")

        for index in range(args.steps):
            robot.send_action(action)
            print(f"  sent step {index + 1}/{args.steps}")
            time.sleep(args.interval)

        final_arm, final_hand = robot.get_joint_pos()
        print_joint_vector("Final arm joints", ARM_FEATURE_NAMES, final_arm[: len(ARM_FEATURE_NAMES)])
        if args.enable_hand:
            print_joint_vector("Final hand joints", HAND_FEATURE_NAMES, final_hand)

        if args.return_zero:
            print("\nReturning to configured reset pose...")
            robot.return_zero()
    finally:
        print("\nDisconnecting...")
        robot.disconnect()
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test O10 arm EEF delta control")
    parser.add_argument("--hand", choices=("left", "right"), default="right")
    parser.add_argument("--port", help="CAN port; defaults to can0 for left, can1 for right")
    parser.add_argument("--dx", type=float, default=0.01, help="EEF x delta in meters")
    parser.add_argument("--dy", type=float, default=0.0, help="EEF y delta in meters")
    parser.add_argument("--dz", type=float, default=0.0, help="EEF z delta in meters")
    parser.add_argument("--roll", type=float, default=0.0, help="EEF roll delta in radians")
    parser.add_argument("--pitch", type=float, default=0.0, help="EEF pitch delta in radians")
    parser.add_argument("--yaw", type=float, default=0.0, help="EEF yaw delta in radians")
    parser.add_argument("--steps", type=int, default=20, help="Split the delta into this many sends")
    parser.add_argument("--interval", type=float, default=0.05, help="Seconds between sends")
    parser.add_argument("--max-translation", type=float, default=0.03, help="Safety limit in meters")
    parser.add_argument("--max-rotation", type=float, default=0.20, help="Safety limit in radians")
    parser.add_argument("--enable-hand", action="store_true", help="Also connect and preserve hand joints")
    parser.add_argument("--reset-gesture", choices=("pinch", "tripod"), default="pinch")
    parser.add_argument("--return-zero", action="store_true", help="Return to reset pose before disconnect")
    parser.add_argument("--execute", action="store_true", help="Connect hardware and move the arm")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.execute:
        return run_execute(args)
    return run_dry_run(args)


def test_build_eef_delta_action_uses_delta_and_hand_features() -> None:
    delta = EefDelta(dx=0.01, dy=-0.02, dz=0.03, roll=0.1, pitch=-0.2, yaw=0.3)
    hand_joints = [float(index) for index in range(len(HAND_FEATURE_NAMES))]

    action = build_eef_delta_action(delta, hand_joints)

    assert list(action) == [*EEF_DELTA_FEATURE_NAMES, *HAND_FEATURE_NAMES]
    assert [action[name] for name in EEF_DELTA_FEATURE_NAMES] == delta.as_list()
    assert [action[name] for name in HAND_FEATURE_NAMES] == hand_joints


def test_split_delta_divides_motion_across_steps() -> None:
    delta = EefDelta(dx=0.02, dy=0.01, dz=-0.01, roll=0.2, pitch=-0.1, yaw=0.05)

    per_step = split_delta(delta, steps=10)

    for actual, expected in zip(per_step.as_list(), [value / 10 for value in delta.as_list()], strict=True):
        assert math.isclose(actual, expected)


if __name__ == "__main__":
    raise SystemExit(main())
