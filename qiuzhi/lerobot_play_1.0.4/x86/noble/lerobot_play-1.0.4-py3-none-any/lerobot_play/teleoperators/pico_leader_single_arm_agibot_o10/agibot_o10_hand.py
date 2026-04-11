import threading
import time
from typing import List

from lerobot_play.teleoperators.pico_leader_single_arm_eef.udexreal_driver import (
    ServerStatus,
    UDEGloveSDK,
)
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_HAND_FEATURE_NAMES,
    glove_vec_to_agibot_o10_joint_angles,
    normalize_handedness,
)


class AgibotO10GloveTeleoperator:
    def __init__(self, handedness: str = "right", control_freq: int = 25):
        self.handedness = normalize_handedness(handedness)
        self.control_freq = control_freq
        self.ude_glove = UDEGloveSDK()
        self.listening_thread = None
        self.data_lock = threading.Lock()
        self.hand_data = [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)
        self.is_connected = False
        self.is_running = False
        self.last_update_time = 0.0
        self.max_data_age_s = 0.5
        self._last_role_warning_t = 0.0

    def init(self) -> bool:
        self.ude_glove.initialize()
        self.is_connected = self.ude_glove.cur_status == ServerStatus.READY
        return self.is_connected

    def start_listening(self) -> None:
        if not self.is_connected:
            raise RuntimeError("宇叠手套未连接")

        self.ude_glove.start_listening()
        self.is_running = True
        self.listening_thread = threading.Thread(
            target=self._data_listening_loop,
            daemon=True,
        )
        self.listening_thread.start()

    def stop(self) -> None:
        self.is_running = False
        if self.listening_thread:
            self.listening_thread.join(timeout=1.0)
        self.ude_glove.end_listening()

    def get_hand_data(self) -> List[float]:
        with self.data_lock:
            return self.hand_data.copy()

    def has_hand_data(self, max_age_s: float | None = None) -> bool:
        with self.data_lock:
            if self.last_update_time <= 0.0:
                return False
            if max_age_s is None:
                return True
            return (time.time() - self.last_update_time) <= max_age_s

    def wait_until_ready(self, timeout_s: float = 2.0) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.has_hand_data():
                return True
            time.sleep(0.02)
        return self.has_hand_data()

    def wait_for_hand_data(self, timeout_s: float = 2.0) -> List[float]:
        if self.wait_until_ready(timeout_s=timeout_s):
            return self.get_hand_data()
        return self.get_hand_data()

    def update_hand_data(self, new_data: List[float]) -> None:
        if len(new_data) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
            raise ValueError(
                f"手部数据长度必须为{len(AGIBOT_O10_HAND_FEATURE_NAMES)}，实际为{len(new_data)}"
            )

        with self.data_lock:
            self.hand_data = new_data.copy()
            self.last_update_time = time.time()

    def _infer_role_handedness(self, role_name: str) -> str | None:
        normalized_role = role_name.strip().upper()
        if not normalized_role:
            return None
        if normalized_role.endswith("LEFT") or normalized_role.endswith("_LEFT"):
            return "left"
        if normalized_role.endswith("RIGHT") or normalized_role.endswith("_RIGHT"):
            return "right"
        if normalized_role.endswith("L"):
            return "left"
        if normalized_role.endswith("R"):
            return "right"
        return None

    def _select_role_name(self, role_list: List[str]) -> str | None:
        if not role_list:
            return None

        unclassified_roles: list[str] = []
        for role_name in role_list:
            inferred_handedness = self._infer_role_handedness(role_name)
            if inferred_handedness == self.handedness:
                return role_name
            if inferred_handedness is None:
                unclassified_roles.append(role_name)

        if len(role_list) == 1 and unclassified_roles:
            return unclassified_roles[0]

        return None

    def _data_listening_loop(self) -> None:
        while self.is_running:
            try:
                role_list = self.ude_glove.get_role_name_list()
                if role_list:
                    role_name = self._select_role_name(role_list)
                    if role_name is not None:
                        finger_data = self.ude_glove.get_vec_finger_data(role_name)
                        self.update_hand_data(
                            glove_vec_to_agibot_o10_joint_angles(
                                finger_data,
                                self.handedness,
                            )
                        )
                    elif time.time() - self._last_role_warning_t > 2.0:
                        self._last_role_warning_t = time.time()
                        print(
                            "Warning: no Agibot O10 glove role matched "
                            f"handedness={self.handedness}. Available roles: {role_list}"
                        )
            except Exception as exc:
                print(f"宇叠手套 O10 数据读取错误: {exc}")
            time.sleep(1.0 / self.control_freq)
