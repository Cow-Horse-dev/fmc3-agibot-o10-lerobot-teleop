import sys
import os
import time
import argparse
import tty
import termios
import select

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
lerobot_play_root = os.path.join(
    repo_root,
    "qiuzhi",
    "lerobot_play_1.0.4",
    "x86",
    "noble",
    "lerobot_play-1.0.4-py3-none-any",
)
sys.path.insert(0, lerobot_play_root)
sys.path.insert(0, os.path.join(repo_root, "yudie"))
sys.path.insert(0, os.path.join(repo_root, "yudie", "omnihand_2025"))

from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_TRIGGER_GESTURES,
    get_agibot_o10_trigger_gesture_joint_angles,
)

from AGIBOT.Omnihand_o10_yudie import (
    init_hand_OmnimultiChannel,
    init_hand_Omni_multiCan,
    is_hand_ready,
)

HOLD_LOCK = 0.6
RELEASE_DELAY = 0.12


def parse_args():
    parser = argparse.ArgumentParser(description="O10 捏取手势键盘测试")
    parser.add_argument("--hand", choices=["left", "right"], default="right")
    parser.add_argument("--gesture", choices=sorted(AGIBOT_O10_TRIGGER_GESTURES), default="pinch",
                        help="pinch=拇指+食指, tripod=拇指+食指+中指")
    parser.add_argument("--canType", choices=["multiChannel", "multiCan"], default="multiChannel")
    return parser.parse_args()


def init_hand(hand_side: str, can_type: str):
    if can_type == "multiChannel":
        left, right = init_hand_OmnimultiChannel(hand_side)
    else:
        left, right = init_hand_Omni_multiCan(hand_side)

    hand = left if hand_side == "left" else right
    if hand is None:
        print(f"初始化 {hand_side} 手失败")
        sys.exit(1)

    if not is_hand_ready(hand):
        print("手部设备未就绪，请检查 CAN 连接")
        sys.exit(1)

    return hand


def drain_stdin():
    """读掉 stdin 缓冲区里所有字符，返回最后一个"""
    last = None
    while True:
        rlist, _, _ = select.select([sys.stdin], [], [], 0)
        if not rlist:
            break
        last = sys.stdin.read(1)
    return last


def main():
    args = parse_args()
    gesture_open = get_agibot_o10_trigger_gesture_joint_angles(
        args.gesture,
        args.hand,
        "open",
    )
    gesture_closed = get_agibot_o10_trigger_gesture_joint_angles(
        args.gesture,
        args.hand,
        "closed",
    )

    print(f"正在初始化 O10 {args.hand} 手 (CAN: {args.canType}, 手势: {args.gesture})...")
    hand = init_hand(args.hand, args.canType)
    print("初始化成功！")

    hand.set_all_active_joint_angles(gesture_open)
    print("拇指已就位")
    print("按住空格 = 捏取，松开 = 张开，q = 退出")

    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        grasping = False
        prev_grasping = None
        last_space_time = 0
        grasp_start_time = 0

        while True:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.02)
            now = time.monotonic()

            if rlist:
                ch = sys.stdin.read(1)
                drain_stdin()

                if ch == "q":
                    break
                elif ch == " ":
                    last_space_time = now
                    if not grasping:
                        grasping = True
                        grasp_start_time = now
            else:
                if grasping:
                    since_start = now - grasp_start_time
                    since_last = now - last_space_time
                    if since_start > HOLD_LOCK and since_last > RELEASE_DELAY:
                        grasping = False

            if grasping != prev_grasping:
                target = gesture_closed if grasping else gesture_open
                hand.set_all_active_joint_angles(target)
                prev_grasping = grasping

            state = "捏取" if grasping else "张开"
            angles = hand.get_all_active_joint_angles()
            sys.stdout.write(f"\r状态: {state} | 关节: {angles}    ")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        hand.set_all_active_joint_angles(gesture_open)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        print("\n已复位并退出")


if __name__ == "__main__":
    main()
