import time
import threading

import numpy as np

from lerobot_play.teleoperators.pico_leader_single_arm_eef.pico_leader_single_arm_eef import (
    PicoLeaderSingleArmEEF,
)
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_EEF_DELTA_FEATURE_NAMES,
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    agibot_o10_eef_delta_gripper_action_feature_types,
    agibot_o10_eef_delta_action_feature_types,
    agibot_o10_gripper_action_feature_types,
    agibot_o10_gripper_value_from_hand_joints,
    agibot_o10_joint_action_feature_types,
    build_agibot_o10_eef_delta_action_dict,
    build_agibot_o10_eef_delta_gripper_action_dict,
    build_agibot_o10_gripper_action_dict,
    build_agibot_o10_joint_action_dict,
    get_agibot_o10_reset_pose_gesture_joint_angles,
    get_agibot_o10_trigger_gesture_joint_angles,
    normalize_agibot_o10_action_control_mode,
    normalize_agibot_o10_hand_action_mode,
)
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore, load_reset_poses

from .agibot_o10_hand import AgibotO10GloveTeleoperator
from .config_pico_leader_single_arm_agibot_o10 import (
    PicoLeaderSingleArmAgibotO10Config,
)


def _rpy_from_rotation_matrix(rotation: np.ndarray) -> list[float]:
    sy = np.sqrt(rotation[0, 0] * rotation[0, 0] + rotation[1, 0] * rotation[1, 0])
    singular = sy < 1e-6
    if not singular:
        roll = np.arctan2(rotation[2, 1], rotation[2, 2])
        pitch = np.arctan2(-rotation[2, 0], sy)
        yaw = np.arctan2(rotation[1, 0], rotation[0, 0])
    else:
        roll = np.arctan2(-rotation[1, 2], rotation[1, 1])
        pitch = np.arctan2(-rotation[2, 0], sy)
        yaw = 0.0
    return [float(roll), float(pitch), float(yaw)]


class PicoLeaderSingleArmAgibotO10(PicoLeaderSingleArmEEF):
    config_class = PicoLeaderSingleArmAgibotO10Config
    name = "pico_leader_single_arm_agibot_o10"

    def __init__(self, config: PicoLeaderSingleArmAgibotO10Config):
        super().__init__(config)
        self.enable_hand = config.enable_hand
        self.hand_teleoperator = (
            AgibotO10GloveTeleoperator(handedness=config.handedness)
            if self.enable_hand
            else None
        )
        self.hand_state_lock = threading.Lock()
        self.arm_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_ARM_FEATURE_NAMES,
            path=None,
            label=f"{config.handedness} arm reset joint target",
            group_key="arm",
        )
        self.hand_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
            path=None,
            label=f"{config.handedness} hand reset joint target",
            group_key="hand",
        )
        self.reset_arm_joint_pos = [0.0] * len(AGIBOT_O10_ARM_FEATURE_NAMES)
        self.reset_hand_joint_pos = [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)
        self.commanded_hand_joint_pos = self.reset_hand_joint_pos.copy()
        self.last_eef_action_pose = self.transform_pose.copy()
        if self._is_trigger_gesture_mode():
            self._reset_trigger_gesture_hand_to_open()

    def connect(self, calibrate: bool = True) -> None:
        self._start_events_thread()
        if self._is_trigger_gesture_mode():
            print("Trigger-gesture hand mode: skipping glove connection.")
            self._reset_trigger_gesture_hand_to_open()
        elif self.hand_teleoperator is not None:
            if not self.hand_teleoperator.init():
                raise RuntimeError(
                    "Failed to initialize the UDE glove receiver for Agibot O10. "
                    "Please make sure HDService/HandDriver is running and UDP port 5555 is available."
                )
            self.hand_teleoperator.start_listening()
            if not self.hand_teleoperator.wait_until_ready(timeout_s=2.0):
                self.hand_teleoperator.stop()
                raise RuntimeError(
                    "Failed to receive fresh UDE glove data for Agibot O10. "
                    "Please confirm the correct glove pair is online in HDWeb and "
                    "that the left/right role matches the teleop handedness."
                )
            self._initialize_hand_reset_target()
        else:
            print("Agibot O10 hand teleoperation disabled. Running in arm-only mode.")
        self._refresh_reset_targets_from_store()
        if self._is_trigger_gesture_mode():
            self._reset_trigger_gesture_hand_to_open()
        self._is_connected = True

    @property
    def action_features(self):
        if self._action_control_mode() == "eef_delta":
            if self._hand_action_mode() == "gripper_1d":
                return agibot_o10_eef_delta_gripper_action_feature_types()
            return agibot_o10_eef_delta_action_feature_types()
        if self._hand_action_mode() == "gripper_1d":
            return agibot_o10_gripper_action_feature_types()
        return agibot_o10_joint_action_feature_types()

    def _action_control_mode(self) -> str:
        return normalize_agibot_o10_action_control_mode(
            getattr(self.config, "action_control_mode", "joint")
        )

    def _hand_action_mode(self) -> str:
        return normalize_agibot_o10_hand_action_mode(
            getattr(self.config, "hand_action_mode", "dexterous_10d")
        )

    def _gripper_gesture(self) -> str:
        return (
            getattr(self.config, "gripper_gesture", None)
            or getattr(self.config, "trigger_gesture", None)
            or getattr(self.config, "reset_gesture", None)
            or "pinch"
        )

    def _reset_poses_path(self) -> str | None:
        return getattr(self.config, "reset_poses_path", None)

    def _hand_joints_to_gripper_value(self, hand_joints: list[float]) -> float:
        return agibot_o10_gripper_value_from_hand_joints(
            hand_joints,
            self._gripper_gesture(),
            getattr(self.config, "handedness", "right"),
            reset_poses_path=self._reset_poses_path(),
        )

    def _current_eef_delta_action(self) -> list[float]:
        current_pose = self.transform_pose.copy()
        previous_matrix = self.pose_transform_to_matrix(
            self.last_eef_action_pose[:3],
            self.last_eef_action_pose[3:],
        )
        current_matrix = self.pose_transform_to_matrix(current_pose[:3], current_pose[3:])
        relative_rotation = previous_matrix[:3, :3].T @ current_matrix[:3, :3]
        delta = [
            current_pose[0] - self.last_eef_action_pose[0],
            current_pose[1] - self.last_eef_action_pose[1],
            current_pose[2] - self.last_eef_action_pose[2],
            *_rpy_from_rotation_matrix(relative_rotation),
        ]
        self.last_eef_action_pose = current_pose
        return [float(value) for value in delta]

    def _set_commanded_hand_joint_pos(self, joint_pos: list[float]) -> None:
        with self.hand_state_lock:
            self.commanded_hand_joint_pos = joint_pos.copy()

    def _set_reset_arm_joint_pos(self, joint_pos: list[float], *, persist: bool) -> list[float]:
        normalized_joint_pos = self.arm_reset_store.normalize(joint_pos)
        self.reset_arm_joint_pos = normalized_joint_pos.copy()
        return normalized_joint_pos

    def _get_reset_arm_joint_pos(self) -> list[float]:
        return self.reset_arm_joint_pos.copy()

    def _get_commanded_hand_joint_pos(self) -> list[float]:
        with self.hand_state_lock:
            return self.commanded_hand_joint_pos.copy()

    def _set_reset_hand_joint_pos(
        self,
        joint_pos: list[float],
        *,
        persist: bool,
        sync_commanded: bool,
    ) -> list[float]:
        normalized_joint_pos = self.hand_reset_store.normalize(joint_pos)
        with self.hand_state_lock:
            self.reset_hand_joint_pos = normalized_joint_pos.copy()
            if sync_commanded:
                self.commanded_hand_joint_pos = normalized_joint_pos.copy()
        return normalized_joint_pos

    def _get_reset_hand_joint_pos(self) -> list[float]:
        with self.hand_state_lock:
            return self.reset_hand_joint_pos.copy()

    def _log_hand_joint_pos(self, title: str, joint_pos: list[float]) -> None:
        print(title)
        for feature_name, joint_value in zip(
            AGIBOT_O10_HAND_FEATURE_NAMES, joint_pos, strict=True
        ):
            print(f"  {feature_name}: {joint_value:.4f}")

    def _log_arm_joint_pos(self, title: str, joint_pos: list[float]) -> None:
        print(title)
        for feature_name, joint_value in zip(
            AGIBOT_O10_ARM_FEATURE_NAMES, joint_pos, strict=True
        ):
            print(f"  {feature_name}: {joint_value:.4f}")

    def _current_arm_joint_pos(self) -> list[float]:
        now = time.time()
        return [self.lpfs[index].sample(now) for index in range(len(AGIBOT_O10_ARM_FEATURE_NAMES))]

    def _apply_reset_arm_joint_pos(self, joint_pos: list[float]) -> None:
        target_joint_pos = self.arm_reset_store.normalize(joint_pos)
        target_pose = self.arm_kdl.forward_kinematics(target_joint_pos[:6])
        self.transform_pose = self.homogeneous_matrix_to_pose(target_pose).tolist()
        now = time.time()
        for index, joint_value in enumerate(target_joint_pos):
            self.lpfs[index].update(now, joint_value)
        self.history = target_joint_pos.copy()
        self.reset_arm_joint_pos = target_joint_pos.copy()

    def _refresh_reset_targets_from_store(self) -> None:
        reset_poses_path = getattr(self.config, "reset_poses_path", None)
        reset_gesture = getattr(self.config, "reset_gesture", None)
        if not reset_poses_path or not reset_gesture:
            return

        try:
            arm_loaded, hand_loaded = load_reset_poses(
                reset_poses_path, self.config.handedness, reset_gesture,
            )
        except Exception as exc:
            print(f"Warning: failed to load reset poses: {exc}")
            return

        if arm_loaded is not None:
            stored_arm_joint_pos = self._set_reset_arm_joint_pos(
                arm_loaded,
                persist=False,
            )
            self._log_arm_joint_pos(
                "Loaded persistent Agibot O10 arm reset target:",
                stored_arm_joint_pos,
            )

        if hand_loaded is not None:
            stored_hand_joint_pos = self._set_reset_hand_joint_pos(
                hand_loaded,
                persist=False,
                sync_commanded=False,
            )
            self._log_hand_joint_pos(
                "Loaded persistent Agibot O10 hand reset target:",
                stored_hand_joint_pos,
            )

    def _initialize_hand_reset_target(self) -> None:
        if self.hand_teleoperator is None:
            return

        reset_poses_path = getattr(self.config, "reset_poses_path", None)
        reset_gesture = getattr(self.config, "reset_gesture", None)
        stored_joint_pos = None
        if reset_poses_path and reset_gesture:
            try:
                _, stored_joint_pos = load_reset_poses(
                    reset_poses_path, self.config.handedness, reset_gesture,
                )
            except Exception as exc:
                print(f"Warning: failed to load reset poses for hand init: {exc}")
                stored_joint_pos = None

        if stored_joint_pos is not None:
            stored_joint_pos = self._set_reset_hand_joint_pos(
                stored_joint_pos,
                persist=False,
                sync_commanded=True,
            )
            self._log_hand_joint_pos(
                "Loaded persistent Agibot O10 hand reset target:",
                stored_joint_pos,
            )
            return

        self.capture_current_hand_joint_pos_as_reset_target(persist=True)

    def capture_current_hand_joint_pos_as_reset_target(
        self, persist: bool = True
    ) -> list[float]:
        if self.hand_teleoperator is None:
            return self._get_reset_hand_joint_pos()

        current_joint_pos = self.hand_teleoperator.wait_for_hand_data(timeout_s=2.0)
        has_fresh_hand_data = self.hand_teleoperator.has_hand_data()
        should_persist = persist and has_fresh_hand_data
        current_joint_pos = self._set_reset_hand_joint_pos(
            current_joint_pos,
            persist=should_persist,
            sync_commanded=True,
        )

        if persist and not has_fresh_hand_data:
            print(
                "Warning: no fresh Agibot O10 glove data received yet, "
                "using an in-memory hand reset target for this run only."
            )

        if should_persist:
            title = "Captured and saved Agibot O10 hand reset target:"
        else:
            title = "Captured Agibot O10 temporary hand reset target:"
        self._log_hand_joint_pos(title, current_joint_pos)
        return current_joint_pos

    def _is_hand_control_enabled(self) -> bool:
        if getattr(self, "controller_side", self.handedness) == "left":
            return self.startflag and self.ctrl["LTr"]
        return self.startflag and self.ctrl["RTr"]

    def _is_trigger_gesture_mode(self) -> bool:
        return getattr(self.config, "hand_mode", "glove") == "trigger_gesture"

    def _get_trigger_gesture_hand_pos(self, state_key: str) -> list[float]:
        return get_agibot_o10_reset_pose_gesture_joint_angles(
            self._reset_poses_path(),
            getattr(self.config, "trigger_gesture", "pinch"),
            self.handedness,
            state_key,
        ) or get_agibot_o10_trigger_gesture_joint_angles(
            getattr(self.config, "trigger_gesture", "pinch"),
            self.handedness,
            state_key,
        )

    def _reset_trigger_gesture_hand_to_open(self) -> None:
        self._set_reset_hand_joint_pos(
            self._get_trigger_gesture_hand_pos("open"),
            persist=False,
            sync_commanded=True,
        )

    def _is_trigger_gesture_grasp_pressed(self) -> bool:
        controller_side = getattr(self, "controller_side", self.handedness)
        button_key = "RG" if controller_side == "right" else "LG"
        grip_key = "rightGrip" if controller_side == "right" else "leftGrip"
        return bool(self.ctrl[button_key]) or float(self.ctrl.get(grip_key, 0.0)) >= 0.2

    def reset_pose(self):
        self._refresh_reset_targets_from_store()
        if self._is_trigger_gesture_mode():
            self._reset_trigger_gesture_hand_to_open()

        arm_joint_pos = self._get_reset_arm_joint_pos()
        if not any(abs(joint_value) > 1e-9 for joint_value in arm_joint_pos):
            arm_joint_pos = self._current_arm_joint_pos()
            arm_joint_pos = self._set_reset_arm_joint_pos(
                arm_joint_pos,
                persist=False,
            )

        self._apply_reset_arm_joint_pos(arm_joint_pos)
        self.last_eef_action_pose = self.transform_pose.copy()
        self.arm_init = False
        self.trans_init = None
        self.quat_init = None
        self.vr_init_pose = None
        self.arm_init_pose = None
        self._log_arm_joint_pos("RESET Arm position target:", arm_joint_pos)

        self._set_commanded_hand_joint_pos(self._get_reset_hand_joint_pos())
        print("RESET Hand position")

    def get_joint_pos(self):
        state = [0.0] * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES))
        now = time.time()
        for index in range(len(AGIBOT_O10_ARM_FEATURE_NAMES)):
            state[index] = self.lpfs[index].sample(now)

        if self._is_trigger_gesture_mode():
            if self._is_hand_control_enabled():
                state_key = (
                    "closed"
                    if self._is_trigger_gesture_grasp_pressed()
                    else "open"
                )
                hand_ctrl_data = self._get_trigger_gesture_hand_pos(state_key)
                self._set_commanded_hand_joint_pos(hand_ctrl_data)
            else:
                hand_ctrl_data = self._get_commanded_hand_joint_pos()
        elif (
            self.hand_teleoperator is not None
            and self._is_hand_control_enabled()
            and self.hand_teleoperator.has_hand_data(
                max_age_s=self.hand_teleoperator.max_data_age_s
            )
        ):
            hand_ctrl_data = self.hand_teleoperator.get_hand_data()
            self._set_commanded_hand_joint_pos(hand_ctrl_data)
        else:
            hand_ctrl_data = self._get_commanded_hand_joint_pos()

        for index, joint_value in enumerate(hand_ctrl_data):
            state[len(AGIBOT_O10_ARM_FEATURE_NAMES) + index] = joint_value

        return state

    def get_action(self):
        joint_pos = self.get_joint_pos()
        if self._action_control_mode() == "eef_delta":
            hand_start = len(AGIBOT_O10_ARM_FEATURE_NAMES)
            if self._hand_action_mode() == "gripper_1d":
                return build_agibot_o10_eef_delta_gripper_action_dict(
                    [
                        *self._current_eef_delta_action(),
                        self._hand_joints_to_gripper_value(joint_pos[hand_start:]),
                    ]
                )
            return build_agibot_o10_eef_delta_action_dict(
                [*self._current_eef_delta_action(), *joint_pos[hand_start:]]
            )
        if self._hand_action_mode() == "gripper_1d":
            hand_start = len(AGIBOT_O10_ARM_FEATURE_NAMES)
            return build_agibot_o10_gripper_action_dict(
                [
                    *joint_pos[:hand_start],
                    self._hand_joints_to_gripper_value(joint_pos[hand_start:]),
                ]
            )
        return build_agibot_o10_joint_action_dict(joint_pos)
