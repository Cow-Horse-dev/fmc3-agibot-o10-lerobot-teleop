from dataclasses import dataclass, field
from typing import Any, List

from lerobot.robots.config import RobotConfig

from lerobot_play.utils.camera_config_parser import parse_camera_configs
from lerobot_play.utils.shared_camera_config import apply_shared_camera_config


@RobotConfig.register_subclass("pico_follower_single_arm_agibot_o10")
@dataclass
class PicoFollowerSingleArmAgibotO10Config(RobotConfig):
    port: str
    handedness: str = "right"
    enable_hand: bool = True
    allow_camera_read_failures: bool = False
    camera_read_timeout_ms: int = 200
    channel_mode: str = "multiChannel"
    device_id: int = 1
    canfd_id: int = 0
    channel_id: int | None = None
    reset_poses_path: str | None = None
    reset_gesture: str | None = None
    include_eef_pose: bool = True
    action_control_mode: str = "joint"  # "joint" or "eef_delta"
    hand_action_mode: str = "dexterous_10d"  # "dexterous_10d" or "gripper_1d"
    gripper_gesture: str | None = None
    tactile_mode: str = "none"

    disable_torque_on_disconnect: bool = True
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])
    cameras: dict[str, Any] = field(default_factory=dict)
    camera_controls: dict[str, dict] = field(default_factory=dict)
    camera_config_path: str | None = None
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
                    "cameras": self.cameras,
                    "camera_controls": self.camera_controls,
                }
            }
        )
        robot_config = materialized["robot"]
        self.cameras = parse_camera_configs(robot_config.get("cameras", {}))
        self.camera_controls = robot_config.get("camera_controls", {})
