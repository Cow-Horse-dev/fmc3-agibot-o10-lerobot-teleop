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
from lerobot_play.robots.pico_follower_dual_arm_agibot_o10.airbot_pico_follower_dual_arm_agibot_o10 import (
    DUAL_ARM_ACTION_FEATURE_NAMES,
)
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
)
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore

from .config_pico_leader_dual_arm_agibot_o10 import (
    PicoLeaderDualArmAgibotO10Config,
)

logger = logging.getLogger(__name__)

_NUM_ARM_JOINTS = len(AGIBOT_O10_ARM_FEATURE_NAMES)
_NUM_HAND_JOINTS = len(AGIBOT_O10_HAND_FEATURE_NAMES)
_SIDE_ACTION_DIM = _NUM_ARM_JOINTS + _NUM_HAND_JOINTS  # 16


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

        # Reset stores
        self.left_arm_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_ARM_FEATURE_NAMES,
            path=left_cfg.get("arm_reset_joints_path"),
            label="left arm reset joint target",
            group_key="arm",
        )
        self.left_hand_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
            path=left_cfg.get("hand_reset_joints_path"),
            label="left hand reset joint target",
            group_key="hand",
        )
        self.right_arm_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_ARM_FEATURE_NAMES,
            path=right_cfg.get("arm_reset_joints_path"),
            label="right arm reset joint target",
            group_key="arm",
        )
        self.right_hand_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
            path=right_cfg.get("hand_reset_joints_path"),
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

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, calibrate: bool = True) -> None:
        self._start_events_thread()

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
        self._is_connected = True
    # ------------------------------------------------------------------
    # Action features
    # ------------------------------------------------------------------

    @cached_property
    def action_features(self) -> dict[str, type]:
        return {name: float for name in DUAL_ARM_ACTION_FEATURE_NAMES}

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
        normalized = store.normalize(joint_pos)
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
        normalized = store.normalize(joint_pos)
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
        store = getattr(self, f"{side}_hand_reset_store")
        try:
            stored = store.load()
        except Exception as exc:
            print(f"Warning: failed to load persistent {side} hand reset target: {exc}")
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
            arm_store = getattr(self, f"{side}_arm_reset_store")
            hand_store = getattr(self, f"{side}_hand_reset_store")

            try:
                arm_loaded = arm_store.load()
            except Exception as exc:
                print(f"Warning: failed to load {side} arm reset target: {exc}")
                arm_loaded = None
            try:
                hand_loaded = hand_store.load()
            except Exception as exc:
                print(f"Warning: failed to load {side} hand reset target: {exc}")
                hand_loaded = None

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

    # ------------------------------------------------------------------
    # IK update (per-side)
    # ------------------------------------------------------------------

    def _update_arm(self, side: str, pose: np.ndarray) -> None:
        """Run IK for one arm and push result into that side's LPFs."""
        arm_kdl = getattr(self, f"{side}_arm_kdl")
        lpfs = getattr(self, f"{side}_lpfs")

        now = time.time()
        joint_pos = [lpfs[i].sample(now) for i in range(_NUM_ARM_JOINTS)]
        result = arm_kdl.inverse_kinematics(np.array(pose, dtype=float), joint_pos)

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

        target = arm_store.normalize(joint_pos)
        target_pose = arm_kdl.forward_kinematics(target[:_NUM_ARM_JOINTS])
        pose_vec = self.homogeneous_matrix_to_pose(target_pose).tolist()
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
        """Left hand enabled by RTr (right trigger), right hand by LTr."""
        if side == "right":
            return self.startflag and self.ctrl["LTr"]
        return self.startflag and self.ctrl["RTr"]

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

            # Start/stop uses same buttons as single-arm right-hand mode:
            # X to start, Y to stop+reset
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
                # Determine trigger for this side's arm
                if side == "left":
                    start_trigger = self.ctrl["RTr"]
                else:
                    start_trigger = self.ctrl["LTr"]

                enable = self.startflag and start_trigger
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
                self.homogeneous_matrix_to_pose(T).tolist(),
            )
        except Exception as e:
            print(f"{side} arm VR control error: {e}")
    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_pose(self):
        self._refresh_reset_targets_from_store()

        for side in ("left", "right"):
            arm_pos = self._get_reset_arm_joint_pos(side)
            if not any(abs(v) > 1e-9 for v in arm_pos):
                arm_pos = self._current_arm_joint_pos(side)
                arm_pos = self._set_reset_arm_joint_pos(side, arm_pos)

            self._apply_reset_arm_joint_pos(side, arm_pos)
            setattr(self, f"{side}_arm_init", False)
            setattr(self, f"{side}_trans_init", None)
            setattr(self, f"{side}_quat_init", None)
            setattr(self, f"{side}_vr_init_pose", None)
            setattr(self, f"{side}_arm_init_pose", None)
            print(f"RESET {side} arm position")

            self._set_commanded_hand_joint_pos(
                side, self._get_reset_hand_joint_pos(side),
            )
            print(f"RESET {side} hand position")

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

        if (
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
