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
    AGIBOT_O10_EEF_DELTA_FEATURE_NAMES,
    AGIBOT_O10_GRIPPER_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AGIBOT_O10_POSE_FEATURE_NAMES,
    AgibotO10Hand,
    agibot_o10_gripper_value_from_hand_joints,
    agibot_o10_hand_joints_from_gripper_value,
    normalize_agibot_o10_action_control_mode,
    normalize_agibot_o10_hand_action_mode,
)
from lerobot_play.utils.camera_autodetect import resolve_auto_opencv_cameras
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore, load_reset_poses
from lerobot_play.utils.realsense_controls import apply_realsense_controls
from lerobot_play.utils.runtime_helpers import validate_o10_tactile_mode

from .config_pico_follower_dual_arm_agibot_o10 import (
    PicoFollowerDualArmAgibotO10Config,
)

logger = logging.getLogger(__name__)


def _rotation_matrix_from_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=float,
    )


def _apply_eef_delta_to_pose(current_pose: np.ndarray, eef_delta: list[float]) -> np.ndarray:
    target_pose = np.array(current_pose, dtype=float, copy=True)
    target_pose[:3, 3] += np.array(eef_delta[:3], dtype=float)
    target_pose[:3, :3] = target_pose[:3, :3] @ _rotation_matrix_from_rpy(*eef_delta[3:6])
    return target_pose


_NUM_ARM_JOINTS = len(AGIBOT_O10_ARM_FEATURE_NAMES)
_NUM_HAND_JOINTS = len(AGIBOT_O10_HAND_FEATURE_NAMES)
_SIDE_ACTION_DIM = _NUM_ARM_JOINTS + _NUM_HAND_JOINTS  # 16
_SIDE_EEF_DELTA_ACTION_DIM = len(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES) + _NUM_HAND_JOINTS
_SIDE_GRIPPER_ACTION_DIM = _NUM_ARM_JOINTS + len(AGIBOT_O10_GRIPPER_FEATURE_NAMES)


def _solve_ik(arm_kdl, target_pose: np.ndarray, seed_joints: list[float]) -> list[float]:
    try:
        result = arm_kdl.inverse_kinematics(target_pose, seed_joints, force_calculate=True)
    except TypeError:
        result = arm_kdl.inverse_kinematics(target_pose, seed_joints)
    if len(result) == 0:
        raise RuntimeError("Agibot O10 eef_delta IK failed; refusing to send an arm target.")
    return [float(value) for value in result[0][:_NUM_ARM_JOINTS]]

# 32D action: left arm[6] + left hand[10] + right arm[6] + right hand[10]
DUAL_ARM_ACTION_FEATURE_NAMES = tuple(
    f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
)

DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES = tuple(
    f"left.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES
) + tuple(
    f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
)

DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES = tuple(
    f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"left.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES
)

DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES = tuple(
    f"left.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES
) + tuple(
    f"left.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES
)

DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES = tuple(
    f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
)

DUAL_ARM_GRIPPER_STATE_FEATURE_NAMES = DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES

# 46D state: left arm[6] + left hand[10] + left pose[7]
#          + right arm[6] + right hand[10] + right pose[7]
DUAL_ARM_STATE_FEATURE_NAMES = (
    DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES[:_SIDE_ACTION_DIM]
    + tuple(
        f"left.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES
    )
    + DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES[_SIDE_ACTION_DIM:]
    + tuple(
        f"right.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES
    )
)

# 130D 全手触觉 feature names：5 指 × 16 + 手掌 25 + 手背 25。
TACTILE_FINGERTIP_NAMES = tuple(
    f"tactile.{finger}_{i}"
    for finger in ("thumb", "index", "middle", "ring", "little")
    for i in range(16)
)

TACTILE_FULL_NAMES = TACTILE_FINGERTIP_NAMES + tuple(
    f"tactile.palm_{i}" for i in range(25)
) + tuple(
    f"tactile.dorsum_{i}" for i in range(25)
)

# 双臂 raw 130D 触觉 feature names（带 left./right. 前缀）
DUAL_ARM_TACTILE_FULL_FEATURE_NAMES = tuple(
    f"{side}.{name}"
    for side in ("left", "right")
    for name in TACTILE_FULL_NAMES
)  # 260D

LEFT_TACTILE_RAW_KEY = "observation.tactile.left_raw"
RIGHT_TACTILE_RAW_KEY = "observation.tactile.right_raw"


def _tactile_raw_key(side: str) -> str:
    return LEFT_TACTILE_RAW_KEY if side == "left" else RIGHT_TACTILE_RAW_KEY


def _tactile_raw_feature_spec(side: str) -> dict[str, object]:
    return {
        "dtype": "float32",
        "shape": (len(TACTILE_FULL_NAMES),),
        "names": [f"{side}.{name}" for name in TACTILE_FULL_NAMES],
    }


def _make_arm() -> ah.Play:
    return ah.Play.create(
        ah.MotorType.OD,
        ah.MotorType.OD,
        ah.MotorType.OD,
        ah.MotorType.DM,
        ah.MotorType.DM,
        ah.MotorType.DM,
        ah.EEFType.NA,
        ah.MotorType.NA,
    )


class PicoFollowerDualArmAgibotO10(Robot):
    config_class = PicoFollowerDualArmAgibotO10Config
    name = "pico_follower_dual_arm_agibot_o10"

    def __init__(self, config: PicoFollowerDualArmAgibotO10Config):
        super().__init__(config)
        self.config = config
        self.arm_kdl = ArmKdlNumerical(eef_type="none")

        # --- left side ---
        left_cfg = config.left
        self.left_port = left_cfg.get("port", "can1")
        self.left_executor = ah.create_asio_executor(8)
        self.left_io_context = self.left_executor.get_io_context()
        self.left_arm = _make_arm()
        self.left_hand = AgibotO10Hand(
            handedness=left_cfg.get("handedness", "left"),
            channel_mode=left_cfg.get("channel_mode", "multiChannel"),
            device_id=left_cfg.get("device_id", 1),
            canfd_id=left_cfg.get("canfd_id", 0),
            channel_id=left_cfg.get("channel_id"),
        )
        self.left_hand_joints = [0.0] * _NUM_HAND_JOINTS
        self.left_arm_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_ARM_FEATURE_NAMES,
            path=None,
            label="left arm reset joint target",
            group_key="arm",
        )
        self.left_hand_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
            path=None,
            label="left hand reset joint target",
            group_key="hand",
        )
        self.left_reset_arm_joint_pos = [0.0] * _NUM_ARM_JOINTS
        self.left_reset_hand_joint_pos = [0.0] * _NUM_HAND_JOINTS

        # --- right side ---
        right_cfg = config.right
        self.right_port = right_cfg.get("port", "can0")
        self.right_executor = ah.create_asio_executor(8)
        self.right_io_context = self.right_executor.get_io_context()
        self.right_arm = _make_arm()
        self.right_hand = AgibotO10Hand(
            handedness=right_cfg.get("handedness", "right"),
            channel_mode=right_cfg.get("channel_mode", "multiChannel"),
            device_id=right_cfg.get("device_id", 1),
            canfd_id=right_cfg.get("canfd_id", 0),
            channel_id=right_cfg.get("channel_id"),
        )
        self.right_hand_joints = [0.0] * _NUM_HAND_JOINTS
        self.right_arm_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_ARM_FEATURE_NAMES,
            path=None,
            label="right arm reset joint target",
            group_key="arm",
        )
        self.right_hand_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
            path=None,
            label="right hand reset joint target",
            group_key="hand",
        )
        self.right_reset_arm_joint_pos = [0.0] * _NUM_ARM_JOINTS
        self.right_reset_hand_joint_pos = [0.0] * _NUM_HAND_JOINTS

        # --- cameras ---
        resolve_auto_opencv_cameras(config.cameras)
        self.cameras = make_cameras_from_configs(config.cameras)
        self._camera_observation_cache: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}
        self._camera_fallback_active: dict[str, bool] = {}

        self._is_connected = False

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self) -> None:
        if self.is_connected:
            raise RuntimeError(f"{self} already connected")

        # Left arm
        if not self.left_arm.init(self.left_io_context, self.left_port, 250):
            raise RuntimeError("Failed to initialize left arm")
        if self.config.enable_hand:
            try:
                self.left_hand.connect()
            except Exception:
                self.left_arm.uninit()
                raise

        # Right arm (if it fails, also tear down left so caller doesn't inherit a live arm)
        if not self.right_arm.init(self.right_io_context, self.right_port, 250):
            logger.error("Failed to initialize right arm; tearing down left arm")
            self.left_arm.uninit()
            if self.config.enable_hand:
                try:
                    self.left_hand.disconnect()
                except Exception:
                    pass
            raise RuntimeError("Failed to initialize right arm")
        if self.config.enable_hand:
            try:
                self.right_hand.connect()
            except Exception:
                self.right_arm.uninit()
                self.left_arm.uninit()
                try:
                    self.left_hand.disconnect()
                except Exception:
                    pass
                raise

        connected_cameras = {}
        try:
            for camera_name, cam in self.cameras.items():
                try:
                    cam.connect()
                except Exception as exc:
                    if not getattr(self.config, "allow_camera_read_failures", False):
                        raise
                    logger.warning("Skipping unavailable camera %s: %s", camera_name, exc)
                    continue
                apply_realsense_controls(
                    camera_name,
                    cam,
                    getattr(self.config, "camera_controls", None),
                )
                connected_cameras[camera_name] = cam
        except Exception:
            for cam in connected_cameras.values():
                try:
                    cam.disconnect()
                except Exception:
                    pass
            if self.config.enable_hand:
                try:
                    self.left_hand.disconnect()
                except Exception:
                    pass
                try:
                    self.right_hand.disconnect()
                except Exception:
                    pass
            self.left_arm.uninit()
            self.right_arm.uninit()
            raise
        self.cameras = connected_cameras

        self.enable_motors()
        self.configure()
        self._load_reset_target_from_file()
        self._is_connected = True

    def enable_motors(self) -> None:
        self.left_arm.enable()
        self.right_arm.enable()

    def disable_motors(self) -> None:
        self.left_arm.disable()
        self.right_arm.disable()

    def configure(self) -> None:
        self.left_arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)
        self.right_arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)

    # ------------------------------------------------------------------
    # Joint helpers
    # ------------------------------------------------------------------

    def get_joint_pos(self) -> dict[str, list[list[float]]]:
        """Return joint positions for both sides.

        Returns dict with 'left' and 'right', each a pair
        ``[arm_pos, hand_pos]``.
        """
        left_hand_pos = (
            self.left_hand.read_active_joint_angles()
            if self.config.enable_hand
            else self.left_hand_joints.copy()
        )
        right_hand_pos = (
            self.right_hand.read_active_joint_angles()
            if self.config.enable_hand
            else self.right_hand_joints.copy()
        )
        return {
            "left": [
                list(self.left_arm.state().pos),
                left_hand_pos,
            ],
            "right": [
                list(self.right_arm.state().pos),
                right_hand_pos,
            ],
        }

    @staticmethod
    def _log_joint_pos(title: str, feature_names: tuple[str, ...], joint_pos: list[float]) -> None:
        logger.info(title)
        for feature_name, joint_value in zip(feature_names, joint_pos, strict=True):
            logger.info("  %s: %.4f", feature_name, joint_value)

    # ------------------------------------------------------------------
    # Reset target persistence
    # ------------------------------------------------------------------

    def capture_current_joint_pos_as_reset_target(
        self, persist: bool = True
    ) -> dict[str, tuple[list[float], list[float]]]:
        positions = self.get_joint_pos()
        result: dict[str, tuple[list[float], list[float]]] = {}

        for side in ("left", "right"):
            arm_pos, hand_pos = positions[side]
            arm_pos = arm_pos[:_NUM_ARM_JOINTS]
            arm_store = getattr(self, f"{side}_arm_reset_store")
            hand_store = getattr(self, f"{side}_hand_reset_store")

            if persist:
                logger.info(
                    "Persist requested for %s reset target capture, "
                    "but centralized reset_poses JSON is not modified at runtime.",
                    side,
                )
            arm_pos = arm_store.normalize(arm_pos)
            hand_pos = hand_store.normalize(hand_pos)

            setattr(self, f"{side}_reset_arm_joint_pos", arm_pos.copy())
            setattr(self, f"{side}_reset_hand_joint_pos", hand_pos.copy())
            setattr(self, f"{side}_hand_joints", hand_pos.copy())

            self._log_joint_pos(
                f"Captured Agibot O10 {side} arm reset target:",
                AGIBOT_O10_ARM_FEATURE_NAMES,
                arm_pos,
            )
            self._log_joint_pos(
                f"Captured Agibot O10 {side} hand reset target:",
                AGIBOT_O10_HAND_FEATURE_NAMES,
                hand_pos,
            )
            result[side] = (arm_pos, hand_pos)

        return result

    def _load_reset_target_from_file(self) -> None:
        for side in ("left", "right"):
            side_cfg = getattr(self.config, side)
            reset_poses_path = side_cfg.get("reset_poses_path")
            reset_gesture = side_cfg.get("reset_gesture")

            if reset_poses_path and reset_gesture:
                try:
                    arm_loaded, hand_loaded = load_reset_poses(
                        reset_poses_path, side, reset_gesture,
                    )
                except Exception as exc:
                    logger.warning("Failed to load %s reset poses: %s", side, exc)
                    arm_loaded, hand_loaded = None, None
            else:
                arm_loaded, hand_loaded = None, None

            if arm_loaded is not None:
                setattr(self, f"{side}_reset_arm_joint_pos", arm_loaded)
            if hand_loaded is not None:
                setattr(self, f"{side}_reset_hand_joint_pos", hand_loaded)
                setattr(self, f"{side}_hand_joints", hand_loaded.copy())

            self._log_joint_pos(
                f"Reset {side} arm target",
                AGIBOT_O10_ARM_FEATURE_NAMES,
                getattr(self, f"{side}_reset_arm_joint_pos"),
            )
            self._log_joint_pos(
                f"Reset {side} hand target",
                AGIBOT_O10_HAND_FEATURE_NAMES,
                getattr(self, f"{side}_reset_hand_joint_pos"),
            )

    # ------------------------------------------------------------------
    # Feature descriptors
    # ------------------------------------------------------------------

    @staticmethod
    def _camera_uses_depth(camera_config: Any) -> bool:
        return bool(getattr(camera_config, "use_depth", False))

    @staticmethod
    def _depth_observation_name(camera_name: str) -> str:
        return f"{camera_name}_depth"

    def _get_camera_observation_cache(self) -> dict[str, tuple[np.ndarray, np.ndarray | None]]:
        cache = getattr(self, "_camera_observation_cache", None)
        if cache is None:
            cache = {}
            self._camera_observation_cache = cache
        return cache

    def _get_camera_fallback_active(self) -> dict[str, bool]:
        fallback_active = getattr(self, "_camera_fallback_active", None)
        if fallback_active is None:
            fallback_active = {}
            self._camera_fallback_active = fallback_active
        return fallback_active

    def _mark_camera_read_success(self, camera_name: str) -> None:
        if self._get_camera_fallback_active().pop(camera_name, False):
            logger.info("Camera %s recovered.", camera_name)

    def _mark_camera_read_failure(
        self, camera_name: str, exc: Exception, *, using_cached_frame: bool
    ) -> None:
        fallback_active = self._get_camera_fallback_active()
        if fallback_active.get(camera_name):
            return
        fallback_active[camera_name] = True
        fallback_mode = "reusing last frame" if using_cached_frame else "using zero frame"
        logger.warning("Camera read failed for %s, %s: %s", camera_name, fallback_mode, exc)

    def _zero_camera_color_frame(self, camera_name: str) -> np.ndarray:
        camera_config = self.config.cameras[camera_name]
        return np.zeros((camera_config.height, camera_config.width, 3), dtype=np.uint8)

    def _zero_camera_depth_frame(self, camera_name: str) -> np.ndarray:
        camera_config = self.config.cameras[camera_name]
        return np.zeros((camera_config.height, camera_config.width), dtype=np.uint16)

    def _read_camera_observation(self, camera_name: str, camera: Any) -> tuple[np.ndarray, np.ndarray | None]:
        uses_depth = self._camera_uses_depth(self.config.cameras[camera_name])
        cache = self._get_camera_observation_cache()
        try:
            if uses_depth:
                color_frame, depth_frame = camera.async_read_color_and_depth()
                cache[camera_name] = (color_frame, depth_frame)
                self._mark_camera_read_success(camera_name)
                return color_frame, depth_frame

            color_frame = camera.async_read()
            cache[camera_name] = (color_frame, None)
            self._mark_camera_read_success(camera_name)
            return color_frame, None
        except Exception as exc:
            if not getattr(self.config, "allow_camera_read_failures", False):
                raise

            cached_frames = cache.get(camera_name)
            if cached_frames is not None:
                self._mark_camera_read_failure(camera_name, exc, using_cached_frame=True)
                return cached_frames

            zero_color_frame = self._zero_camera_color_frame(camera_name)
            zero_depth_frame = self._zero_camera_depth_frame(camera_name) if uses_depth else None
            cache[camera_name] = (zero_color_frame, zero_depth_frame)
            self._mark_camera_read_failure(camera_name, exc, using_cached_frame=False)
            return zero_color_frame, zero_depth_frame

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
    def action_features(self) -> dict[str, type]:
        if self._action_control_mode() == "eef_delta":
            if self._hand_action_mode() == "gripper_1d":
                return {name: float for name in DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES}
            return {name: float for name in DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES}
        if self._hand_action_mode() == "gripper_1d":
            return {name: float for name in DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES}
        return {name: float for name in DUAL_ARM_ACTION_FEATURE_NAMES}

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        if self._hand_action_mode() == "gripper_1d":
            state_feature_names = DUAL_ARM_GRIPPER_STATE_FEATURE_NAMES
        else:
            state_feature_names = (
                DUAL_ARM_STATE_FEATURE_NAMES
                if self.config.include_eef_pose
                else DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES
            )
        state_ft = {name: float for name in state_feature_names}
        tactile_mode = validate_o10_tactile_mode(getattr(self.config, "tactile_mode", "none"))
        tactile_ft: dict[str, type | dict[str, object]] = {}
        if tactile_mode == "130d":
            tactile_ft = {
                _tactile_raw_key("left"): _tactile_raw_feature_spec("left"),
                _tactile_raw_key("right"): _tactile_raw_feature_spec("right"),
            }
        return {**state_ft, **tactile_ft, **self._cameras_ft}

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    # ------------------------------------------------------------------
    # Kinematics
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Servo helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_arm_arrive(arm_target, arm_pose, tolerance=0.02):
        return all(
            abs(target - pose) <= tolerance
            for target, pose in zip(arm_target, arm_pose)
        )

    def servo_joint_pos(self, arm, joints: list[float], vel: float = 3.0, eff: float = 8.0):
        velocities = [vel] * (self.config.arm_joints_num - 1)
        effort = [eff] * (self.config.arm_joints_num - 1)
        return arm.pvt(joints, velocities, effort)

    # ------------------------------------------------------------------
    # Observation / Action
    # ------------------------------------------------------------------

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        positions = self.get_joint_pos()
        obs_dict: dict[str, Any] = {}

        for side in ("left", "right"):
            arm_pos, hand_pos = positions[side]
            for idx, feat in enumerate(AGIBOT_O10_ARM_FEATURE_NAMES):
                obs_dict[f"{side}.{feat}"] = arm_pos[idx]
            if self._hand_action_mode() == "gripper_1d":
                gripper_feature = AGIBOT_O10_GRIPPER_FEATURE_NAMES[0]
                obs_dict[f"{side}.{gripper_feature}"] = self._hand_joints_to_gripper_value(
                    side,
                    hand_pos,
                )
            else:
                for idx, feat in enumerate(AGIBOT_O10_HAND_FEATURE_NAMES):
                    obs_dict[f"{side}.{feat}"] = hand_pos[idx]
            if self._hand_action_mode() != "gripper_1d" and self.config.include_eef_pose:
                pose = self.homogeneous_matrix_to_pose(
                    self.arm_kdl.forward_kinematics(arm_pos[:_NUM_ARM_JOINTS])
                )
                for idx, feat in enumerate(AGIBOT_O10_POSE_FEATURE_NAMES):
                    obs_dict[f"{side}.{feat}"] = pose[idx]

        # 触觉数据（raw 130D）
        tactile_mode = validate_o10_tactile_mode(getattr(self.config, "tactile_mode", "none"))
        if self.config.enable_hand and tactile_mode != "none":
            for side, hand_obj in (("left", self.left_hand), ("right", self.right_hand)):
                if tactile_mode == "130d":
                    tactile_full = hand_obj.read_tactile_full_cached()
                    for idx, name in enumerate(TACTILE_FULL_NAMES):
                        obs_dict[f"{side}.{name}"] = tactile_full[idx]

        for cam_key, cam in self.cameras.items():
            color_frame, depth_frame = self._read_camera_observation(cam_key, cam)
            obs_dict[cam_key] = color_frame
            if depth_frame is not None:
                obs_dict[self._depth_observation_name(cam_key)] = np.expand_dims(
                    depth_frame, axis=-1
                )

        return obs_dict

    def _action_control_mode(self) -> str:
        return normalize_agibot_o10_action_control_mode(
            getattr(self.config, "action_control_mode", "joint")
        )

    def _hand_action_mode(self) -> str:
        return normalize_agibot_o10_hand_action_mode(
            getattr(self.config, "hand_action_mode", "dexterous_10d")
        )

    def _side_config(self, side: str) -> dict[str, Any]:
        return getattr(self.config, side, {}) or {}

    def _side_handedness(self, side: str) -> str:
        return self._side_config(side).get("handedness", side)

    def _side_gripper_gesture(self, side: str) -> str:
        side_config = self._side_config(side)
        return (
            side_config.get("gripper_gesture")
            or side_config.get("trigger_gesture")
            or side_config.get("reset_gesture")
            or "pinch"
        )

    def _side_reset_poses_path(self, side: str) -> str | None:
        return self._side_config(side).get("reset_poses_path")

    def _hand_joints_to_gripper_value(self, side: str, hand_joints: list[float]) -> float:
        return agibot_o10_gripper_value_from_hand_joints(
            hand_joints,
            self._side_gripper_gesture(side),
            self._side_handedness(side),
            reset_poses_path=self._side_reset_poses_path(side),
        )

    def _gripper_value_to_hand_joints(self, side: str, gripper_value: float) -> list[float]:
        return agibot_o10_hand_joints_from_gripper_value(
            gripper_value,
            self._side_gripper_gesture(side),
            self._side_handedness(side),
            reset_poses_path=self._side_reset_poses_path(side),
        )

    def _extract_side_gripper_value(self, action: dict[str, Any], side: str) -> float:
        return float(action[f"{side}.{AGIBOT_O10_GRIPPER_FEATURE_NAMES[0]}"])

    def _extract_eef_delta_side_action(
        self,
        action: dict[str, Any],
        side: str,
    ) -> tuple[list[float], list[float]]:
        eef_delta = [
            float(action[f"{side}.{name}"])
            for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES
        ]
        if self._hand_action_mode() == "gripper_1d":
            hand_joints = self._gripper_value_to_hand_joints(
                side,
                self._extract_side_gripper_value(action, side),
            )
        else:
            hand_joints = [
                float(action[f"{side}.{name}"])
                for name in AGIBOT_O10_HAND_FEATURE_NAMES
            ]
        return eef_delta, hand_joints

    def _solve_eef_delta_side_joints(
        self,
        current_arm_joints: list[float],
        eef_delta: list[float],
    ) -> list[float]:
        current_pose = self.arm_kdl.forward_kinematics(current_arm_joints[:_NUM_ARM_JOINTS])
        target_pose = _apply_eef_delta_to_pose(current_pose, eef_delta)
        return _solve_ik(self.arm_kdl, target_pose, current_arm_joints[:_NUM_ARM_JOINTS])

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        if self._action_control_mode() == "eef_delta":
            positions = self.get_joint_pos()
            all_values: list[float] = []

            left_eef_delta, left_hand_joints = self._extract_eef_delta_side_action(action, "left")
            left_arm_joints = self._solve_eef_delta_side_joints(positions["left"][0], left_eef_delta)
            self.servo_joint_pos(self.left_arm, left_arm_joints)
            if self.config.enable_hand:
                self.left_hand.write_active_joint_angles(left_hand_joints)
            self.left_hand_joints = left_hand_joints.copy()
            if self._hand_action_mode() == "gripper_1d":
                all_values.extend([
                    *left_eef_delta,
                    self._extract_side_gripper_value(action, "left"),
                ])
            else:
                all_values.extend([*left_eef_delta, *left_hand_joints])

            right_eef_delta, right_hand_joints = self._extract_eef_delta_side_action(action, "right")
            right_arm_joints = self._solve_eef_delta_side_joints(positions["right"][0], right_eef_delta)
            self.servo_joint_pos(self.right_arm, right_arm_joints)
            if self.config.enable_hand:
                self.right_hand.write_active_joint_angles(right_hand_joints)
            self.right_hand_joints = right_hand_joints.copy()
            if self._hand_action_mode() == "gripper_1d":
                all_values.extend([
                    *right_eef_delta,
                    self._extract_side_gripper_value(action, "right"),
                ])
            else:
                all_values.extend([*right_eef_delta, *right_hand_joints])

            action_feature_names = (
                DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES
                if self._hand_action_mode() == "gripper_1d"
                else DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES
            )
            return {
                name: all_values[idx]
                for idx, name in enumerate(action_feature_names)
            }

        # Extract left arm + hand joints
        left_arm_joints = [float(action[f"left.{n}"]) for n in AGIBOT_O10_ARM_FEATURE_NAMES]
        if self._hand_action_mode() == "gripper_1d":
            left_gripper = self._extract_side_gripper_value(action, "left")
            left_hand_joints = self._gripper_value_to_hand_joints("left", left_gripper)
        else:
            left_gripper = None
            left_hand_joints = [float(action[f"left.{n}"]) for n in AGIBOT_O10_HAND_FEATURE_NAMES]

        # Extract right arm + hand joints
        right_arm_joints = [float(action[f"right.{n}"]) for n in AGIBOT_O10_ARM_FEATURE_NAMES]
        if self._hand_action_mode() == "gripper_1d":
            right_gripper = self._extract_side_gripper_value(action, "right")
            right_hand_joints = self._gripper_value_to_hand_joints("right", right_gripper)
        else:
            right_gripper = None
            right_hand_joints = [float(action[f"right.{n}"]) for n in AGIBOT_O10_HAND_FEATURE_NAMES]

        # Send to hardware
        self.servo_joint_pos(self.left_arm, left_arm_joints)
        if self.config.enable_hand:
            self.left_hand.write_active_joint_angles(left_hand_joints)
        self.left_hand_joints = left_hand_joints.copy()

        self.servo_joint_pos(self.right_arm, right_arm_joints)
        if self.config.enable_hand:
            self.right_hand.write_active_joint_angles(right_hand_joints)
        self.right_hand_joints = right_hand_joints.copy()

        # Build action feedback dict
        if self._hand_action_mode() == "gripper_1d":
            all_values = left_arm_joints + [left_gripper] + right_arm_joints + [right_gripper]
            action_feature_names = DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES
        else:
            all_values = left_arm_joints + left_hand_joints + right_arm_joints + right_hand_joints
            action_feature_names = DUAL_ARM_ACTION_FEATURE_NAMES
        return {
            name: all_values[idx]
            for idx, name in enumerate(action_feature_names)
        }

    # ------------------------------------------------------------------
    # Reset / zero
    # ------------------------------------------------------------------

    def return_zero(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        left_joints = self.left_reset_arm_joint_pos.copy()
        right_joints = self.right_reset_arm_joint_pos.copy()
        left_hand_reset = self.left_reset_hand_joint_pos.copy()
        right_hand_reset = self.right_reset_hand_joint_pos.copy()
        velocities = [0.8] * (self.config.arm_joints_num - 1)
        effort = [10.0] * (self.config.arm_joints_num - 1)

        while True:
            left_state = list(self.left_arm.state().pos)
            right_state = list(self.right_arm.state().pos)
            left_arrived = self.is_arm_arrive(left_joints, left_state)
            right_arrived = self.is_arm_arrive(right_joints, right_state)
            if left_arrived and right_arrived:
                break
            if not left_arrived:
                self.left_arm.pvt(left_joints, velocities, effort)
            if not right_arrived:
                self.right_arm.pvt(right_joints, velocities, effort)
            if self.config.enable_hand:
                self.left_hand.write_active_joint_angles(left_hand_reset)
                self.right_hand.write_active_joint_angles(right_hand_reset)
            time.sleep(0.004)

        if self.config.enable_hand:
            self.left_hand.write_active_joint_angles(left_hand_reset)
            self.right_hand.write_active_joint_angles(right_hand_reset)
        self.left_hand_joints = left_hand_reset
        self.right_hand_joints = right_hand_reset

    def reset_zero(self):
        self.return_zero()

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _safe_shutdown(self, timeout: float = 10.0):
        logger.info("Starting safe shutdown procedure...")
        self.disable_motors()
        self.left_arm.uninit()
        self.right_arm.uninit()
        if self.config.enable_hand:
            self.left_hand.disconnect()
            self.right_hand.disconnect()
        for cam in getattr(self, "cameras", {}).values():
            try:
                cam.disconnect()
            except Exception as cam_exc:
                logger.error(f"Camera disconnect failed: {cam_exc}")
        logger.info("Motors disabled and devices disconnected")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            for step in (
                lambda: self.disable_motors(),
                lambda: self.left_arm.uninit(),
                lambda: self.right_arm.uninit(),
            ):
                try:
                    step()
                except Exception as step_exc:
                    logger.error(f"Teardown step failed: {step_exc}")
            if self.config.enable_hand:
                for hand_disconnect in (
                    lambda: self.left_hand.disconnect(),
                    lambda: self.right_hand.disconnect(),
                ):
                    try:
                        hand_disconnect()
                    except Exception as hand_exc:
                        logger.error(f"Hand disconnect failed: {hand_exc}")
            for cam in getattr(self, "cameras", {}).values():
                try:
                    cam.disconnect()
                except Exception as cam_exc:
                    logger.error(f"Camera disconnect failed: {cam_exc}")
        self._is_connected = False
        logger.info(f"{self} safely disconnected.")
