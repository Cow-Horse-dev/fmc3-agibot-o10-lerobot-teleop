# import sys
# import os

# project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# sys.path.insert(0, project_root)

import logging
import time
import typing
from typing import Any, List
import numpy as np
from time import time_ns
import pkg_resources

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from lerobot.teleoperators.teleoperator import Teleoperator
from pathlib import Path

import airbot_hardware_py as ah
from airbot_state_machine import robotic_arm
from lerobot_play.teleoperators.airbot_tok4_leader.config_TOK4_leader import (
    AirbotTOK4LeaderConfig,
)

logger = logging.getLogger(__name__)


class AirbotTOK4Leader(Teleoperator):
    config_class = AirbotTOK4LeaderConfig
    name = "airbot_TOK4_leader"

    def __init__(self, config: AirbotTOK4LeaderConfig):
        super().__init__(config)
        self.config = config

        self.left_arm_port = self.config.left_arm_port
        self.right_arm_port = self.config.right_arm_port

        self.left_arm = robotic_arm.RoboticArm()
        self.right_arm = robotic_arm.RoboticArm()

        self.cameras = make_cameras_from_configs(config.cameras)
        self._is_connected = False

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self) -> None:
        urdf_path_str = pkg_resources.resource_filename(
            "lerobot_play", "urdf/play_e2/urdf/play_e2.urdf"
        )
        if self.is_connected:
            raise RuntimeError(f"{self} already connected")
        if not self.left_arm.initialize(self.left_arm_port, urdf_path_str):
            raise RuntimeError("Failed to initialize left play with E2")
        if not self.right_arm.initialize(self.right_arm_port, urdf_path_str):
            raise RuntimeError("Failed to initialize right play with E2")

        self.enable_motors()
        self.configure()
        self._is_connected = True

    def enable_motors(self) -> None:
        pass

    def disable_motors(self) -> None:
        pass

    def configure(self):
        self.left_arm.switch_state(robotic_arm.ArmState.GRAVITY_COMPENSATION)
        self.right_arm.switch_state(robotic_arm.ArmState.GRAVITY_COMPENSATION)

    def action_features(self):
        pass

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    def observation_features(self):
        pass

    def get_joint_pos(self):
        left_state = self.left_arm.get_position() + [self.left_arm.eef_get_position()]
        right_state = self.right_arm.get_position() + [
            self.right_arm.eef_get_position()
        ]
        return [left_state, right_state]

    def get_action(self):
        action = self.get_joint_pos()

        action_dict = {
            "left_joint1.pos": action[0][0],
            "left_joint2.pos": action[0][1],
            "left_joint3.pos": action[0][2],
            "left_joint4.pos": action[0][3],
            "left_joint5.pos": action[0][4],
            "left_joint6.pos": action[0][5],
            "left_eef.pos": action[0][6],
            "right_joint1.pos": action[1][0],
            "right_joint2.pos": action[1][1],
            "right_joint3.pos": action[1][2],
            "right_joint4.pos": action[1][3],
            "right_joint5.pos": action[1][4],
            "right_joint6.pos": action[1][5],
            "right_eef.pos": action[1][6],
        }
        return action_dict

    def get_eef_pos(self):
        pass

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        pass

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        pass

    @property
    def feedback_features(self) -> dict[str, type]:
        return {}

    def send_feedback(self, feedback: dict[str, float]) -> None:
        pass

    def return_init(self):
        self.left_arm.set_param("arm.control_mode", robotic_arm.ControlMode.PVT)
        self.left_arm.set_param("immediate_update", 1)

        self.right_arm.set_param("arm.control_mode", robotic_arm.ControlMode.PVT)
        self.right_arm.set_param("immediate_update", 1)

        self.left_arm.switch_state(robotic_arm.ArmState.DEFAULT)
        self.right_arm.switch_state(robotic_arm.ArmState.DEFAULT)

        home = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        target_vel = [0.5, 1.5, 0.5, 0.5, 2.0, 0.5]
        target_eff = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
        self.left_arm.pvt(home, target_vel, target_eff)
        self.left_arm.wait_reach(home, 0.02, 15.0)
        self.right_arm.pvt(home, target_vel, target_eff)
        self.right_arm.wait_reach(home, 0.02, 15.0)

        self.left_arm.switch_state(robotic_arm.ArmState.GRAVITY_COMPENSATION)
        self.right_arm.switch_state(robotic_arm.ArmState.GRAVITY_COMPENSATION)

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        logger.warning("airbot play arms and eefs stopped immediately")

    def _safe_shutdown(self, timeout: float = 10.0):
        logger.info("Starting safe shutdown procedure...")
        self.left_arm.shutdown()
        self.right_arm.shutdown()

        logger.info("Motors disabled and uninitialized")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            self.left_arm.shutdown()
            self.right_arm.shutdown()

        self._is_connected = False
        logger.info(f"{self} safely disconnected.")


if __name__ == "__main__":
    # config = AirbotPTKLeaderConfig()
    # arm = AirbotPTKLeader(config)
    teleop_config = AirbotTOK4LeaderConfig(
        left_arm_port="can2",
        right_arm_port="can3",
        id="PTK_leader",
    )
    arm = AirbotTOK4Leader(teleop_config)
    arm.connect()

    now = time.time()
    while time.time() - now <= 10:
        if arm.get_is_valid():
            print(arm.get_joint_pos())
        else:
            print("is not valid")
        time.sleep(1)

    arm.disconnect()
