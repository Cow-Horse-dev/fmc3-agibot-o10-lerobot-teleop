"""
Copyright: qiuzhi.tech
Author: hanyang
Date: 2025-09-08 16:21:15
LastEditTime: 2025-09-08 19:42:09
"""
# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass, field
from typing import List

# Import camera configuration classes
from lerobot.cameras.configs import CameraConfig, Cv2Rotation, ColorMode
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from lerobot.robots.config import RobotConfig


@RobotConfig.register_subclass("airbot_play_follower")
@dataclass
class AirbotPlayFollowerConfig(RobotConfig):
    """Core configuration for airbot play robot"""

    # CAN ports for left/right arms
    can_port: str = "can0"

    # Safety: disable torque on disconnect
    disable_torque_on_disconnect: bool = True

    # Safety limits: max relative target position per arm
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])

    cameras: dict[str, CameraConfig] = field(default_factory=dict)

    # Angle units: False=radians (recommended), True=degrees (legacy)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
