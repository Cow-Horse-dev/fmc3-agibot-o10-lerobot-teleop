import logging
import time
from concurrent.futures import ThreadPoolExecutor
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
    agibot_o10_eef_absolute_pose_to_matrix,
    normalize_agibot_o10_action_control_mode,
    normalize_agibot_o10_hand_action_mode,
)
from lerobot_play.utils.camera_autodetect import resolve_auto_opencv_cameras
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore
from lerobot_play.utils.o10_camera_io import (
    CameraObservationReader,
    camera_feature_shapes,
    depth_observation_name,
)
from lerobot_play.utils.o10_hand_control import (
    default_gripper_gesture,
    gripper_value_to_hand_joints,
    hand_joints_to_gripper_value,
)
from lerobot_play.utils.o10_motion import (
    apply_eef_delta_to_pose,
    homogeneous_matrix_to_pose,
    solve_o10_ik,
)
from lerobot_play.utils.o10_reset import load_o10_reset_targets, normalize_joint_values
from lerobot_play.utils.o10_schema import (
    DUAL_ARM_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_ABSOLUTE_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_ABSOLUTE_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_GRIPPER_STATE_FEATURE_NAMES,
    DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES,
    DUAL_ARM_STATE_FEATURE_NAMES,
    NUM_O10_ARM_JOINTS,
    NUM_O10_HAND_JOINTS,
    SIDE_ACTION_DIM,
    TACTILE_FULL_NAMES,
    dual_arm_tactile_raw_feature_spec,
    dual_arm_tactile_raw_key,
)
from lerobot_play.utils.realsense_controls import apply_realsense_controls
from lerobot_play.utils.runtime_helpers import validate_o10_tactile_mode

from .config_pico_follower_dual_arm_agibot_o10 import (
    PicoFollowerDualArmAgibotO10Config,
)

logger = logging.getLogger(__name__)


_NUM_ARM_JOINTS = NUM_O10_ARM_JOINTS
_NUM_HAND_JOINTS = NUM_O10_HAND_JOINTS
_SIDE_ACTION_DIM = SIDE_ACTION_DIM
_SIDE_EEF_DELTA_ACTION_DIM = len(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES) + _NUM_HAND_JOINTS
_SIDE_GRIPPER_ACTION_DIM = _NUM_ARM_JOINTS + len(AGIBOT_O10_GRIPPER_FEATURE_NAMES)


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
        self.camera_reader = CameraObservationReader(
            config.cameras,
            allow_read_failures=getattr(self.config, "allow_camera_read_failures", False),
            timeout_ms=int(getattr(self.config, "camera_read_timeout_ms", 200)),
        )
        self._camera_read_executor: ThreadPoolExecutor | None = None

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
        if len(self.cameras) > 1:
            self._camera_read_executor = ThreadPoolExecutor(
                max_workers=len(self.cameras),
                thread_name_prefix="o10-dual-camera",
            )

        if self.config.enable_hand:
            tactile_mode = validate_o10_tactile_mode(
                getattr(self.config, "tactile_mode", "none")
            )
            if tactile_mode != "none":
                # 30Hz to match record fps; max ~33ms tactile-vs-joint drift.
                tactile_period_s = 1.0 / 30.0
                try:
                    self.left_hand.start_tactile_reader(period_s=tactile_period_s)
                    self.right_hand.start_tactile_reader(period_s=tactile_period_s)
                except Exception as exc:
                    logger.warning("Failed to start tactile reader threads: %s", exc)

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
        use_cached_hand_pos = (
            self._hand_action_mode() == "gripper_1d"
            and validate_o10_tactile_mode(getattr(self.config, "tactile_mode", "none")) == "none"
        )
        left_hand_pos = (
            self.left_hand.read_active_joint_angles()
            if self.config.enable_hand and not use_cached_hand_pos
            else self.left_hand_joints.copy()
        )
        right_hand_pos = (
            self.right_hand.read_active_joint_angles()
            if self.config.enable_hand and not use_cached_hand_pos
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
            arm_pos = normalize_joint_values(arm_store, arm_pos)
            hand_pos = normalize_joint_values(hand_store, hand_pos)

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

            try:
                arm_loaded, hand_loaded = load_o10_reset_targets(
                    reset_poses_path, side, reset_gesture,
                )
            except Exception as exc:
                logger.warning("Failed to load %s reset poses: %s", side, exc)
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

    def _read_camera_observations(self) -> dict[str, tuple[np.ndarray, np.ndarray | None]]:
        if not hasattr(self, "camera_reader"):
            self.camera_reader = CameraObservationReader(
                self.config.cameras,
                allow_read_failures=getattr(self.config, "allow_camera_read_failures", False),
                timeout_ms=int(getattr(self.config, "camera_read_timeout_ms", 200)),
            )
        return self.camera_reader.read_all(
            self.cameras,
            executor=getattr(self, "_camera_read_executor", None),
            thread_name_prefix="o10-dual-camera",
        )

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return camera_feature_shapes(self.cameras, self.config.cameras)

    @cached_property
    def action_features(self) -> dict[str, type]:
        if self._action_control_mode() == "eef_delta":
            if self._hand_action_mode() == "gripper_1d":
                return {name: float for name in DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES}
            return {name: float for name in DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES}
        if self._action_control_mode() == "eef_absolute":
            if self._hand_action_mode() == "gripper_1d":
                return {name: float for name in DUAL_ARM_EEF_ABSOLUTE_GRIPPER_ACTION_FEATURE_NAMES}
            return {name: float for name in DUAL_ARM_EEF_ABSOLUTE_ACTION_FEATURE_NAMES}
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
            # Dual raw tactile schema lives in o10_schema; source tests still look
            # for DUAL_ARM_TACTILE_FULL_FEATURE_NAMES and the two raw dataset keys:
            # "observation.tactile.left_raw", "observation.tactile.right_raw".
            tactile_ft = {
                dual_arm_tactile_raw_key("left"): dual_arm_tactile_raw_feature_spec("left"),
                dual_arm_tactile_raw_key("right"): dual_arm_tactile_raw_feature_spec("right"),
            }
        return {**state_ft, **tactile_ft, **self._cameras_ft}

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

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
                pose = homogeneous_matrix_to_pose(
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

        for cam_key, (color_frame, depth_frame) in self._read_camera_observations().items():
            obs_dict[cam_key] = color_frame
            if depth_frame is not None:
                obs_dict[depth_observation_name(cam_key)] = np.expand_dims(
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
        return default_gripper_gesture(
            side_config.get("gripper_gesture"),
            side_config.get("trigger_gesture"),
            side_config.get("reset_gesture"),
            getattr(self.config, "trigger_gesture", None),
        )

    def _side_reset_poses_path(self, side: str) -> str | None:
        return self._side_config(side).get("reset_poses_path")

    def _hand_joints_to_gripper_value(self, side: str, hand_joints: list[float]) -> float:
        return hand_joints_to_gripper_value(
            hand_joints,
            self._side_gripper_gesture(side),
            self._side_handedness(side),
            reset_poses_path=self._side_reset_poses_path(side),
        )

    def _gripper_value_to_hand_joints(self, side: str, gripper_value: float) -> list[float]:
        return gripper_value_to_hand_joints(
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

    def _extract_eef_absolute_side_action(
        self,
        action: dict[str, Any],
        side: str,
    ) -> tuple[list[float], list[float]]:
        eef_pose = [
            float(action[f"{side}.{name}"])
            for name in AGIBOT_O10_POSE_FEATURE_NAMES
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
        return eef_pose, hand_joints

    def _solve_eef_delta_side_joints(
        self,
        current_arm_joints: list[float],
        eef_delta: list[float],
    ) -> list[float]:
        current_pose = self.arm_kdl.forward_kinematics(current_arm_joints[:_NUM_ARM_JOINTS])
        target_pose = apply_eef_delta_to_pose(current_pose, eef_delta)
        return solve_o10_ik(self.arm_kdl, target_pose, current_arm_joints[:_NUM_ARM_JOINTS])

    def _solve_eef_absolute_side_joints(
        self,
        current_arm_joints: list[float],
        eef_pose: list[float],
    ) -> list[float]:
        target_pose = agibot_o10_eef_absolute_pose_to_matrix(eef_pose)
        return solve_o10_ik(self.arm_kdl, target_pose, current_arm_joints[:_NUM_ARM_JOINTS])

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

        if self._action_control_mode() == "eef_absolute":
            positions = self.get_joint_pos()
            all_values: list[float] = []

            left_eef_pose, left_hand_joints = self._extract_eef_absolute_side_action(action, "left")
            left_arm_joints = self._solve_eef_absolute_side_joints(positions["left"][0], left_eef_pose)
            self.servo_joint_pos(self.left_arm, left_arm_joints)
            if self.config.enable_hand:
                self.left_hand.write_active_joint_angles(left_hand_joints)
            self.left_hand_joints = left_hand_joints.copy()
            if self._hand_action_mode() == "gripper_1d":
                all_values.extend([
                    *left_eef_pose,
                    self._extract_side_gripper_value(action, "left"),
                ])
            else:
                all_values.extend([*left_eef_pose, *left_hand_joints])

            right_eef_pose, right_hand_joints = self._extract_eef_absolute_side_action(action, "right")
            right_arm_joints = self._solve_eef_absolute_side_joints(positions["right"][0], right_eef_pose)
            self.servo_joint_pos(self.right_arm, right_arm_joints)
            if self.config.enable_hand:
                self.right_hand.write_active_joint_angles(right_hand_joints)
            self.right_hand_joints = right_hand_joints.copy()
            if self._hand_action_mode() == "gripper_1d":
                all_values.extend([
                    *right_eef_pose,
                    self._extract_side_gripper_value(action, "right"),
                ])
            else:
                all_values.extend([*right_eef_pose, *right_hand_joints])

            action_feature_names = (
                DUAL_ARM_EEF_ABSOLUTE_GRIPPER_ACTION_FEATURE_NAMES
                if self._hand_action_mode() == "gripper_1d"
                else DUAL_ARM_EEF_ABSOLUTE_ACTION_FEATURE_NAMES
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

        reset_timeout_s = float(getattr(self.config, "reset_timeout_s", 8.0))
        reset_started_s = time.perf_counter()

        while True:
            left_state = list(self.left_arm.state().pos)
            right_state = list(self.right_arm.state().pos)
            left_arrived = self.is_arm_arrive(left_joints, left_state)
            right_arrived = self.is_arm_arrive(right_joints, right_state)
            if left_arrived and right_arrived:
                break
            if time.perf_counter() - reset_started_s >= reset_timeout_s:
                logger.warning(
                    "Timed out resetting dual-arm O10 after %.2fs "
                    "(left_arrived=%s, right_arrived=%s). Continuing to avoid blocking control.",
                    reset_timeout_s,
                    left_arrived,
                    right_arrived,
                )
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
        camera_read_executor = getattr(self, "_camera_read_executor", None)
        if camera_read_executor is not None:
            camera_read_executor.shutdown(wait=False, cancel_futures=True)
            self._camera_read_executor = None
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
