from dataclasses import dataclass, field
from typing import Any, List

from lerobot.robots.config import RobotConfig

from lerobot_play.utils.camera_config_parser import parse_camera_configs
from lerobot_play.utils.shared_camera_config import apply_shared_camera_config


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
    cameras: dict[str, Any] = field(default_factory=dict)
    camera_controls: dict[str, dict] = field(default_factory=dict)
    camera_config_path: str | None = None
    camera_profile: str | None = None
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500

    def __post_init__(self) -> None:
        if not self.camera_config_path:
            return

        materialized = apply_shared_camera_config(
            {
                "robot": {
                    "camera_config_path": self.camera_config_path,
                    "camera_profile": self.camera_profile,
                    "cameras": self.cameras,
                    "camera_controls": self.camera_controls,
                }
            }
        )
        robot_config = materialized["robot"]
        self.cameras = parse_camera_configs(robot_config.get("cameras", {}))
        self.camera_controls = robot_config.get("camera_controls", {})
