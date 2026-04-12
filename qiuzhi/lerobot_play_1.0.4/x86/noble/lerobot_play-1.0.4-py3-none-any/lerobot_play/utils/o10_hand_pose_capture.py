from __future__ import annotations

from pathlib import Path
from typing import Callable, TYPE_CHECKING

from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AgibotO10Hand,
    normalize_handedness,
)
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore

if TYPE_CHECKING:
    from lerobot_play.teleoperators.pico_leader_single_arm_agibot_o10.agibot_o10_hand import (
        AgibotO10GloveTeleoperator,
    )


O10_HAND_POSE_KIND_FULL_RESET = "full_reset"
O10_HAND_POSE_KIND_GRASP_PRESET = "grasp_preset"


def normalize_o10_hand_pose_kind(pose_kind: str) -> str:
    normalized_pose_kind = str(pose_kind).strip().lower()
    if normalized_pose_kind not in {
        O10_HAND_POSE_KIND_FULL_RESET,
        O10_HAND_POSE_KIND_GRASP_PRESET,
    }:
        raise ValueError(
            "Unsupported O10 hand pose kind: "
            f"{pose_kind}. Expected one of: full_reset, grasp_preset"
        )
    return normalized_pose_kind


def default_o10_hand_pose_path(repo_root: Path, handedness: str, pose_kind: str) -> Path:
    normalized_handedness = normalize_handedness(handedness)
    normalized_pose_kind = normalize_o10_hand_pose_kind(pose_kind)
    suffix = (
        "hand_full_reset_pose.json"
        if normalized_pose_kind == O10_HAND_POSE_KIND_FULL_RESET
        else "hand_grasp_preset_pose.json"
    )
    return repo_root.expanduser().resolve() / "configs" / f"o10_{normalized_handedness}_{suffix}"


def default_o10_hand_pose_description(handedness: str, pose_kind: str) -> str:
    normalized_handedness = normalize_handedness(handedness)
    normalized_pose_kind = normalize_o10_hand_pose_kind(pose_kind)
    if normalized_pose_kind == O10_HAND_POSE_KIND_FULL_RESET:
        return (
            f"O10 {normalized_handedness}手全手控制默认复位手型。"
            "用于 Y 键复位、启动复位、退出复位，以及 full_hand 模式的基础手型。"
        )
    return (
        f"O10 {normalized_handedness}手固定抓取手型骨架。"
        "用于 grasp_preset 模式下未激活手指的锁定姿态，以及拇指横向姿态基准。"
    )


def format_o10_hand_joint_report(title: str, joint_values: list[float]) -> str:
    lines = [title]
    for feature_name, joint_value in zip(
        AGIBOT_O10_HAND_FEATURE_NAMES,
        joint_values,
        strict=True,
    ):
        lines.append(f"  {feature_name}: {joint_value:.6f}")
    return "\n".join(lines)


def save_o10_hand_joint_target(
    output_path: str | Path,
    joint_values: list[float],
    *,
    description: str | None = None,
) -> list[float]:
    store = PersistentJointTargetStore(
        feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
        path=output_path,
        label="Agibot O10 hand joint target",
    )
    return store.save(joint_values, description=description)


def capture_robot_o10_hand_joint_pos(
    *,
    handedness: str,
    channel_mode: str,
    device_id: int,
    canfd_id: int,
    channel_id: int | None,
    hand_factory: Callable[..., AgibotO10Hand] = AgibotO10Hand,
) -> list[float]:
    hand = hand_factory(
        handedness=handedness,
        channel_mode=channel_mode,
        device_id=device_id,
        canfd_id=canfd_id,
        channel_id=channel_id,
    )
    hand.connect()
    try:
        return hand.read_active_joint_angles()
    finally:
        hand.disconnect()


def capture_glove_o10_hand_joint_pos(
    *,
    handedness: str,
    timeout_s: float,
    glove_factory: Callable[..., object] | None = None,
) -> list[float]:
    if glove_factory is None:
        from lerobot_play.teleoperators.pico_leader_single_arm_agibot_o10.agibot_o10_hand import (
            AgibotO10GloveTeleoperator,
        )

        glove_factory = AgibotO10GloveTeleoperator

    glove = glove_factory(handedness=handedness)
    if not glove.init():
        raise RuntimeError(
            "Failed to initialize the UDE glove receiver for Agibot O10. "
            "Please make sure HDService/HandDriver is running and the glove is online."
        )

    glove.start_listening()
    try:
        if not glove.wait_until_ready(timeout_s=timeout_s):
            raise RuntimeError(
                "Failed to receive fresh UDE glove data for Agibot O10 within "
                f"{timeout_s:.1f}s. Please confirm the correct glove role is online in HDWeb."
            )
        return glove.get_hand_data()
    finally:
        glove.stop()
