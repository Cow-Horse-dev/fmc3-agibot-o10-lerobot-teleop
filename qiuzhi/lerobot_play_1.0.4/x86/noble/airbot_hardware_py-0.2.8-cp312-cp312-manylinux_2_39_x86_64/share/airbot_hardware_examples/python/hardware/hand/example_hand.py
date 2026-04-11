import time
import argparse
import signal
import sys
import airbot_hardware_py as ah


stop_flag = False


def signal_handler(sig, frame):
    global stop_flag
    print("\n[Signal] Caught Ctrl+C, preparing to stop...")
    stop_flag = True


def all_target(current_pos, target_pos, tol=20):
    """Check if all positions are within tolerance."""
    for i in range(6):
        if abs(current_pos[i] - target_pos[i]) > tol:
            return False
    return True


def main():
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser("airbot_dexterous_hand_ctrl")

    parser.add_argument(
        "-j",
        "--joints",
        type=int,
        nargs=6,
        default=[0, 0, 0, 0, 0, 0],
        help="Target joint positions for the hand (6 values, e.g. -j 200 300 400 500 600 600)",
    )

    parser.add_argument(
        "-t",
        "--type",
        type=str,
        default="BRAINCO_REVO2",
        help="Dexterous hand type, e.g. INS_RH56F1, ROH_A002, BRAINCO_REVO2, etc.",
    )

    parser.add_argument(
        "--hand-id",
        type=int,
        default=1,
        help="Specify the hand device ID (default: 1)",
    )

    parser.add_argument(
        "-i", "--can", default="can0", help="CAN interface name (default: can0)"
    )

    args = parser.parse_args()

    target_pos = args.joints
    hand_type_str = args.type
    hand_id = args.hand_id
    can_interface = args.can

    try:
        hand_type = getattr(ah.DexterousHandTypes, hand_type_str)
    except AttributeError:
        print(f"❌ Invalid hand type: {hand_type_str}")
        print(
            "Available types:",
            [t for t in dir(ah.DexterousHandTypes) if not t.startswith("__")],
        )
        sys.exit(1)

    print(f"[Init] Initializing hand type: {hand_type_str} (ID={hand_id})")

    executor = ah.create_asio_executor(3)
    io_context = executor.get_io_context()

    hand = ah.create_dexterous_hand(hand_id, hand_type)

    if not hand.init(io_context, can_interface, 250):
        print("❌ Failed to initialize hand.")
        sys.exit(1)

    hand.update_state()
    time.sleep(0.05)
    state = hand.state()
    print("[First State] positions:", list(state.positions))

    print("[Running] Press Ctrl+C to stop.")
    start_time = time.time()

    while (
        not stop_flag
        and not all_target(list(state.positions), target_pos)
        and time.time() - start_time < 10
    ):
        hand.update_state()

        hand_cmd = ah.HandState()
        hand_cmd.positions = target_pos
        hand_cmd.velocities = [1000] * 6
        # hand_cmd.forces = [50] * 6

        hand.set_pos(hand_cmd)

        state = hand.state()
        print("hand_state:", list(state.positions))

        time.sleep(0.015)

    print("\n[Shutdown] Uninitializing hand...")
    hand.uninit()
    print("[Exit] Program terminated safely.")


if __name__ == "__main__":
    main()
