from dataclasses import dataclass, field
from typing import List

from lerobot.cameras.configs import CameraConfig
from lerobot.robots.config import RobotConfig


@dataclass
class DualArmSideConfig:
    port: str = "can0"
    handedness: str = "right"
    channel_mode: str = "multiChannel"
    device_id: int = 1
    canfd_id: int = 0
    channel_id: int | None = None
    reset_poses_path: str | None = None
    reset_gesture: str | None = None


@RobotConfig.register_subclass("pico_follower_dual_arm_agibot_o10")
@dataclass
class PicoFollowerDualArmAgibotO10Config(RobotConfig):
    left: dict = field(default_factory=dict)
    right: dict = field(default_factory=dict)
    enable_hand: bool = True
    allow_camera_read_failures: bool = False
    include_eef_pose: bool = True
    action_control_mode: str = "joint"  # "joint" or "eef_delta"
    hand_action_mode: str = "dexterous_10d"  # "dexterous_10d" or "gripper_1d"
    tactile_mode: str = "none"  # "none" or "130d"
    disable_torque_on_disconnect: bool = True
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
