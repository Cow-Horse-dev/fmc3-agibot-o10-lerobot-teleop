from __future__ import annotations

import numpy as np


NUM_O10_ARM_JOINTS = 6


def rotation_matrix_from_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=float,
    )


def rpy_from_rotation_matrix(rotation: np.ndarray) -> list[float]:
    sy = np.sqrt(rotation[0, 0] * rotation[0, 0] + rotation[1, 0] * rotation[1, 0])
    singular = sy < 1e-6
    if not singular:
        roll = np.arctan2(rotation[2, 1], rotation[2, 2])
        pitch = np.arctan2(-rotation[2, 0], sy)
        yaw = np.arctan2(rotation[1, 0], rotation[0, 0])
    else:
        roll = np.arctan2(-rotation[1, 2], rotation[1, 1])
        pitch = np.arctan2(-rotation[2, 0], sy)
        yaw = 0.0
    return [float(roll), float(pitch), float(yaw)]


def apply_eef_delta_to_pose(current_pose: np.ndarray, eef_delta: list[float]) -> np.ndarray:
    target_pose = np.array(current_pose, dtype=float, copy=True)
    target_pose[:3, 3] += np.array(eef_delta[:3], dtype=float)
    target_pose[:3, :3] = target_pose[:3, :3] @ rotation_matrix_from_rpy(*eef_delta[3:6])
    return target_pose


def solve_o10_ik(
    arm_kdl,
    target_pose: np.ndarray,
    seed_joints: list[float],
    *,
    num_arm_joints: int = NUM_O10_ARM_JOINTS,
) -> list[float]:
    try:
        result = arm_kdl.inverse_kinematics(target_pose, seed_joints, force_calculate=True)
    except TypeError:
        result = arm_kdl.inverse_kinematics(target_pose, seed_joints)
    if len(result) == 0:
        raise RuntimeError("Agibot O10 eef_delta IK failed; refusing to send an arm target.")
    return [float(value) for value in result[0][:num_arm_joints]]


def homogeneous_matrix_to_pose(matrix) -> np.ndarray:
    matrix = np.array(matrix)
    if matrix.shape != (4, 4):
        raise ValueError("输入必须是4x4矩阵")

    position = matrix[:3, 3].flatten()
    rotation_matrix = matrix[:3, :3]
    quaternion = rotation_matrix_to_quaternion(rotation_matrix)
    return np.concatenate([position, quaternion])


def rotation_matrix_to_quaternion(rotation: np.ndarray) -> np.ndarray:
    if not np.allclose(np.dot(rotation, rotation.T), np.eye(3), atol=1e-8):
        raise ValueError("旋转矩阵不满足正交条件")

    quaternion = np.zeros(4)
    trace = np.trace(rotation)

    if trace > 0:
        scalar = np.sqrt(trace + 1.0) * 2
        quaternion[3] = 0.25 * scalar
        quaternion[0] = (rotation[2, 1] - rotation[1, 2]) / scalar
        quaternion[1] = (rotation[0, 2] - rotation[2, 0]) / scalar
        quaternion[2] = (rotation[1, 0] - rotation[0, 1]) / scalar
    elif (rotation[0, 0] > rotation[1, 1]) and (rotation[0, 0] > rotation[2, 2]):
        scalar = np.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2
        quaternion[3] = (rotation[2, 1] - rotation[1, 2]) / scalar
        quaternion[0] = 0.25 * scalar
        quaternion[1] = (rotation[0, 1] + rotation[1, 0]) / scalar
        quaternion[2] = (rotation[0, 2] + rotation[2, 0]) / scalar
    elif rotation[1, 1] > rotation[2, 2]:
        scalar = np.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2
        quaternion[3] = (rotation[0, 2] - rotation[2, 0]) / scalar
        quaternion[0] = (rotation[0, 1] + rotation[1, 0]) / scalar
        quaternion[1] = 0.25 * scalar
        quaternion[2] = (rotation[1, 2] + rotation[2, 1]) / scalar
    else:
        scalar = np.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2
        quaternion[3] = (rotation[1, 0] - rotation[0, 1]) / scalar
        quaternion[0] = (rotation[0, 2] + rotation[2, 0]) / scalar
        quaternion[1] = (rotation[1, 2] + rotation[2, 1]) / scalar
        quaternion[2] = 0.25 * scalar

    return quaternion / np.linalg.norm(quaternion)
