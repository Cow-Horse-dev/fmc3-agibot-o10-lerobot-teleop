import sys
import os
import socket
import subprocess
from pathlib import Path
import psutil

# project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# sys.path.insert(0, project_root)

import logging
import time
import math
import typing
import threading
from typing import Any, List
import numpy as np
from time import time_ns
import asyncio
import zmq
import pkg_resources
from scipy.spatial.transform import Rotation

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
import airbot_hardware_py as ah
from lerobot_play._compat import Teleoperator
from airbot_state_machine import robotic_arm
from lerobot_play.teleoperators.pico_leader_single_arm_eef.config_pico_leader_single_arm_eef import (
    PicoLeaderSingleArmEEFConfig,
)
from lerobot_play.teleoperators.pico_leader_single_arm_eef import pico_webrtc
from .lpf import OnlineVariableStepLPF
from mmk2_kdl_py import ArmKdlNumerical
from .udexreal_hand import UdexrealTeleoperator

logger = logging.getLogger(__name__)


class PicoLeaderSingleArmEEF(Teleoperator):
    config_class = PicoLeaderSingleArmEEFConfig
    name = "pico_leader_single_arm_eef"

    def __init__(self, config: PicoLeaderSingleArmEEFConfig):
        super().__init__(config)
        self.config = config
        self.running = True
        self.ctrl = {
            "A": False,
            "B": False,
            "RThU": False,  # 右手柄主触摸板触摸
            "RJ": False,  # 右手柄主触摸板按压
            "RG": False,  # 右手柄抓握键
            "RTr": False,  # 右手柄扳机键
            "X": False,
            "Y": False,
            "LThU": False,  # 左手柄主触摸板触摸
            "LJ": False,  # 左手柄主触摸板按压
            "LG": False,  # 左手柄抓握键
            "LTr": False,  # 左手柄扳机键
            "leftJS": {
                "ud": 0.0,
                "lr": 0.0,
            },  # 左手柄主触摸板推压程度 ud为上下，lr为左右，ud推压至下极限为-1，推压至上极限为1; lr推压至左极限为-1，推压至右极限为1
            "leftTrig": 0.0,  # 左手柄扳机键按压程度
            "leftGrip": 0.0,  # 左手柄抓握键按压程度
            "rightJS": {
                "ud": 0.0,
                "lr": 0.0,
            },  # 右手柄主触摸板 ud为上下，lr为左右，ud推压至下极限为-1，推压至上极限为1; lr推压至左极限为-1，推压至右极限为1
            "rightTrig": 0.0,  # 右手柄扳机键按压程度
            "rightGrip": 0.0,  # 右手柄抓握键按压程度
        }
        self.pose = None
        self.temp_pose = [0.0] * 6
        self.solve_fail = False
        self.allow_flip = False
        self.process = None
        self.history = [0.0] * 7
        if self.config.eef_device == "G2":
            self.transform_pose = [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]
        else:
            self.transform_pose = [0.12610013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]

        self.handedness = config.handedness
        self.wrist_pose_source = getattr(config, "wrist_pose_source", "auto").lower()
        self.head_info = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        self.left_info = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        self.right_info = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        self.active_pose_source = None
        self.startflag = False
        self.last_button_debug_state = None

        self.pause_event = threading.Event()
        self.stop_event = threading.Event()

        self.zmq_context = zmq.Context()
        # 订阅姿态数据
        self.pose_socket = self.zmq_context.socket(zmq.SUB)
        self.pose_socket.setsockopt(zmq.CONFLATE, 1)
        self.pose_socket.connect(f"tcp://localhost:{config.vr_pose_port}")
        self.pose_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        # 订阅控制器数据
        self.control_socket = self.zmq_context.socket(zmq.SUB)
        self.control_socket.setsockopt(zmq.CONFLATE, 1)
        self.control_socket.connect(f"tcp://localhost:{config.vr_ctrl_port}")
        self.control_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        if config.eef_device == "G2":
            self.arm_kdl = ArmKdlNumerical(eef_type="G2")
        else:
            self.arm_kdl = ArmKdlNumerical(eef_type="none")
            self.hand_teleoperator = UdexrealTeleoperator(handedness=config.handedness)

        self.lpfs = [
            OnlineVariableStepLPF(fc=100, kp=10, kd=0.2, v_max=5000, a_max=100)
            for _ in range(6)
        ]

        self.worker_script = pico_webrtc.__file__
        self.start_WebRTC()
        thread_process = threading.Thread(target=self.wait)
        thread_process.daemon = True  # 设置为守护线程，主程序结束时会自动停止
        thread_process.start()

        self.cameras = make_cameras_from_configs(config.cameras)
        self._is_connected = False
        self.arm_init = False

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def start_WebRTC(self):
        """启动WebRTC服务器进程"""
        try:
            print(f"=== 开始启动 WebRTC 进程 ===")
            print(f"worker_script: {self.worker_script}")

            pose_port_busy = self._is_tcp_port_open(self.config.vr_pose_port)
            ctrl_port_busy = self._is_tcp_port_open(self.config.vr_ctrl_port)
            if pose_port_busy and ctrl_port_busy:
                if self._has_live_webrtc_stream():
                    print(
                        "检测到已有健康的 WebRTC/ZMQ 发布进程，"
                        f"直接复用端口 {self.config.vr_pose_port}/{self.config.vr_ctrl_port}"
                    )
                    self.process = None
                    return True

                print(
                    "检测到已有 WebRTC/ZMQ 进程占用端口，但没有收到实时 pose/control 数据，"
                    "准备清理旧进程后重新启动。"
                )
                self._stop_existing_webrtc_publishers()
                pose_port_busy = self._is_tcp_port_open(self.config.vr_pose_port)
                ctrl_port_busy = self._is_tcp_port_open(self.config.vr_ctrl_port)

            if pose_port_busy or ctrl_port_busy:
                print(
                    "警告: Pico WebRTC 端口被部分占用，"
                    f"请先清理 {self.config.vr_pose_port}/{self.config.vr_ctrl_port} 上的旧进程"
                )
                self.process = None
                return False

            # 检查文件是否存在
            if not os.path.exists(self.worker_script):
                print(f"错误: 文件不存在: {self.worker_script}")
                self.process = None
                return False

            # 构建命令行参数
            args = [
                sys.executable,
                self.worker_script,
                "--arm_device",
                self.config.vr_device,
            ]

            package_root = Path(__file__).resolve().parents[3]
            env = os.environ.copy()
            existing_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                f"{package_root}:{existing_pythonpath}"
                if existing_pythonpath
                else str(package_root)
            )

            print(f"启动WebRTC进程命令: {' '.join(args)}")

            # 确保正确设置 self.process
            self.process = subprocess.Popen(args, cwd=str(package_root), env=env)
            print(f"WebRTC进程已启动 PID: {self.process.pid}")
            print(f"self.process 对象: {self.process}")

            # 等待进程启动
            time.sleep(2)

            # 检查进程是否还在运行
            returncode = self.process.poll()
            print(f"进程返回码: {returncode}")

            if returncode is not None:
                print("警告: WebRTC进程启动后立即退出")
                return False

            print("WebRTC进程启动成功")
            return True

        except Exception as e:
            print(f"启动WebRTC进程失败: {e}")
            print(f"异常类型: {type(e).__name__}")
            import traceback

            traceback.print_exc()
            self.process = None  # 确保设置为 None
            return False

    @staticmethod
    def _is_tcp_port_open(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    def _get_listener_processes_for_ports(self) -> list[psutil.Process]:
        listener_pids = set()
        target_ports = {self.config.vr_pose_port, self.config.vr_ctrl_port}

        for connection in psutil.net_connections(kind="tcp"):
            if connection.status != psutil.CONN_LISTEN:
                continue
            if not connection.laddr or connection.laddr.port not in target_ports:
                continue
            if connection.pid in (None, os.getpid()):
                continue
            listener_pids.add(connection.pid)

        processes = []
        for pid in sorted(listener_pids):
            try:
                processes.append(psutil.Process(pid))
            except psutil.Error:
                continue
        return processes

    def _stop_existing_webrtc_publishers(self):
        for process in self._get_listener_processes_for_ports():
            try:
                cmdline = " ".join(process.cmdline())
            except psutil.Error:
                cmdline = "<unknown>"

            print(f"停止旧 WebRTC/ZMQ 进程 PID={process.pid}: {cmdline}")
            try:
                process.terminate()
                process.wait(timeout=3)
            except psutil.TimeoutExpired:
                print(f"PID={process.pid} 未在 3 秒内退出，改为强制杀掉")
                process.kill()
                try:
                    process.wait(timeout=3)
                except psutil.Error:
                    pass
            except psutil.Error as exc:
                print(f"停止 PID={process.pid} 失败: {exc}")

    def _receive_zmq_message_once(self, port: int, timeout_s: float) -> dict[str, Any] | None:
        temp_context = zmq.Context()
        temp_socket = temp_context.socket(zmq.SUB)
        temp_socket.setsockopt(zmq.CONFLATE, 1)
        temp_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        temp_socket.setsockopt(zmq.RCVTIMEO, max(1, int(timeout_s * 1000)))
        temp_socket.connect(f"tcp://127.0.0.1:{port}")
        time.sleep(0.1)

        try:
            return temp_socket.recv_json()
        except zmq.Again:
            return None
        finally:
            temp_socket.close(linger=0)
            temp_context.term()

    def _has_live_webrtc_stream(self, timeout_s: float = 1.5) -> bool:
        pose_message = self._receive_zmq_message_once(self.config.vr_pose_port, timeout_s)
        control_message = self._receive_zmq_message_once(self.config.vr_ctrl_port, timeout_s)

        pose_ok = isinstance(pose_message, dict) and "tracking_state" in pose_message
        control_ok = isinstance(control_message, dict) and "buttons" in control_message

        if not pose_ok:
            print(f"端口 {self.config.vr_pose_port} 未收到有效 pose 数据")
        if not control_ok:
            print(f"端口 {self.config.vr_ctrl_port} 未收到有效 control 数据")

        return pose_ok and control_ok

    def stop_WebRTC(self, signum=None, frame=None):
        print(f"=== 收到信号 {signum}，调用 stop_WebRTC ===")
        print(f"self 对象ID: {id(self)}")
        print(f"当前 self.process: {self.process}")
        print(f"self.process 类型: {type(self.process)}")
        print(f"hasattr(self, 'process'): {hasattr(self, 'process')}")

        # 检查所有属性
        print("所有包含 'process' 的属性:")
        for attr_name in dir(self):
            if "process" in attr_name.lower():
                attr_value = getattr(self, attr_name)
                print(f"  {attr_name}: {attr_value} (类型: {type(attr_value)})")

        self.running = False

        if self.process is not None:
            print(f"进程 PID: {self.process.pid}")
            returncode = self.process.poll()
            print(f"进程返回码: {returncode}")

            if returncode is None:
                print("进程仍在运行，正在终止...")
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                    print("WebRTC进程已停止")
                except subprocess.TimeoutExpired:
                    print("进程未响应，强制杀死...")
                    self.process.kill()
                    self.process.wait()
                    print("WebRTC进程已被强制杀死")
            else:
                print(f"进程已退出，返回码: {returncode}")
        else:
            print("self.process 为 None")
            # 检查是否在其他地方被修改
            print("检查可能的问题...")

    def wait(self):
        try:
            while True:
                self.receive_zmq_data()
                # print(self.right_info.data)
                time.sleep(0.01)
        except KeyboardInterrupt:
            """关闭ZMQ连接"""
            print("开始关闭进程")
            self.pose_socket.close()
            self.control_socket.close()
            self.zmq_context.term()
            self.stop_WebRTC()

    def receive_zmq_data(self):
        """接收并处理ZMQ数据"""
        # 非阻塞接收姿态数据
        try:
            pose_msg = self.pose_socket.recv_json(zmq.NOBLOCK)
            self._update_pose_data(pose_msg)
        except zmq.Again:
            pass

        # 非阻塞接收控制器数据
        try:
            control_msg = self.control_socket.recv_json(zmq.NOBLOCK)
            # print(control_msg)
            self._update_control_data(control_msg)
        except zmq.Again:
            pass

    def _update_pose_data(self, pose_msg):
        """更新姿态数据"""
        try:
            # 更新头部姿态
            if "head_pose" in pose_msg:
                head_data = pose_msg["head_pose"]
                if len(head_data) == 7:
                    self.head_info = head_data.copy()

            # 更新左手姿态
            if "left_pose" in pose_msg:
                left_data = pose_msg["left_pose"]
                if len(left_data) == 7:
                    self.left_info = left_data.copy()

            # 更新右手姿态
            if "right_pose" in pose_msg:
                right_data = pose_msg["right_pose"]
                if len(right_data) == 7:
                    self.right_info = right_data.copy()

            # 更新追踪状态
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
            self.pose, pose_source = self._select_control_pose()
            if pose_source != self.active_pose_source:
                print(f"当前使用 {pose_source} wrist pose 作为控臂输入")
                self.active_pose_source = pose_source
        except Exception as e:
            print(f"Error updating pose data: {e}")

    def _is_default_pose(self, pose) -> bool:
        if pose is None or len(pose) != 7:
            return True

        pos = np.array(pose[:3], dtype=float)
        quat = np.array(pose[3:7], dtype=float)
        if np.isnan(pos).any() or np.isnan(quat).any():
            return True

        if not np.allclose(pos, 0.0, atol=1e-6):
            return False

        default_quaternions = (
            np.array([0.0, 0.0, 0.0, 1.0], dtype=float),
            np.array(
                [0.7071067690849304, 4.329780301713277e-17, 0.7071067690849304, 4.329780301713277e-17],
                dtype=float,
            ),
        )
        return any(np.allclose(quat, default_quat, atol=1e-4) for default_quat in default_quaternions)

    def _select_control_pose(self) -> tuple[list[float], str]:
        requested_source = self.wrist_pose_source
        if requested_source not in {"auto", "left", "right"}:
            requested_source = "auto"

        if requested_source in {"left", "right"}:
            pose = self.left_info if requested_source == "left" else self.right_info
            return pose, requested_source

        if self.config.vr_device == "pico_wrist":
            if self.handedness == "right":
                candidates = (("right", self.right_info), ("left", self.left_info))
            else:
                candidates = (("left", self.left_info), ("right", self.right_info))
        else:
            if self.handedness == "right":
                candidates = (("right", self.right_info), ("left", self.left_info))
            else:
                candidates = (("left", self.left_info), ("right", self.right_info))

        for source_name, pose in candidates:
            if not self._is_default_pose(pose):
                return pose, source_name

        return candidates[0][1], candidates[0][0]

    def _update_control_data(self, control_msg):
        """更新控制器数据到原始格式"""
        if "buttons" in control_msg:
            buttons = control_msg["buttons"]
            self.ctrl["A"] = buttons.get("A", False)
            self.ctrl["B"] = buttons.get("B", False)
            self.ctrl["X"] = buttons.get("X", False)
            self.ctrl["Y"] = buttons.get("Y", False)
            self.ctrl["RThU"] = buttons.get("RThU", False)
            self.ctrl["RJ"] = buttons.get("RJ", False)
            self.ctrl["RG"] = buttons.get("RG", False)
            self.ctrl["RTr"] = buttons.get("RTr", False)
            self.ctrl["LThU"] = buttons.get("LThU", False)
            self.ctrl["LJ"] = buttons.get("LJ", False)
            self.ctrl["LG"] = buttons.get("LG", False)
            self.ctrl["LTr"] = buttons.get("LTr", False)

        if "triggers" in control_msg:
            triggers = control_msg["triggers"]
            self.ctrl["leftTrig"] = triggers.get("left", 0.0)
            self.ctrl["rightTrig"] = triggers.get("right", 0.0)

        if "grips" in control_msg:
            grips = control_msg["grips"]
            self.ctrl["leftGrip"] = grips.get("left", 0.0)
            self.ctrl["rightGrip"] = grips.get("right", 0.0)

        if "joysticks" in control_msg:
            joysticks = control_msg["joysticks"]
            if "left" in joysticks:
                self.ctrl["leftJS"]["ud"] = joysticks["left"].get("ud", 0.0)
                self.ctrl["leftJS"]["lr"] = joysticks["left"].get("lr", 0.0)
            if "right" in joysticks:
                self.ctrl["rightJS"]["ud"] = joysticks["right"].get("ud", 0.0)
                self.ctrl["rightJS"]["lr"] = joysticks["right"].get("lr", 0.0)

        button_debug_state = (
            self.ctrl["X"],
            self.ctrl["Y"],
            self.ctrl["LTr"],
            self.ctrl["A"],
            self.ctrl["B"],
            self.ctrl["RTr"],
        )
        if button_debug_state != self.last_button_debug_state:
            print(
                "control buttons: "
                f"X={int(self.ctrl['X'])} "
                f"Y={int(self.ctrl['Y'])} "
                f"LTr={int(self.ctrl['LTr'])} "
                f"A={int(self.ctrl['A'])} "
                f"B={int(self.ctrl['B'])} "
                f"RTr={int(self.ctrl['RTr'])}"
            )
            self.last_button_debug_state = button_debug_state

    def update_arm(self, pose: np.ndarray):
        joint_pos = [0.0] * 6
        target_pose_mat = np.array(pose, dtype=float)
        if target_pose_mat.shape != (4, 4):
            raise ValueError("pose must be a 4x4 homogeneous transform matrix")

        now = time.time()
        for i in range(6):
            joint_pos[i] = self.lpfs[i].sample(now)

        result = self.arm_kdl.inverse_kinematics(target_pose_mat, joint_pos)

        if len(result) == 0:
            self.solve_fail = True
            print(f"Inverse kinematics failed. Given pose: {[target_pose_mat]}")
            return
        # elif np.abs(self.history[0][3] - result_left[0][3]) > math.pi * 2 / 3 or np.abs(self.history[1][3] - result_right[0][5]) > math.pi * 2 / 3:
        #     print(
        #         f"wrist flip joint_pos"
        #     )
        #     print(f"wrist flip result")
        #     if not self.allow_flip:
        #         self.solve_fail = True
        #         return
        # else:
        #     self.solve_fail = False
        pos = result[0]

        now = time.time()
        for i in range(6):
            self.lpfs[i].update(now, pos[i])
        self.history = pos

    def homogeneous_matrix_to_pose(self, matrix):
        """
        将4x4齐次变换矩阵转换为位姿表示 [x, y, z, qx, qy, qz, qw]

        参数:
            matrix: 4x4齐次变换矩阵

        返回:
            list: [x, y, z, qx, qy, qz, qw] 位置和四元数姿态

        注意:
            使用右手坐标系，旋转顺序为：绕X轴旋转(Roll)，绕Y轴旋转(Pitch)，绕Z轴旋转(Yaw)
        """
        # 输入检查
        matrix = np.array(matrix)
        if matrix.shape != (4, 4):
            raise ValueError("输入必须是4x4矩阵")

        # 提取位置（平移部分）
        position = matrix[:3, 3].flatten()

        # 提取旋转矩阵
        rotation_matrix = matrix[:3, :3]

        # 将旋转矩阵转换为四元数
        def rotation_matrix_to_quaternion(R):
            """
            将3x3旋转矩阵转换为四元数 [qx, qy, qz, qw]

            使用Shepperd算法，这是数值最稳定的方法之一
            """
            # 确保矩阵是正交的
            if not np.allclose(np.dot(R, R.T), np.eye(3), atol=1e-8):
                raise ValueError("旋转矩阵不满足正交条件")

            # 计算四元数元素
            q = np.zeros(4)

            # 计算迹
            trace = np.trace(R)

            if trace > 0:
                S = np.sqrt(trace + 1.0) * 2  # S=4*qw
                q[3] = 0.25 * S
                q[0] = (R[2, 1] - R[1, 2]) / S
                q[1] = (R[0, 2] - R[2, 0]) / S
                q[2] = (R[1, 0] - R[0, 1]) / S
            elif (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
                S = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2  # S=4*qx
                q[3] = (R[2, 1] - R[1, 2]) / S
                q[0] = 0.25 * S
                q[1] = (R[0, 1] + R[1, 0]) / S
                q[2] = (R[0, 2] + R[2, 0]) / S
            elif R[1, 1] > R[2, 2]:
                S = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2  # S=4*qy
                q[3] = (R[0, 2] - R[2, 0]) / S
                q[0] = (R[0, 1] + R[1, 0]) / S
                q[1] = 0.25 * S
                q[2] = (R[1, 2] + R[2, 1]) / S
            else:
                S = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2  # S=4*qz
                q[3] = (R[1, 0] - R[0, 1]) / S
                q[0] = (R[0, 2] + R[2, 0]) / S
                q[1] = (R[1, 2] + R[2, 1]) / S
                q[2] = 0.25 * S

            # 确保四元数是单位四元数
            q = q / np.linalg.norm(q)
            return q

        # 转换为四元数
        quaternion = rotation_matrix_to_quaternion(rotation_matrix)

        # 返回 [x, y, z, qx, qy, qz, qw]
        return np.concatenate([position, quaternion])

    def get_end_pose(self):
        joints = [0.0] * 6
        end_pose_mat = self.arm_kdl.forward_kinematics(joints)
        position = end_pose_mat[:3, 3]
        rot_matrix = end_pose_mat[:3, :3]
        quat = Rotation.from_matrix(rot_matrix).as_quat()
        return [position, quat]

    def handle_pose_data(self):
        while not self.stop_event.is_set():
            self.pause_event.wait()
            if self.stop_event.is_set():
                break
            if self.is_connected:
                if self.handedness == "right":
                    enable_button = self.ctrl["X"]
                    reset_button = self.ctrl["Y"]
                    start_trigger = self.ctrl["LTr"]
                else:
                    enable_button = self.ctrl["A"]
                    reset_button = self.ctrl["B"]
                    start_trigger = self.ctrl["RTr"]

                if enable_button and not self.startflag:
                    self.startflag = True
                    print("start VR control")

                if reset_button and self.startflag:
                    self.startflag = False
                    self.reset_pose()
                    print("RESET Arm position")
                    print("stop Arm control")

                enable = self.startflag and start_trigger
                if enable:
                    try:
                        if self._is_default_pose(self.pose):
                            self.arm_init = False
                            time.sleep(1 / 30)
                            continue

                        vr_trans = self.pose[:3]
                        vr_quat = self.pose[3:7]

                        vr_trans = np.array(vr_trans, dtype=float)
                        vr_quat = np.array(vr_quat, dtype=float)

                        vr_cur_pose = self.pose_transform_to_matrix(vr_trans, vr_quat)

                        # 初始化偏置
                        if not self.arm_init:
                            self.trans_init = np.array(vr_trans)

                            self.quat_init = np.array(vr_quat)

                            self.vr_init_pose = self.pose_transform_to_matrix(
                                self.trans_init, self.quat_init
                            )

                            # arm_end_pose = self.get_end_pose()

                            self.arm_init_pose = self.pose_transform_to_matrix(
                                self.transform_pose[:3], self.transform_pose[3:]
                            )
                            print(f"VR初始位置: {self.trans_init}")
                            print(f"VR初始朝向: {self.quat_init}")
                            print(f"机械臂末端初始位姿: {self.arm_init_pose}\n")
                            self.arm_init = True

                        relative_transform = np.dot(
                            np.linalg.inv(self.vr_init_pose), vr_cur_pose
                        )

                        T = np.dot(self.arm_init_pose, relative_transform)

                        self.update_arm(T)
                        self.transform_pose = self.homogeneous_matrix_to_pose(T)
                    except Exception as e:
                        print(f"VR臂控制出错: {str(e)}\n")
                else:
                    self.arm_init = False
                    # self.transform_pose[0] = [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]

                time.sleep(1 / 30)

    def _start_events_thread(self):
        self.pause_event.set()
        thread = threading.Thread(target=self.handle_pose_data, daemon=True)
        thread.start()
        return thread

    def pose_transform_to_matrix(self, pos, rot):
        pos = np.array(pos, dtype=float)
        quat = np.array(rot, dtype=float)
        rotation = Rotation.from_quat(quat).as_matrix()
        trans = np.eye(4)
        trans[:3, :3] = rotation
        trans[:3, 3] = pos
        return trans

    def connect(self, calibrate: bool = True) -> None:
        self._start_events_thread()
        if self.config.eef_device != "G2":
            if self.hand_teleoperator and self.hand_teleoperator.init():
                self.hand_teleoperator.start_listening()
        self._is_connected = True

    def enable_motors(self) -> None:
        pass

    def disable_motors(self) -> None:
        pass

    def configure(self):
        pass

    @property
    def action_features(self):
        if self.config.eef_device == "G2":
            return {
                "joint1.pos": float,
                "joint2.pos": float,
                "joint3.pos": float,
                "joint4.pos": float,
                "joint5.pos": float,
                "joint6.pos": float,
                "eef.pos": float,
                "pose.x": float,
                "pose.y": float,
                "pose.z": float,
                "quaternion.qx": float,
                "quaternion.qy": float,
                "quaternion.qz": float,
                "quaternion.qw": float,
            }

        return {
            "joint1.pos": float,
            "joint2.pos": float,
            "joint3.pos": float,
            "joint4.pos": float,
            "joint5.pos": float,
            "joint6.pos": float,
            "Thumb1_1.pos": float,
            "Thumb1_3.pos": float,
            "Index1.pos": float,
            "Middle1.pos": float,
            "Ring1.pos": float,
            "Pinky1.pos": float,
            "pose.x": float,
            "pose.y": float,
            "pose.z": float,
            "quaternion.qx": float,
            "quaternion.qy": float,
            "quaternion.qz": float,
            "quaternion.qw": float,
        }

    def calibrate(self):
        pass

    @property
    def is_calibrated(self):
        return True

    def observation_features(self):
        pass

    def get_joint_pos(self):
        if self.config.eef_device == "G2":
            state = [0.0] * 7
            now = time.time()
            for i in range(6):
                state[i] = self.lpfs[i].sample(now)
            state[6] = 0.072 - 0.072 * self.ctrl["leftGrip"] ** 2
        else:
            state = [0.0] * 12
            now = time.time()
            for i in range(6):
                state[i] = self.lpfs[i].sample(now)
            hand_ctrl_data = self.hand_teleoperator.get_hand_data()
            for i in range(6):
                state[6 + i] = hand_ctrl_data[i]

        return state

    def get_action(self):
        action = self.get_joint_pos()
        pose = self.transform_pose.copy()

        if self.config.eef_device == "G2":

            action_dict = {
                "joint1.pos": action[0],
                "joint2.pos": action[1],
                "joint3.pos": action[2],
                "joint4.pos": action[3],
                "joint5.pos": action[4],
                "joint6.pos": action[5],
                "eef.pos": action[6],
                "pose.x": pose[0],
                "pose.y": pose[1],
                "pose.z": pose[2],
                "quaternion.qx": pose[3],
                "quaternion.qy": pose[4],
                "quaternion.qz": pose[5],
                "quaternion.qw": pose[6],
            }
            return action_dict
        else:
            action_dict = {
                "joint1.pos": action[0],
                "joint2.pos": action[1],
                "joint3.pos": action[2],
                "joint4.pos": action[3],
                "joint5.pos": action[4],
                "joint6.pos": action[5],
                "Thumb1_1.pos": action[6],
                "Thumb1_3.pos": action[7],
                "Index1.pos": action[8],
                "Middle1.pos": action[9],
                "Ring1.pos": action[10],
                "Pinky1.pos": action[11],
                "pose.x": pose[0],
                "pose.y": pose[1],
                "pose.z": pose[2],
                "quaternion.qx": pose[3],
                "quaternion.qy": pose[4],
                "quaternion.qz": pose[5],
                "quaternion.qw": pose[6],
            }
            return action_dict

    def get_eef_pos(self):
        pass

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")
        pass

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        pass

    @property
    def feedback_features(self) -> dict[str, type]:
        return {}

    def send_feedback(self, feedback: dict[str, float]) -> None:
        pass

    def return_init(self):
        if self.config.eef_device == "G2":
            self.transform_pose = [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]
        else:
            self.transform_pose = [0.12610013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]

    def reset_pose(self):
        self.return_init()
        self.arm_init = False
        self.trans_init = None
        self.quat_init = None
        self.vr_init_pose = None
        self.arm_init_pose = None

        try:
            target_pose = self.pose_transform_to_matrix(
                self.transform_pose[:3], self.transform_pose[3:]
            )
            self.update_arm(target_pose)
        except Exception as exc:
            print(f"RESET Arm position failed: {exc}")

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        logger.warning("airbot play arms and eefs stopped immediately")

    def _safe_shutdown(self, timeout: float = 10.0):
        logger.info("Starting safe shutdown procedure...")
        print(self.process)
        if self.process is not None:
            returncode = self.process.poll()
            print(f"进程返回码: {returncode}")

            if returncode is None:
                print("进程仍在运行，正在终止...")
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                    print("WebRTC进程已停止")
                except subprocess.TimeoutExpired:
                    print("进程未响应，强制杀死...")
                    self.process.kill()
                    self.process.wait()
                    print("WebRTC进程已被强制杀死")
            else:
                print(f"进程已退出，返回码: {returncode}")

        logger.info("Motors disabled and uninitialized")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            if self.config.eef_device != "G2":
                if self.hand_teleoperator:
                    self.hand_teleoperator.stop()
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            if self.process is not None:
                returncode = self.process.poll()
                print(f"进程返回码: {returncode}")

                if returncode is None:
                    print("进程仍在运行，正在终止...")
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                        print("WebRTC进程已停止")
                    except subprocess.TimeoutExpired:
                        print("进程未响应，强制杀死...")
                        self.process.kill()
                        self.process.wait()
                        print("WebRTC进程已被强制杀死")
                else:
                    print(f"进程已退出，返回码: {returncode}")

        self._is_connected = False
        logger.info(f"{self} safely disconnected.")
