# Copyright (c) 2025, Agibot Co., Ltd.
# OmniHand 2025 SDK is licensed under Mulan PSL v2.

from omnihand_2025 import AgibotHandO10, EFinger, EControlMode, EHandType #omnihand_2025
from typing import List
import math

def init_hand_OmnimultiChannel(hand_type: str):
    """
    初始化手 多口CANFD
    """
    left_hand, right_hand = None, None

    if hand_type in ('left', 'both'):
        left_hand = AgibotHandO10.create_hand(device_id = 1,canfd_id = 0, channel_id= 0,hand_type = EHandType.LEFT)
    if hand_type in ('right', 'both'):
        right_hand = AgibotHandO10.create_hand(device_id = 1,canfd_id = 0, channel_id= 1,hand_type = EHandType.RIGHT)
    return [left_hand , right_hand]

def init_hand_Omni_multiCan(hand_type: str):
    """
    初始化手 多个CANFD
    """

    [left_hand_scanfd_id, right_hand_scanfd_id] = AgibotHandO10.find_canfd_ids_by_serial_numbers(["C066967CA0250EA49AA0", "A3392413700100A484B0"])
    if left_hand_scanfd_id == -1 and right_hand_scanfd_id == -1:
        print("Cannot find CANFD devices by serial numbers!")
        return[None, None]
    
    left_hand, right_hand = None, None

    if(hand_type == 'left'):
        left_hand = AgibotHandO10.create_hand(canfd_id = left_hand_scanfd_id, channel_id= 0,hand_type = EHandType.LEFT)
    elif(hand_type == 'right'):
        right_hand = AgibotHandO10.create_hand(canfd_id = right_hand_scanfd_id, channel_id= 0,hand_type = EHandType.RIGHT)
    else:
        left_hand = AgibotHandO10.create_hand(canfd_id = left_hand_scanfd_id, channel_id= 0,hand_type = EHandType.LEFT)
        right_hand = AgibotHandO10.create_hand(canfd_id = right_hand_scanfd_id, channel_id= 0,hand_type = EHandType.RIGHT)
    return [left_hand , right_hand]
def set_hand_position(hand: AgibotHandO10, positions: list, hand_type: str):
    """
    设置手的位置
    """
    if hand is None:
        return

    positions = get_finger_data_for_AgibotHandO10hand_Angles(hand_type, positions)
    hand.set_all_active_joint_angles(positions)

def is_hand_ready(hand: AgibotHandO10) -> bool:
    """
    Check whether the underlying CAN hand device is reachable.
    """
    if hand is None:
        return False

    try:
        device_info = hand.get_device_info()
    except Exception as exc:
        print(f"Failed to query OmniHand device info: {exc}")
        return False

    device_id = getattr(device_info, "device_id", 0)
    if device_id == 0:
        print("OmniHand CAN device is not ready. Please check the CANFD driver, USB connection and channel selection.")
        return False

    return True

def get_finger_data_for_o10hand(hand_data: List) -> List[float]:
        """
        Get specific hand data and transfer into the 10 freedom form for OmniHand 2025.
        """
        def to_10hand_rad(data: float, min_val: int, max_val: int) -> float:
            if data < min_val:
                data = min_val
            if data > max_val:
                data = max_val
            # normalize to rad
            x = data * math.pi / 180
            return x
        def reverse_to_10hand_rad(data: float, min_val: int, max_val: int) -> float:
            if data < min_val:
                data = min_val
            if data > max_val:
                data = max_val
            # normalize to rad
            x = data * math.pi / 180
            return -x
        def to_10hand_rad_minus(data: float, min_val: int, max_val: int) -> float:
            data = data * -1
            if data < min_val:
                data = min_val
            if data > max_val:
                data = max_val
            # normalize to rad
            x = data * math.pi / 180
            return x
        def reverse_to_10hand_rad_minus(data: float, min_val: int, max_val: int) -> float:
            data = data * -1
            if data < min_val:
                data = min_val
            if data > max_val:
                data = max_val
            # normalize to rad
            x = data * math.pi / 180
            return -x
        
        joints = [
                reverse_to_10hand_rad(hand_data[20], -10, 50),
                reverse_to_10hand_rad(hand_data[2], -100, 0),
                reverse_to_10hand_rad_minus(hand_data[1], 0, 49),
                reverse_to_10hand_rad(hand_data[7], -12, 0),
                to_10hand_rad_minus(hand_data[6], 0, 90),
                to_10hand_rad_minus(hand_data[10], 0, 90),
                reverse_to_10hand_rad(hand_data[15], 0, 10),
                to_10hand_rad_minus(hand_data[14], 0, 90),
                reverse_to_10hand_rad(hand_data[19], 0, 10),
                to_10hand_rad_minus(hand_data[18], 0, 90),
        ]
        print(f"Finger Data: {joints}")
        return joints

def get_finger_data_for_AgibotHandO10hand_Angles(hand: str, hand_data: List) -> List[int]:
    """
    Get specific hand data and transfer into the 10 freedom form for OmniHand 2025.
    """
    RobotHandAngleLimitationLeft = [-60,100,-49,12,90,90,-10,90,-10,90]
    RobotHandAngleLimitationRight = [60,-100,49,-12,90,90,10,90,10,90]
    GloveHandAnglesLimitationLeft = [37, 30, 58, 30, 79, 81, 20, 81, 30, 100]
    GloveHandAnglesLimitationRight = [37, 30, 60, 30, 81, 81, 20, 81, 30, 100]

    def to_10hand_Mapping(data: float, index: int) -> float:
        data = abs(data)
        if(hand == 'left'):
            data = GloveHandAnglesLimitationLeft[index] if data > GloveHandAnglesLimitationLeft[index] else data
            x = (data / GloveHandAnglesLimitationLeft[index]) * RobotHandAngleLimitationLeft[index]
            if(index == 0):
                x += 10
        else:
            data = GloveHandAnglesLimitationRight[index] if data > GloveHandAnglesLimitationRight[index] else data
            x = (data / GloveHandAnglesLimitationRight[index]) * RobotHandAngleLimitationRight[index]
            if(index == 0):
                x -= 10
        return int(round(x)) * math.pi / 180

    joints = [
        to_10hand_Mapping(hand_data[20], 0) ,
        to_10hand_Mapping(hand_data[3], 1),
        to_10hand_Mapping(hand_data[2], 2) ,
        to_10hand_Mapping(hand_data[7], 3),
        to_10hand_Mapping(hand_data[6], 4) ,
        to_10hand_Mapping(hand_data[10], 5) ,
        to_10hand_Mapping(hand_data[15], 6) ,
        to_10hand_Mapping(hand_data[14], 7) ,
        to_10hand_Mapping(hand_data[19], 8) ,
        to_10hand_Mapping(hand_data[18], 9) ,
    ]
    print(f"Finger Data: {joints}")
    return joints
