import logging
import time
import math
from functools import cached_property
import typing
from typing import Any, List
import numpy as np
from time import time_ns
import threading

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from lerobot.robots.robot import Robot
from mmk2_kdl_py import ArmKdlNumerical

import airbot_hardware_py as ah
from .config_pico_follower_single_arm_eef import PicoFollowerSingleArmEEFConfig

logger = logging.getLogger(__name__)


class PicoFollowerSingleArmEEF(Robot):
    config_class = PicoFollowerSingleArmEEFConfig
    name = "pico_follower_single_arm_eef"

    def __init__(self, config: PicoFollowerSingleArmEEFConfig):
        super().__init__(config)
        self.config = config
        if self.config.eef_device == "G2":
            self.arm_kdl = ArmKdlNumerical(eef_type="G2")
        else:
            self.arm_kdl = ArmKdlNumerical(eef_type="none")

        self.arm_port = self.config.port

        self.executor = ah.create_asio_executor(8)

        self.io_context = self.executor.get_io_context()

        if self.config.eef_device == "G2":
            self.arm = ah.PlayWithEEF.create(
                ah.MotorType.OD,
                ah.MotorType.OD,
                ah.MotorType.OD,
                ah.MotorType.DM,
                ah.MotorType.DM,
                ah.MotorType.DM,
                ah.EEFType.G2,
                ah.MotorType.DM,
            )
        else:
            self.executor_hand = ah.create_asio_executor(8)
            self.io_context_hand = self.executor_hand.get_io_context()
            self.arm = ah.Play.create(
                ah.MotorType.OD,
                ah.MotorType.OD,
                ah.MotorType.OD,
                ah.MotorType.DM,
                ah.MotorType.DM,
                ah.MotorType.DM,
                ah.EEFType.NA,
                ah.MotorType.NA,
            )
            if self.config.eef_device == "INS_RH56E2":
                self.hand = ah.create_dexterous_hand(
                    self.config.hand_id, ah.DexterousHandTypes.INS_RH56E2
                )
            elif self.config.eef_device == "INS_RH56F1":
                self.hand = ah.create_dexterous_hand(
                    self.config.hand_id, ah.DexterousHandTypes.INS_RH56F1
                )
            elif self.config.eef_device == "INS_RH56DFX":
                self.hand = ah.create_dexterous_hand(
                    self.config.hand_id, ah.DexterousHandTypes.INS_RH56DFX
                )
            elif self.config.eef_device == "BRAINCO_REVO2":
                self.hand = ah.create_dexterous_hand(
                    self.config.hand_id, ah.DexterousHandTypes.BRAINCO_REVO2
                )
            self.hand_target_pos = [0, 0, 0, 0, 0, 0]
            self.eef_cmd = ah.HandState()
            self.eef_cmd.positions = self.hand_target_pos
            self.eef_cmd.velocities = [1000] * 6

            self.hand_joints = [0, 0, 0, 0, 0, 0]

        self.cameras = make_cameras_from_configs(config.cameras)

        for cam in self.cameras.values():
            cam.connect()

        self._is_connected = False
        self.hand_time = None
        self.hand_lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self) -> None:
        if self.is_connected:
            raise RuntimeError(f"{self} already connected")

        if not self.arm.init(self.io_context, self.arm_port, 250):
            raise RuntimeError("Failed to initialize arm")

        if self.config.eef_device != "G2":
            if not self.hand.init(self.io_context_hand, self.arm_port, 250):
                raise RuntimeError("Failed to initialize hand")

            self.hand_control_thread = threading.Thread(
                target=self.servo_hand_pos, daemon=True  # 设置为守护线程
            )
            self.hand_control_thread.start()

        self.enable_motors()
        self.configure()
        self._is_connected = True

    def enable_motors(self) -> None:
        self.arm.enable()

    def disable_motors(self) -> None:
        self.arm.disable()

    def configure(self):
        self.arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)
        if self.config.eef_device == "G2":
            self.arm.set_param("eef.control_mode", ah.MotorControlMode.PVT)

    def get_joint_pos(self):
        if self.config.eef_device == "G2":
            return self.arm.state().pos
        else:
            # self.hand.update_state()
            return [self.arm.state().pos, self.hand.state().positions]

    @property
    def _motors_ft(self) -> dict[str, type]:
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
        else:
            return {
                "joint1.pos": float,
                "joint2.pos": float,
                "joint3.pos": float,
                "joint4.pos": float,
                "joint5.pos": float,
                "joint6.pos": float,
                "pose.x": float,
                "pose.y": float,
                "pose.z": float,
                "quaternion.qx": float,
                "quaternion.qy": float,
                "quaternion.qz": float,
                "quaternion.qw": float,
                "Thumb1_1.pos": float,
                "Thumb1_3.pos": float,
                "Index1.pos": float,
                "Middle1.pos": float,
                "Ring1.pos": float,
                "Pinky1.pos": float,
            }

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @cached_property
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
        else:
            return {
                "joint1.pos": float,
                "joint2.pos": float,
                "joint3.pos": float,
                "joint4.pos": float,
                "joint5.pos": float,
                "joint6.pos": float,
                "pose.x": float,
                "pose.y": float,
                "pose.z": float,
                "quaternion.qx": float,
                "quaternion.qy": float,
                "quaternion.qz": float,
                "quaternion.qw": float,
                "Thumb1_1.pos": float,
                "Thumb1_3.pos": float,
                "Index1.pos": float,
                "Middle1.pos": float,
                "Ring1.pos": float,
                "Pinky1.pos": float,
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

    def servo_joint_pos(self, joints: typing.List[float], eef, vel=3.0, eff=8.0):
        if self.config.eef_device == "G2":
            velocities = [vel] * (self.config.arm_joints_num - 1) + [25]
            effort = [eff] * (self.config.arm_joints_num - 1) + [5.0]
            pos = joints + [eef]
            return self.arm.pvt(pos, velocities, effort)
        else:
            velocities = [vel] * (self.config.arm_joints_num - 1)
            effort = [eff] * (self.config.arm_joints_num - 1)
            pos = joints
            return self.arm.pvt(pos, velocities, effort)

    def servo_hand_pos(self):
        while True:
            self.hand.update_state()
            hand_cmd = ah.HandState()
            hand_cmd.positions = [int(x) for x in self.hand_joints]
            hand_cmd.velocities = [1000] * 6

            self.hand.set_pos(hand_cmd)

            time.sleep(0.03)

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

        if self.config.eef_device == "G2":
            pos = self.get_joint_pos()
            array = self.arm_kdl.forward_kinematics(pos[:6])
            pose = self.homogeneous_matrix_to_pose(array)

            obs_dict = {
                "joint1.pos": pos[0],
                "joint2.pos": pos[1],
                "joint3.pos": pos[2],
                "joint4.pos": pos[3],
                "joint5.pos": pos[4],
                "joint6.pos": pos[5],
                "eef.pos": pos[6],
                "pose.x": pose[0],
                "pose.y": pose[1],
                "pose.z": pose[2],
                "quaternion.qx": pose[3],
                "quaternion.qy": pose[4],
                "quaternion.qz": pose[5],
                "quaternion.qw": pose[6],
            }
        else:
            pos = self.get_joint_pos()
            array = self.arm_kdl.forward_kinematics(pos[0][:6])
            pose = self.homogeneous_matrix_to_pose(array)

            obs_dict = {
                "joint1.pos": pos[0][0],
                "joint2.pos": pos[0][1],
                "joint3.pos": pos[0][2],
                "joint4.pos": pos[0][3],
                "joint5.pos": pos[0][4],
                "joint6.pos": pos[0][5],
                "pose.x": pose[0],
                "pose.y": pose[1],
                "pose.z": pose[2],
                "quaternion.qx": pose[3],
                "quaternion.qy": pose[4],
                "quaternion.qz": pose[5],
                "quaternion.qw": pose[6],
                "Thumb1_1.pos": pos[1][0],
                "Thumb1_3.pos": pos[1][1],
                "Index1.pos": pos[1][2],
                "Middle1.pos": pos[1][3],
                "Ring1.pos": pos[1][4],
                "Pinky1.pos": pos[1][5],
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
            "joints": [],
            "eef": 0.0,
        }

        # 提取关节数据
        for i in range(1, 7):  # joint1 到 joint6
            key = f"joint{i}.pos"

            if key in action:
                converted["joints"].append(action[key])

        # 提取末端执行器数据
        if "eef.pos" in action:
            converted["eef"] = action["eef.pos"]

        return converted

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        temp = action.copy()
        action = self.convert_action_format(action)

        if self.config.eef_device == "G2":
            self.servo_joint_pos(action["joints"], action["eef"])
            return {
                "joint1.pos": action["joints"][0],
                "joint2.pos": action["joints"][1],
                "joint3.pos": action["joints"][2],
                "joint4.pos": action["joints"][3],
                "joint5.pos": action["joints"][4],
                "joint6.pos": action["joints"][5],
                "eef.pos": action["eef"],
                "pose.x": temp["pose.x"],
                "pose.y": temp["pose.y"],
                "pose.z": temp["pose.z"],
                "quaternion.qx": temp["quaternion.qx"],
                "quaternion.qy": temp["quaternion.qy"],
                "quaternion.qz": temp["quaternion.qz"],
                "quaternion.qw": temp["quaternion.qw"],
            }
        else:
            self.servo_joint_pos(action["joints"], 0)
            with self.hand_lock:
                self.hand_joints = [
                    temp["Thumb1_1.pos"],
                    temp["Thumb1_3.pos"],
                    temp["Index1.pos"],
                    temp["Middle1.pos"],
                    temp["Ring1.pos"],
                    temp["Pinky1.pos"],
                ]
            return {
                "joint1.pos": action["joints"][0],
                "joint2.pos": action["joints"][1],
                "joint3.pos": action["joints"][2],
                "joint4.pos": action["joints"][3],
                "joint5.pos": action["joints"][4],
                "joint6.pos": action["joints"][5],
                "pose.x": temp["pose.x"],
                "pose.y": temp["pose.y"],
                "pose.z": temp["pose.z"],
                "quaternion.qx": temp["quaternion.qx"],
                "quaternion.qy": temp["quaternion.qy"],
                "quaternion.qz": temp["quaternion.qz"],
                "quaternion.qw": temp["quaternion.qw"],
                "Thumb1_1.pos": temp["Thumb1_1.pos"],
                "Thumb1_3.pos": temp["Thumb1_3.pos"],
                "Index1.pos": temp["Index1.pos"],
                "Middle1.pos": temp["Middle1.pos"],
                "Ring1.pos": temp["Ring1.pos"],
                "Pinky1.pos": temp["Pinky1.pos"],
            }

    def return_zero(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")

        joints = [0.0] * (self.config.arm_joints_num - 1)
        velocities = [0.8] * (self.config.arm_joints_num - 1)
        effort = [10.0] * (self.config.arm_joints_num - 1)

        if self.config.eef_device == "G2":
            while True:
                state = self.get_joint_pos()
                arm_arrived = self.is_arm_arrive(joints, state)
                eef_arrived = self.is_eef_arrive(joints[6], state[6])
                if arm_arrived and eef_arrived:
                    break
                else:
                    self.arm.pvt(joints, velocities, effort)
        else:
            while True:
                state = self.get_joint_pos()
                arm_arrived = self.is_arm_arrive(joints, state[0])
                if arm_arrived:
                    break
                else:
                    self.arm.pvt(joints, velocities, effort)
                    self.hand_joints = [0] * 6
                    time.sleep(0.004)

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
        self.arm.uninit()
        if self.config.eef_device != "G2":
            self.hand.uninit()
            print("Hand uninitialized.")
        logger.info("Motors disabled and uninitialized")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected.")
        try:
            self._safe_shutdown()
        except Exception as e:
            logger.error(f"Safe shutdown failed: {e}")
            self.disable_motors()
            self.arm.uninit()
            if self.config.eef_device != "G2":
                self.hand.uninit()
                print("Hand uninitialized.")
        self._is_connected = False
        logger.info(f"{self} safely disconnected.")
