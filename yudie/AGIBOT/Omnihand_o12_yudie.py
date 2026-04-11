from agibot_hand import AgibotHandO12, EHandType
import time
from typing import List

class Agibot_HandO12:

    def __init__(self, hand_type='left'):
        if(hand_type=='left'):
            self.hand = AgibotHandO12(hand_type=EHandType.LEFT)
        else:
            self.hand = AgibotHandO12(hand_type=EHandType.RIGHT)
    
        vendor_info = self.hand.get_vendor_info()
        print("Get Vendor Info:")
        print(vendor_info)

        device_info = self.hand.get_device_info() 
        print("Get Device Info:")
        print(device_info)

        aim_positions = [2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000]
        self.hand.set_all_joint_positions(aim_positions)
        time.sleep(1)
        print("Reset Finished.")

    def reset_positions(self):
        self.hand.set_all_joint_positions(self.aim_positions)

    def set_positions(self, list):
        self.hand.set_all_joint_positions(list)

    def get_angles(self):
        active_angles = self.hand.get_all_active_joint_angles()
        print("Active Joint Angels:", active_angles)
    
    def set_angles(self, list):
        list = self.get_finger_data_for_AgibotHandO12hand_Angles(list)
        self.hand.set_all_active_joint_angles(list)

    def get_finger_data_for_AgibotHandO12hand_Angles(hand: str, hand_data: List) -> List[float]:
        """
        Get specific hand data and transfer into the 12 freedom form for OmniHand pro 2025.
        """
        RobotHandRadLimitationLeft = [0.942,-1.387,-0.827,-1.291,-0.26,1.352,1.45,0.26,1.357,1.45,1.535,1.535]
        RobotHandRadLimitationRight = [-0.942,1.387,-0.827,-1.291,-0.26,1.352,1.45,0.26,1.357,1.45,1.535,1.535]
        GloveHandAnglesLimitation = [45, 20, 72, 60, 25, 88, 88, 25, 80, 88, 80, 75]
        
        def to_12hand_Mapping(data: float, index: int) -> float:
            sign = -1 if(data > 0 and (index == 4 or index == 7)) else 1
            data = abs(data)
            if data > GloveHandAnglesLimitation[index]:
                data = GloveHandAnglesLimitation[index]
            x = (sign * data / GloveHandAnglesLimitation[index]) * RobotHandRadLimitationLeft[index] if hand == 'left' else RobotHandRadLimitationRight[index]
            return x
        
        joints = [
            to_12hand_Mapping(hand_data[20], 0) ,
            to_12hand_Mapping(5 + hand_data[3], 1),
            to_12hand_Mapping(hand_data[2], 2) ,
            to_12hand_Mapping(hand_data[1], 3) ,
            to_12hand_Mapping(hand_data[7], 4),
            to_12hand_Mapping(hand_data[6], 5) ,
            to_12hand_Mapping(hand_data[5], 6) ,
            to_12hand_Mapping(hand_data[11], 7) ,
            to_12hand_Mapping(hand_data[10], 8) ,
            to_12hand_Mapping(hand_data[9], 9) ,
            to_12hand_Mapping(hand_data[14], 10) ,
            to_12hand_Mapping(hand_data[18], 11) ,
        ]
        print(f"Finger Data: {joints}")
        return joints