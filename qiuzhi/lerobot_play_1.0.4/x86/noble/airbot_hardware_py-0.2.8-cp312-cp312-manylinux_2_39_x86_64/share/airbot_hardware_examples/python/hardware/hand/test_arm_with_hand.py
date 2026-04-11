import time
import argparse
import math
import threading
import sys
import airbot_hardware_py as ah


def all_zero(pos, tol=1e-3):
    return all(abs(p) < tol for p in pos)


def main():
    parser = argparse.ArgumentParser("test_arm_with_hand")

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

    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Test duration in seconds (default: 10s)",
    )

    args = parser.parse_args()
    hand_type_str = args.type
    hand_id = args.hand_id
    can_interface = args.can
    duration = args.duration

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

    executor = ah.create_asio_executor(8)
    executor_hand = ah.create_asio_executor(3)
    io_context = executor.get_io_context()
    io_context_hand = executor_hand.get_io_context()

    # 创建 Arm 和 Hand
    arm = ah.Play.create(
        ah.MotorType.OD,
        ah.MotorType.OD,
        ah.MotorType.OD,
        ah.MotorType.DM,
        ah.MotorType.DM,
        ah.MotorType.DM,
        ah.EEFType.NA,
        ah.MotorType.NA,
    )
    hand = ah.create_dexterous_hand(hand_id, hand_type)

    assert arm.init(io_context, can_interface, 250)
    assert hand.init(io_context_hand, can_interface, 250)

    arm.enable()
    arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)

    # Arm归零
    print("Arm homing to zero...")
    start = time.time()
    while not all_zero(arm.state().pos):
        arm.pvt([0.0] * 6, [math.pi / 10] * 6)
        time.sleep(0.01)
        if time.time() - start > 5:
            break
    print("Arm homed to zero!")

    # Hand周期性运动 + 状态打印
    hand_running = True
    start_time = time.time()

    def hand_motion():
        amp = 0.4
        phase_offsets = [
            0.0,
            0.0,
            math.pi / 3,
            math.pi / 2,
            2 * math.pi / 3,
            5 * math.pi / 6,
        ]
        hand_pos_range = (0, 1000)

        while hand_running and (time.time() - start_time < duration):
            t = time.time() - start_time
            cmd = ah.HandState()
            positions = [0, 0, 0, 0, 0, 0]
            for i in range(6):
                if i < 2:  # 前两个手指保持 0，不动
                    positions[i] = 0
                    continue
                min_p, max_p = hand_pos_range
                mid = (min_p + max_p) / 2.0
                half_range = (max_p - min_p) / 2.0
                phase = 2 * math.pi * 1 * t + phase_offsets[i]
                val = mid + half_range * amp * math.sin(phase)
                positions[i] = int(math.floor(max(min(val, max_p), min_p)))
            cmd.positions = positions
            cmd.velocities = [1000] * 6
            hand.set_pos(cmd)

            # 打印手部状态
            hand.update_state()
            state = hand.state()
            print("🖐 Hand positions:", [int(p) for p in state.positions])

            time.sleep(0.04)  # 25Hz

    hand_thread = threading.Thread(target=hand_motion)
    hand_thread.start()
    time.sleep(1)

    ratio = 2.0
    synced = False

    try:
        while time.time() - start_time < duration:
            t = time.time() * 1000
            target = math.sin(t / 1000 * ratio)
            if not synced and abs(arm.state().pos[0] - target) > 0.01:
                arm.pvt([target, 0, 0, 0, 0, 0], [math.pi / 10] * 6)
            else:
                synced = True
                arm.pvt([target, 0, 0, 0, 0, 0])
            time.sleep(0.004)

    finally:
        # 停止循环
        hand_running = False
        hand_thread.join()
        hand.uninit()
        arm.disable()
        arm.uninit()
        print(f"\n✅ Arm and Hand test finished after {duration:.1f} seconds.")


if __name__ == "__main__":
    main()
