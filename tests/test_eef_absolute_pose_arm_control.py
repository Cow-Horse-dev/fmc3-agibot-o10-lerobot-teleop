#!/usr/bin/env python3
"""Smoke test for controlling an Agibot O10 arm with an absolute EEF pose.

The absolute pose is expressed in the same base frame used by
``robot.arm_kdl.forward_kinematics``:

    python tests/test_eef_absolute_pose_arm_control.py --hand right --read-current
    python tests/test_eef_absolute_pose_arm_control.py --hand right --x 0.30 --y -0.10 --z 0.25

Default mode is dry-run and does not connect to hardware. To move a real arm,
pass --execute explicitly:

    python tests/test_eef_absolute_pose_arm_control.py \
      --hand right --x 0.30 --y -0.10 --z 0.25 --execute

When --roll/--pitch/--yaw are omitted in --execute mode, the script preserves
the current EEF orientation and only moves to the requested absolute xyz.
In --ik-only mode, omitted orientation values preserve the seed/reset EEF
orientation.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
MMK2_KDL_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "mmk2_kdl_py-0.1.4-py3-none-any"
)

for package_root in (LEROBOT_PLAY_ROOT, MMK2_KDL_ROOT):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


ARM_FEATURE_NAMES = tuple(f"joint{index}.pos" for index in range(1, 7))
HAND_FEATURE_NAMES = (
    "thumb_cm_roll.pos",
    "thumb_cm_yaw.pos",
    "thumb_cm_pitch.pos",
    "index_mp_yaw.pos",
    "index_mp_pitch.pos",
    "middle_mp_pitch.pos",
    "ring_mp_yaw.pos",
    "ring_mp_pitch.pos",
    "pinky_mp_yaw.pos",
    "pinky_mp_pitch.pos",
)


@dataclass(frozen=True)
class AbsolutePose:
    x: float
    y: float
    z: float
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


@dataclass(frozen=True)
class IkCandidate:
    label: str
    joints: list[float]


def default_port(handedness: str) -> str:
    return "can0" if handedness == "left" else "can1"


def default_reset_poses_path() -> Path:
    return REPO_ROOT / "configs" / "reset_poses" / "o10_dual_reset.json"


def load_reset_arm_joints(path: str | Path, handedness: str) -> list[float]:
    filepath = Path(path).expanduser()
    data = json.loads(filepath.read_text(encoding="utf-8"))
    arm_section = data["arm"]
    feature_names = arm_section["feature_names"]
    side_values = arm_section[handedness]
    return [float(side_values[name]) for name in feature_names]


def rotation_matrix_from_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=float,
    )


def pose_matrix_from_xyz_rpy(pose: AbsolutePose) -> np.ndarray:
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = rotation_matrix_from_rpy(pose.roll, pose.pitch, pose.yaw)
    matrix[:3, 3] = [pose.x, pose.y, pose.z]
    return matrix


def rpy_from_rotation_matrix(rotation: np.ndarray) -> tuple[float, float, float]:
    sy = math.sqrt(float(rotation[0, 0] ** 2 + rotation[1, 0] ** 2))
    singular = sy < 1e-6
    if not singular:
        roll = math.atan2(float(rotation[2, 1]), float(rotation[2, 2]))
        pitch = math.atan2(float(-rotation[2, 0]), sy)
        yaw = math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))
    else:
        roll = math.atan2(float(-rotation[1, 2]), float(rotation[1, 1]))
        pitch = math.atan2(float(-rotation[2, 0]), sy)
        yaw = 0.0
    return roll, pitch, yaw


def absolute_pose_from_matrix(matrix: np.ndarray) -> AbsolutePose:
    matrix = np.array(matrix, dtype=float)
    if matrix.shape != (4, 4):
        raise ValueError(f"Expected 4x4 pose matrix, got shape {matrix.shape}")
    roll, pitch, yaw = rpy_from_rotation_matrix(matrix[:3, :3])
    return AbsolutePose(
        x=float(matrix[0, 3]),
        y=float(matrix[1, 3]),
        z=float(matrix[2, 3]),
        roll=roll,
        pitch=pitch,
        yaw=yaw,
    )


def translation_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.array(a[:3, 3], dtype=float) - np.array(b[:3, 3], dtype=float)))


def validate_target_distance(current_pose: np.ndarray, target_pose: np.ndarray, max_distance: float) -> None:
    distance = translation_distance(current_pose, target_pose)
    if distance > max_distance:
        current_xyz = ", ".join(f"{value:+.4f}" for value in current_pose[:3, 3])
        target_xyz = ", ".join(f"{value:+.4f}" for value in target_pose[:3, 3])
        raise ValueError(
            f"Target is {distance:.4f} m from current EEF pose, "
            f"exceeds --max-distance {max_distance:.4f} m "
            f"(current xyz=[{current_xyz}], target xyz=[{target_xyz}])"
        )


def interpolate_pose_matrices(start_pose: np.ndarray, target_pose: np.ndarray, max_step_distance: float) -> list[np.ndarray]:
    if max_step_distance <= 0.0:
        raise ValueError("--max-step-distance must be greater than 0")
    distance = translation_distance(start_pose, target_pose)
    steps = max(1, math.ceil(distance / max_step_distance))
    waypoints: list[np.ndarray] = []
    for index in range(1, steps + 1):
        ratio = index / steps
        waypoint = np.array(target_pose, dtype=float, copy=True)
        waypoint[:3, 3] = start_pose[:3, 3] + (target_pose[:3, 3] - start_pose[:3, 3]) * ratio
        waypoints.append(waypoint)
    return waypoints


def joint_deltas(current_joints: Sequence[float], target_joints: Sequence[float]) -> list[float]:
    return [
        float(target) - float(current)
        for current, target in zip(current_joints, target_joints, strict=True)
    ]


def format_joint_deltas(current_joints: Sequence[float], target_joints: Sequence[float]) -> str:
    deltas = joint_deltas(current_joints, target_joints)
    return ", ".join(
        f"{name}={delta:+.4f}"
        for name, delta in zip(ARM_FEATURE_NAMES, deltas, strict=True)
    )


def validate_joint_delta(
    current_joints: Sequence[float],
    target_joints: Sequence[float],
    max_joint_delta: float,
) -> None:
    deltas = [abs(delta) for delta in joint_deltas(current_joints, target_joints)]
    largest_delta = max(deltas) if deltas else 0.0
    if largest_delta > max_joint_delta:
        raise ValueError(
            f"Largest IK joint delta {largest_delta:.4f} rad exceeds "
            f"--max-joint-delta {max_joint_delta:.4f} rad "
            f"({format_joint_deltas(current_joints, target_joints)})"
        )


def collect_ik_candidates(
    arm_kdl,
    target_pose: np.ndarray,
    seed_joints: Sequence[float],
) -> list[IkCandidate]:
    seed = [float(value) for value in seed_joints]
    candidates: list[IkCandidate] = []

    try:
        default_result = arm_kdl.inverse_kinematics(target_pose, seed)
        candidates.extend(
            IkCandidate(
                label=f"default[{index}]",
                joints=[float(value) for value in solution[: len(ARM_FEATURE_NAMES)]],
            )
            for index, solution in enumerate(default_result)
        )
    except TypeError:
        pass

    try:
        force_result = arm_kdl.inverse_kinematics(target_pose, seed, force_calculate=True)
        candidates.extend(
            IkCandidate(
                label=f"force_calculate[{index}]",
                joints=[float(value) for value in solution[: len(ARM_FEATURE_NAMES)]],
            )
            for index, solution in enumerate(force_result)
        )
    except TypeError:
        pass
    return candidates


def solve_ik(arm_kdl, target_pose: np.ndarray, seed_joints: Sequence[float]) -> list[float]:
    seed = [float(value) for value in seed_joints]
    candidates = collect_ik_candidates(arm_kdl, target_pose, seed)
    if not candidates:
        raise RuntimeError("IK failed for the requested absolute EEF pose.")

    def solution_distance(candidate: IkCandidate) -> float:
        return float(np.linalg.norm(np.array(candidate.joints, dtype=float) - np.array(seed, dtype=float)))

    best_solution = min(candidates, key=solution_distance)
    return best_solution.joints.copy()


def solve_numerical_ik(arm_kdl, target_pose: np.ndarray, seed_joints: Sequence[float]) -> list[float]:
    seed = np.array(seed_joints, dtype=float)
    result = arm_kdl.solve_ik(target_pose, method="numerical", current_q=seed)
    return [float(value) for value in np.array(result, dtype=float).reshape(-1)[: len(ARM_FEATURE_NAMES)]]


def rotation_vector_from_matrix(rotation: np.ndarray) -> np.ndarray:
    trace = float(np.trace(rotation))
    cos_theta = np.clip((trace - 1.0) / 2.0, -1.0, 1.0)
    theta = float(np.arccos(cos_theta))
    axis_scaled = np.array(
        [
            rotation[2, 1] - rotation[1, 2],
            rotation[0, 2] - rotation[2, 0],
            rotation[1, 0] - rotation[0, 1],
        ],
        dtype=float,
    )
    if theta < 1e-9:
        return axis_scaled / 2.0
    return theta * axis_scaled / (2.0 * math.sin(theta))


def pose_error_vector(actual_pose: np.ndarray, target_pose: np.ndarray, rotation_weight: float) -> np.ndarray:
    translation_error = np.array(target_pose[:3, 3], dtype=float) - np.array(actual_pose[:3, 3], dtype=float)
    rotation_error = rotation_vector_from_matrix(target_pose[:3, :3] @ actual_pose[:3, :3].T)
    return np.concatenate([translation_error, rotation_error * rotation_weight])


def numerical_pose_jacobian(
    arm_kdl,
    joints: Sequence[float],
    *,
    epsilon: float,
    rotation_weight: float,
) -> np.ndarray:
    current_joints = np.array(joints, dtype=float)
    current_pose = arm_kdl.forward_kinematics(current_joints)
    jacobian = np.zeros((6, len(ARM_FEATURE_NAMES)), dtype=float)
    for joint_index in range(len(ARM_FEATURE_NAMES)):
        plus_joints = current_joints.copy()
        minus_joints = current_joints.copy()
        plus_joints[joint_index] += epsilon
        minus_joints[joint_index] -= epsilon
        plus_pose = arm_kdl.forward_kinematics(plus_joints)
        minus_pose = arm_kdl.forward_kinematics(minus_joints)
        jacobian[:3, joint_index] = (plus_pose[:3, 3] - minus_pose[:3, 3]) / (2.0 * epsilon)
        plus_rotation_delta = rotation_vector_from_matrix(plus_pose[:3, :3] @ current_pose[:3, :3].T)
        minus_rotation_delta = rotation_vector_from_matrix(minus_pose[:3, :3] @ current_pose[:3, :3].T)
        jacobian[3:, joint_index] = (
            (plus_rotation_delta - minus_rotation_delta)
            / (2.0 * epsilon)
            * rotation_weight
        )
    return jacobian


def solve_local_ik(
    arm_kdl,
    target_pose: np.ndarray,
    seed_joints: Sequence[float],
    *,
    max_iterations: int,
    damping: float,
    max_iteration_step: float,
    rotation_weight: float,
    position_tolerance: float,
    rotation_tolerance: float,
) -> list[float]:
    current_joints = np.array(seed_joints, dtype=float)
    best_joints = current_joints.copy()
    best_score = float("inf")
    for _ in range(max_iterations):
        current_pose = arm_kdl.forward_kinematics(current_joints)
        unweighted_rotation_error = rotation_vector_from_matrix(target_pose[:3, :3] @ current_pose[:3, :3].T)
        translation_error = float(np.linalg.norm(target_pose[:3, 3] - current_pose[:3, 3]))
        rotation_error = float(np.linalg.norm(unweighted_rotation_error))
        error = pose_error_vector(current_pose, target_pose, rotation_weight)
        score = float(np.linalg.norm(error))
        if score < best_score:
            best_score = score
            best_joints = current_joints.copy()
        if translation_error <= position_tolerance and rotation_error <= rotation_tolerance:
            break
        jacobian = numerical_pose_jacobian(
            arm_kdl,
            current_joints,
            epsilon=1e-5,
            rotation_weight=rotation_weight,
        )
        damped_normal = jacobian @ jacobian.T + (damping**2) * np.eye(6)
        delta = jacobian.T @ np.linalg.solve(damped_normal, error)
        delta_norm = float(np.linalg.norm(delta))
        if delta_norm > max_iteration_step:
            delta = delta / delta_norm * max_iteration_step
        current_joints = current_joints + delta
    return [float(value) for value in best_joints]


def solve_target_joints(
    arm_kdl,
    target_pose: np.ndarray,
    seed_joints: Sequence[float],
    *,
    method: str,
    args: argparse.Namespace,
) -> list[float]:
    if method == "analytical":
        return solve_ik(arm_kdl, target_pose, seed_joints)
    if method == "numerical":
        return solve_numerical_ik(arm_kdl, target_pose, seed_joints)
    if method == "local":
        return solve_local_ik(
            arm_kdl,
            target_pose,
            seed_joints,
            max_iterations=args.local_ik_iterations,
            damping=args.local_ik_damping,
            max_iteration_step=args.local_ik_max_step,
            rotation_weight=args.local_ik_rotation_weight,
            position_tolerance=args.max_ik_position_error,
            rotation_tolerance=args.max_ik_rotation_error,
        )
    raise ValueError("--ik-method both is only for --ik-only comparison; choose analytical, numerical, or local for --execute")


def validate_ik_accuracy(
    arm_kdl,
    target_pose: np.ndarray,
    target_joints: Sequence[float],
    *,
    max_position_error: float,
    max_rotation_error: float,
) -> None:
    actual_pose = arm_kdl.forward_kinematics(target_joints)
    position_error = translation_distance(actual_pose, target_pose)
    rotation_error = float(
        np.linalg.norm(rotation_vector_from_matrix(target_pose[:3, :3] @ actual_pose[:3, :3].T))
    )
    if position_error > max_position_error:
        raise ValueError(
            f"IK FK position error {position_error:.6f} m exceeds "
            f"--max-ik-position-error {max_position_error:.6f} m"
        )
    if rotation_error > max_rotation_error:
        raise ValueError(
            f"IK FK rotation error {rotation_error:.6f} rad exceeds "
            f"--max-ik-rotation-error {max_rotation_error:.6f} rad"
        )


def print_pose(title: str, pose: AbsolutePose) -> None:
    print(f"\n{title}:")
    print(f"  {'pose.x':>16s}: {pose.x:+.6f}")
    print(f"  {'pose.y':>16s}: {pose.y:+.6f}")
    print(f"  {'pose.z':>16s}: {pose.z:+.6f}")
    print(f"  {'roll':>16s}: {pose.roll:+.6f}")
    print(f"  {'pitch':>16s}: {pose.pitch:+.6f}")
    print(f"  {'yaw':>16s}: {pose.yaw:+.6f}")


def print_joint_vector(title: str, names: Sequence[str], values: Sequence[float]) -> None:
    print(f"\n{title}:")
    for name, value in zip(names, values, strict=True):
        print(f"  {name:>25s}: {float(value):+.6f}")


def print_joint_deltas(title: str, current_joints: Sequence[float], target_joints: Sequence[float]) -> None:
    print(f"\n{title}:")
    for name, delta in zip(ARM_FEATURE_NAMES, joint_deltas(current_joints, target_joints), strict=True):
        print(f"  {name:>25s}: {delta:+.6f}")


def print_ik_candidates(candidates: Sequence[IkCandidate], seed_joints: Sequence[float]) -> None:
    if not candidates:
        print("\nNo IK candidates.")
        return
    for candidate in rank_ik_candidates(candidates, seed_joints):
        distance = float(
            np.linalg.norm(np.array(candidate.joints, dtype=float) - np.array(seed_joints, dtype=float))
        )
        print_joint_vector(f"IK candidate {candidate.label} (distance={distance:.6f})", ARM_FEATURE_NAMES, candidate.joints)
        print_joint_deltas(f"IK candidate {candidate.label} deltas", seed_joints, candidate.joints)


def print_ik_solution(
    title: str,
    solution_joints: Sequence[float],
    seed_joints: Sequence[float],
    arm_kdl,
    target_matrix: np.ndarray,
) -> None:
    print_joint_vector(title, ARM_FEATURE_NAMES, solution_joints)
    print_joint_deltas(f"{title} deltas", seed_joints, solution_joints)
    actual_matrix = arm_kdl.forward_kinematics(solution_joints)
    translation_error = translation_distance(actual_matrix, target_matrix)
    rotation_error = float(np.linalg.norm(actual_matrix[:3, :3] - target_matrix[:3, :3]))
    print(f"\n{title} FK error:")
    print(f"  {'translation_m':>25s}: {translation_error:.6f}")
    print(f"  {'rotation_frobenius':>25s}: {rotation_error:.6f}")


def rank_ik_candidates(candidates: Sequence[IkCandidate], seed_joints: Sequence[float]) -> list[IkCandidate]:
    seed = np.array(seed_joints, dtype=float)
    return sorted(
        candidates,
        key=lambda candidate: np.linalg.norm(np.array(candidate.joints, dtype=float) - seed),
    )


def target_pose_from_args(
    args: argparse.Namespace,
    fallback_orientation: AbsolutePose | None = None,
) -> AbsolutePose:
    missing = [name for name in ("x", "y", "z") if getattr(args, name) is None]
    if missing:
        raise ValueError(f"Absolute pose requires --x, --y, and --z; missing: {', '.join(missing)}")
    return AbsolutePose(
        x=float(args.x),
        y=float(args.y),
        z=float(args.z),
        roll=float(args.roll if args.roll is not None else (fallback_orientation.roll if fallback_orientation else 0.0)),
        pitch=float(args.pitch if args.pitch is not None else (fallback_orientation.pitch if fallback_orientation else 0.0)),
        yaw=float(args.yaw if args.yaw is not None else (fallback_orientation.yaw if fallback_orientation else 0.0)),
    )


def run_dry_run(args: argparse.Namespace) -> int:
    target = target_pose_from_args(args)
    target_matrix = pose_matrix_from_xyz_rpy(target)
    current_for_preview = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0))
    preview_waypoints = interpolate_pose_matrices(current_for_preview, target_matrix, args.max_step_distance)

    print("DRY RUN: no hardware connection and no arm movement.")
    print(f"Hand: {args.hand}")
    print(f"CAN port: {args.port or default_port(args.hand)}")
    if args.roll is None or args.pitch is None or args.yaw is None:
        print("Dry-run has no current arm pose, so omitted orientation values preview as 0.0 rad.")
    print_pose("Requested absolute EEF pose", target)
    print(f"\nPreview from origin would use {len(preview_waypoints)} waypoint(s).")
    print(f"Real execute mode computes waypoints from the current EEF pose.")
    print("\nTarget 4x4 matrix:")
    print(np.array2string(target_matrix, precision=6, suppress_small=False))
    print("\nPass --execute to solve IK and move the real arm.")
    print("Use --read-current first to get the current absolute EEF coordinates.")
    return 0


def run_ik_only(args: argparse.Namespace) -> int:
    from mmk2_kdl_py import ArmKdlNumerical

    seed_joints = (
        [float(value) for value in args.seed_joints]
        if args.seed_joints is not None
        else load_reset_arm_joints(args.reset_poses_path, args.hand)
    )
    if len(seed_joints) != len(ARM_FEATURE_NAMES):
        raise ValueError(f"--seed-joints expects {len(ARM_FEATURE_NAMES)} values")

    arm_kdl = ArmKdlNumerical(eef_type=args.eef_type)
    seed_pose = absolute_pose_from_matrix(arm_kdl.forward_kinematics(seed_joints))
    target = target_pose_from_args(args, fallback_orientation=seed_pose)
    target_matrix = pose_matrix_from_xyz_rpy(target)
    candidates = collect_ik_candidates(arm_kdl, target_matrix, seed_joints)

    print("IK ONLY: no CAN connection and no arm movement.")
    print(f"Hand: {args.hand}")
    print(f"EEF type: {args.eef_type}")
    print_joint_vector("Seed arm joints", ARM_FEATURE_NAMES, seed_joints)
    print_pose("Seed absolute EEF pose", seed_pose)
    if args.roll is None or args.pitch is None or args.yaw is None:
        print("\nMissing --roll/--pitch/--yaw values preserve the seed EEF orientation.")
    print_pose("Target absolute EEF pose", target)
    print("\nTarget 4x4 matrix:")
    print(np.array2string(target_matrix, precision=6, suppress_small=False))
    if args.ik_method in ("analytical", "both") and candidates:
        ranked_candidates = rank_ik_candidates(candidates, seed_joints)
        print_ik_candidates(
            ranked_candidates if args.show_all_ik else ranked_candidates[:1],
            seed_joints,
        )
        if not args.show_all_ik and len(candidates) > 1:
            print(f"\n{len(candidates) - 1} additional IK candidate(s) hidden; pass --show-all-ik to print them.")
    elif args.ik_method in ("analytical", "both"):
        print_ik_candidates(candidates, seed_joints)

    numerical_solution = None
    if args.ik_method in ("numerical", "both"):
        numerical_solution = solve_numerical_ik(arm_kdl, target_matrix, seed_joints)
        print_ik_solution(
            "Numerical IK solution",
            numerical_solution,
            seed_joints,
            arm_kdl,
            target_matrix,
        )

    return 0 if candidates or numerical_solution is not None else 1


def move_to_joint_target(
    robot,
    target_joints: Sequence[float],
    *,
    timeout: float,
    interval: float,
    tolerance: float,
    velocity: float,
    effort: float,
) -> bool:
    deadline = time.monotonic() + timeout
    target = [float(value) for value in target_joints]
    while time.monotonic() < deadline:
        current_joints, _ = robot.get_joint_pos()
        current = current_joints[: len(ARM_FEATURE_NAMES)]
        if all(abs(target_value - current_value) <= tolerance for target_value, current_value in zip(target, current, strict=True)):
            return True
        robot.servo_joint_pos(target, vel=velocity, eff=effort)
        time.sleep(interval)
    return False


def perform_start_reset(robot, args: argparse.Namespace) -> None:
    if args.skip_start_reset or args.read_current:
        return
    print("\nReturning to configured reset pose before absolute EEF move...")
    robot.return_zero()
    time.sleep(args.reset_settle)


def build_robot(args: argparse.Namespace):
    from lerobot_play.robots.pico_follower_single_arm_agibot_o10.airbot_pico_follower_single_arm_agibot_o10 import (
        PicoFollowerSingleArmAgibotO10,
    )
    from lerobot_play.robots.pico_follower_single_arm_agibot_o10.config_pico_follower_single_arm_agibot_o10 import (
        PicoFollowerSingleArmAgibotO10Config,
    )

    config = PicoFollowerSingleArmAgibotO10Config(
        port=args.port or default_port(args.hand),
        handedness=args.hand,
        enable_hand=args.enable_hand,
        allow_camera_read_failures=True,
        cameras={},
        action_control_mode="joint",
        hand_action_mode="dexterous_10d",
        reset_poses_path=str(Path(args.reset_poses_path).expanduser()),
        reset_gesture=args.reset_gesture,
    )
    return PicoFollowerSingleArmAgibotO10(config)


def run_execute(args: argparse.Namespace) -> int:
    robot = build_robot(args)
    port = args.port or default_port(args.hand)

    print(f"Connecting {args.hand} arm on {port}...")
    robot.connect()
    try:
        perform_start_reset(robot, args)

        current_joints, current_hand = robot.get_joint_pos()
        current_joints = current_joints[: len(ARM_FEATURE_NAMES)]
        current_pose_matrix = robot.arm_kdl.forward_kinematics(current_joints)
        current_pose = absolute_pose_from_matrix(current_pose_matrix)
        print_joint_vector("Current arm joints", ARM_FEATURE_NAMES, current_joints)
        print_pose("Current absolute EEF pose", current_pose)
        if args.enable_hand:
            print_joint_vector("Current hand joints", HAND_FEATURE_NAMES, current_hand)

        if args.read_current:
            print("\nRead-only mode, no movement.")
            return 0

        target = target_pose_from_args(args, fallback_orientation=current_pose)
        if args.roll is None or args.pitch is None or args.yaw is None:
            print("\nMissing --roll/--pitch/--yaw values will preserve the current EEF orientation.")
        target_pose_matrix = pose_matrix_from_xyz_rpy(target)
        validate_target_distance(current_pose_matrix, target_pose_matrix, args.max_distance)
        waypoints = interpolate_pose_matrices(
            current_pose_matrix,
            target_pose_matrix,
            args.max_step_distance,
        )

        print_pose("Target absolute EEF pose", target)
        print(
            f"\nMoving through {len(waypoints)} absolute EEF waypoint(s), "
            f"max_step_distance={args.max_step_distance:.4f} m..."
        )

        arrived = True
        seed_joints = current_joints
        for index, waypoint in enumerate(waypoints, start=1):
            waypoint_pose = absolute_pose_from_matrix(waypoint)
            target_joints = solve_ik(robot.arm_kdl, waypoint, seed_joints)
            print_pose(f"Waypoint {index}/{len(waypoints)} absolute EEF pose", waypoint_pose)
            print_joint_vector(f"Waypoint {index}/{len(waypoints)} IK joints", ARM_FEATURE_NAMES, target_joints)
            print_joint_deltas(f"Waypoint {index}/{len(waypoints)} IK joint deltas", seed_joints, target_joints)
            validate_joint_delta(seed_joints, target_joints, args.max_joint_delta)
            waypoint_arrived = move_to_joint_target(
                robot,
                target_joints,
                timeout=args.timeout,
                interval=args.interval,
                tolerance=args.tolerance,
                velocity=args.velocity,
                effort=args.effort,
            )
            if not waypoint_arrived:
                arrived = False
                print(f"\nWaypoint {index}/{len(waypoints)} did not arrive within tolerance.")
                break
            seed_joints, _ = robot.get_joint_pos()
            seed_joints = seed_joints[: len(ARM_FEATURE_NAMES)]

        final_joints, _ = robot.get_joint_pos()
        final_joints = final_joints[: len(ARM_FEATURE_NAMES)]
        final_pose = absolute_pose_from_matrix(robot.arm_kdl.forward_kinematics(final_joints))
        print_joint_vector("Final arm joints", ARM_FEATURE_NAMES, final_joints)
        print_pose("Final absolute EEF pose", final_pose)
        print(f"\nArrived within tolerance: {arrived}")

        if args.return_zero:
            print("\nReturning to configured reset pose...")
            robot.return_zero()
        return 0 if arrived else 1
    finally:
        print("\nDisconnecting...")
        robot.disconnect()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test O10 absolute EEF pose control")
    parser.add_argument("--hand", choices=("left", "right"), default="right")
    parser.add_argument("--port", help="CAN port; defaults to can0 for left, can1 for right")
    parser.add_argument("--x", type=float, help="Absolute EEF x in robot base frame, meters")
    parser.add_argument("--y", type=float, help="Absolute EEF y in robot base frame, meters")
    parser.add_argument("--z", type=float, help="Absolute EEF z in robot base frame, meters")
    parser.add_argument("--roll", type=float, help="Absolute EEF roll in radians; omitted keeps current/seed roll")
    parser.add_argument("--pitch", type=float, help="Absolute EEF pitch in radians; omitted keeps current/seed pitch")
    parser.add_argument("--yaw", type=float, help="Absolute EEF yaw in radians; omitted keeps current/seed yaw")
    parser.add_argument("--max-distance", type=float, default=0.30, help="Max total target distance from current EEF pose")
    parser.add_argument("--max-step-distance", type=float, default=0.02, help="Max interpolated waypoint distance")
    parser.add_argument("--max-joint-delta", type=float, default=0.50, help="Max IK change for any one joint")
    parser.add_argument("--timeout", type=float, default=8.0, help="Move timeout in seconds")
    parser.add_argument("--interval", type=float, default=0.02, help="Seconds between PVT sends")
    parser.add_argument("--tolerance", type=float, default=0.02, help="Joint arrival tolerance in radians")
    parser.add_argument("--velocity", type=float, default=0.8, help="PVT velocity sent to each joint")
    parser.add_argument("--effort", type=float, default=8.0, help="PVT effort sent to each joint")
    parser.add_argument("--enable-hand", action="store_true", help="Also connect and print hand joints")
    parser.add_argument("--reset-gesture", choices=("pinch", "tripod"), default="pinch")
    parser.add_argument("--reset-poses-path", default=str(default_reset_poses_path()), help="Reset pose JSON used for IK seed and execute reset")
    parser.add_argument("--seed-joints", type=float, nargs=len(ARM_FEATURE_NAMES), help="IK-only seed joints; defaults to reset pose")
    parser.add_argument("--eef-type", default="none", help="ArmKdlNumerical eef_type for --ik-only")
    parser.add_argument("--ik-only", action="store_true", help="Only solve IK from reset/seed joints; no CAN and no movement")
    parser.add_argument(
        "--ik-method",
        choices=("analytical", "numerical", "local", "both"),
        default="analytical",
        help="IK solver to use; both is only for --ik-only comparison",
    )
    parser.add_argument("--local-ik-iterations", type=int, default=200, help="Max iterations for local numerical IK")
    parser.add_argument("--local-ik-damping", type=float, default=0.05, help="Damping term for local numerical IK")
    parser.add_argument("--local-ik-max-step", type=float, default=0.05, help="Max joint step per local IK iteration")
    parser.add_argument("--local-ik-rotation-weight", type=float, default=0.25, help="Rotation error weight for local IK")
    parser.add_argument("--max-ik-position-error", type=float, default=0.01, help="Max accepted local IK position error in meters")
    parser.add_argument("--max-ik-rotation-error", type=float, default=0.10, help="Max accepted local IK rotation error in radians")
    parser.add_argument("--show-all-ik", action="store_true", help="Print all IK candidates in --ik-only mode")
    parser.add_argument("--skip-start-reset", action="store_true", help="Skip the default reset before moving")
    parser.add_argument("--reset-settle", type=float, default=0.5, help="Seconds to wait after start reset")
    parser.add_argument("--return-zero", action="store_true", help="Return to reset pose before disconnect")
    parser.add_argument("--read-current", action="store_true", help="Connect, print current EEF pose, and exit")
    parser.add_argument("--execute", action="store_true", help="Connect hardware and move the arm")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.read_current and not args.execute:
        print("--read-current needs --execute because it must query the real arm.")
        return 2
    try:
        if args.ik_only:
            return run_ik_only(args)
        if args.execute:
            return run_execute(args)
        return run_dry_run(args)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2


def test_pose_matrix_from_xyz_rpy_sets_absolute_translation() -> None:
    pose = AbsolutePose(x=0.30, y=-0.10, z=0.25, roll=0.0, pitch=0.0, yaw=0.0)

    matrix = pose_matrix_from_xyz_rpy(pose)

    assert matrix.shape == (4, 4)
    assert np.allclose(matrix[:3, 3], [0.30, -0.10, 0.25])
    assert np.allclose(matrix[:3, :3], np.eye(3))


def test_pose_matrix_from_xyz_rpy_applies_absolute_yaw() -> None:
    matrix = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0, yaw=math.pi / 2))

    expected_rotation = np.array(
        [
            [0.0, -1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    assert np.allclose(matrix[:3, :3], expected_rotation)


def test_validate_target_distance_rejects_far_absolute_pose() -> None:
    current = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0))
    target = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.10, y=0.0, z=0.0))

    try:
        validate_target_distance(current, target, max_distance=0.05)
    except ValueError as exc:
        assert "exceeds --max-distance" in str(exc)
    else:
        raise AssertionError("Expected far absolute target to be rejected")


def test_interpolate_pose_matrices_splits_translation_into_safe_steps() -> None:
    start = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0))
    target = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.10, y=0.0, z=0.0, yaw=math.pi / 2))

    waypoints = interpolate_pose_matrices(start, target, max_step_distance=0.02)

    assert len(waypoints) == 5
    assert np.allclose(waypoints[0][:3, 3], [0.02, 0.0, 0.0])
    assert np.allclose(waypoints[-1][:3, 3], [0.10, 0.0, 0.0])
    assert np.allclose(waypoints[-1][:3, :3], target[:3, :3])


class _FakeResetRobot:
    def __init__(self) -> None:
        self.reset_calls = 0

    def return_zero(self) -> None:
        self.reset_calls += 1


class _FakeMultiSolutionKdl:
    def inverse_kinematics(self, target_pose, seed, force_calculate=False):
        return [
            [1.57, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.01, 0.01, -0.01, 0.0, 0.0, 0.0],
        ]


class _FakeForceVsDefaultKdl:
    def inverse_kinematics(self, target_pose, seed, force_calculate=False):
        if force_calculate:
            return [[0.0, 0.0, 0.0, -1.50, 0.0, 1.50]]
        return [[0.0, 0.02, 0.01, -0.02, 0.0, 0.02]]


class _FakeIkOnlyKdl:
    target_poses: list[np.ndarray] = []
    seed_pose = pose_matrix_from_xyz_rpy(
        AbsolutePose(x=0.125, y=0.0, z=0.212, roll=0.2, pitch=-0.1, yaw=0.4)
    )

    def __init__(self, eef_type: str) -> None:
        self.eef_type = eef_type

    def forward_kinematics(self, seed_joints):
        return self.seed_pose

    def inverse_kinematics(self, target_pose, seed, force_calculate=False):
        self.target_poses.append(np.array(target_pose, dtype=float))
        return [[0.0] * len(ARM_FEATURE_NAMES)]


class _FakeNumericalIkKdl(_FakeIkOnlyKdl):
    numerical_calls: list[tuple[str, np.ndarray]] = []

    def solve_ik(self, target_pose, method="analytical", ref_pos=None, current_q=None):
        self.numerical_calls.append((method, np.array(current_q, dtype=float)))
        return np.array([0.01, 0.02, -0.01, 0.03, -0.02, 0.01])


def test_solve_ik_chooses_solution_closest_to_seed_joints() -> None:
    seed_joints = [0.0] * len(ARM_FEATURE_NAMES)
    target_pose = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0))

    target_joints = solve_ik(_FakeMultiSolutionKdl(), target_pose, seed_joints)

    assert target_joints == [0.01, 0.01, -0.01, 0.0, 0.0, 0.0]


def test_solve_ik_prefers_default_ik_when_force_calculate_flips_wrist() -> None:
    seed_joints = [0.0] * len(ARM_FEATURE_NAMES)
    target_pose = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0))

    target_joints = solve_ik(_FakeForceVsDefaultKdl(), target_pose, seed_joints)

    assert target_joints == [0.0, 0.02, 0.01, -0.02, 0.0, 0.02]


def test_collect_ik_candidates_labels_default_and_force_solutions() -> None:
    seed_joints = [0.0] * len(ARM_FEATURE_NAMES)
    target_pose = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0))

    candidates = collect_ik_candidates(_FakeForceVsDefaultKdl(), target_pose, seed_joints)

    assert [candidate.label for candidate in candidates] == ["default[0]", "force_calculate[0]"]


def test_rank_ik_candidates_orders_by_distance_from_seed() -> None:
    seed_joints = [0.0] * len(ARM_FEATURE_NAMES)
    candidates = [
        IkCandidate(label="far", joints=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        IkCandidate(label="near", joints=[0.1, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ]

    ranked = rank_ik_candidates(candidates, seed_joints)

    assert [candidate.label for candidate in ranked] == ["near", "far"]


def test_run_ik_only_preserves_seed_orientation_when_orientation_omitted(monkeypatch) -> None:
    _FakeIkOnlyKdl.target_poses = []
    monkeypatch.setitem(
        sys.modules,
        "mmk2_kdl_py",
        types.SimpleNamespace(ArmKdlNumerical=_FakeIkOnlyKdl),
    )
    args = parse_args(
        [
            "--hand",
            "right",
            "--x",
            "0.12",
            "--y",
            "0.0",
            "--z",
            "0.22",
            "--ik-only",
            "--seed-joints",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
        ]
    )

    assert run_ik_only(args) == 0

    assert _FakeIkOnlyKdl.target_poses
    assert np.allclose(_FakeIkOnlyKdl.target_poses[0][:3, :3], _FakeIkOnlyKdl.seed_pose[:3, :3])


def test_solve_numerical_ik_uses_seed_as_current_q() -> None:
    seed_joints = [0.0, 0.1, -0.1, 0.2, -0.2, 0.3]
    target_pose = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0))
    kdl = _FakeNumericalIkKdl(eef_type="none")
    _FakeNumericalIkKdl.numerical_calls = []

    solution = solve_numerical_ik(kdl, target_pose, seed_joints)

    assert solution == [0.01, 0.02, -0.01, 0.03, -0.02, 0.01]
    assert _FakeNumericalIkKdl.numerical_calls
    method, current_q = _FakeNumericalIkKdl.numerical_calls[0]
    assert method == "numerical"
    assert np.allclose(current_q, seed_joints)


def test_run_ik_only_can_print_numerical_solution(monkeypatch, capsys) -> None:
    _FakeNumericalIkKdl.target_poses = []
    _FakeNumericalIkKdl.numerical_calls = []
    monkeypatch.setitem(
        sys.modules,
        "mmk2_kdl_py",
        types.SimpleNamespace(ArmKdlNumerical=_FakeNumericalIkKdl),
    )
    args = parse_args(
        [
            "--hand",
            "right",
            "--x",
            "0.12",
            "--y",
            "0.0",
            "--z",
            "0.22",
            "--ik-only",
            "--ik-method",
            "numerical",
            "--seed-joints",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
        ]
    )

    assert run_ik_only(args) == 0

    output = capsys.readouterr().out
    assert "Numerical IK solution" in output
    assert "Analytical IK" not in output
    assert _FakeNumericalIkKdl.numerical_calls


def test_parse_args_accepts_local_ik_method_for_execute() -> None:
    args = parse_args(
        [
            "--hand",
            "right",
            "--x",
            "0.12",
            "--y",
            "0.0",
            "--z",
            "0.22",
            "--execute",
            "--ik-method",
            "local",
        ]
    )

    assert args.ik_method == "local"


def test_solve_target_joints_rejects_both_for_execute() -> None:
    seed_joints = [0.0] * len(ARM_FEATURE_NAMES)
    target_pose = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.0, y=0.0, z=0.0))

    try:
        solve_target_joints(
            _FakeNumericalIkKdl(eef_type="none"),
            target_pose,
            seed_joints,
            method="both",
            args=parse_args(["--x", "0.0", "--y", "0.0", "--z", "0.0"]),
        )
    except ValueError as exc:
        assert "--ik-method both" in str(exc)
    else:
        raise AssertionError("Expected --ik-method both to be rejected for execution")


def test_validate_ik_accuracy_rejects_large_position_error() -> None:
    target_pose = pose_matrix_from_xyz_rpy(AbsolutePose(x=0.50, y=0.0, z=0.0))

    try:
        validate_ik_accuracy(
            _FakeIkOnlyKdl(eef_type="none"),
            target_pose,
            [0.0] * len(ARM_FEATURE_NAMES),
            max_position_error=0.001,
            max_rotation_error=1.0,
        )
    except ValueError as exc:
        assert "IK FK position error" in str(exc)
    else:
        raise AssertionError("Expected inaccurate IK result to be rejected")


def test_load_reset_arm_joints_reads_requested_side(tmp_path) -> None:
    reset_path = tmp_path / "reset.json"
    reset_path.write_text(
        """
        {
          "arm": {
            "feature_names": ["joint1.pos", "joint2.pos", "joint3.pos", "joint4.pos", "joint5.pos", "joint6.pos"],
            "right": {
              "joint1.pos": 1, "joint2.pos": 2, "joint3.pos": 3,
              "joint4.pos": 4, "joint5.pos": 5, "joint6.pos": 6
            },
            "left": {
              "joint1.pos": -1, "joint2.pos": -2, "joint3.pos": -3,
              "joint4.pos": -4, "joint5.pos": -5, "joint6.pos": -6
            }
          }
        }
        """,
        encoding="utf-8",
    )

    assert load_reset_arm_joints(reset_path, "right") == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_target_pose_from_args_preserves_fallback_orientation_when_omitted() -> None:
    args = parse_args(["--x", "0.12", "--y", "0.0", "--z", "0.22"])
    fallback = AbsolutePose(x=1.0, y=2.0, z=3.0, roll=0.1, pitch=-0.2, yaw=0.3)

    target = target_pose_from_args(args, fallback_orientation=fallback)

    assert target == AbsolutePose(x=0.12, y=0.0, z=0.22, roll=0.1, pitch=-0.2, yaw=0.3)


def test_target_pose_from_args_allows_explicit_orientation_override() -> None:
    args = parse_args(["--x", "0.12", "--y", "0.0", "--z", "0.22", "--yaw", "0.7"])
    fallback = AbsolutePose(x=1.0, y=2.0, z=3.0, roll=0.1, pitch=-0.2, yaw=0.3)

    target = target_pose_from_args(args, fallback_orientation=fallback)

    assert target == AbsolutePose(x=0.12, y=0.0, z=0.22, roll=0.1, pitch=-0.2, yaw=0.7)


def test_validate_joint_delta_reports_per_joint_deltas() -> None:
    current_joints = [0.0] * len(ARM_FEATURE_NAMES)
    target_joints = [0.0, 0.0, 1.0, 0.0, -0.75, 0.0]

    try:
        validate_joint_delta(current_joints, target_joints, max_joint_delta=0.5)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected large joint deltas to be rejected")

    assert "joint3.pos=+1.0000" in message
    assert "joint5.pos=-0.7500" in message


def test_perform_start_reset_runs_by_default() -> None:
    robot = _FakeResetRobot()
    args = parse_args(["--x", "0.1", "--y", "0.0", "--z", "0.2"])
    args.reset_settle = 0.0

    perform_start_reset(robot, args)

    assert robot.reset_calls == 1


def test_perform_start_reset_can_be_skipped() -> None:
    robot = _FakeResetRobot()
    args = parse_args(["--x", "0.1", "--y", "0.0", "--z", "0.2", "--skip-start-reset"])
    args.reset_settle = 0.0

    perform_start_reset(robot, args)

    assert robot.reset_calls == 0


def test_perform_start_reset_skips_read_current() -> None:
    robot = _FakeResetRobot()
    args = parse_args(["--execute", "--read-current"])
    args.reset_settle = 0.0

    perform_start_reset(robot, args)

    assert robot.reset_calls == 0


if __name__ == "__main__":
    raise SystemExit(main())
