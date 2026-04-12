import time
import threading

from lerobot_play.teleoperators.pico_leader_single_arm_eef.pico_leader_single_arm_eef import (
    PicoLeaderSingleArmEEF,
)
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    agibot_o10_joint_action_feature_types,
    build_agibot_o10_joint_action_dict,
)
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore
from lerobot_play.utils.o10_hand_grasp_presets import (
    HAND_CONTROL_MODE_GRASP_PRESET,
    apply_hand_grasp_preset,
    normalize_hand_control_mode,
    normalize_hand_grasp_preset,
)

from .agibot_o10_hand import AgibotO10GloveTeleoperator
from .config_pico_leader_single_arm_agibot_o10 import (
    PicoLeaderSingleArmAgibotO10Config,
)


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
        self.hand_reset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
            path=config.hand_reset_joints_path,
            label=f"{config.handedness} hand reset joint target",
        )
        self.hand_grasp_preset_store = PersistentJointTargetStore(
            feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
            path=config.hand_grasp_preset_joints_path,
            label=f"{config.handedness} hand grasp preset joint target",
        )
        self.reset_hand_joint_pos = [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)
        self.grasp_preset_joint_pos = self.reset_hand_joint_pos.copy()
        self.commanded_hand_joint_pos = self.reset_hand_joint_pos.copy()
        self.hand_control_mode = normalize_hand_control_mode(config.hand_control_mode)
        self.hand_grasp_preset = normalize_hand_grasp_preset(config.hand_grasp_preset)

    def connect(self, calibrate: bool = True) -> None:
        self._start_events_thread()
        if self.hand_teleoperator is not None:
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
            self._initialize_hand_grasp_preset_target()
            if self.hand_control_mode == HAND_CONTROL_MODE_GRASP_PRESET:
                print(
                    "Agibot O10 hand grasp preset enabled: "
                    f"{self.hand_grasp_preset}. "
                    "Inactive fingers will stay at the grasp preset hand pose."
                )
        else:
            print("Agibot O10 hand teleoperation disabled. Running in arm-only mode.")
        self._is_connected = True

    @property
    def action_features(self):
        return agibot_o10_joint_action_feature_types()

    def _set_commanded_hand_joint_pos(self, joint_pos: list[float]) -> None:
        with self.hand_state_lock:
            self.commanded_hand_joint_pos = joint_pos.copy()

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
        normalized_joint_pos = (
            self.hand_reset_store.save(joint_pos)
            if persist
            else self.hand_reset_store.normalize(joint_pos)
        )
        with self.hand_state_lock:
            self.reset_hand_joint_pos = normalized_joint_pos.copy()
            if sync_commanded:
                self.commanded_hand_joint_pos = normalized_joint_pos.copy()
        return normalized_joint_pos

    def _get_reset_hand_joint_pos(self) -> list[float]:
        with self.hand_state_lock:
            return self.reset_hand_joint_pos.copy()

    def _set_grasp_preset_joint_pos(
        self,
        joint_pos: list[float],
        *,
        persist: bool,
    ) -> list[float]:
        normalized_joint_pos = (
            self.hand_grasp_preset_store.save(joint_pos)
            if persist
            else self.hand_grasp_preset_store.normalize(joint_pos)
        )
        with self.hand_state_lock:
            self.grasp_preset_joint_pos = normalized_joint_pos.copy()
        return normalized_joint_pos

    def _get_grasp_preset_joint_pos(self) -> list[float]:
        with self.hand_state_lock:
            return self.grasp_preset_joint_pos.copy()

    def _log_hand_joint_pos(self, title: str, joint_pos: list[float]) -> None:
        print(title)
        for feature_name, joint_value in zip(
            AGIBOT_O10_HAND_FEATURE_NAMES, joint_pos, strict=True
        ):
            print(f"  {feature_name}: {joint_value:.4f}")

    def _initialize_hand_reset_target(self) -> None:
        if self.hand_teleoperator is None:
            return

        try:
            stored_joint_pos = self.hand_reset_store.load()
        except Exception as exc:
            print(f"Warning: failed to load persistent Agibot O10 hand reset target: {exc}")
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

    def _initialize_hand_grasp_preset_target(self) -> None:
        try:
            stored_joint_pos = self.hand_grasp_preset_store.load()
        except Exception as exc:
            print(f"Warning: failed to load Agibot O10 hand grasp preset target: {exc}")
            stored_joint_pos = None

        if stored_joint_pos is None:
            stored_joint_pos = self._get_reset_hand_joint_pos()
            if self.hand_grasp_preset_store.has_path:
                print(
                    "Warning: Agibot O10 hand grasp preset target file is missing. "
                    "Falling back to the full-hand reset pose for the grasp preset base pose."
                )
        stored_joint_pos = self._set_grasp_preset_joint_pos(
            stored_joint_pos,
            persist=False,
        )
        self._log_hand_joint_pos(
            "Loaded Agibot O10 hand grasp preset target:",
            stored_joint_pos,
        )

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
        if self.handedness == "right":
            return self.startflag and self.ctrl["LTr"]
        return self.startflag and self.ctrl["RTr"]

    def reset_pose(self):
        super().reset_pose()
        self._set_commanded_hand_joint_pos(self._get_reset_hand_joint_pos())
        print("RESET Hand position")

    def _apply_hand_control_mode(self, requested_joint_pos: list[float]) -> list[float]:
        if self.hand_control_mode != HAND_CONTROL_MODE_GRASP_PRESET:
            return requested_joint_pos

        return apply_hand_grasp_preset(
            requested_joint_pos=requested_joint_pos,
            preset_joint_pos=self._get_grasp_preset_joint_pos(),
            preset=self.hand_grasp_preset,
        )

    def get_joint_pos(self):
        state = [0.0] * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES))
        now = time.time()
        for index in range(len(AGIBOT_O10_ARM_FEATURE_NAMES)):
            state[index] = self.lpfs[index].sample(now)

        if (
            self.hand_teleoperator is not None
            and self._is_hand_control_enabled()
            and self.hand_teleoperator.has_hand_data(
                max_age_s=self.hand_teleoperator.max_data_age_s
            )
        ):
            hand_ctrl_data = self.hand_teleoperator.get_hand_data()
            hand_ctrl_data = self._apply_hand_control_mode(hand_ctrl_data)
            self._set_commanded_hand_joint_pos(hand_ctrl_data)
        else:
            hand_ctrl_data = self._get_commanded_hand_joint_pos()

        for index, joint_value in enumerate(hand_ctrl_data):
            state[len(AGIBOT_O10_ARM_FEATURE_NAMES) + index] = joint_value

        return state

    def get_action(self):
        return build_agibot_o10_joint_action_dict(self.get_joint_pos())
