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

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from lerobot.teleoperators.teleoperator import Teleoperator

import airbot_hardware_py as ah
from lerobot_play.teleoperators.airbot_tok2_mini_leader.config_TOK2_mini_leader import (
    AirbotTOK2MiniLeaderConfig,
)

logger = logging.getLogger(__name__)


class AirbotTOK2MiniLeader(Teleoperator):
    config_class = AirbotTOK2MiniLeaderConfig
    name = "airbot_TOK2_mini_leader"

    def __init__(self, config: AirbotTOK2MiniLeaderConfig):
        super().__init__(config)
        self.config = config

        self.left_arm_port = self.config.left_arm_port
        self.right_arm_port = self.config.right_arm_port

        self.executor_left = ah.create_asio_executor(8)
        self.executor_right = ah.create_asio_executor(8)

        self.io_context_left = self.executor_left.get_io_context()
        self.io_context_right = self.executor_right.get_io_context()

        self.left_arm = ah.PlayWithEEF.create(
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.MotorType.EC,
            ah.EEFType.E2,
            ah.MotorType.EC,
        )
        self.right_arm = ah.PlayWithEEF.create(
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
        if not self.left_arm.init(self.io_context_left, self.left_arm_port, 250):
            raise RuntimeError("Failed to initialize left replay")
        if not self.right_arm.init(self.io_context_right, self.right_arm_port, 250):
            raise RuntimeError("Failed to initialize right replay")

        self.enable_motors()
        self.configure()
        self._is_connected = True

    def enable_motors(self) -> None:
        self.left_arm.enable()
        self.right_arm.enable()

    def disable_motors(self) -> None:
        self.left_arm.disable()
        self.right_arm.disable()

    def configure(self):
        self.left_arm.set_param("arm.control_mode", ah.MotorControlMode.MIT)
        self.right_arm.set_param("arm.control_mode", ah.MotorControlMode.MIT)

    def action_features(self):
        pass

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    def observation_features(self):
        pass

    def is_state_valid(self):
        return self.left_arm.state().is_valid and self.right_arm.state().is_valid

    def free_drive(self):
        self.left_arm.mit(
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
        )
        self.right_arm.mit(
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
        )

    def get_joint_pos(self):
        self.free_drive()
        return [self.left_arm.state().pos, self.right_arm.state().pos]

    def get_action(self):
        self.free_drive()
        action = self.get_joint_pos()

        action_dict = {
            "left_joint1.pos": action[0][0],
            "left_joint2.pos": action[0][1] - 0.176,
            "left_joint3.pos": -(action[0][2] + 0.084),
            "left_joint4.pos": action[0][3],
            "left_joint5.pos": -action[0][4],
            "left_joint6.pos": action[0][5],
            "left_eef.pos": max(
                0.0, min(abs(action[0][6]) * (0.072 / 0.01) - 0.005, 0.072)
            ),
            "right_joint1.pos": action[1][0],
            "right_joint2.pos": action[1][1],
            "right_joint3.pos": -(action[1][2]),
            "right_joint4.pos": action[1][3],
            "right_joint5.pos": -action[1][4],
            "right_joint6.pos": action[1][5],
            "right_eef.pos": max(
                0.0, min(abs(action[1][6]) * (0.072 / 0.01) - 0.005, 0.072)
            ),
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

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        logger.warning("airbot play arms and eefs stopped immediately")

    def _safe_shutdown(self, timeout: float = 10.0):
        logger.info("Starting safe shutdown procedure...")
        self.disable_motors()

        self.left_arm.uninit()
        self.right_arm.uninit()

        logger.info("Motors disabled and uninitialized")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            self.disable_motors()
            self.left_arm.uninit()
            self.right_arm.uninit()

        self._is_connected = False
        logger.info(f"{self} safely disconnected.")


# if __name__ == "__main__":
#     # config = AirbotPTKLeaderConfig()
#     # arm = AirbotPTKLeader(config)
#     teleop_config = AirbotTOKLeaderConfig(
#         left_arm_port="can2",
#         right_arm_port="can3",
#         id="PTK_leader",
#     )
#     arm = AirbotTOKLeader(teleop_config)
#     arm.connect()

#     now = time.time()
#     while time.time() - now <= 10:
#         if arm.get_is_valid():
#             print(arm.get_joint_pos())
#         else:
#             print("is not valid")
#         time.sleep(1)

#     arm.disconnect()
