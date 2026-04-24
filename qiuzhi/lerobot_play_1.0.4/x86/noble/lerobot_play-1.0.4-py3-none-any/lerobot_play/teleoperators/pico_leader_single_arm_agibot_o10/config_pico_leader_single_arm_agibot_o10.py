from dataclasses import dataclass, field
from typing import List

from lerobot.cameras.configs import CameraConfig
from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("pico_leader_single_arm_agibot_o10")
@dataclass
class PicoLeaderSingleArmAgibotO10Config(TeleoperatorConfig):
    vr_pose_port: int = 8000
    vr_ctrl_port: int = 8001
    vr_device: str = "pico_wrist"
    eef_device: str = "AGIBOT_O10"
    handedness: str = "right"
    controller_side: str = "right"
    wrist_pose_source: str = "auto"
    enable_hand: bool = True
    hand_mode: str = "glove"
    trigger_gesture: str = "pinch"
    reset_poses_path: str | None = None
    reset_gesture: str | None = None
    disable_torque_on_disconnect: bool = True
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
