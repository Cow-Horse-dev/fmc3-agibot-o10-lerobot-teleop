#!/usr/bin/env python3
"""Manual O10 cylindrical-grasp smoke test.

Default behavior:
  - connect the left O10 hand
  - move it to the cylindrical open pose
  - hold Space to close the hand in a cylindrical grasp
  - release Space to open the hand
  - press q to exit without changing the current hand pose
"""

from __future__ import annotations

import argparse
import select
import sys
import termios
import threading
import time
import tty
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
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
if str(REPO_ROOT / "yudie") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "yudie"))

from lerobot_play.utils.agibot_o10 import (  # noqa: E402
    AGIBOT_O10_TRIGGER_GESTURES,
    AgibotO10Hand,
    get_agibot_o10_trigger_gesture_joint_angles,
)

NON_THUMB_FLEXION_INDICES = (4, 5, 7, 9)
NON_THUMB_YAW_INDICES = (3, 6, 8)
REFERENCE_FINGER_FLEXION_INDEX = 4
THUMB_YAW_PERPENDICULAR_BY_HAND = {"left": 1.51, "right": -1.51}
FOUR_FINGER_VERTICAL_FLEXION = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hold Space to close the O10 hand in a cylindrical grasp."
    )
    parser.add_argument("--hand", choices=["left", "right"], default="left")
    parser.add_argument(
        "--gesture",
        choices=sorted(AGIBOT_O10_TRIGGER_GESTURES),
        default="cylindrical",
        help="gesture to drive with Space",
    )
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--canfd-id", type=int, default=0)
    parser.add_argument(
        "--channel-id",
        type=int,
        default=None,
        help="defaults to the repo convention: left=0, right=1",
    )
    parser.add_argument(
        "--input-mode",
        choices=["auto", "pynput", "terminal"],
        default="auto",
        help="pynput gives true key release; terminal uses key-repeat timing as a fallback",
    )
    parser.add_argument(
        "--release-delay",
        type=float,
        default=0.12,
        help="terminal fallback: open after this many seconds without repeated Space",
    )
    parser.add_argument(
        "--hold-lock",
        type=float,
        default=0.5,
        help="terminal fallback: keep closed for at least this many seconds after Space",
    )
    return parser.parse_args()


def read_key(timeout_s: float = 0.1) -> str | None:
    readable, _, _ = select.select([sys.stdin], [], [], timeout_s)
    if not readable:
        return None
    return sys.stdin.read(1)


def print_joint_values(label: str, values: list[float]) -> None:
    formatted = ", ".join(f"{value:+.3f}" for value in values)
    print(f"{label}: [{formatted}]")


def build_four_finger_linked_pose(pose: list[float]) -> list[float]:
    linked_pose = list(pose)
    linked_flexion = float(linked_pose[REFERENCE_FINGER_FLEXION_INDEX])
    for index in NON_THUMB_FLEXION_INDICES:
        linked_pose[index] = linked_flexion
    return linked_pose


def build_perpendicular_open_pose(pose: list[float], handedness: str) -> list[float]:
    open_pose = list(pose)
    open_pose[1] = THUMB_YAW_PERPENDICULAR_BY_HAND[handedness]
    for index in NON_THUMB_YAW_INDICES:
        open_pose[index] = 0.0
    for index in NON_THUMB_FLEXION_INDICES:
        open_pose[index] = FOUR_FINGER_VERTICAL_FLEXION
    return open_pose


class SpaceCupGraspController:
    def __init__(self, hand, open_pose: list[float], closed_pose: list[float]) -> None:
        self.hand = hand
        self.open_pose = list(open_pose)
        self.closed_pose = list(closed_pose)
        self.current_state = "open"
        self._space_down = False
        self._quit_event = threading.Event()

    @property
    def should_quit(self) -> bool:
        return self._quit_event.is_set()

    def close(self) -> None:
        if self.current_state == "closed":
            return
        self.hand.write_active_joint_angles(self.closed_pose)
        self.current_state = "closed"
        print("\rSpace down: closed cylindrical grasp.      ")

    def open(self) -> None:
        if self.current_state == "open":
            return
        self.hand.write_active_joint_angles(self.open_pose)
        self.current_state = "open"
        print("\rSpace released: opened hand.               ")

    def request_quit(self) -> None:
        self._quit_event.set()

    def wait_until_quit(self) -> None:
        self._quit_event.wait()

    def on_press(self, key, keyboard) -> None:
        if self._is_space(key, keyboard):
            self._space_down = True
            self.close()
        elif self._is_char(key, "o"):
            self._space_down = False
            self.open()
        elif self._is_char(key, "q"):
            self.request_quit()

    def on_release(self, key, keyboard) -> None:
        if self._is_space(key, keyboard):
            self._space_down = False
            self.open()

    @staticmethod
    def _is_space(key, keyboard) -> bool:
        return key == keyboard.Key.space or getattr(key, "char", None) == " "

    @staticmethod
    def _is_char(key, expected: str) -> bool:
        char = getattr(key, "char", None)
        return isinstance(char, str) and char.lower() == expected


def run_pynput_loop(controller: SpaceCupGraspController) -> None:
    from pynput import keyboard

    listener = keyboard.Listener(
        on_press=lambda key: controller.on_press(key, keyboard),
        on_release=lambda key: controller.on_release(key, keyboard),
    )
    listener.start()
    try:
        controller.wait_until_quit()
    finally:
        listener.stop()


def run_terminal_repeat_loop(
    controller: SpaceCupGraspController,
    *,
    release_delay_s: float,
    hold_lock_s: float,
) -> None:
    old_terminal_settings = termios.tcgetattr(sys.stdin)
    last_space_time = 0.0
    space_start_time = 0.0
    try:
        tty.setcbreak(sys.stdin.fileno())
        while not controller.should_quit:
            key = read_key(0.02)
            now = time.monotonic()
            if key == " ":
                last_space_time = now
                if controller.current_state != "closed":
                    space_start_time = now
                controller.close()
            elif key and key.lower() == "o":
                controller.open()
            elif key and key.lower() == "q":
                controller.request_quit()

            if controller.current_state == "closed":
                held_long_enough = now - space_start_time > hold_lock_s
                repeat_stopped = now - last_space_time > release_delay_s
                if held_long_enough and repeat_stopped:
                    controller.open()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_terminal_settings)


def run_input_loop(controller: SpaceCupGraspController, args: argparse.Namespace) -> None:
    if args.input_mode in {"auto", "pynput"}:
        try:
            run_pynput_loop(controller)
            return
        except Exception as exc:
            if args.input_mode == "pynput":
                raise
            print(f"pynput keyboard listener unavailable ({exc}); using terminal fallback.")

    run_terminal_repeat_loop(
        controller,
        release_delay_s=args.release_delay,
        hold_lock_s=args.hold_lock,
    )


def main() -> int:
    args = parse_args()
    open_pose = build_perpendicular_open_pose(
        get_agibot_o10_trigger_gesture_joint_angles(
            args.gesture,
            args.hand,
            "open",
        ),
        args.hand,
    )
    closed_pose = build_four_finger_linked_pose(
        get_agibot_o10_trigger_gesture_joint_angles(
            args.gesture,
            args.hand,
            "closed",
        )
    )

    hand = AgibotO10Hand(
        handedness=args.hand,
        device_id=args.device_id,
        canfd_id=args.canfd_id,
        channel_id=args.channel_id,
    )

    print(
        "Connecting O10 hand "
        f"(hand={args.hand}, gesture={args.gesture}, "
        f"device_id={args.device_id}, canfd_id={args.canfd_id}, "
        f"channel_id={args.channel_id if args.channel_id is not None else 'default'})..."
    )
    hand.connect()
    print("Connected.")

    print_joint_values("Open pose", open_pose)
    print_joint_values("Closed pose", closed_pose)
    hand.write_active_joint_angles(open_pose)

    print("\nControls: hold Space=close cylindrical grasp, release Space=open, o=open, q=quit")
    controller = SpaceCupGraspController(hand, open_pose, closed_pose)
    try:
        run_input_loop(controller, args)
        print(f"\nExiting; leaving hand in current state: {controller.current_state}.")
        return 0
    except KeyboardInterrupt:
        print(f"\nInterrupted; leaving hand in current state: {controller.current_state}.")
        return 130
    finally:
        hand.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
