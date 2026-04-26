from dataclasses import dataclass, field
from typing import List

from lerobot.cameras.configs import CameraConfig
from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("pico_leader_dual_arm_agibot_o10")
@dataclass
class PicoLeaderDualArmAgibotO10Config(TeleoperatorConfig):
    vr_pose_port: int = 8000
    vr_ctrl_port: int = 8001
    vr_device: str = "pico_wrist"
    eef_device: str = "AGIBOT_O10"
    handedness: str = "right"
    wrist_pose_source: str = "auto"
    enable_hand: bool = True
    arm_trigger_mode: str = "split"
    hand_mode: str = "glove"
    trigger_gesture: str = "pinch"
    action_control_mode: str = "joint"  # "joint" or "eef_delta"
    hand_action_mode: str = "dexterous_10d"  # "dexterous_10d" or "gripper_1d"
    left: dict = field(default_factory=dict)
    right: dict = field(default_factory=dict)
    disable_torque_on_disconnect: bool = True
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
