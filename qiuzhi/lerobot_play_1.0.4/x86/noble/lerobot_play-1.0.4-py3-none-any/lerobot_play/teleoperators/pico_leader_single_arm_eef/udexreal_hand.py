import threading
import time
from typing import List
from .base_hand import BaseHandTeleoperator
from .udexreal_driver import UDEGloveSDK


class UdexrealTeleoperator(BaseHandTeleoperator):
    """宇叠手套遥操作器"""

    def __init__(self, handedness="left", control_freq=25):
        super().__init__()
        self.handedness = handedness  # left 或 right
        self.control_freq = control_freq
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self.listening_thread = None

        self.ude_glove = UDEGloveSDK()

        # 手指映射配置（从test_glove_contron_ins_hand.py移植）
        self.finger_names = [
            "Thumb1_1",
            "Thumb1_3",
            "Index1",
            "Middle1",
            "Ring1",
            "Pinky1",
        ]
        self.finger_dict = {
            "Thumb1_1": (10, -60),
            "Thumb1_3": (0, -60),
            "Index1": (0, -80),
            "Middle1": (0, -80),
            "Ring1": (0, -80),
            "Pinky1": (0, -80),
        }
        self.finger_filtering_factor = {
            "Thumb1_1": [0, 250.0, 350.0, 450.0, 550.0, 650.0, 750.0],
            "Thumb1_3": [0, 350.0, 450.0, 550.0, 650.0, 750.0, 850.0],
            "Index1": [
                0,
                200.0,
                250,
                300.0,
                350,
                400.0,
                450,
                500.0,
                550,
                600.0,
                650,
                700.0,
                750,
                800.0,
                850,
                900.0,
            ],
            "Middle1": [
                0,
                200.0,
                250,
                300.0,
                350,
                400.0,
                450,
                500.0,
                550,
                600.0,
                650,
                700.0,
                750,
                800.0,
                850,
                900.0,
            ],
            "Ring1": [
                0,
                200.0,
                250,
                300.0,
                350,
                400.0,
                450,
                500.0,
                550,
                600.0,
                650,
                700.0,
                750,
                800.0,
                850,
                900.0,
            ],
            "Pinky1": [
                0,
                250,
                300.0,
                350,
                400.0,
                450,
                500.0,
                550,
                600.0,
                650,
                700.0,
                750,
                800.0,
                850,
                900.0,
            ],
        }

    def init(self) -> bool:
        """初始化宇叠手套"""
        try:
            self.ude_glove.initialize()
            self.is_connected = True
            self.reconnect_attempts = 0
            print(f"宇叠手套初始化成功 (handedness: {self.handedness})")
            return True
        except Exception as e:
            print(f"宇叠手套初始化失败: {e}")
            self.is_connected = False
            return False

    def start_listening(self) -> None:
        """开始监听手套数据"""
        if not self.is_connected:
            raise RuntimeError("宇叠手套未连接")

        self.ude_glove.start_listening()
        self.is_running = True
        self.listening_thread = threading.Thread(
            target=self._data_listening_loop, daemon=True
        )
        self.listening_thread.start()
        print(f"宇叠手套数据监听已启动 (频率: {self.control_freq}Hz)")

    def stop(self) -> None:
        """停止监听"""
        self.is_running = False
        if self.listening_thread:
            self.listening_thread.join(timeout=1.0)

        # 清理宇叠手套资源
        try:
            self.ude_glove.end_listening()
            print("停止宇叠手套")
        except Exception as e:
            print(f"停止宇叠手套监听时出错: {e}")

        print("宇叠手套已停止")

    def _data_listening_loop(self):
        """数据监听循环 - 子线程运行，不使用ROS2"""
        while self.is_running:
            try:
                # 直接从宇叠手套SDK获取数据
                role_list = self.ude_glove.get_role_name_list()
                if len(role_list) > 0:
                    for role_name in role_list:
                        finger_data = self.ude_glove.get_vec_finger_data(role_name)

                    # 数据处理和映射
                    processed_data = self._process_finger_data(finger_data)
                    self.update_hand_data(processed_data)

            except Exception as e:
                print(f"宇叠手套数据读取错误: {e}")
                self._handle_connection_error()

            time.sleep(1.0 / self.control_freq)

    def _process_finger_data(self, finger_data) -> List[float]:
        """处理手指数据，进行角度映射和滤波

        Args:
            finger_data: 原始手指数据

        Returns:
            List[float]: 处理后的6个关节数据
        """
        angle = [0] * 6
        map_angle = [0] * 6

        if self.handedness == "left":

            angle[0] = finger_data[2].x  # 大拇指向垂直于手掌方向移动
            angle[1] = finger_data[0].x  # 大拇指指向平行于手掌方向移动
            angle[2] = finger_data[3].x
            angle[3] = finger_data[6].x
            angle[4] = finger_data[9].x
            angle[5] = finger_data[12].x

        else:
            angle[0] = finger_data[17].x  # 大拇指向垂直于手掌方向移动
            angle[1] = finger_data[15].x  # 大拇指指向平行于手掌方向移动
            angle[2] = finger_data[18].x
            angle[3] = finger_data[21].x
            angle[4] = finger_data[24].x
            angle[5] = finger_data[27].x

        # 映射和滤波
        for i, ang in enumerate(angle):
            finger_name = self.finger_names[i]
            command = self._map_angle_to_value(finger_name, ang)
            map_angle[i] = self._filtering(finger_name, command)

        # print("map_angle", map_angle)

        return map_angle

    def _map_angle_to_value(self, finger_name: str, current_angle: float) -> int:
        """角度映射函数

        Args:
            finger_name: 手指名称
            current_angle: 当前角度

        Returns:
            int: 映射后的值
        """
        min_angle, max_angle = self.finger_dict[finger_name]
        mapped_value = int(
            ((current_angle - min_angle) / (max_angle - min_angle)) * 1000
        )
        return max(0, min(1000, mapped_value))

    def _filtering(self, finger_name: str, command: int) -> float:
        """滤波函数

        Args:
            finger_name: 手指名称
            command: 输入命令值

        Returns:
            float: 滤波后的值
        """
        max_val = 1000
        factors = self.finger_filtering_factor[finger_name]

        for j in range(len(factors) - 1):
            lower_bound = factors[j]
            upper_bound = factors[j + 1]
            if lower_bound <= command < upper_bound:
                return lower_bound

        return max_val

    def _handle_connection_error(self):
        """处理连接错误，尝试重连"""
        self.reconnect_attempts += 1
        if self.reconnect_attempts <= self.max_reconnect_attempts:
            print(f"尝试重连宇叠手套 ({self.reconnect_attempts}/{self.max_reconnect_attempts})")
            try:
                self.ude_glove.initialize()
                self.is_connected = True
                self.reconnect_attempts = 0
                print("宇叠手套重连成功")
            except Exception as e:
                print(f"重连失败: {e}")
                if self.reconnect_attempts >= self.max_reconnect_attempts:
                    print("宇叠手套重连失败，达到最大重试次数")
                    self.is_connected = False
        else:
            print("宇叠手套连接丢失，达到最大重试次数")
            self.is_connected = False

    def get_device_info(self) -> dict:
        """获取设备信息"""
        info = super().get_device_info()
        info.update(
            {
                "handedness": self.handedness,
                "control_freq": self.control_freq,
                "reconnect_attempts": self.reconnect_attempts,
                "max_reconnect_attempts": self.max_reconnect_attempts,
            }
        )
        return info
