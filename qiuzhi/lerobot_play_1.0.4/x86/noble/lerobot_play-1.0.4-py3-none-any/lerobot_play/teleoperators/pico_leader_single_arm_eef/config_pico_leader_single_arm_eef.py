"""
Copyright: qiuzhi.tech
Author: hanyang
Date: 2025-09-08 16:21:15
LastEditTime: 2025-09-08 19:42:09
"""
from dataclasses import dataclass, field
from typing import List

# Import camera configuration classes
from lerobot.cameras.configs import CameraConfig
from lerobot.robots.config import RobotConfig
from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("pico_leader_single_arm_eef")
@dataclass
class PicoLeaderSingleArmEEFConfig(TeleoperatorConfig):

    vr_pose_port: int = 8000
    vr_ctrl_port: int = 8001
    vr_device: str = "pico_wrist"  # pico_wrist
    eef_device: str = "G2"
    handedness: str = "left"  # 'left' or 'right'
    controller_side: str = "left"  # 'left' or 'right'
    wrist_pose_source: str = "auto"  # auto, left, right

    # Safety: disable torque on disconnect
    disable_torque_on_disconnect: bool = True

    # Safety limits: max relative target position per arm
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])

    cameras: dict[str, CameraConfig] = field(default_factory=dict)

    # Angle units: False=radians (recommended), True=degrees (legacy)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
