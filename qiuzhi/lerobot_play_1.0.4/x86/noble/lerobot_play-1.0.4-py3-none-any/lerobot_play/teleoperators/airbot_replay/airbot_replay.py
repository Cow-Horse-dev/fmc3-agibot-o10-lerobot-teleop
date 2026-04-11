import logging
import time
import math
from functools import cached_property
import typing
from typing import Any, List
import numpy as np
from time import time_ns

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.robots.robot import Robot
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from lerobot.teleoperators.teleoperator import Teleoperator

import airbot_hardware_py as ah
from lerobot_play.teleoperators.airbot_replay.config_replay import AirbotReplayConfig

logger = logging.getLogger(__name__)


class AirbotReplay(Teleoperator):
    config_class = AirbotReplayConfig
    name = "airbot_replay"

    def __init__(self, config: AirbotReplayConfig):
        super().__init__(config)
        self.config = config

        self.can_port = self.config.can_port
        self.executor = ah.create_asio_executor(8)
        self.io_context = self.executor.get_io_context()

        self.arm = ah.PlayWithEEF.create(
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.EEFType.E2,
            ah.MotorType.EC,
        )
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
        if self.is_connected:
            raise RuntimeError(f"{self} already connected")
        if not self.arm.init(self.io_context, self.can_port, 250):
            raise RuntimeError("Failed to initialize replay")

        self.enable_motors()
        self.configure()
        self._is_connected = True

    def enable_motors(self) -> None:
        self.arm.enable()

    def disable_motors(self) -> None:
        self.arm.disable()

    def configure(self):
        self.arm.set_param("arm.control_mode", ah.MotorControlMode.MIT)

    def action_features(self):
        pass

    def is_state_valid(self):
        return self.arm.state().is_valid

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    def observation_features(self):
        pass

    def free_drive(self):
        self.arm.mit(
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
        )

    def get_joint_pos(self):
        self.free_drive()
        return self.arm.state().pos

    def get_action(self):
        self.free_drive()
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
        self.disable_motors()
        self.arm.uninit()
        logger.info("Motors disabled and uninitialized")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            self.disable_motors()
            self.arm.uninit()

        self._is_connected = False
        logger.info(f"{self} safely disconnected.")


# if __name__ == "__main__":
#     config = AirbotReplayConfig()
#     arm = AirbotReplay(config)
#     arm.connect()

#     now = time.time()
#     while time.time() - now <= 10:
#         print(arm.get_joint_pos())
#         time.sleep(0.001)

#     arm.disconnect()
