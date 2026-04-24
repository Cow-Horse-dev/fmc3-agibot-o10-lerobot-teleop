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
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore, load_reset_poses

from .config_pico_follower_single_arm_agibot_o10 import (
    PicoFollowerSingleArmAgibotO10Config,
)

logger = logging.getLogger(__name__)


TACTILE_REGION_NAMES = (
    "tactile.thumb_avg",
    "tactile.index_avg",
    "tactile.middle_avg",
    "tactile.ring_avg",
    "tactile.little_avg",
    "tactile.palm_avg",
    "tactile.dorsum_avg",
)

TACTILE_FINGERTIP_NAMES = tuple(
    f"tactile.{finger}_{index}"
    for finger in ("thumb", "index", "middle", "ring", "little")
    for index in range(16)
)

TACTILE_FULL_NAMES = TACTILE_FINGERTIP_NAMES + tuple(
    f"tactile.palm_{index}" for index in range(25)
) + tuple(
    f"tactile.dorsum_{index}" for index in range(25)
)


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

        self.hand = (
            AgibotO10Hand(
                handedness=self.config.handedness,
                channel_mode=self.config.channel_mode,
                device_id=self.config.device_id,
                canfd_id=self.config.canfd_id,
                channel_id=self.config.channel_id,
            )
            if self.config.enable_hand
            else None
        )
        self.hand_joints = [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)
        self.arm_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_ARM_FEATURE_NAMES,
            path=None,
            label=f"{self.config.handedness} arm reset joint target",
            group_key="arm",
        )
        self.hand_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
            path=None,
            label=f"{self.config.handedness} hand reset joint target",
            group_key="hand",
        )
        self.reset_arm_joint_pos = [0.0] * len(AGIBOT_O10_ARM_FEATURE_NAMES)
        self.reset_hand_joint_pos = [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)

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

        if self.hand is not None:
            try:
                self.hand.connect()
            except Exception:
                self.arm.uninit()
                raise
        else:
            logger.info("Agibot O10 hand follower disabled. Running in arm-only mode.")

        self.enable_motors()
        self.configure()
        self._load_reset_target_from_file()
        self._is_connected = True

    def enable_motors(self) -> None:
        self.arm.enable()

    def disable_motors(self) -> None:
        self.arm.disable()

    def configure(self) -> None:
        self.arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)

    def get_joint_pos(self) -> list[list[float]]:
        hand_joint_pos = (
            self.hand.read_active_joint_angles()
            if self.hand is not None
            else self.hand_joints.copy()
        )
        return [list(self.arm.state().pos), hand_joint_pos]

    @staticmethod
    def _log_joint_pos(title: str, feature_names: tuple[str, ...], joint_pos: list[float]) -> None:
        logger.info(title)
        for feature_name, joint_value in zip(feature_names, joint_pos, strict=True):
            logger.info("  %s: %.4f", feature_name, joint_value)

    def capture_current_joint_pos_as_reset_target(
        self, persist: bool = True
    ) -> tuple[list[float], list[float]]:
        arm_joint_pos, hand_joint_pos = self.get_joint_pos()
        arm_joint_pos = arm_joint_pos[: len(AGIBOT_O10_ARM_FEATURE_NAMES)]
        arm_joint_pos = self.arm_reset_store.normalize(arm_joint_pos)
        hand_joint_pos = self.hand_reset_store.normalize(hand_joint_pos)

        self.reset_arm_joint_pos = arm_joint_pos.copy()
        self.reset_hand_joint_pos = hand_joint_pos.copy()
        self.hand_joints = hand_joint_pos.copy()

        if persist:
            logger.info(
                "Persist requested for reset target capture, "
                "but centralized reset_poses JSON is not modified at runtime."
            )

        self._log_joint_pos(
            "Captured Agibot O10 arm reset target:",
            AGIBOT_O10_ARM_FEATURE_NAMES,
            arm_joint_pos,
        )
        self._log_joint_pos(
            "Captured Agibot O10 hand reset target:",
            AGIBOT_O10_HAND_FEATURE_NAMES,
            hand_joint_pos,
        )
        return arm_joint_pos, hand_joint_pos

    def _load_reset_target_from_file(self) -> None:
        reset_poses_path = getattr(self.config, "reset_poses_path", None)
        reset_gesture = getattr(self.config, "reset_gesture", None)
        if reset_poses_path and reset_gesture:
            try:
                arm_loaded, hand_loaded = load_reset_poses(
                    reset_poses_path, self.config.handedness, reset_gesture,
                )
            except Exception as exc:
                logger.warning("Failed to load reset poses: %s", exc)
                arm_loaded, hand_loaded = None, None
        else:
            arm_loaded, hand_loaded = None, None

        if arm_loaded is not None:
            self.reset_arm_joint_pos = arm_loaded
        if hand_loaded is not None:
            self.reset_hand_joint_pos = hand_loaded
            self.hand_joints = hand_loaded.copy()
        self._log_joint_pos("Reset arm target", AGIBOT_O10_ARM_FEATURE_NAMES, self.reset_arm_joint_pos)
        self._log_joint_pos("Reset hand target", AGIBOT_O10_HAND_FEATURE_NAMES, self.reset_hand_joint_pos)

    @property
    def _motors_ft(self) -> dict[str, type]:
        if self.config.include_eef_pose:
            return agibot_o10_action_feature_types()
        return agibot_o10_joint_action_feature_types()

    @staticmethod
    def _camera_uses_depth(camera_config: Any) -> bool:
        return bool(getattr(camera_config, "use_depth", False))

    @staticmethod
    def _depth_observation_name(camera_name: str) -> str:
        return f"{camera_name}_depth"

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        camera_features: dict[str, tuple] = {}
        for camera_name in self.cameras:
            camera_config = self.config.cameras[camera_name]
            camera_features[camera_name] = (
                camera_config.height,
                camera_config.width,
                3,
            )
            if self._camera_uses_depth(camera_config):
                camera_features[self._depth_observation_name(camera_name)] = (
                    camera_config.height,
                    camera_config.width,
                    1,
                )
        return camera_features

    @cached_property
    def action_features(self):
        return agibot_o10_joint_action_feature_types()

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        tactile_mode = getattr(self.config, "tactile_mode", "none")
        tactile_ft: dict[str, type] = {}
        if tactile_mode == "7d":
            tactile_ft = {name: float for name in TACTILE_REGION_NAMES}
        elif tactile_mode == "80d":
            tactile_ft = {name: float for name in TACTILE_FINGERTIP_NAMES}
        elif tactile_mode == "130d":
            tactile_ft = {name: float for name in TACTILE_FULL_NAMES}
        return {**self._motors_ft, **tactile_ft, **self._cameras_ft}

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

        obs_dict = {
            **{
                feature_name: arm_pos[index]
                for index, feature_name in enumerate(AGIBOT_O10_ARM_FEATURE_NAMES)
            },
            **{
                feature_name: hand_pos[index]
                for index, feature_name in enumerate(AGIBOT_O10_HAND_FEATURE_NAMES)
            },
        }

        if self.config.include_eef_pose:
            pose = self.homogeneous_matrix_to_pose(self.arm_kdl.forward_kinematics(arm_pos[:6]))
            for index, feature_name in enumerate(AGIBOT_O10_POSE_FEATURE_NAMES):
                obs_dict[feature_name] = pose[index]

        tactile_mode = getattr(self.config, "tactile_mode", "none")
        if self.hand is not None and tactile_mode != "none":
            if tactile_mode == "7d":
                tactile_avg = self.hand.read_tactile_avg()
                for index, feature_name in enumerate(TACTILE_REGION_NAMES):
                    obs_dict[feature_name] = tactile_avg[index]
            elif tactile_mode == "80d":
                tactile_fingertip = self.hand.read_tactile_fingertip()
                for index, feature_name in enumerate(TACTILE_FINGERTIP_NAMES):
                    obs_dict[feature_name] = tactile_fingertip[index]
            elif tactile_mode == "130d":
                tactile_full = self.hand.read_tactile_full()
                for index, feature_name in enumerate(TACTILE_FULL_NAMES):
                    obs_dict[feature_name] = tactile_full[index]

        for cam_key, cam in self.cameras.items():
            if self._camera_uses_depth(self.config.cameras[cam_key]):
                color_frame, depth_frame = cam.async_read_color_and_depth()
                obs_dict[cam_key] = color_frame
                obs_dict[self._depth_observation_name(cam_key)] = np.expand_dims(
                    depth_frame, axis=-1
                )
                continue

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
        self.hand_joints = formatted_action["hand_joints"].copy()
        if self.hand is not None:
            self.hand.write_active_joint_angles(formatted_action["hand_joints"])

        return build_agibot_o10_joint_action_dict(
            [*formatted_action["joints"], *formatted_action["hand_joints"]]
        )

    def return_zero(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        joints = self.reset_arm_joint_pos.copy()
        velocities = [0.8] * (self.config.arm_joints_num - 1)
        effort = [10.0] * (self.config.arm_joints_num - 1)
        reset_hand = self.reset_hand_joint_pos.copy()

        while True:
            state = list(self.arm.state().pos)
            arm_arrived = self.is_arm_arrive(joints, state)
            if arm_arrived:
                break
            self.arm.pvt(joints, velocities, effort)
            if self.hand is not None:
                self.hand.write_active_joint_angles(reset_hand)
            time.sleep(0.004)

        if self.hand is not None:
            self.hand.write_active_joint_angles(reset_hand)
        self.hand_joints = reset_hand

    def reset_zero(self):
        self.return_zero()

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

    def _safe_shutdown(self, timeout: float = 10.0):
        logger.info("Starting safe shutdown procedure...")
        self.disable_motors()
        self.arm.uninit()
        if self.hand is not None:
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
            if self.hand is not None:
                self.hand.disconnect()
        self._is_connected = False
        logger.info(f"{self} safely disconnected.")
