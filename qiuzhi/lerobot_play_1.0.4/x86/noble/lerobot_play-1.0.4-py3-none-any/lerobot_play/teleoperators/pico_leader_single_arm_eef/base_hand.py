"""
手部遥操作设备抽象基类

定义手部遥操作设备的统一接口。
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import threading
import time


class BaseHandTeleoperator(ABC):
    """手部遥操作设备抽象基类"""

    def __init__(self):
        self.hand_data = [0] * 6  # 6个关节的数据
        self.data_lock = threading.Lock()
        self.is_connected = False
        self.is_running = False
        self.last_update_time = 0.0

    @abstractmethod
    def init(self) -> bool:
        """初始化手部遥操作设备

        Returns:
            bool: 初始化是否成功
        """
        pass

    @abstractmethod
    def start_listening(self) -> None:
        """开始监听手部数据"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """停止监听并清理资源"""
        pass

    def get_hand_data(self) -> List[float]:
        """获取当前手部数据（线程安全）

        Returns:
            List[float]: 6个关节的角度数据
        """
        with self.data_lock:
            return self.hand_data.copy()

    def is_device_connected(self) -> bool:
        """检查设备是否连接

        Returns:
            bool: 设备连接状态
        """
        return self.is_connected

    def is_data_fresh(self, timeout: float = 1.0) -> bool:
        """检查数据是否新鲜（在超时时间内更新过）

        Args:
            timeout: 超时时间（秒）

        Returns:
            bool: 数据是否新鲜
        """
        current_time = time.time()
        return (current_time - self.last_update_time) < timeout

    def update_hand_data(self, new_data: List[float]) -> None:
        """更新手部数据（线程安全）

        Args:
            new_data: 新的手部数据
        """
        if len(new_data) != 6:
            raise ValueError(f"手部数据长度必须为6，实际为{len(new_data)}")

        with self.data_lock:
            self.hand_data = new_data.copy()
            self.last_update_time = time.time()

    def get_device_info(self) -> dict:
        """获取设备信息

        Returns:
            dict: 设备信息字典
        """
        return {
            "device_type": self.__class__.__name__,
            "is_connected": self.is_connected,
            "is_running": self.is_running,
            "last_update_time": self.last_update_time,
            "data_fresh": self.is_data_fresh(),
        }
