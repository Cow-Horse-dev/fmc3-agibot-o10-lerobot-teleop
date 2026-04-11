import logging
import time
import math
from functools import cached_property
import typing
from typing import Any, List
import numpy as np
from time import time_ns

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from lerobot.robots.robot import Robot
from mmk2_kdl_py import ArmKdlNumerical

import airbot_hardware_py as ah
from .config_pico_follower import PicoFollowerConfig

logger = logging.getLogger(__name__)


class PicoFollower(Robot):
    config_class = PicoFollowerConfig
    name = "pico_follower"

    def __init__(self, config: PicoFollowerConfig):
        super().__init__(config)
        self.config = config
        if self.config.eef_device == "G2":
            self.arm_kdl = ArmKdlNumerical(eef_type="G2")
        else:
            self.arm_kdl = ArmKdlNumerical(eef_type="none")

        self.left_arm_port = self.config.left_arm_port
        self.right_arm_port = self.config.right_arm_port

        self.executor_left = ah.create_asio_executor(8)
        self.executor_right = ah.create_asio_executor(8)

        self.io_context_left = self.executor_left.get_io_context()
        self.io_context_right = self.executor_right.get_io_context()

        self.left_arm = ah.PlayWithEEF.create(
            ah.MotorType.OD,
            ah.MotorType.OD,
            ah.MotorType.OD,
            ah.MotorType.DM,
            ah.MotorType.DM,
            ah.MotorType.DM,
            ah.EEFType.G2,
            ah.MotorType.DM,
        )
        self.right_arm = ah.PlayWithEEF.create(
            ah.MotorType.OD,
            ah.MotorType.OD,
            ah.MotorType.OD,
            ah.MotorType.DM,
            ah.MotorType.DM,
            ah.MotorType.DM,
            ah.EEFType.G2,
            ah.MotorType.DM,
        )

        self.cameras = make_cameras_from_configs(config.cameras)

        for cam in self.cameras.values():
            cam.connect()

        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self) -> None:
        if self.is_connected:
            raise RuntimeError(f"{self} already connected")

        if not self.left_arm.init(self.io_context_left, self.left_arm_port, 250):
            raise RuntimeError("Failed to initialize left arm")
        if not self.right_arm.init(self.io_context_right, self.right_arm_port, 250):
            raise RuntimeError("Failed to initialize right arm")

        self.enable_motors()
        self.configure()
        self._is_connected = True

    def enable_motors(self) -> None:
        self.left_arm.enable()
        self.right_arm.enable()

    def disable_motors(self) -> None:
        self.left_arm.disable()
        self.right_arm.disable()

    def configure(self):
        self.left_arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)
        self.left_arm.set_param("eef.control_mode", ah.MotorControlMode.PVT)
        self.right_arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)
        self.right_arm.set_param("eef.control_mode", ah.MotorControlMode.PVT)

    def get_joint_pos(self):
        return [self.left_arm.state().pos, self.right_arm.state().pos]

    @property
    def _motors_ft(self) -> dict[str, type]:
        return {
            "left_joint1.pos": float,
            "left_joint2.pos": float,
            "left_joint3.pos": float,
            "left_joint4.pos": float,
            "left_joint5.pos": float,
            "left_joint6.pos": float,
            "left_eef.pos": float,
            "right_joint1.pos": float,
            "right_joint2.pos": float,
            "right_joint3.pos": float,
            "right_joint4.pos": float,
            "right_joint5.pos": float,
            "right_joint6.pos": float,
            "right_eef.pos": float,
            "left_pose.x": float,
            "left_pose.y": float,
            "left_pose.z": float,
            "left_quaternion.qx": float,
            "left_quaternion.qy": float,
            "left_quaternion.qz": float,
            "left_quaternion.qw": float,
            "right_pose.x": float,
            "right_pose.y": float,
            "right_pose.z": float,
            "right_quaternion.qx": float,
            "right_quaternion.qy": float,
            "right_quaternion.qz": float,
            "right_quaternion.qw": float,
        }

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @cached_property
    def action_features(self):
        return {
            "left_joint1.pos": float,
            "left_joint2.pos": float,
            "left_joint3.pos": float,
            "left_joint4.pos": float,
            "left_joint5.pos": float,
            "left_joint6.pos": float,
            "left_eef.pos": float,
            "right_joint1.pos": float,
            "right_joint2.pos": float,
            "right_joint3.pos": float,
            "right_joint4.pos": float,
            "right_joint5.pos": float,
            "right_joint6.pos": float,
            "right_eef.pos": float,
            "left_pose.x": float,
            "left_pose.y": float,
            "left_pose.z": float,
            "left_quaternion.qx": float,
            "left_quaternion.qy": float,
            "left_quaternion.qz": float,
            "left_quaternion.qw": float,
            "right_pose.x": float,
            "right_pose.y": float,
            "right_pose.z": float,
            "right_quaternion.qx": float,
            "right_quaternion.qy": float,
            "right_quaternion.qz": float,
            "right_quaternion.qw": float,
        }

    def calibrate(self):
        pass

    def is_calibrated(self):
        pass

    def is_arm_arrive(self, arm_target, arm_pose, tolerance=0.02):
        return all(
            abs(target - pose) <= tolerance
            for target, pose in zip(arm_target, arm_pose)
        )

    def is_eef_arrive(self, eef_target, eef_pose, tolerance=0.005):
        return abs(eef_target - eef_pose) <= tolerance

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        return {**self._motors_ft, **self._cameras_ft}

    def servo_left_joint_pos(self, joints: typing.List[float], eef, vel=3.0, eff=8.0):
        velocities = [vel] * (self.config.arm_joints_num - 1) + [25]
        effort = [eff] * (self.config.arm_joints_num - 1) + [5.0]
        pos = joints + [eef]
        return self.left_arm.pvt(pos, velocities, effort)

    def servo_right_joint_pos(self, joints: typing.List[float], eef, vel=3.0, eff=8.0):
        velocities = [vel] * (self.config.arm_joints_num - 1) + [25]
        effort = [eff] * (self.config.arm_joints_num - 1) + [5.0]
        pos = joints + [eef]
        return self.right_arm.pvt(pos, velocities, effort)

    # def reset_init(self, pos):
    #     velocities = [0.4] * self.config.arm_joints_num
    #     effort = [10.0] * self.config.arm_joints_num
    #     while True:
    #         left_arm_arrived = self.is_arm_arrive(pos[0], self.get_joint_pos()[0], 0.02)
    #         right_arm_arrived = self.is_arm_arrive(
    #             pos[1], self.get_joint_pos()[1], 0.02
    #         )
    #         if left_arm_arrived and right_arm_arrived:
    #             break
    #         else:
    #             self.left_arm.pvt(pos[0][:6], velocities, effort)
    #             self.right_arm.pvt(pos[1][:6], velocities, effort)
    #         time.sleep(0.004)

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

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        # Read arm position
        start = time.perf_counter()

        pos = self.get_joint_pos()
        left_array = self.arm_kdl.forward_kinematics(pos[0][:6])
        right_array = self.arm_kdl.forward_kinematics(pos[1][:6])
        left_pose = self.homogeneous_matrix_to_pose(left_array)
        right_pose = self.homogeneous_matrix_to_pose(right_array)

        obs_dict = {
            "left_joint1.pos": pos[0][0],
            "left_joint2.pos": pos[0][1],
            "left_joint3.pos": pos[0][2],
            "left_joint4.pos": pos[0][3],
            "left_joint5.pos": pos[0][4],
            "left_joint6.pos": pos[0][5],
            "left_eef.pos": pos[0][6],
            "right_joint1.pos": pos[1][0],
            "right_joint2.pos": pos[1][1],
            "right_joint3.pos": pos[1][2],
            "right_joint4.pos": pos[1][3],
            "right_joint5.pos": pos[1][4],
            "right_joint6.pos": pos[1][5],
            "right_eef.pos": pos[1][6],
            "left_pose.x": left_pose[0],
            "left_pose.y": left_pose[1],
            "left_pose.z": left_pose[2],
            "left_quaternion.qx": left_pose[3],
            "left_quaternion.qy": left_pose[4],
            "left_quaternion.qz": left_pose[5],
            "left_quaternion.qw": left_pose[6],
            "right_pose.x": right_pose[0],
            "right_pose.y": right_pose[1],
            "right_pose.z": right_pose[2],
            "right_quaternion.qx": right_pose[3],
            "right_quaternion.qy": right_pose[4],
            "right_quaternion.qz": right_pose[5],
            "right_quaternion.qw": right_pose[6],
        }
        dt_ms = (time.perf_counter() - start) * 1e3
        logger.debug(f"{self} read state: {dt_ms:.1f}ms")

        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            start = time.perf_counter()
            obs_dict[cam_key] = cam.async_read()
            dt_ms = (time.perf_counter() - start) * 1e3
            # print_red(f"{self} read {cam_key}: {dt_ms:.1f}ms")

        return obs_dict

    def convert_action_format(self, action):
        """
        将第二种格式的 action 转换为第一种格式

        第一种格式:
        {
            'left_joints': [j1, j2, j3, j4, j5, j6],
            'left_eef': eef_value,
            'right_joints': [j1, j2, j3, j4, j5, j6],
            'right_eef': eef_value
        }

        第二种格式:
        {
            'left_joint1.pos': value,
            'left_joint2.pos': value,
            ...,
            'left_eef.pos': value,
            ...
        }
        """

        # 检查是否是第二种格式（通过检查是否存在 .pos 后缀的键）
        is_second_format = any(".pos" in key for key in action.keys())

        if not is_second_format:
            # 已经是第一种格式，直接返回
            return action

        # 转换为第一种格式
        converted = {
            "left_joints": [],
            "left_eef": 0.0,
            "right_joints": [],
            "right_eef": 0.0,
        }

        # 提取关节数据
        for i in range(1, 7):  # joint1 到 joint6
            left_key = f"left_joint{i}.pos"
            right_key = f"right_joint{i}.pos"

            if left_key in action:
                converted["left_joints"].append(action[left_key])
            if right_key in action:
                converted["right_joints"].append(action[right_key])

        # 提取末端执行器数据
        if "left_eef.pos" in action:
            converted["left_eef"] = action["left_eef.pos"]
        if "right_eef.pos" in action:
            converted["right_eef"] = action["right_eef.pos"]

        return converted

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        temp = action.copy()
        action = self.convert_action_format(action)

        self.servo_left_joint_pos(action["left_joints"], action["left_eef"])

        self.servo_right_joint_pos(action["right_joints"], action["right_eef"])

        return {
            "left_joint1.pos": action["left_joints"][0],
            "left_joint2.pos": action["left_joints"][1],
            "left_joint3.pos": action["left_joints"][2],
            "left_joint4.pos": action["left_joints"][3],
            "left_joint5.pos": action["left_joints"][4],
            "left_joint6.pos": action["left_joints"][5],
            "left_eef.pos": action["left_eef"],
            "right_joint1.pos": action["right_joints"][0],
            "right_joint2.pos": action["right_joints"][1],
            "right_joint3.pos": action["right_joints"][2],
            "right_joint4.pos": action["right_joints"][3],
            "right_joint5.pos": action["right_joints"][4],
            "right_joint6.pos": action["right_joints"][5],
            "right_eef.pos": action["right_eef"],
            "left_pose.x": temp["left_pose.x"],
            "left_pose.y": temp["left_pose.y"],
            "left_pose.z": temp["left_pose.z"],
            "left_quaternion.qx": temp["left_quaternion.qx"],
            "left_quaternion.qy": temp["left_quaternion.qy"],
            "left_quaternion.qz": temp["left_quaternion.qz"],
            "left_quaternion.qw": temp["left_quaternion.qw"],
            "right_pose.x": temp["right_pose.x"],
            "right_pose.y": temp["right_pose.y"],
            "right_pose.z": temp["right_pose.z"],
            "right_quaternion.qx": temp["right_quaternion.qx"],
            "right_quaternion.qy": temp["right_quaternion.qy"],
            "right_quaternion.qz": temp["right_quaternion.qz"],
            "right_quaternion.qw": temp["right_quaternion.qw"],
        }

    def return_zero(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        joints = [0.0] * self.config.arm_joints_num
        velocities = [0.8] * self.config.arm_joints_num
        effort = [10.0] * self.config.arm_joints_num

        while True:
            state = self.get_joint_pos()
            left_arm_arrived = self.is_arm_arrive(joints, state[0])
            left_eef_arrived = self.is_eef_arrive(joints[6], state[0][6])
            right_arm_arrived = self.is_arm_arrive(joints, state[1])
            right_eef_arrived = self.is_eef_arrive(joints[6], state[1][6])
            if (
                left_arm_arrived
                and left_eef_arrived
                and right_arm_arrived
                and right_eef_arrived
            ):
                break
            else:
                self.left_arm.pvt(joints, velocities, effort)
                self.right_arm.pvt(joints, velocities, effort)
                # print(left_arm_arrived, left_eef_arrived, right_arm_arrived, right_eef_arrived)
                # print(self.get_joint_pos())

    def reset_zero(self):
        self.return_zero()

    def stop_all(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        # arm_joints = self.arm.state().pos

        # velocities = [0.0] * self.config.arm_joints_num
        # self.arm.pvt(arm_joints, velocities)

        # eef_state = self.eef.state()

        # eef_cmd = ah.EEFCommand1()
        # eef_cmd.pos = eef_state.pos
        # eef_cmd.vel = [0.0]
        # self.arm.pvt(eef_cmd)

        # logger.warning("airbot play arms and eefs stopped immediately")

    def _safe_shutdown(self, timeout: float = 10.0):
        logger.info("Starting safe shutdown procedure...")
        self.disable_motors()
        self.left_arm.uninit()
        self.right_arm.uninit()
        logger.info("Motors disabled and uninitialized")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            self.disable_motors()
            self.left_arm.uninit()
            self.right_arm.uninit()

        self._is_connected = False
        logger.info(f"{self} safely disconnected.")
