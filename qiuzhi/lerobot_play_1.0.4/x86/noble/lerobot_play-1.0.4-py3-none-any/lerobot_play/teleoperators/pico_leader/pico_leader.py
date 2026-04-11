import sys
import os
import subprocess

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
from lerobot.teleoperators.teleoperator import Teleoperator
from pathlib import Path

import airbot_hardware_py as ah
from airbot_state_machine import robotic_arm
from lerobot_play.teleoperators.pico_leader.config_pico_leader import (
    PicoLeaderConfig,
)
from lerobot_play.teleoperators.pico_leader import pico_webrtc
from .lpf import OnlineVariableStepLPF
from mmk2_kdl_py import ArmKdlNumerical

logger = logging.getLogger(__name__)


class PicoLeader(Teleoperator):
    config_class = PicoLeaderConfig
    name = "pico_leader"

    def __init__(self, config: PicoLeaderConfig):
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
        self.temp_pose = [[0.0] * 6, [0.0] * 6]
        self.solve_fail = False
        self.allow_flip = False
        self.process = None
        self.history = [[0.0] * 7, [0.0] * 7]
        self.transform_pose = [
            [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0],
            [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0],
        ]

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

        self.lpfs_left = [
            OnlineVariableStepLPF(fc=100, kp=10, kd=0.2, v_max=5000, a_max=100)
            for _ in range(6)
        ]
        self.lpfs_right = [
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
        self.arm_init_left = False
        self.arm_init_right = False

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

            print(f"启动WebRTC进程命令: {' '.join(args)}")

            # 确保正确设置 self.process
            self.process = subprocess.Popen(args)
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
            self.pose = [self.left_info, self.right_info]
        except Exception as e:
            print(f"Error updating pose data: {e}")

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

        # print(self.ctrl)

    def update_arm_left(self, pose_left: np.ndarray):
        joint_pos_left = [0.0] * 6
        target_pose_mat_left = np.array(pose_left, dtype=float)
        if target_pose_mat_left.shape != (4, 4):
            raise ValueError("pose must be a 4x4 homogeneous transform matrix")

        now = time.time()
        for i in range(6):
            joint_pos_left[i] = self.lpfs_left[i].sample(now)

        result_left = self.arm_kdl.inverse_kinematics(
            target_pose_mat_left, joint_pos_left
        )

        if len(result_left) == 0:
            self.solve_fail = True
            print(f"Inverse kinematics failed. Given pose: {[target_pose_mat_left]}")
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
        pos_left = result_left[0]

        now = time.time()
        for i in range(6):
            self.lpfs_left[i].update(now, pos_left[i])
        self.history[0] = pos_left

    def update_arm_right(self, pose_right: np.ndarray):
        joint_pos_right = [0.0] * 6
        target_pose_mat_right = np.array(pose_right, dtype=float)
        if target_pose_mat_right.shape != (4, 4):
            raise ValueError("pose must be a 4x4 homogeneous transform matrix")

        now = time.time()
        for i in range(6):
            joint_pos_right[i] = self.lpfs_right[i].sample(now)

        result_right = self.arm_kdl.inverse_kinematics(
            target_pose_mat_right, joint_pos_right
        )

        if len(result_right) == 0:
            self.solve_fail = True
            print(f"Inverse kinematics failed. Given pose: {[target_pose_mat_right]}")
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
        pos_right = result_right[0]

        now = time.time()
        for i in range(6):
            self.lpfs_right[i].update(now, pos_right[i])
        self.history[1] = pos_right

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
                # print("self.pose", self.pose[0][:3])
                if self.ctrl["LTr"]:
                    try:
                        vr_trans_left = self.pose[0][:3]
                        vr_quat_left = self.pose[0][3:7]

                        vr_trans_left = np.array(vr_trans_left, dtype=float)
                        vr_quat_left = np.array(vr_quat_left, dtype=float)

                        vr_cur_pose_left = self.pose_transform_to_matrix(
                            vr_trans_left, vr_quat_left
                        )

                        # 初始化偏置
                        if not self.arm_init_left:
                            self.trans_init_left = np.array(vr_trans_left)

                            self.quat_init_left = np.array(vr_quat_left)

                            self.vr_init_pose_left = self.pose_transform_to_matrix(
                                self.trans_init_left, self.quat_init_left
                            )

                            # arm_end_pose = self.get_end_pose()

                            self.arm_init_pose_left = self.pose_transform_to_matrix(
                                self.transform_pose[0][:3], self.transform_pose[0][3:]
                            )
                            print(f"VR初始位置: {self.trans_init_left}")
                            print(f"VR初始朝向: {self.quat_init_left}")
                            print(f"机械臂末端初始位姿: {self.arm_init_pose_left}\n")
                            self.arm_init_left = True

                        relative_transform_left = np.dot(
                            np.linalg.inv(self.vr_init_pose_left), vr_cur_pose_left
                        )

                        T_left = np.dot(
                            self.arm_init_pose_left, relative_transform_left
                        )

                        self.update_arm_left(T_left)
                        self.transform_pose[0] = self.homogeneous_matrix_to_pose(T_left)
                    except Exception as e:
                        print(f"VR臂控制出错: {str(e)}\n")
                else:
                    self.arm_init_left = False
                    # self.transform_pose[0] = [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]

                if self.ctrl["RTr"]:
                    try:
                        vr_trans_right = self.pose[1][:3]
                        vr_quat_right = self.pose[1][3:7]

                        vr_trans_right = np.array(vr_trans_right, dtype=float)
                        vr_quat_right = np.array(vr_quat_right, dtype=float)

                        vr_cur_pose_right = self.pose_transform_to_matrix(
                            vr_trans_right, vr_quat_right
                        )

                        # 初始化偏置
                        if not self.arm_init_right:
                            self.trans_init_right = np.array(vr_trans_right)

                            self.quat_init_right = np.array(vr_quat_right)

                            self.vr_init_pose_right = self.pose_transform_to_matrix(
                                self.trans_init_right, self.quat_init_right
                            )

                            # arm_end_pose = self.get_end_pose()

                            self.arm_init_pose_right = self.pose_transform_to_matrix(
                                self.transform_pose[1][:3], self.transform_pose[1][3:]
                            )

                            print(f"VR初始位置: {self.trans_init_right}")
                            print(f"VR初始朝向: {self.quat_init_right}")
                            print(f"机械臂末端初始位姿: {self.arm_init_pose_right}\n")
                            self.arm_init_right = True

                        relative_transform_right = np.dot(
                            np.linalg.inv(self.vr_init_pose_right), vr_cur_pose_right
                        )

                        T_right = np.dot(
                            self.arm_init_pose_right, relative_transform_right
                        )

                        self.update_arm_right(T_right)
                        self.transform_pose[1] = self.homogeneous_matrix_to_pose(
                            T_right
                        )
                    except Exception as e:
                        print(f"VR臂控制出错: {str(e)}\n")
                else:
                    self.arm_init_right = False
                    # self.transform_pose[1] = [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0]

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

    def connect(self) -> None:
        self._start_events_thread()
        self._is_connected = True

    def enable_motors(self) -> None:
        pass

    def disable_motors(self) -> None:
        pass

    def configure(self):
        pass

    def action_features(self):
        pass

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    def observation_features(self):
        pass

    def get_joint_pos(self):
        left_state = [0.0] * 7
        right_state = [0.0] * 7
        now = time.time()
        for i in range(6):
            left_state[i] = self.lpfs_left[i].sample(now)
            right_state[i] = self.lpfs_right[i].sample(now)
        left_state[6] = 0.072 - 0.072 * self.ctrl["leftGrip"] ** 2
        right_state[6] = 0.072 - 0.072 * self.ctrl["rightGrip"] ** 2

        return [left_state, right_state]

    def get_action(self):
        action = self.get_joint_pos()
        pose = self.transform_pose.copy()

        action_dict = {
            "left_joint1.pos": action[0][0],
            "left_joint2.pos": action[0][1],
            "left_joint3.pos": action[0][2],
            "left_joint4.pos": action[0][3],
            "left_joint5.pos": action[0][4],
            "left_joint6.pos": action[0][5],
            "left_eef.pos": action[0][6],
            "right_joint1.pos": action[1][0],
            "right_joint2.pos": action[1][1],
            "right_joint3.pos": action[1][2],
            "right_joint4.pos": action[1][3],
            "right_joint5.pos": action[1][4],
            "right_joint6.pos": action[1][5],
            "right_eef.pos": action[1][6],
            "left_pose.x": pose[0][0],
            "left_pose.y": pose[0][1],
            "left_pose.z": pose[0][2],
            "left_quaternion.qx": pose[0][3],
            "left_quaternion.qy": pose[0][4],
            "left_quaternion.qz": pose[0][5],
            "left_quaternion.qw": pose[0][6],
            "right_pose.x": pose[1][0],
            "right_pose.y": pose[1][1],
            "right_pose.z": pose[1][2],
            "right_quaternion.qx": pose[1][3],
            "right_quaternion.qy": pose[1][4],
            "right_quaternion.qz": pose[1][5],
            "right_quaternion.qw": pose[1][6],
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
        self.transform_pose = [
            [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0],
            [0.28630013, 0.0, 0.21357222, 0.0, 0.0, 0.0, 1.0],
        ]

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
