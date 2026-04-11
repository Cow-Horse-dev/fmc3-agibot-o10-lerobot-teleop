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
from lerobot_play.teleoperators.airbot_play_with_E2_leader.config_play_with_E2_leader import (
    AirbotPlaywithE2LeaderConfig,
)

logger = logging.getLogger(__name__)


class AirbotplaywithE2Leader(Teleoperator):
    config_class = AirbotPlaywithE2LeaderConfig
    name = "airbot_play_with_E2_leader"

    def __init__(self, config: AirbotPlaywithE2LeaderConfig):
        super().__init__(config)
        self.config = config

        self.can_port = self.config.can_port

        self.arm = robotic_arm.RoboticArm()

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
        if not self.arm.initialize(self.can_port, urdf_path_str):
            raise RuntimeError("Failed to initialize play with E2")

        self.enable_motors()
        self.configure()
        self._is_connected = True

    def enable_motors(self) -> None:
        # self.arm.enable()
        pass

    def disable_motors(self) -> None:
        # self.arm.disable()
        pass

    def configure(self):
        # self.arm.set_param("arm.control_mode", ah.MotorControlMode.MIT)
        # self.arm.set_param("eef.control_mode", ah.MotorControlMode.MIT)
        self.arm.switch_state(robotic_arm.ArmState.GRAVITY_COMPENSATION)
        time.sleep(1)

    def action_features(self):
        pass

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    def observation_features(self):
        pass

    def get_joint_pos(self):
        return self.arm.get_position() + [self.arm.eef_get_position()]

    def get_action(self):
        action = self.get_joint_pos()
        action_dict = {
            "joint1.pos": action[0],
            "joint2.pos": action[1],
            "joint3.pos": action[2],
            "joint4.pos": action[3],
            "joint5.pos": action[4],
            "joint6.pos": action[5],
            "eef.pos": max(0.0, min(action[6] * 1.5, 0.072)),
        }
        return action_dict

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        pass

    def return_init(self):
        self.arm.set_param("arm.control_mode", robotic_arm.ControlMode.PVT)
        self.arm.set_param("immediate_update", 1)
        self.arm.switch_state(robotic_arm.ArmState.DEFAULT)
        home = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        target_vel = [0.5, 1.5, 0.5, 0.5, 2.0, 0.5]
        target_eff = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
        self.arm.pvt(home, target_vel, target_eff)
        self.arm.wait_reach(home, 0.02, 15.0)
        self.arm.switch_state(robotic_arm.ArmState.GRAVITY_COMPENSATION)

    @property
    def feedback_features(self) -> dict[str, type]:
        return {}

    def send_feedback(self, feedback: dict[str, float]) -> None:
        pass

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        logger.warning("airbot play arms and eefs stopped immediately")

    def _safe_shutdown(self, timeout: float = 10.0):
        logger.info("Starting safe shutdown procedure...")
        self.arm.shutdown()
        logger.info("Motors disabled and uninitialized")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            self.arm.shutdown()

        self._is_connected = False
        logger.info(f"{self} safely disconnected.")


if __name__ == "__main__":
    # config = AirbotPlaywithE2LeaderConfig()
    # arm = AirbotplaywithE2Leader(config)
    teleop_config = AirbotPlaywithE2LeaderConfig(
        can_port="can0",
        id="Play_with_E2_leader",
    )
    arm = AirbotplaywithE2Leader(teleop_config)
    arm.connect()

    now = time.time()
    while time.time() - now <= 20:
        if arm.arm.state().is_valid:
            print(arm.get_joint_pos())
        else:
            print("arm pos is not valid")

        arm.free_drive()

        time.sleep(0.01)

    arm.disconnect()
