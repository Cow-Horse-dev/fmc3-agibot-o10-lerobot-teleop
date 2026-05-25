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
    agibot_o10_action_feature_types,
    agibot_o10_eef_absolute_action_feature_types,
    agibot_o10_eef_absolute_gripper_action_feature_types,
    agibot_o10_eef_absolute_pose_to_matrix,
    agibot_o10_eef_delta_action_feature_types,
    agibot_o10_eef_delta_gripper_action_feature_types,
    agibot_o10_gripper_action_feature_types,
    agibot_o10_gripper_state_feature_types,
    agibot_o10_joint_action_feature_types,
    build_agibot_o10_eef_absolute_action_dict,
    build_agibot_o10_eef_absolute_gripper_action_dict,
    build_agibot_o10_eef_delta_action_dict,
    build_agibot_o10_eef_delta_gripper_action_dict,
    build_agibot_o10_gripper_action_dict,
    build_agibot_o10_joint_action_dict,
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
from lerobot_play.utils.o10_schema import TACTILE_FULL_NAMES, tactile_raw_feature_spec, tactile_raw_key
from lerobot_play.utils.realsense_controls import apply_realsense_controls
from lerobot_play.utils.runtime_helpers import validate_o10_tactile_mode

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
        self.camera_reader = CameraObservationReader(
            config.cameras,
            allow_read_failures=getattr(self.config, "allow_camera_read_failures", False),
            timeout_ms=int(getattr(self.config, "camera_read_timeout_ms", 200)),
        )
        self._camera_read_executor: ThreadPoolExecutor | None = None
        connected_cameras = {}
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
        self.cameras = connected_cameras
        if len(self.cameras) > 1:
            self._camera_read_executor = ThreadPoolExecutor(
                max_workers=len(self.cameras),
                thread_name_prefix="o10-single-camera",
            )

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
        use_cached_hand_pos = (
            self._hand_action_mode() == "gripper_1d"
            and validate_o10_tactile_mode(getattr(self.config, "tactile_mode", "none")) == "none"
        )
        hand_joint_pos = (
            self.hand.read_active_joint_angles()
            if self.hand is not None and not use_cached_hand_pos
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
        arm_joint_pos = normalize_joint_values(self.arm_reset_store, arm_joint_pos)
        hand_joint_pos = normalize_joint_values(self.hand_reset_store, hand_joint_pos)

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
        try:
            arm_loaded, hand_loaded = load_o10_reset_targets(
                reset_poses_path,
                self.config.handedness,
                reset_gesture,
            )
        except Exception as exc:
            logger.warning("Failed to load reset poses: %s", exc)
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
        if self._hand_action_mode() == "gripper_1d":
            return agibot_o10_gripper_state_feature_types()
        if self.config.include_eef_pose:
            return agibot_o10_action_feature_types()
        return agibot_o10_joint_action_feature_types()

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
            thread_name_prefix="o10-single-camera",
        )

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return camera_feature_shapes(self.cameras, self.config.cameras)

    @cached_property
    def action_features(self):
        if self._action_control_mode() == "eef_delta":
            if self._hand_action_mode() == "gripper_1d":
                return agibot_o10_eef_delta_gripper_action_feature_types()
            return agibot_o10_eef_delta_action_feature_types()
        if self._action_control_mode() == "eef_absolute":
            if self._hand_action_mode() == "gripper_1d":
                return agibot_o10_eef_absolute_gripper_action_feature_types()
            return agibot_o10_eef_absolute_action_feature_types()
        if self._hand_action_mode() == "gripper_1d":
            return agibot_o10_gripper_action_feature_types()
        return agibot_o10_joint_action_feature_types()

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        tactile_mode = validate_o10_tactile_mode(getattr(self.config, "tactile_mode", "none"))
        tactile_ft: dict[str, type] = {}
        if tactile_mode == "130d":
            tactile_ft = {
                tactile_raw_key(self.config.handedness): tactile_raw_feature_spec(
                    TACTILE_FULL_NAMES
                )
            }
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

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        arm_pos, hand_pos = self.get_joint_pos()

        obs_dict = {
            **{
                feature_name: arm_pos[index]
                for index, feature_name in enumerate(AGIBOT_O10_ARM_FEATURE_NAMES)
            },
        }

        if self._hand_action_mode() == "gripper_1d":
            obs_dict[AGIBOT_O10_GRIPPER_FEATURE_NAMES[0]] = hand_joints_to_gripper_value(
                hand_pos,
                default_gripper_gesture(
                    getattr(self.config, "gripper_gesture", None),
                    getattr(self.config, "trigger_gesture", None),
                    getattr(self.config, "reset_gesture", None),
                ),
                getattr(self.config, "handedness", "right"),
                reset_poses_path=self._reset_poses_path(),
            )
        else:
            obs_dict.update(
                {
                    feature_name: hand_pos[index]
                    for index, feature_name in enumerate(AGIBOT_O10_HAND_FEATURE_NAMES)
                }
            )

        if self._hand_action_mode() != "gripper_1d" and self.config.include_eef_pose:
            pose = homogeneous_matrix_to_pose(self.arm_kdl.forward_kinematics(arm_pos[:6]))
            for index, feature_name in enumerate(AGIBOT_O10_POSE_FEATURE_NAMES):
                obs_dict[feature_name] = pose[index]

        tactile_mode = validate_o10_tactile_mode(getattr(self.config, "tactile_mode", "none"))
        if self.hand is not None and tactile_mode != "none":
            if tactile_mode == "130d":
                tactile_full = self.hand.read_tactile_full()
                for index, feature_name in enumerate(TACTILE_FULL_NAMES):
                    obs_dict[feature_name] = tactile_full[index]

        for cam_key, (color_frame, depth_frame) in self._read_camera_observations().items():
            obs_dict[cam_key] = color_frame
            if depth_frame is not None:
                obs_dict[depth_observation_name(cam_key)] = np.expand_dims(
                    depth_frame, axis=-1
                )

        return obs_dict

    def convert_action_format(self, action: dict[str, Any]) -> dict[str, list[float]]:
        if "joints" in action and "hand_joints" in action:
            joints = [float(value) for value in action["joints"]]
            hand_joints = [float(value) for value in action["hand_joints"]]
        else:
            joints = [float(action[name]) for name in AGIBOT_O10_ARM_FEATURE_NAMES]
            if self._hand_action_mode() == "gripper_1d":
                hand_joints = gripper_value_to_hand_joints(
                    float(action[AGIBOT_O10_GRIPPER_FEATURE_NAMES[0]]),
                    default_gripper_gesture(
                        getattr(self.config, "gripper_gesture", None),
                        getattr(self.config, "trigger_gesture", None),
                        getattr(self.config, "reset_gesture", None),
                    ),
                    getattr(self.config, "handedness", "right"),
                    reset_poses_path=self._reset_poses_path(),
                )
            else:
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

    def _action_control_mode(self) -> str:
        return normalize_agibot_o10_action_control_mode(
            getattr(self.config, "action_control_mode", "joint")
        )

    def _hand_action_mode(self) -> str:
        return normalize_agibot_o10_hand_action_mode(
            getattr(self.config, "hand_action_mode", "dexterous_10d")
        )

    def _reset_poses_path(self) -> str | None:
        return getattr(self.config, "reset_poses_path", None)

    def convert_eef_delta_action_format(self, action: dict[str, Any]) -> dict[str, list[float]]:
        if "eef_delta" in action and "hand_joints" in action:
            eef_delta = [float(value) for value in action["eef_delta"]]
            hand_joints = [float(value) for value in action["hand_joints"]]
        else:
            eef_delta = [float(action[name]) for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES]
            if self._hand_action_mode() == "gripper_1d":
                hand_joints = gripper_value_to_hand_joints(
                    float(action[AGIBOT_O10_GRIPPER_FEATURE_NAMES[0]]),
                    default_gripper_gesture(
                        getattr(self.config, "gripper_gesture", None),
                        getattr(self.config, "trigger_gesture", None),
                        getattr(self.config, "reset_gesture", None),
                    ),
                    getattr(self.config, "handedness", "right"),
                    reset_poses_path=self._reset_poses_path(),
                )
            else:
                hand_joints = [float(action[name]) for name in AGIBOT_O10_HAND_FEATURE_NAMES]

        if len(eef_delta) != len(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES):
            raise ValueError(
                f"Expected {len(AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)} eef_delta values, got {len(eef_delta)}"
            )
        if len(hand_joints) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
            raise ValueError(
                f"Expected {len(AGIBOT_O10_HAND_FEATURE_NAMES)} hand joints, got {len(hand_joints)}"
            )

        return {
            "eef_delta": eef_delta,
            "hand_joints": hand_joints,
        }

    def convert_eef_absolute_action_format(self, action: dict[str, Any]) -> dict[str, list[float]]:
        if "eef_pose" in action and "hand_joints" in action:
            eef_pose = [float(value) for value in action["eef_pose"]]
            hand_joints = [float(value) for value in action["hand_joints"]]
        else:
            eef_pose = [float(action[name]) for name in AGIBOT_O10_POSE_FEATURE_NAMES]
            if self._hand_action_mode() == "gripper_1d":
                hand_joints = gripper_value_to_hand_joints(
                    float(action[AGIBOT_O10_GRIPPER_FEATURE_NAMES[0]]),
                    default_gripper_gesture(
                        getattr(self.config, "gripper_gesture", None),
                        getattr(self.config, "trigger_gesture", None),
                        getattr(self.config, "reset_gesture", None),
                    ),
                    getattr(self.config, "handedness", "right"),
                    reset_poses_path=self._reset_poses_path(),
                )
            else:
                hand_joints = [float(action[name]) for name in AGIBOT_O10_HAND_FEATURE_NAMES]

        if len(eef_pose) != len(AGIBOT_O10_POSE_FEATURE_NAMES):
            raise ValueError(
                f"Expected {len(AGIBOT_O10_POSE_FEATURE_NAMES)} eef_absolute pose values, got {len(eef_pose)}"
            )
        if len(hand_joints) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
            raise ValueError(
                f"Expected {len(AGIBOT_O10_HAND_FEATURE_NAMES)} hand joints, got {len(hand_joints)}"
            )

        return {
            "eef_pose": eef_pose,
            "hand_joints": hand_joints,
        }

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        if self._action_control_mode() == "eef_delta":
            formatted_action = self.convert_eef_delta_action_format(action)
            current_arm_joints, _ = self.get_joint_pos()
            current_pose = self.arm_kdl.forward_kinematics(
                current_arm_joints[: len(AGIBOT_O10_ARM_FEATURE_NAMES)]
            )
            target_pose = apply_eef_delta_to_pose(current_pose, formatted_action["eef_delta"])
            joints = solve_o10_ik(
                self.arm_kdl,
                target_pose,
                current_arm_joints[: len(AGIBOT_O10_ARM_FEATURE_NAMES)],
            )

            self.servo_joint_pos(joints)
            self.hand_joints = formatted_action["hand_joints"].copy()
            if self.hand is not None:
                self.hand.write_active_joint_angles(formatted_action["hand_joints"])

            if self._hand_action_mode() == "gripper_1d":
                return build_agibot_o10_eef_delta_gripper_action_dict(
                    [
                        *formatted_action["eef_delta"],
                        hand_joints_to_gripper_value(
                            formatted_action["hand_joints"],
                            default_gripper_gesture(
                                getattr(self.config, "gripper_gesture", None),
                                getattr(self.config, "trigger_gesture", None),
                                getattr(self.config, "reset_gesture", None),
                            ),
                            getattr(self.config, "handedness", "right"),
                            reset_poses_path=self._reset_poses_path(),
                        ),
                    ]
                )
            return build_agibot_o10_eef_delta_action_dict(
                [*formatted_action["eef_delta"], *formatted_action["hand_joints"]]
            )

        if self._action_control_mode() == "eef_absolute":
            formatted_action = self.convert_eef_absolute_action_format(action)
            current_arm_joints, _ = self.get_joint_pos()
            target_pose = agibot_o10_eef_absolute_pose_to_matrix(formatted_action["eef_pose"])
            joints = solve_o10_ik(
                self.arm_kdl,
                target_pose,
                current_arm_joints[: len(AGIBOT_O10_ARM_FEATURE_NAMES)],
            )

            self.servo_joint_pos(joints)
            self.hand_joints = formatted_action["hand_joints"].copy()
            if self.hand is not None:
                self.hand.write_active_joint_angles(formatted_action["hand_joints"])

            if self._hand_action_mode() == "gripper_1d":
                return build_agibot_o10_eef_absolute_gripper_action_dict(
                    [
                        *formatted_action["eef_pose"],
                        hand_joints_to_gripper_value(
                            formatted_action["hand_joints"],
                            default_gripper_gesture(
                                getattr(self.config, "gripper_gesture", None),
                                getattr(self.config, "trigger_gesture", None),
                                getattr(self.config, "reset_gesture", None),
                            ),
                            getattr(self.config, "handedness", "right"),
                            reset_poses_path=self._reset_poses_path(),
                        ),
                    ]
                )
            return build_agibot_o10_eef_absolute_action_dict(
                [*formatted_action["eef_pose"], *formatted_action["hand_joints"]]
            )

        formatted_action = self.convert_action_format(action)

        self.servo_joint_pos(formatted_action["joints"])
        self.hand_joints = formatted_action["hand_joints"].copy()
        if self.hand is not None:
            self.hand.write_active_joint_angles(formatted_action["hand_joints"])

        if self._hand_action_mode() == "gripper_1d":
            return build_agibot_o10_gripper_action_dict(
                [
                    *formatted_action["joints"],
                    hand_joints_to_gripper_value(
                        formatted_action["hand_joints"],
                        default_gripper_gesture(
                            getattr(self.config, "gripper_gesture", None),
                            getattr(self.config, "trigger_gesture", None),
                            getattr(self.config, "reset_gesture", None),
                        ),
                        getattr(self.config, "handedness", "right"),
                        reset_poses_path=self._reset_poses_path(),
                    ),
                ]
            )
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

        reset_timeout_s = float(getattr(self.config, "reset_timeout_s", 8.0))
        reset_started_s = time.perf_counter()

        while True:
            state = list(self.arm.state().pos)
            arm_arrived = self.is_arm_arrive(joints, state)
            if arm_arrived:
                break
            if time.perf_counter() - reset_started_s >= reset_timeout_s:
                logger.warning(
                    "Timed out resetting Agibot O10 after %.2fs. "
                    "Continuing to avoid blocking control.",
                    reset_timeout_s,
                )
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
            self.disable_motors()
            self.arm.uninit()
            if self.hand is not None:
                self.hand.disconnect()
            for cam in getattr(self, "cameras", {}).values():
                try:
                    cam.disconnect()
                except Exception as cam_exc:
                    logger.error(f"Camera disconnect failed: {cam_exc}")
        self._is_connected = False
        logger.info(f"{self} safely disconnected.")
