import logging
import time
import math
from functools import cached_property
import typing
from typing import Any, List
import numpy as np
from time import time_ns

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from lerobot.robots.robot import Robot

import airbot_hardware_py as ah
from .config_play_follower import AirbotPlayFollowerConfig
from ...utils import print_red

logger = logging.getLogger(__name__)


class AirbotPlayFollower(Robot):
    config_class = AirbotPlayFollowerConfig
    name = "airbot_play_follower"

    def __init__(self, config: AirbotPlayFollowerConfig):
        super().__init__(config)
        self.config = config

        self.can_port = self.config.can_port
        self.executor = ah.create_asio_executor(8)
        self.io_context = self.executor.get_io_context()

        self.arm = ah.PlayWithEEF.create(
            ah.MotorType.OD,
            ah.MotorType.OD,
            ah.MotorType.OD,
            ah.MotorType.DM,
            ah.MotorType.DM,
            ah.MotorType.DM,
            ah.EEFType.G2,
            ah.MotorType.DM,
        )
        self.cameras = make_cameras_from_configs(config.cameras)
        for cam in self.cameras.values():
            cam.connect()
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self) -> None:
        if self.is_connected:
            raise RuntimeError(f"{self} already connected")
        if not self.arm.init(self.io_context, self.can_port, 250):
            raise RuntimeError("Failed to initialize arm")

        self.enable_motors()
        self.configure()
        self._is_connected = True

    def enable_motors(self) -> None:
        self.arm.enable()

    def disable_motors(self) -> None:
        self.arm.disable()

    def configure(self):
        self.arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)
        self.arm.set_param("eef.control_mode", ah.MotorControlMode.PVT)

    def get_joint_pos(self):
        return self.arm.state().pos

    @property
    def _motors_ft(self) -> dict[str, type]:
        return {
            "joint1.pos": float,
            "joint2.pos": float,
            "joint3.pos": float,
            "joint4.pos": float,
            "joint5.pos": float,
            "joint6.pos": float,
            "eef.pos": float,
        }

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @cached_property
    def action_features(self):
        return {
            "joint1.pos": float,
            "joint2.pos": float,
            "joint3.pos": float,
            "joint4.pos": float,
            "joint5.pos": float,
            "joint6.pos": float,
            "eef.pos": float,
        }

    def is_state_valid(self):
        return self.arm.state().is_valid

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    def is_arm_arrive(self, arm_target, arm_pose, tolerance=0.02):
        return all(
            abs(target - pose) <= tolerance
            for target, pose in zip(arm_target, arm_pose)
        )

    def is_eef_arrive(self, eef_target, eef_pose, tolerance=0.005):
        return abs(eef_target - eef_pose) <= tolerance

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        return {**self._motors_ft, **self._cameras_ft}

    def servo_joint_pos(self, joints: typing.List[float], eef, vel=3, eff=8.0):
        velocities = [vel] * (self.config.arm_joints_num - 1) + [25]
        effort = [eff] * (self.config.arm_joints_num - 1) + [5.0]
        pos = joints + [eef]
        return self.arm.pvt(pos, velocities, effort)

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        # Read arm position
        start = time.perf_counter()
        pos = self.get_joint_pos()
        obs_dict = {
            "joint1.pos": pos[0],
            "joint2.pos": pos[1],
            "joint3.pos": pos[2],
            "joint4.pos": pos[3],
            "joint5.pos": pos[4],
            "joint6.pos": pos[5],
            "eef.pos": pos[6],
        }
        dt_ms = (time.perf_counter() - start) * 1e3
        logger.debug(f"{self} read state: {dt_ms:.1f}ms")

        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            start = time.perf_counter()
            obs_dict[cam_key] = cam.async_read()
            dt_ms = (time.perf_counter() - start) * 1e3
            # print_red(f"{self} read {cam_key}: {dt_ms:.1f}ms")

        return obs_dict

    def convert_action_format(self, action):

        # 检查是否是第二种格式（通过检查是否存在 .pos 后缀的键）
        is_second_format = any(".pos" in key for key in action.keys())

        if not is_second_format:
            # 已经是第一种格式，直接返回
            return action

        # 转换为第一种格式
        converted = {
            "joints": [],
            "eef": 0.0,
        }

        # 提取关节数据
        for i in range(1, 7):  # joint1 到 joint6
            key = f"joint{i}.pos"

            if key in action:
                converted["joints"].append(action[key])

        # 提取末端执行器数据
        if "eef.pos" in action:
            converted["eef"] = action["eef.pos"]

        return converted

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        action = self.convert_action_format(action)

        self.servo_joint_pos(action["joints"], action["eef"])
        return {
            "joint1.pos": action["joints"][0],
            "joint2.pos": action["joints"][1],
            "joint3.pos": action["joints"][2],
            "joint4.pos": action["joints"][3],
            "joint5.pos": action["joints"][4],
            "joint6.pos": action["joints"][5],
            "eef.pos": action["eef"],
        }

    def return_zero(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        joints = [0.0] * self.config.arm_joints_num
        velocities = [0.7] * self.config.arm_joints_num
        effort = [10.0] * self.config.arm_joints_num
        while True:
            state = self.get_joint_pos()
            if self.is_arm_arrive(joints, state) and self.is_eef_arrive(
                joints[6], state[6]
            ):
                break
            else:
                self.arm.pvt(joints, velocities, effort)

        return 1

    def reset_zero(self):
        self.return_zero()

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        arm_joints = self.arm.state().pos

        velocities = [0.0] * self.config.arm_joints_num
        effort = [10.0] * self.config.arm_joints_num
        self.arm.pvt(arm_joints, velocities, effort)

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
