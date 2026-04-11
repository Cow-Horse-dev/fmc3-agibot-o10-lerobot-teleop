from dataclasses import dataclass, field
from typing import List

# Import camera configuration classes
from lerobot.cameras.configs import CameraConfig
from lerobot.robots.config import RobotConfig


@RobotConfig.register_subclass("airbot_TOK2_follower")
@dataclass
class AirbotTOK2FollowerConfig(RobotConfig):

    # CAN ports for left/right arms
    left_arm_port: str
    right_arm_port: str

    # Safety: disable torque on disconnect
    disable_torque_on_disconnect: bool = True

    # Safety limits: max relative target position per arm
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])

    cameras: dict[str, CameraConfig] = field(default_factory=dict)

    # Angle units: False=radians (recommended), True=degrees (legacy)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
