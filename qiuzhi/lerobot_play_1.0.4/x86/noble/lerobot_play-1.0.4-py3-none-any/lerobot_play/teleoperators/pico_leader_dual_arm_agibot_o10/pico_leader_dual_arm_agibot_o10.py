import logging
import threading
import time
from functools import cached_property
from typing import Any

import numpy as np
from mmk2_kdl_py import ArmKdlNumerical

from lerobot_play.teleoperators.pico_leader_single_arm_eef.pico_leader_single_arm_eef import (
    PicoLeaderSingleArmEEF,
)
from lerobot_play.teleoperators.pico_leader_single_arm_eef.lpf import (
    OnlineVariableStepLPF,
)
from lerobot_play.teleoperators.pico_leader_single_arm_agibot_o10.agibot_o10_hand import (
    AgibotO10GloveTeleoperator,
)
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    normalize_agibot_o10_action_control_mode,
    normalize_agibot_o10_hand_action_mode,
)
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore
from lerobot_play.utils.o10_hand_control import (
    default_gripper_gesture,
    gripper_value_to_hand_joints,
    hand_joints_to_gripper_value,
    trigger_gesture_hand_pos,
)
from lerobot_play.utils.o10_motion import homogeneous_matrix_to_pose, rpy_from_rotation_matrix
from lerobot_play.utils.o10_reset import load_o10_reset_targets, normalize_joint_values
from lerobot_play.utils.o10_schema import (
    DUAL_ARM_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_ABSOLUTE_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_ABSOLUTE_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES,
    NUM_O10_ARM_JOINTS,
    NUM_O10_HAND_JOINTS,
    SIDE_ACTION_DIM,
)

from .config_pico_leader_dual_arm_agibot_o10 import (
    PicoLeaderDualArmAgibotO10Config,
)

logger = logging.getLogger(__name__)

_NUM_ARM_JOINTS = NUM_O10_ARM_JOINTS
_NUM_HAND_JOINTS = NUM_O10_HAND_JOINTS
_SIDE_ACTION_DIM = SIDE_ACTION_DIM


class PicoLeaderDualArmAgibotO10(PicoLeaderSingleArmEEF):
    """Dual-arm leader teleoperator for Agibot O10 with OmniHand gloves.

    Inherits WebRTC/ZMQ infrastructure from PicoLeaderSingleArmEEF and
    extends it with two independent IK solvers, two sets of LPFs, and two
    glove teleoperators (left + right).
    """

    config_class = PicoLeaderDualArmAgibotO10Config
    name = "pico_leader_dual_arm_agibot_o10"
    def __init__(self, config: PicoLeaderDualArmAgibotO10Config):
        # Bypass PicoLeaderSingleArmEEF.__init__ single-arm setup;
        # call the grandparent (Teleoperator) init, then replicate only
        # the shared WebRTC/ZMQ infrastructure from the parent.
        super().__init__(config)

        # --- per-side state ---
        self.enable_hand = config.enable_hand
        self.hand_state_lock = threading.Lock()

        left_cfg = config.left
        right_cfg = config.right

        # IK solvers (both use the same URDF, eef_type="none")
        self.left_arm_kdl = ArmKdlNumerical(eef_type="none")
        self.right_arm_kdl = ArmKdlNumerical(eef_type="none")

        # LPFs: 6 per arm
        self.left_lpfs = [
            OnlineVariableStepLPF(fc=100, kp=10, kd=0.2, v_max=5000, a_max=100)
            for _ in range(_NUM_ARM_JOINTS)
        ]
        self.right_lpfs = [
            OnlineVariableStepLPF(fc=100, kp=10, kd=0.2, v_max=5000, a_max=100)
            for _ in range(_NUM_ARM_JOINTS)
        ]

        # Transform poses (EEF home in task space)
        self.left_transform_pose = [0.12610013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]
        self.right_transform_pose = [0.12610013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]
        self.left_last_eef_action_pose = self.left_transform_pose.copy()
        self.right_last_eef_action_pose = self.right_transform_pose.copy()

        # IK history
        self.left_history = [0.0] * _NUM_ARM_JOINTS
        self.right_history = [0.0] * _NUM_ARM_JOINTS

        # Arm init flags (per-side)
        self.left_arm_init = False
        self.right_arm_init = False
        # VR init poses (per-side)
        self.left_trans_init = None
        self.left_quat_init = None
        self.left_vr_init_pose = None
        self.left_arm_init_pose = None
        self.right_trans_init = None
        self.right_quat_init = None
        self.right_vr_init_pose = None
        self.right_arm_init_pose = None

        # Glove teleoperators
        self.left_hand_teleoperator = (
            AgibotO10GloveTeleoperator(handedness="left")
            if self.enable_hand
            else None
        )
        self.right_hand_teleoperator = (
            AgibotO10GloveTeleoperator(handedness="right")
            if self.enable_hand
            else None
        )

        # Reset stores (path=None: normalize-only, no file I/O)
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
        # Reset joint positions
        self.left_reset_arm_joint_pos = [0.0] * _NUM_ARM_JOINTS
        self.left_reset_hand_joint_pos = [0.0] * _NUM_HAND_JOINTS
        self.left_commanded_hand_joint_pos = self.left_reset_hand_joint_pos.copy()
        self.right_reset_arm_joint_pos = [0.0] * _NUM_ARM_JOINTS
        self.right_reset_hand_joint_pos = [0.0] * _NUM_HAND_JOINTS
        self.right_commanded_hand_joint_pos = self.right_reset_hand_joint_pos.copy()
        if self._is_trigger_gesture_mode():
            self._reset_trigger_gesture_hands_to_open()

    def _update_pose_data(self, pose_msg):
        try:
            if "head_pose" in pose_msg:
                head_data = pose_msg["head_pose"]
                if len(head_data) == 7:
                    self.head_info = head_data.copy()

            if "left_pose" in pose_msg:
                left_data = pose_msg["left_pose"]
                if len(left_data) == 7:
                    self.left_info = left_data.copy()

            if "right_pose" in pose_msg:
                right_data = pose_msg["right_pose"]
                if len(right_data) == 7:
                    self.right_info = right_data.copy()

            if "tracking_state" in pose_msg:
                state = pose_msg["tracking_state"]
                self.ctrl.update(
                    {
                        "HBattery": float(state.get("head_battery", 0.0)),
                        "LIsTracked": bool(state.get("left_tracked", False)),
                        "LBattery": float(state.get("left_battery", 0.0)),
                        "RIsTracked": bool(state.get("right_tracked", False)),
                        "RBattery": float(state.get("right_battery", 0.0)),
                        "LWristTracked": bool(state.get("left_wrist_tracked", False)),
                        "LWristBattery": float(state.get("left_wrist_battery", 0.0)),
                        "RWristTracked": bool(state.get("right_wrist_tracked", False)),
                        "RWristBattery": float(state.get("right_wrist_battery", 0.0)),
                    }
                )

            if self.active_pose_source != "dual":
                print("当前使用双臂 wrist pose 作为控臂输入")
                self.active_pose_source = "dual"
        except Exception as e:
            print(f"Error updating dual-arm pose data: {e}")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, calibrate: bool = True) -> None:
        self._start_events_thread()

        hand_mode = getattr(self.config, "hand_mode", "glove")
        if hand_mode == "trigger_gesture":
            print("Trigger-gesture hand mode: skipping glove connection.")
        else:
            for side, glove in (("left", self.left_hand_teleoperator),
                                ("right", self.right_hand_teleoperator)):
                if glove is None:
                    print(f"Agibot O10 {side} hand teleoperation disabled.")
                    continue
                if not glove.init():
                    raise RuntimeError(
                        f"Failed to initialize the UDE glove receiver for Agibot O10 {side} hand. "
                        "Please make sure HDService/HandDriver is running."
                    )
                glove.start_listening()
                if not glove.wait_until_ready(timeout_s=2.0):
                    glove.stop()
                    raise RuntimeError(
                        f"Failed to receive fresh UDE glove data for Agibot O10 {side} hand."
                    )
                self._initialize_hand_reset_target(side)

        self._refresh_reset_targets_from_store()
        if hand_mode == "trigger_gesture":
            self._reset_trigger_gesture_hands_to_open()
        self._is_connected = True
    # ------------------------------------------------------------------
    # Action features
    # ------------------------------------------------------------------

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

    def _current_side_eef_delta_action(self, side: str) -> list[float]:
        current_pose = getattr(self, f"{side}_transform_pose").copy()
        last_pose = getattr(self, f"{side}_last_eef_action_pose")
        previous_matrix = self.pose_transform_to_matrix(last_pose[:3], last_pose[3:])
        current_matrix = self.pose_transform_to_matrix(current_pose[:3], current_pose[3:])
        relative_rotation = previous_matrix[:3, :3].T @ current_matrix[:3, :3]
        delta = [
            current_pose[0] - last_pose[0],
            current_pose[1] - last_pose[1],
            current_pose[2] - last_pose[2],
            *rpy_from_rotation_matrix(relative_rotation),
        ]
        setattr(self, f"{side}_last_eef_action_pose", current_pose)
        return [float(value) for value in delta]

    def _current_side_eef_absolute_action(self, side: str) -> list[float]:
        return [float(value) for value in getattr(self, f"{side}_transform_pose")]

    # ------------------------------------------------------------------
    # Per-side accessors
    # ------------------------------------------------------------------

    def _get_side_attrs(self, side: str):
        """Return (arm_kdl, lpfs, transform_pose, history, arm_init,
        glove, arm_reset_store, hand_reset_store) for the given side."""
        return (
            getattr(self, f"{side}_arm_kdl"),
            getattr(self, f"{side}_lpfs"),
            getattr(self, f"{side}_transform_pose"),
            getattr(self, f"{side}_history"),
            getattr(self, f"{side}_arm_init"),
            getattr(self, f"{side}_hand_teleoperator"),
            getattr(self, f"{side}_arm_reset_store"),
            getattr(self, f"{side}_hand_reset_store"),
        )

    def _set_commanded_hand_joint_pos(self, side: str, joint_pos: list[float]) -> None:
        with self.hand_state_lock:
            setattr(self, f"{side}_commanded_hand_joint_pos", joint_pos.copy())

    def _get_commanded_hand_joint_pos(self, side: str) -> list[float]:
        with self.hand_state_lock:
            return getattr(self, f"{side}_commanded_hand_joint_pos").copy()

    def _set_reset_hand_joint_pos(
        self, side: str, joint_pos: list[float],
        *, persist: bool, sync_commanded: bool,
    ) -> list[float]:
        store = getattr(self, f"{side}_hand_reset_store")
        normalized = normalize_joint_values(store, joint_pos)
        with self.hand_state_lock:
            setattr(self, f"{side}_reset_hand_joint_pos", normalized.copy())
            if sync_commanded:
                setattr(self, f"{side}_commanded_hand_joint_pos", normalized.copy())
        return normalized
    def _get_reset_hand_joint_pos(self, side: str) -> list[float]:
        with self.hand_state_lock:
            return getattr(self, f"{side}_reset_hand_joint_pos").copy()

    def _set_reset_arm_joint_pos(self, side: str, joint_pos: list[float]) -> list[float]:
        store = getattr(self, f"{side}_arm_reset_store")
        normalized = normalize_joint_values(store, joint_pos)
        setattr(self, f"{side}_reset_arm_joint_pos", normalized.copy())
        return normalized

    def _get_reset_arm_joint_pos(self, side: str) -> list[float]:
        return getattr(self, f"{side}_reset_arm_joint_pos").copy()

    def _current_arm_joint_pos(self, side: str) -> list[float]:
        lpfs = getattr(self, f"{side}_lpfs")
        now = time.time()
        return [lpfs[i].sample(now) for i in range(_NUM_ARM_JOINTS)]

    # ------------------------------------------------------------------
    # Reset target persistence
    # ------------------------------------------------------------------

    def _initialize_hand_reset_target(self, side: str) -> None:
        glove = getattr(self, f"{side}_hand_teleoperator")
        if glove is None:
            return

        side_cfg = getattr(self.config, side)
        reset_poses_path = side_cfg.get("reset_poses_path")
        reset_gesture = side_cfg.get("reset_gesture")
        stored = None
        if reset_poses_path and reset_gesture:
            try:
                _, stored = load_o10_reset_targets(reset_poses_path, side, reset_gesture)
            except Exception as exc:
                print(f"Warning: failed to load {side} reset poses for hand init: {exc}")
                stored = None

        if stored is not None:
            stored = self._set_reset_hand_joint_pos(
                side, stored, persist=False, sync_commanded=True,
            )
            self._log_joint_pos(
                f"Loaded persistent Agibot O10 {side} hand reset target:", stored,
            )
            return

        self._capture_current_hand_as_reset(side, persist=True)
    def _capture_current_hand_as_reset(self, side: str, persist: bool = True) -> list[float]:
        glove = getattr(self, f"{side}_hand_teleoperator")
        if glove is None:
            return self._get_reset_hand_joint_pos(side)

        current = glove.wait_for_hand_data(timeout_s=2.0)
        has_fresh = glove.has_hand_data()
        should_persist = persist and has_fresh
        current = self._set_reset_hand_joint_pos(
            side, current, persist=should_persist, sync_commanded=True,
        )
        if persist and not has_fresh:
            print(f"Warning: no fresh {side} glove data, using in-memory reset target.")
        title = (
            f"Captured and saved Agibot O10 {side} hand reset target:"
            if should_persist
            else f"Captured Agibot O10 {side} temporary hand reset target:"
        )
        self._log_joint_pos(title, current)
        return current

    def _refresh_reset_targets_from_store(self) -> None:
        for side in ("left", "right"):
            side_cfg = getattr(self.config, side)
            reset_poses_path = side_cfg.get("reset_poses_path")
            reset_gesture = side_cfg.get("reset_gesture")

            if not reset_poses_path or not reset_gesture:
                continue

            try:
                arm_loaded, hand_loaded = load_o10_reset_targets(
                    reset_poses_path, side, reset_gesture,
                )
            except Exception as exc:
                print(f"Warning: failed to load {side} reset poses: {exc}")
                continue

            if arm_loaded is not None:
                arm_loaded = self._set_reset_arm_joint_pos(side, arm_loaded)
                self._log_joint_pos(f"Loaded {side} arm reset target:", arm_loaded)
            if hand_loaded is not None:
                hand_loaded = self._set_reset_hand_joint_pos(
                    side, hand_loaded, persist=False, sync_commanded=False,
                )
                self._log_joint_pos(f"Loaded {side} hand reset target:", hand_loaded)
    @staticmethod
    def _log_joint_pos(title: str, joint_pos: list[float]) -> None:
        print(title)
        for val in joint_pos:
            print(f"  {val:.4f}")

    def _is_trigger_gesture_mode(self) -> bool:
        return getattr(self.config, "hand_mode", "glove") == "trigger_gesture"

    def _get_trigger_gesture_name(self, side: str) -> str:
        side_cfg = getattr(self.config, side, {}) or {}
        gesture_name = side_cfg.get(
            "trigger_gesture",
            getattr(self.config, "trigger_gesture", "pinch"),
        )
        return gesture_name

    def _get_trigger_gesture_hand_pos(self, side: str, state_key: str) -> list[float]:
        return trigger_gesture_hand_pos(
            self._side_reset_poses_path(side),
            self._get_trigger_gesture_name(side),
            self._side_handedness(side),
            state_key,
        )

    def _get_trigger_gesture_hand_pos_from_gripper_value(
        self,
        side: str,
        gripper_value: float,
    ) -> list[float]:
        return gripper_value_to_hand_joints(
            gripper_value,
            self._get_trigger_gesture_name(side),
            self._side_handedness(side),
            reset_poses_path=self._side_reset_poses_path(side),
        )

    def _reset_trigger_gesture_hands_to_open(self) -> None:
        for side in ("left", "right"):
            hand_pos = self._get_trigger_gesture_hand_pos(side, "open")
            self._set_reset_hand_joint_pos(
                side, hand_pos, persist=False, sync_commanded=True,
            )

    def _get_trigger_gesture_gripper_value(self, side: str) -> float:
        button_key = "LG" if side == "left" else "RG"
        if bool(self.ctrl.get(button_key, False)):
            return 1.0

        grip_key = "leftGrip" if side == "left" else "rightGrip"
        grip_value = float(self.ctrl.get(grip_key, 0.0))
        return min(1.0, max(0.0, grip_value))

    # ------------------------------------------------------------------
    # IK update (per-side)
    # ------------------------------------------------------------------

    def _update_arm(self, side: str, pose: np.ndarray) -> None:
        """Run IK for one arm and push result into that side's LPFs."""
        arm_kdl = getattr(self, f"{side}_arm_kdl")
        lpfs = getattr(self, f"{side}_lpfs")

        now = time.time()
        joint_pos = [lpfs[i].sample(now) for i in range(_NUM_ARM_JOINTS)]
        # force_calculate=True: fall back to numerical solver near analytical
        # singularities; otherwise IK returns 0 solutions and the arm freezes
        # on common near-home targets (e.g. small wrist yaw from zero seed).
        result = arm_kdl.inverse_kinematics(
            np.array(pose, dtype=float), joint_pos, force_calculate=True,
        )

        if len(result) == 0:
            print(f"IK failed for {side} arm. Pose: {pose}")
            return

        pos = result[0]
        now = time.time()
        for i in range(_NUM_ARM_JOINTS):
            lpfs[i].update(now, pos[i])
        setattr(self, f"{side}_history", list(pos))

    def _apply_reset_arm_joint_pos(self, side: str, joint_pos: list[float]) -> None:
        arm_kdl = getattr(self, f"{side}_arm_kdl")
        lpfs = getattr(self, f"{side}_lpfs")
        arm_store = getattr(self, f"{side}_arm_reset_store")

        target = normalize_joint_values(arm_store, joint_pos)
        target_pose = arm_kdl.forward_kinematics(target[:_NUM_ARM_JOINTS])
        pose_vec = homogeneous_matrix_to_pose(target_pose).tolist()
        setattr(self, f"{side}_transform_pose", pose_vec)

        now = time.time()
        for i, val in enumerate(target):
            lpfs[i].update(now, val)
        setattr(self, f"{side}_history", target.copy())
        setattr(self, f"{side}_reset_arm_joint_pos", target.copy())
    # ------------------------------------------------------------------
    # Hand control trigger logic
    # ------------------------------------------------------------------

    def _is_hand_control_enabled(self, side: str) -> bool:
        return self._is_arm_control_enabled(side)

    def _is_arm_control_enabled(self, side: str) -> bool:
        trigger_mode = getattr(self.config, "arm_trigger_mode", "split").lower()
        if trigger_mode == "left":
            trigger_pressed = self.ctrl["LTr"]
        elif trigger_mode == "right":
            trigger_pressed = self.ctrl["RTr"]
        elif trigger_mode == "both":
            trigger_pressed = self.ctrl["LTr"] and self.ctrl["RTr"]
        elif side == "left":
            trigger_pressed = self.ctrl["LTr"]
        else:
            trigger_pressed = self.ctrl["RTr"]
        return self.startflag and trigger_pressed

    # ------------------------------------------------------------------
    # Main control loop override
    # ------------------------------------------------------------------

    def handle_pose_data(self):
        """Override parent to drive both arms from left_info / right_info."""
        while not self.stop_event.is_set():
            self.pause_event.wait()
            if self.stop_event.is_set():
                break
            if not self.is_connected:
                time.sleep(1 / 30)
                continue

            # Dual-arm enable/reset is always owned by the left controller.
            enable_button = self.ctrl["X"]
            reset_button = self.ctrl["Y"]

            if enable_button and not self.startflag:
                self.startflag = True
                print("start dual-arm VR control")

            if reset_button and self.startflag:
                self.startflag = False
                self.reset_pose()
                print("stop dual-arm control")

            # Process each arm independently
            for side, pose_info in (("left", self.left_info),
                                    ("right", self.right_info)):
                enable = self._is_arm_control_enabled(side)
                if enable:
                    self._control_arm_with_wrist(side, pose_info)
                else:
                    setattr(self, f"{side}_arm_init", False)

            time.sleep(1 / 30)
    def _control_arm_with_wrist(self, side: str, pose_info: list[float]) -> None:
        """Run one IK step for *side* using the given 7D wrist pose."""
        try:
            if self._is_default_pose(pose_info):
                setattr(self, f"{side}_arm_init", False)
                return

            vr_trans = np.array(pose_info[:3], dtype=float)
            vr_quat = np.array(pose_info[3:7], dtype=float)
            vr_cur_pose = self.pose_transform_to_matrix(vr_trans, vr_quat)

            arm_init = getattr(self, f"{side}_arm_init")
            if not arm_init:
                setattr(self, f"{side}_trans_init", vr_trans.copy())
                setattr(self, f"{side}_quat_init", vr_quat.copy())
                setattr(
                    self, f"{side}_vr_init_pose",
                    self.pose_transform_to_matrix(vr_trans, vr_quat),
                )
                tp = getattr(self, f"{side}_transform_pose")
                setattr(
                    self, f"{side}_arm_init_pose",
                    self.pose_transform_to_matrix(tp[:3], tp[3:]),
                )
                print(f"{side} arm VR init pos: {vr_trans}")
                print(f"{side} arm VR init quat: {vr_quat}")
                setattr(self, f"{side}_arm_init", True)

            vr_init_pose = getattr(self, f"{side}_vr_init_pose")
            arm_init_pose = getattr(self, f"{side}_arm_init_pose")
            relative_transform = np.dot(np.linalg.inv(vr_init_pose), vr_cur_pose)
            T = np.dot(arm_init_pose, relative_transform)

            self._update_arm(side, T)
            setattr(
                self, f"{side}_transform_pose",
                homogeneous_matrix_to_pose(T).tolist(),
            )
        except Exception as e:
            print(f"{side} arm VR control error: {e}")
    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_pose(self):
        self._refresh_reset_targets_from_store()
        if self._is_trigger_gesture_mode():
            self._reset_trigger_gesture_hands_to_open()

        for side in ("left", "right"):
            arm_pos = self._get_reset_arm_joint_pos(side)
            if not any(abs(v) > 1e-9 for v in arm_pos):
                arm_pos = self._current_arm_joint_pos(side)
                arm_pos = self._set_reset_arm_joint_pos(side, arm_pos)

            self._apply_reset_arm_joint_pos(side, arm_pos)
            setattr(
                self,
                f"{side}_last_eef_action_pose",
                getattr(self, f"{side}_transform_pose").copy(),
            )
            setattr(self, f"{side}_arm_init", False)
            setattr(self, f"{side}_trans_init", None)
            setattr(self, f"{side}_quat_init", None)
            setattr(self, f"{side}_vr_init_pose", None)
            setattr(self, f"{side}_arm_init_pose", None)
            print(f"RESET {side} arm position")

            self._set_commanded_hand_joint_pos(side, self._get_reset_hand_joint_pos(side))
            print(f"RESET {side} hand position")

    def return_init(self):
        self.reset_pose()

    # ------------------------------------------------------------------
    # Joint position / action output
    # ------------------------------------------------------------------

    def _get_side_joint_pos(self, side: str) -> list[float]:
        """Return 16D joint pos for one side: arm[6] + hand[10]."""
        lpfs = getattr(self, f"{side}_lpfs")
        glove = getattr(self, f"{side}_hand_teleoperator")

        state = [0.0] * _SIDE_ACTION_DIM
        now = time.time()
        for i in range(_NUM_ARM_JOINTS):
            state[i] = lpfs[i].sample(now)

        hand_mode = getattr(self.config, "hand_mode", "glove")
        if hand_mode == "trigger_gesture":
            if self._is_hand_control_enabled(side):
                gripper_value = self._get_trigger_gesture_gripper_value(side)
                hand_data = self._get_trigger_gesture_hand_pos_from_gripper_value(
                    side,
                    gripper_value,
                )
                self._set_commanded_hand_joint_pos(side, hand_data)
            else:
                hand_data = self._get_commanded_hand_joint_pos(side)
        elif (
            glove is not None
            and self._is_hand_control_enabled(side)
            and glove.has_hand_data(max_age_s=glove.max_data_age_s)
        ):
            hand_data = glove.get_hand_data()
            self._set_commanded_hand_joint_pos(side, hand_data)
        else:
            hand_data = self._get_commanded_hand_joint_pos(side)

        for i, val in enumerate(hand_data):
            state[_NUM_ARM_JOINTS + i] = val
        return state
    def get_joint_pos(self) -> list[float]:
        """Return 32D: left_arm[6]+left_hand[10]+right_arm[6]+right_hand[10]."""
        left = self._get_side_joint_pos("left")
        right = self._get_side_joint_pos("right")
        return left + right

    def get_action(self) -> dict[str, float]:
        """Return 32D action dict keyed by DUAL_ARM_ACTION_FEATURE_NAMES."""
        joint_pos = self.get_joint_pos()
        if self._action_control_mode() == "eef_delta":
            left_hand = joint_pos[_NUM_ARM_JOINTS:_SIDE_ACTION_DIM]
            right_hand = joint_pos[_SIDE_ACTION_DIM + _NUM_ARM_JOINTS:]
            if self._hand_action_mode() == "gripper_1d":
                values = [
                    *self._current_side_eef_delta_action("left"),
                    self._hand_joints_to_gripper_value("left", left_hand),
                    *self._current_side_eef_delta_action("right"),
                    self._hand_joints_to_gripper_value("right", right_hand),
                ]
                action_feature_names = DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES
            else:
                values = [
                    *self._current_side_eef_delta_action("left"),
                    *left_hand,
                    *self._current_side_eef_delta_action("right"),
                    *right_hand,
                ]
                action_feature_names = DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES
            return {
                name: values[idx]
                for idx, name in enumerate(action_feature_names)
            }
        if self._action_control_mode() == "eef_absolute":
            left_hand = joint_pos[_NUM_ARM_JOINTS:_SIDE_ACTION_DIM]
            right_hand = joint_pos[_SIDE_ACTION_DIM + _NUM_ARM_JOINTS:]
            if self._hand_action_mode() == "gripper_1d":
                values = [
                    *self._current_side_eef_absolute_action("left"),
                    self._hand_joints_to_gripper_value("left", left_hand),
                    *self._current_side_eef_absolute_action("right"),
                    self._hand_joints_to_gripper_value("right", right_hand),
                ]
                action_feature_names = DUAL_ARM_EEF_ABSOLUTE_GRIPPER_ACTION_FEATURE_NAMES
            else:
                values = [
                    *self._current_side_eef_absolute_action("left"),
                    *left_hand,
                    *self._current_side_eef_absolute_action("right"),
                    *right_hand,
                ]
                action_feature_names = DUAL_ARM_EEF_ABSOLUTE_ACTION_FEATURE_NAMES
            return {
                name: values[idx]
                for idx, name in enumerate(action_feature_names)
            }
        if self._hand_action_mode() == "gripper_1d":
            left = joint_pos[:_SIDE_ACTION_DIM]
            right = joint_pos[_SIDE_ACTION_DIM:]
            values = [
                *left[:_NUM_ARM_JOINTS],
                self._hand_joints_to_gripper_value("left", left[_NUM_ARM_JOINTS:]),
                *right[:_NUM_ARM_JOINTS],
                self._hand_joints_to_gripper_value("right", right[_NUM_ARM_JOINTS:]),
            ]
            return {
                name: values[idx]
                for idx, name in enumerate(DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES)
            }
        return {
            name: joint_pos[idx]
            for idx, name in enumerate(DUAL_ARM_ACTION_FEATURE_NAMES)
        }

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            for glove in (self.left_hand_teleoperator, self.right_hand_teleoperator):
                if glove is not None:
                    glove.stop()
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            if self.process is not None:
                returncode = self.process.poll()
                if returncode is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except Exception:
                        self.process.kill()
                        self.process.wait()
        self._is_connected = False
        logger.info(f"{self} safely disconnected.")
