# Copyright (c) 2025, Agibot Co., Ltd.
# OmniHand 2025 SDK is licensed under Mulan PSL v2.

from omnihand_2025 import AgibotHandO10, EFinger, EControlMode, EHandType
import time

def main():
    # left_hand_scanfd_id = AgibotHandO10.find_canfd_id_by_serial_number("201BFF2AF01202D44690")
    # right_hand_scanfd_id = AgibotHandO10.find_canfd_id_by_serial_number("A029A58630B30D14DBB")
    [left_hand_scanfd_id, right_hand_scanfd_id] = AgibotHandO10.find_canfd_ids_by_serial_numbers(["201BFF2AF01202D44690", "A029A58630B30D14DBB"])
    if left_hand_scanfd_id == -1 or right_hand_scanfd_id == -1:
        print("Cannot find CANFD devices by serial numbers!")
        return
    
    left_hand = AgibotHandO10.create_hand(canfd_id=left_hand_scanfd_id, hand_type=EHandType.LEFT)
    right_hand = AgibotHandO10.create_hand(canfd_id=right_hand_scanfd_id, hand_type=EHandType.RIGHT)
    
    # 启用详细日志查看 CAN 通信
    left_hand.show_data_details(True)
    right_hand.show_data_details(True)

    left_hand.set_joint_position(2, 200)
    # time.sleep(1)
    right_hand.set_joint_position(10, 200)
    time.sleep(1)

    id2_joint_posi = left_hand.get_joint_position(2)
    print("Joint 2 position of left hand: ", id2_joint_posi)
    id2_joint_posi_right = right_hand.get_joint_position(10)
    print("Joint 10 position of right hand: ", id2_joint_posi_right)

    init_positions = [2048,2048,4096,2048,4096,4096,2048,4096,2048,4096]
    left_hand.set_all_joint_positions(init_positions)
    time.sleep(1)

    real_positions = left_hand.get_all_joint_positions()
    print("All joint positions of left hand: ", real_positions)

    right_hand.set_all_joint_positions(init_positions)
    time.sleep(1)

    real_positions_right = right_hand.get_all_joint_positions()
    print("All joint positions of right hand: ", real_positions_right)


if __name__ == "__main__":
    main()