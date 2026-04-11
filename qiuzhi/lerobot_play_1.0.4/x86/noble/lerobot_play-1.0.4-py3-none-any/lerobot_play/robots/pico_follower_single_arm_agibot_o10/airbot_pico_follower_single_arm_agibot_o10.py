import logging
import time
from functools import cached_property
from typing import Any

import numpy as np
from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.robots.robot import Robot
from lerobot.utils.errors import DeviceNotConnectedError
from mmk2_kdl_py import ArmKdlNumerical

import airbot_hardware_py as ah
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AGIBOT_O10_POSE_FEATURE_NAMES,
    AgibotO10Hand,
    agibot_o10_action_feature_types,
    agibot_o10_joint_action_feature_types,
    build_agibot_o10_joint_action_dict,
)
from lerobot_play.utils.camera_autodetect import resolve_auto_opencv_cameras

from .config_pico_follower_single_arm_agibot_o10 import (
    PicoFollowerSingleArmAgibotO10Config,
)

logger = logging.getLogger(__name__)


class PicoFollowerSingleArmAgibotO10(Robot):
    config_class = PicoFollowerSingleArmAgibotO10Config
    name = "pico_follower_single_arm_agibot_o10"

    def __init__(self, config: PicoFollowerSingleArmAgibotO10Config):
        super().__init__(config)
        self.config = config
        self.arm_kdl = ArmKdlNumerical(eef_type="none")
        self.arm_port = self.config.port

        self.executor = ah.create_asio_executor(8)
        self.io_context = self.executor.get_io_context()
        self.arm = ah.Play.create(
            ah.MotorType.OD,
            ah.MotorType.OD,
            ah.MotorType.OD,
            ah.MotorType.DM,
            ah.MotorType.DM,
            ah.MotorType.DM,
            ah.EEFType.NA,
            ah.MotorType.NA,
        )

        self.hand = AgibotO10Hand(
            handedness=self.config.handedness,
            channel_mode=self.config.channel_mode,
            device_id=self.config.device_id,
            canfd_id=self.config.canfd_id,
            channel_id=self.config.channel_id,
        )
        self.hand_joints = [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)

        resolve_auto_opencv_cameras(config.cameras)
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

        if not self.arm.init(self.io_context, self.arm_port, 250):
            raise RuntimeError("Failed to initialize arm")

        try:
            self.hand.connect()
        except Exception:
            self.arm.uninit()
            raise

        self.enable_motors()
        self.configure()
        self._is_connected = True

    def enable_motors(self) -> None:
        self.arm.enable()

    def disable_motors(self) -> None:
        self.arm.disable()

    def configure(self) -> None:
        self.arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)

    def get_joint_pos(self) -> list[list[float]]:
        return [list(self.arm.state().pos), self.hand.read_active_joint_angles()]

    @property
    def _motors_ft(self) -> dict[str, type]:
        return agibot_o10_action_feature_types()

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @cached_property
    def action_features(self):
        return agibot_o10_joint_action_feature_types()

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        return {**self._motors_ft, **self._cameras_ft}

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    def is_arm_arrive(self, arm_target, arm_pose, tolerance=0.02):
        return all(
            abs(target - pose) <= tolerance
            for target, pose in zip(arm_target, arm_pose)
        )

    def servo_joint_pos(self, joints: list[float], vel: float = 3.0, eff: float = 8.0):
        velocities = [vel] * (self.config.arm_joints_num - 1)
        effort = [eff] * (self.config.arm_joints_num - 1)
        return self.arm.pvt(joints, velocities, effort)

    def homogeneous_matrix_to_pose(self, matrix):
        matrix = np.array(matrix)
        if matrix.shape != (4, 4):
            raise ValueError("输入必须是4x4矩阵")

        position = matrix[:3, 3].flatten()
        rotation_matrix = matrix[:3, :3]

        def rotation_matrix_to_quaternion(rotation):
            if not np.allclose(np.dot(rotation, rotation.T), np.eye(3), atol=1e-8):
                raise ValueError("旋转矩阵不满足正交条件")

            quaternion = np.zeros(4)
            trace = np.trace(rotation)

            if trace > 0:
                scalar = np.sqrt(trace + 1.0) * 2
                quaternion[3] = 0.25 * scalar
                quaternion[0] = (rotation[2, 1] - rotation[1, 2]) / scalar
                quaternion[1] = (rotation[0, 2] - rotation[2, 0]) / scalar
                quaternion[2] = (rotation[1, 0] - rotation[0, 1]) / scalar
            elif (rotation[0, 0] > rotation[1, 1]) and (
                rotation[0, 0] > rotation[2, 2]
            ):
                scalar = np.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2
                quaternion[3] = (rotation[2, 1] - rotation[1, 2]) / scalar
                quaternion[0] = 0.25 * scalar
                quaternion[1] = (rotation[0, 1] + rotation[1, 0]) / scalar
                quaternion[2] = (rotation[0, 2] + rotation[2, 0]) / scalar
            elif rotation[1, 1] > rotation[2, 2]:
                scalar = np.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2
                quaternion[3] = (rotation[0, 2] - rotation[2, 0]) / scalar
                quaternion[0] = (rotation[0, 1] + rotation[1, 0]) / scalar
                quaternion[1] = 0.25 * scalar
                quaternion[2] = (rotation[1, 2] + rotation[2, 1]) / scalar
            else:
                scalar = np.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2
                quaternion[3] = (rotation[1, 0] - rotation[0, 1]) / scalar
                quaternion[0] = (rotation[0, 2] + rotation[2, 0]) / scalar
                quaternion[1] = (rotation[1, 2] + rotation[2, 1]) / scalar
                quaternion[2] = 0.25 * scalar

            return quaternion / np.linalg.norm(quaternion)

        quaternion = rotation_matrix_to_quaternion(rotation_matrix)
        return np.concatenate([position, quaternion])

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        arm_pos, hand_pos = self.get_joint_pos()
        pose = self.homogeneous_matrix_to_pose(self.arm_kdl.forward_kinematics(arm_pos[:6]))

        obs_dict = {
            **{
                feature_name: arm_pos[index]
                for index, feature_name in enumerate(AGIBOT_O10_ARM_FEATURE_NAMES)
            },
            **{
                feature_name: hand_pos[index]
                for index, feature_name in enumerate(AGIBOT_O10_HAND_FEATURE_NAMES)
            },
            **{
                feature_name: pose[index]
                for index, feature_name in enumerate(AGIBOT_O10_POSE_FEATURE_NAMES)
            },
        }

        for cam_key, cam in self.cameras.items():
            obs_dict[cam_key] = cam.async_read()

        return obs_dict

    def convert_action_format(self, action: dict[str, Any]) -> dict[str, list[float]]:
        if "joints" in action and "hand_joints" in action:
            joints = [float(value) for value in action["joints"]]
            hand_joints = [float(value) for value in action["hand_joints"]]
        else:
            joints = [float(action[name]) for name in AGIBOT_O10_ARM_FEATURE_NAMES]
            hand_joints = [float(action[name]) for name in AGIBOT_O10_HAND_FEATURE_NAMES]

        if len(joints) != len(AGIBOT_O10_ARM_FEATURE_NAMES):
            raise ValueError(
                f"Expected {len(AGIBOT_O10_ARM_FEATURE_NAMES)} arm joints, got {len(joints)}"
            )
        if len(hand_joints) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
            raise ValueError(
                f"Expected {len(AGIBOT_O10_HAND_FEATURE_NAMES)} hand joints, got {len(hand_joints)}"
            )

        return {
            "joints": joints,
            "hand_joints": hand_joints,
        }

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        formatted_action = self.convert_action_format(action)

        self.servo_joint_pos(formatted_action["joints"])
        self.hand.write_active_joint_angles(formatted_action["hand_joints"])
        self.hand_joints = formatted_action["hand_joints"].copy()

        return build_agibot_o10_joint_action_dict(
            [*formatted_action["joints"], *formatted_action["hand_joints"]]
        )

    def return_zero(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        joints = [0.0] * (self.config.arm_joints_num - 1)
        velocities = [0.8] * (self.config.arm_joints_num - 1)
        effort = [10.0] * (self.config.arm_joints_num - 1)
        zero_hand = [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)

        while True:
            state = list(self.arm.state().pos)
            arm_arrived = self.is_arm_arrive(joints, state)
            if arm_arrived:
                break
            self.arm.pvt(joints, velocities, effort)
            self.hand.write_active_joint_angles(zero_hand)
            time.sleep(0.004)

        self.hand.write_active_joint_angles(zero_hand)
        self.hand_joints = zero_hand

    def reset_zero(self):
        self.return_zero()

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

    def _safe_shutdown(self, timeout: float = 10.0):
        logger.info("Starting safe shutdown procedure...")
        self.disable_motors()
        self.arm.uninit()
        self.hand.disconnect()
        logger.info("Motors disabled and devices disconnected")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            self.disable_motors()
            self.arm.uninit()
            self.hand.disconnect()
        self._is_connected = False
        logger.info(f"{self} safely disconnected.")
