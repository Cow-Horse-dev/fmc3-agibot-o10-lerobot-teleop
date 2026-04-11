from dataclasses import dataclass, field
from typing import List

from lerobot.cameras.configs import CameraConfig
from lerobot.robots.config import RobotConfig


@RobotConfig.register_subclass("pico_follower_single_arm_agibot_o10")
@dataclass
class PicoFollowerSingleArmAgibotO10Config(RobotConfig):
    port: str
    handedness: str = "right"
    channel_mode: str = "multiChannel"
    device_id: int = 1
    canfd_id: int = 0
    channel_id: int | None = None
    hand_reset_joints_path: str | None = None
    include_tactile_observation: bool = False

    disable_torque_on_disconnect: bool = True
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
