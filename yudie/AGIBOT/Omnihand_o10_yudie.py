# Copyright (c) 2025, Agibot Co., Ltd.
# OmniHand 2025 SDK is licensed under Mulan PSL v2.

from omnihand_2025 import AgibotHandO10, EFinger, EControlMode, EHandType #omnihand_2025
from typing import Dict, List
import math

from lerobot_play.utils.agibot_o10 import O10HandMapper

_O10_GLOVE_SLOT_INDICES = (20, 3, 2, 7, 6, 10, 15, 14, 19, 18)
_o10_mapper_by_hand_id: Dict[int, O10HandMapper] = {}


def _get_or_create_mapper(hand: AgibotHandO10, hand_type: str) -> O10HandMapper:
    mapper = _o10_mapper_by_hand_id.get(id(hand))
    if mapper is None:
        mapper = O10HandMapper(handedness=hand_type)
        _o10_mapper_by_hand_id[id(hand)] = mapper
    return mapper


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
    """设置手的位置 — 调用共享的 O10HandMapper（lerobot_play 那侧的实现）。"""
    if hand is None:
        return

    glove_deg = get_finger_data_for_AgibotHandO10hand_Angles(hand_type, positions)
    mapper = _get_or_create_mapper(hand, hand_type)
    rad_targets = mapper.map(glove_deg)
    hand.set_all_active_joint_angles(rad_targets)

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

def get_finger_data_for_AgibotHandO10hand_Angles(hand: str, hand_data: List) -> List[float]:
    """从 24 路手套原始 deg 中挑出 10 路对应 OmniHand O10 的关节，去符号；
    实际 deg→rad 的缩放与滤波交给 O10HandMapper。"""
    return [abs(float(hand_data[slot])) for slot in _O10_GLOVE_SLOT_INDICES]
