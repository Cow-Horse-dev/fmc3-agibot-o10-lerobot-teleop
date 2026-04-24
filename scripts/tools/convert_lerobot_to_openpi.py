#!/usr/bin/env python3
"""将 LeRobot v3.0 双臂数据集转换为 openpi 训练格式。

输入：LeRobot v3.0 数据集
  - 3 路相机（top, left_wrist, right_wrist）
  - 46D 关节状态（左右臂各 6 + 左右手各 10 + 左右 EEF pose 各 7）
  - 6D 触觉均值（左右手各 thumb_avg, index_avg, middle_avg）
  - 32D action（左右臂各 6 + 左右手各 10）

输出：openpi 兼容格式（HDF5 / tfrecord）

用法：
    python scripts/tools/convert_lerobot_to_openpi.py \\
        --input ~/workspace/dataset/Robot/agi_arm_bot/pen_touch_camera_dual_YYYYMMDD \\
        --output ~/workspace/dataset/openpi/pen_touch_camera_dual \\
        --task "pen touch camera"
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 维度常量
# ---------------------------------------------------------------------------
STATE_DIM = 46       # 左右臂各 6 + 左右手各 10 + 左右 EEF pose 各 7
TACTILE_DIM = 6      # 左右手各 thumb_avg, index_avg, middle_avg
ACTION_DIM = 32      # 左右臂各 6 + 左右手各 10
IMAGE_SIZE = 224     # SigLIP 输入尺寸
CAMERA_NAMES = ["top", "left_wrist", "right_wrist"]


# ---------------------------------------------------------------------------
# 数据读取
# ---------------------------------------------------------------------------

def load_lerobot_dataset(dataset_path: str):
    """加载 LeRobot v3.0 数据集。

    Returns:
        LeRobotDataset 实例。
    """
    # TODO: 确认 lerobot 版本 API，可能需要调整 import 路径
    from lerobot.common.datasets.lerobot_dataset import LeRobotDataset

    ds = LeRobotDataset(dataset_path)
    logger.info("Loaded dataset from %s — %d episodes", dataset_path, ds.num_episodes)
    return ds


def resize_image(img: np.ndarray, size: int = IMAGE_SIZE) -> np.ndarray:
    """将图像 resize 到 (size, size, 3)，用于 SigLIP 输入。"""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("需要 Pillow: pip install Pillow")

    pil_img = Image.fromarray(img)
    pil_img = pil_img.resize((size, size), Image.BILINEAR)
    return np.array(pil_img)


# ---------------------------------------------------------------------------
# 单 episode 转换
# ---------------------------------------------------------------------------

def convert_episode(episode_data: dict, task: str) -> dict:
    """将单个 episode 的 LeRobot 数据转为 openpi 格式字典。

    Args:
        episode_data: LeRobot episode 数据（含 observation.state, action, 相机图像等）。
        task: 任务描述字符串。

    Returns:
        dict，包含 openpi 所需的各字段。
    """
    # --- 关节状态 46D ---
    state = np.array(episode_data["observation.state"], dtype=np.float32)
    assert state.shape[-1] == STATE_DIM, f"Expected state dim {STATE_DIM}, got {state.shape[-1]}"

    # --- 触觉均值 6D ---
    # TODO: 确认 LeRobot 数据集中触觉字段的实际 key 名
    tactile_keys = [
        "observation.tactile.left_thumb_avg",
        "observation.tactile.left_index_avg",
        "observation.tactile.left_middle_avg",
        "observation.tactile.right_thumb_avg",
        "observation.tactile.right_index_avg",
        "observation.tactile.right_middle_avg",
    ]
    tactile_parts = []
    for key in tactile_keys:
        if key in episode_data:
            tactile_parts.append(np.array(episode_data[key], dtype=np.float32).reshape(-1, 1))
        else:
            logger.warning("Missing tactile key %s — filling with zeros", key)
            tactile_parts.append(np.zeros((state.shape[0], 1), dtype=np.float32))
    tactile = np.concatenate(tactile_parts, axis=-1)  # (T, 6)

    # 拼接为 52D 状态向量
    full_state = np.concatenate([state, tactile], axis=-1)  # (T, 52)

    # --- Action 32D ---
    action = np.array(episode_data["action"], dtype=np.float32)
    assert action.shape[-1] == ACTION_DIM, f"Expected action dim {ACTION_DIM}, got {action.shape[-1]}"

    # --- 相机图像 ---
    images = {}
    for cam_name in CAMERA_NAMES:
        key = f"observation.images.{cam_name}"
        if key in episode_data:
            raw_imgs = episode_data[key]  # (T, H, W, 3) or list
            resized = np.stack([resize_image(img) for img in raw_imgs])
            images[cam_name] = resized
        else:
            logger.warning("Missing camera %s — skipping", cam_name)

    # TODO: 按 openpi 实际要求组装最终输出格式
    # openpi 可能需要 tfrecord / HDF5 / 自定义 dict
    return {
        "state": full_state,
        "action": action,
        "images": images,
        "task": task,
    }


# ---------------------------------------------------------------------------
# 写出
# ---------------------------------------------------------------------------

def write_openpi_dataset(episodes: list[dict], output_dir: Path) -> None:
    """将转换后的 episode 列表写入 openpi 格式。

    TODO: 根据 openpi 实际数据加载接口实现具体写出逻辑。
    当前骨架以 numpy npz 格式保存，后续替换为 openpi 原生格式。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for idx, ep in enumerate(episodes):
        ep_path = output_dir / f"episode_{idx:06d}.npz"
        np.savez_compressed(
            ep_path,
            state=ep["state"],
            action=ep["action"],
            task=ep["task"],
            **{f"image_{k}": v for k, v in ep["images"].items()},
        )
        if (idx + 1) % 100 == 0:
            logger.info("Wrote %d / %d episodes", idx + 1, len(episodes))

    logger.info("Done — %d episodes saved to %s", len(episodes), output_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="LeRobot v3.0 → openpi 数据转换")
    parser.add_argument("--input", required=True, help="LeRobot 数据集路径")
    parser.add_argument("--output", required=True, help="openpi 输出目录")
    parser.add_argument("--task", default="pen touch camera", help="任务描述")
    args = parser.parse_args()

    ds = load_lerobot_dataset(args.input)
    output_dir = Path(args.output).expanduser()

    episodes = []
    for ep_idx in range(ds.num_episodes):
        # TODO: 确认 LeRobot v3.0 按 episode 取数据的 API
        ep_data = ds[ep_idx]
        converted = convert_episode(ep_data, task=args.task)
        episodes.append(converted)

    write_openpi_dataset(episodes, output_dir)


if __name__ == "__main__":
    main()
