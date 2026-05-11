#!/usr/bin/env python3
"""可视化 O10 130D 触觉到 12x32 heatmap 的实时效果。

常用命令：
    python scripts/tools/visualize_o10_tactile_heatmap.py --demo
    python scripts/tools/visualize_o10_tactile_heatmap.py --hand left
    python scripts/tools/visualize_o10_tactile_heatmap.py --hand right
    python scripts/tools/visualize_o10_tactile_heatmap.py --hand both
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.tools.convert_o10_tactile_heatmap import (
    HEATMAP_SHAPE,
    LayoutBlock,
    O10_130D_TO_HEATMAP_LAYOUT,
    raw_130d_to_heatmap,
)


LEROBOT_PLAY_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

PHYSICAL_HEATMAP_SHAPE = (16, 32)
FINGER_NAMES = ("thumb", "index", "middle", "ring", "little")
FINGER_RAW_RANGES = {
    "thumb": (0, 16),
    "index": (16, 32),
    "middle": (32, 48),
    "ring": (48, 64),
    "little": (64, 80),
}
PHYSICAL_FINGER_COLS = {
    "thumb": (0, 2),
    "index": (7, 9),
    "middle": (15, 17),
    "ring": (23, 25),
    "little": (30, 32),
}
PHYSICAL_HEATMAP_LAYOUT = (
    LayoutBlock("thumb", 0, 16, 0, 8, 0, 2),
    LayoutBlock("index", 16, 32, 0, 8, 7, 9),
    LayoutBlock("middle", 32, 48, 0, 8, 15, 17),
    LayoutBlock("ring", 48, 64, 0, 8, 23, 25),
    LayoutBlock("little", 64, 80, 0, 8, 30, 32),
    LayoutBlock("palm", 80, 105, 10, 15, 6, 11),
    LayoutBlock("dorsum", 105, 130, 10, 15, 21, 26),
)
RAW_TACTILE_KEYS = {
    "left": "observation.tactile.left_raw",
    "right": "observation.tactile.right_raw",
}
HEATMAP_TACTILE_KEYS = {
    "left": "observation.tactile.left",
    "right": "observation.tactile.right",
}


@dataclass(frozen=True)
class VisualLayout:
    name: str
    shape: tuple[int, int]
    blocks: tuple[LayoutBlock, ...]


VISUAL_LAYOUTS = {
    "training": VisualLayout("training", HEATMAP_SHAPE, O10_130D_TO_HEATMAP_LAYOUT),
    "physical": VisualLayout("physical", PHYSICAL_HEATMAP_SHAPE, PHYSICAL_HEATMAP_LAYOUT),
}


def _optional_cv2():
    try:
        import cv2
    except ImportError:
        return None
    return cv2


def _as_2d_float32(values: object, *, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError(f"{name} 必须是二维数组，实际 shape={array.shape}")
    return array


def _normalize_heatmap(heatmap: np.ndarray, vmin: float | None, vmax: float | None) -> np.ndarray:
    values = np.asarray(heatmap, dtype=np.float32)
    if values.ndim != 2:
        raise ValueError(f"heatmap 必须是二维数组，实际 shape={values.shape}")

    low = float(values.min() if vmin is None else vmin)
    high = float(values.max() if vmax is None else vmax)
    if high <= low:
        return np.zeros(HEATMAP_SHAPE, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def colorize_heatmap(heatmap: np.ndarray, vmin: float | None = None, vmax: float | None = None) -> np.ndarray:
    """把二维 float heatmap 转成 RGB uint8 颜色图。"""
    normalized = _normalize_heatmap(heatmap, vmin, vmax)
    stops = np.array(
        [
            [0, 0, 0],
            [0, 64, 255],
            [0, 220, 255],
            [255, 220, 0],
            [255, 32, 0],
        ],
        dtype=np.float32,
    )
    scaled = normalized * (len(stops) - 1)
    lower = np.floor(scaled).astype(np.int32)
    upper = np.clip(lower + 1, 0, len(stops) - 1)
    fraction = (scaled - lower)[..., None]
    rgb = stops[lower] * (1.0 - fraction) + stops[upper] * fraction
    return rgb.astype(np.uint8)


def _draw_rect_rgb(
    image: np.ndarray,
    top: int,
    left: int,
    bottom: int,
    right: int,
    color: tuple[int, int, int],
    thickness: int = 1,
) -> None:
    image[top : top + thickness, left:right] = color
    image[bottom - thickness : bottom, left:right] = color
    image[top:bottom, left : left + thickness] = color
    image[top:bottom, right - thickness : right] = color


def render_heatmap(
    heatmap: np.ndarray,
    *,
    title: str | None = None,
    scale: int = 24,
    vmin: float | None = None,
    vmax: float | None = None,
    layout_blocks: tuple[LayoutBlock, ...] | None = None,
) -> np.ndarray:
    """渲染单手 heatmap，返回 RGB uint8 图像。"""
    if scale < 1:
        raise ValueError(f"scale 必须 >= 1，实际 {scale}")

    heatmap = _as_2d_float32(heatmap, name="heatmap")
    rows, cols = heatmap.shape
    color = colorize_heatmap(heatmap, vmin=vmin, vmax=vmax)
    body = np.repeat(np.repeat(color, scale, axis=0), scale, axis=1)
    body_h, body_w = body.shape[:2]

    grid_color = (36, 36, 36)
    for row in range(rows + 1):
        y = min(row * scale, body_h - 1)
        body[y : y + 1, :] = grid_color
    for col in range(cols + 1):
        x = min(col * scale, body_w - 1)
        body[:, x : x + 1] = grid_color

    block_color = (245, 245, 245)
    if layout_blocks is None and heatmap.shape == HEATMAP_SHAPE:
        layout_blocks = O10_130D_TO_HEATMAP_LAYOUT
    for block in layout_blocks or ():
        _draw_rect_rgb(
            body,
            block.row_start * scale,
            block.col_start * scale,
            block.row_stop * scale,
            block.col_stop * scale,
            block_color,
            thickness=max(1, scale // 8),
        )

    if title is None:
        return body

    title_h = max(28, scale + 8)
    canvas = np.zeros((title_h + body_h, body_w, 3), dtype=np.uint8)
    canvas[:title_h] = (18, 18, 18)
    canvas[title_h:] = body

    cv2 = _optional_cv2()
    if cv2 is not None:
        cv2.putText(
            canvas,
            title,
            (8, max(20, title_h - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (235, 235, 235),
            1,
            cv2.LINE_AA,
        )
    return canvas


def render_heatmap_panel(
    heatmaps: Mapping[str, np.ndarray],
    *,
    scale: int = 24,
    gap: int = 16,
    vmin: float | None = None,
    vmax: float | None = None,
    layout_blocks: tuple[LayoutBlock, ...] | None = None,
) -> np.ndarray:
    """把左/右手 heatmap 横向拼成一个 RGB 预览图。"""
    if not heatmaps:
        raise ValueError("至少需要一个 heatmap")

    if vmin is None:
        vmin = min(float(np.asarray(heatmap, dtype=np.float32).min()) for heatmap in heatmaps.values())
    if vmax is None:
        vmax = max(float(np.asarray(heatmap, dtype=np.float32).max()) for heatmap in heatmaps.values())

    panels = [
        render_heatmap(
            heatmap,
            title=title,
            scale=scale,
            vmin=vmin,
            vmax=vmax,
            layout_blocks=layout_blocks,
        )
        for title, heatmap in heatmaps.items()
    ]
    height = max(panel.shape[0] for panel in panels)
    width = sum(panel.shape[1] for panel in panels) + gap * (len(panels) - 1)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = (12, 12, 12)

    x_offset = 0
    for panel in panels:
        y_offset = (height - panel.shape[0]) // 2
        canvas[y_offset : y_offset + panel.shape[0], x_offset : x_offset + panel.shape[1]] = panel
        x_offset += panel.shape[1] + gap
    return canvas


def save_rgb_image(path: str | Path, image: np.ndarray) -> None:
    """保存 RGB 图像。优先用 OpenCV 写 PNG，缺 OpenCV 时回退到 PIL。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(image, dtype=np.uint8)

    cv2 = _optional_cv2()
    if cv2 is not None:
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if not cv2.imwrite(str(output_path), bgr):
            raise OSError(f"写入图片失败: {output_path}")
        return

    from PIL import Image

    Image.fromarray(rgb).save(output_path)


def _selected_hands(hand: str) -> list[str]:
    return ["left", "right"] if hand == "both" else [hand]


def _finger_physical_patch(values: np.ndarray, start: int, hand: str) -> np.ndarray:
    offsets = (
        [[15, 14], [13, 12], [11, 10], [9, 8], [7, 6], [5, 4], [3, 2], [1, 0]]
        if hand == "left"
        else [[14, 15], [12, 13], [10, 11], [8, 9], [6, 7], [4, 5], [2, 3], [0, 1]]
    )
    return values[start + np.asarray(offsets, dtype=np.int64)]


def raw_130d_to_visual_heatmap(raw: object, *, hand: str, layout: str = "training") -> np.ndarray:
    """把单手 raw 130D 转成可视化 heatmap。

    `training` 使用训练数据集的 12x32 紧凑布局；`physical` 使用 SDK 文档里的
    手指 8x2 左右镜像排列，掌心/手背仍按 5x5 近似显示。
    """
    if hand not in {"left", "right"}:
        raise ValueError(f"hand 必须是 left/right，实际 {hand!r}")
    if layout == "training":
        return raw_130d_to_heatmap(raw)
    if layout != "physical":
        raise ValueError(f"layout 必须是 training/physical，实际 {layout!r}")

    values = np.asarray(raw, dtype=np.float32).reshape(-1)
    if values.shape != (130,):
        raise ValueError(f"O10 tactile raw 必须是 130D，实际 shape={values.shape}")

    heatmap = np.zeros(PHYSICAL_HEATMAP_SHAPE, dtype=np.float32)
    for finger_name in FINGER_NAMES:
        start, _ = FINGER_RAW_RANGES[finger_name]
        col_start, col_stop = PHYSICAL_FINGER_COLS[finger_name]
        heatmap[0:8, col_start:col_stop] = _finger_physical_patch(values, start, hand)
    heatmap[10:15, 6:11] = values[80:105].reshape(5, 5)
    heatmap[10:15, 21:26] = values[105:130].reshape(5, 5)
    return heatmap


def apply_tactile_baseline(
    raw: object,
    *,
    baseline: object | None = None,
    deadband: float = 0.0,
) -> np.ndarray:
    """减 baseline、去死区并裁掉负值，返回 float32 raw 向量。"""
    values = np.asarray(raw, dtype=np.float32).reshape(-1)
    if baseline is not None:
        values = values - np.asarray(baseline, dtype=np.float32).reshape(values.shape)
    if deadband > 0:
        values[np.abs(values) < deadband] = 0.0
    return np.clip(values, 0.0, None).astype(np.float32)


def _demo_raw(hand: str) -> np.ndarray:
    raw = np.zeros(130, dtype=np.float32)
    if hand == "left":
        raw[0:16] = np.linspace(20, 180, 16, dtype=np.float32)
        raw[80:105] = 95.0
    else:
        raw[16:32] = np.linspace(20, 180, 16, dtype=np.float32)
        raw[105:130] = 115.0
    return raw


def _raw_to_heatmaps(
    raw_by_hand: Mapping[str, object],
    *,
    layout: str,
    baselines: Mapping[str, np.ndarray] | None = None,
    deadband: float = 0.0,
) -> dict[str, np.ndarray]:
    heatmaps = {}
    for hand, raw in raw_by_hand.items():
        processed = apply_tactile_baseline(
            raw,
            baseline=None if baselines is None else baselines.get(hand),
            deadband=deadband,
        )
        heatmaps[hand] = raw_130d_to_visual_heatmap(processed, hand=hand, layout=layout)
    return heatmaps


def _load_agibot_hand_class():
    if str(LEROBOT_PLAY_ROOT) not in sys.path:
        sys.path.insert(0, str(LEROBOT_PLAY_ROOT))
    from lerobot_play.utils.agibot_o10 import AgibotO10Hand

    return AgibotO10Hand


def _connect_hands(args: argparse.Namespace):
    AgibotO10Hand = _load_agibot_hand_class()
    hands = {}
    for hand in _selected_hands(args.hand):
        channel_id = args.left_channel_id if hand == "left" else args.right_channel_id
        hands[hand] = AgibotO10Hand(
            handedness=hand,
            channel_mode="multiChannel",
            device_id=args.device_id,
            canfd_id=args.canfd_id,
            channel_id=channel_id,
        )
        print(f"Connecting {hand} hand tactile heatmap, channel_id={channel_id}...")
        hands[hand].connect()
    return hands


def _collect_baselines(
    hands: Mapping[str, object],
    *,
    frames: int,
    interval: float,
) -> dict[str, np.ndarray] | None:
    if frames <= 0:
        return None
    print(f"Collecting tactile baseline: {frames} frames. Keep hands untouched...")
    samples = {hand: [] for hand in hands}
    for _ in range(frames):
        for hand, hand_hw in hands.items():
            samples[hand].append(np.asarray(hand_hw.read_tactile_full(), dtype=np.float32).reshape(130))
        time.sleep(interval)
    return {hand: np.mean(values, axis=0).astype(np.float32) for hand, values in samples.items()}


def _print_summary(heatmaps: Mapping[str, np.ndarray]) -> None:
    parts = []
    for hand, heatmap in heatmaps.items():
        parts.append(f"{hand}: max={float(heatmap.max()):.1f}, sum={float(heatmap.sum()):.1f}")
    print(" | ".join(parts), flush=True)


def _render_panel_from_heatmaps(args: argparse.Namespace, heatmaps: Mapping[str, np.ndarray]) -> np.ndarray:
    layout = VISUAL_LAYOUTS[args.layout]
    vmin = None if args.auto_range else args.vmin
    vmax = None if args.auto_range else args.vmax
    return render_heatmap_panel(
        heatmaps,
        scale=args.scale,
        vmin=vmin,
        vmax=vmax,
        layout_blocks=layout.blocks,
    )


def _show_frame(args: argparse.Namespace, frame: np.ndarray, heatmaps: Mapping[str, np.ndarray]) -> None:
    cv2 = _optional_cv2()
    if args.save is not None:
        save_rgb_image(args.save, frame)
    if args.no_window:
        _print_summary(heatmaps)
        return
    if cv2 is None:
        raise ImportError("实时窗口需要 OpenCV；请先安装 opencv-python，或加 --no-window --save")
    cv2.imshow("O10 tactile heatmap", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    while True:
        key = cv2.waitKey(max(1, int(args.interval * 1000))) & 0xFF
        if key in (ord("q"), 27):
            return


def load_heatmaps_from_dataset_frame(
    dataset_dir: Path,
    *,
    episode_index: int = 0,
    frame_index: int = 0,
    layout: str = "training",
) -> dict[str, np.ndarray]:
    """从 LeRobot 数据集 parquet 中读取某一帧触觉并生成可视化 heatmap。"""
    data_paths = sorted((dataset_dir / "data").glob("**/*.parquet"))
    if not data_paths:
        raise FileNotFoundError(f"没有找到数据 parquet: {dataset_dir / 'data'}")

    df = pd.concat((pd.read_parquet(path) for path in data_paths), ignore_index=True)
    if "episode_index" in df.columns:
        df = df[df["episode_index"] == episode_index]
    if df.empty:
        raise ValueError(f"没有找到 episode_index={episode_index}")

    if "frame_index" in df.columns:
        rows = df[df["frame_index"] == frame_index]
        if rows.empty:
            raise ValueError(f"episode {episode_index} 中没有 frame_index={frame_index}")
        row = rows.iloc[0]
    else:
        if frame_index >= len(df):
            raise ValueError(f"frame_index={frame_index} 超出 episode 长度 {len(df)}")
        row = df.iloc[frame_index]

    heatmaps = {}
    for hand in ("left", "right"):
        raw_key = RAW_TACTILE_KEYS[hand]
        heatmap_key = HEATMAP_TACTILE_KEYS[hand]
        if raw_key in row.index:
            heatmaps[hand] = raw_130d_to_visual_heatmap(row[raw_key], hand=hand, layout=layout)
        elif heatmap_key in row.index:
            heatmaps[hand] = _as_2d_float32(row[heatmap_key], name=heatmap_key)

    if not heatmaps:
        raise ValueError("该帧没有 observation.tactile.left/right 或 left_raw/right_raw 字段")
    return heatmaps


def _show_or_save_loop(args: argparse.Namespace, hands: Mapping[str, object] | None = None) -> None:
    cv2 = _optional_cv2()
    if cv2 is None and not args.no_window:
        raise ImportError("实时窗口需要 OpenCV；请先安装 opencv-python，或加 --no-window --save")

    baselines = None if hands is None else _collect_baselines(
        hands,
        frames=args.baseline_frames,
        interval=args.interval,
    )
    while True:
        if hands is None:
            heatmaps = _raw_to_heatmaps(
                {hand: _demo_raw(hand) for hand in _selected_hands(args.hand)},
                layout=args.layout,
                deadband=args.deadband,
            )
        else:
            heatmaps = _raw_to_heatmaps(
                {hand: hand_hw.read_tactile_full() for hand, hand_hw in hands.items()},
                layout=args.layout,
                baselines=baselines,
                deadband=args.deadband,
            )

        frame = _render_panel_from_heatmaps(args, heatmaps)
        if args.save is not None:
            save_rgb_image(args.save, frame)
        if args.no_window:
            _print_summary(heatmaps)
            return

        assert cv2 is not None
        cv2.imshow("O10 tactile heatmap", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        key = cv2.waitKey(max(1, int(args.interval * 1000))) & 0xFF
        if key in (ord("q"), 27):
            return


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="O10 130D 触觉 heatmap 可视化")
    parser.add_argument("--hand", choices=("left", "right", "both"), default="both")
    parser.add_argument("--layout", choices=("training", "physical"), default="physical")
    parser.add_argument("--demo", action="store_true", help="不连接硬件，显示模拟左右手触觉热力图")
    parser.add_argument("--dataset", type=Path, help="从 LeRobot 数据集读取一帧触觉做可视化")
    parser.add_argument("--episode-index", type=int, default=0)
    parser.add_argument("--frame-index", type=int, default=0)
    parser.add_argument("--interval", type=float, default=0.1, help="实时刷新周期，单位秒，默认匹配 O10 触觉 10Hz")
    parser.add_argument("--scale", type=int, default=24, help="每个 tactile cell 的显示像素大小")
    parser.add_argument("--save", type=Path, help="保存当前预览图；实时模式下会覆盖写入最新帧")
    parser.add_argument("--no-window", action="store_true", help="不弹窗，只打印摘要；配合 --save 可保存一帧")
    parser.add_argument("--baseline-frames", type=int, default=30, help="硬件实时模式启动时采集多少帧作为 baseline；0 表示关闭")
    parser.add_argument("--deadband", type=float, default=3.0, help="baseline 后小于该值的触觉变化视为噪声")
    parser.add_argument("--vmin", type=float, default=0.0, help="固定色阶最小值")
    parser.add_argument("--vmax", type=float, default=255.0, help="固定色阶最大值")
    parser.add_argument("--auto-range", action="store_true", help="每帧按当前 min/max 自动拉伸色阶")
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--canfd-id", type=int, default=0)
    parser.add_argument("--left-channel-id", type=int, default=0)
    parser.add_argument("--right-channel-id", type=int, default=1)
    return parser


def parse_args() -> argparse.Namespace:
    parser = build_arg_parser()
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dataset is not None:
        heatmaps = load_heatmaps_from_dataset_frame(
            args.dataset,
            episode_index=args.episode_index,
            frame_index=args.frame_index,
            layout=args.layout,
        )
        frame = _render_panel_from_heatmaps(args, heatmaps)
        _show_frame(args, frame, heatmaps)
        return 0

    if args.demo:
        _show_or_save_loop(args, hands=None)
        return 0

    hands = _connect_hands(args)
    try:
        _show_or_save_loop(args, hands=hands)
    except KeyboardInterrupt:
        print("\nStopping tactile heatmap visualization...")
    finally:
        for hand_hw in hands.values():
            hand_hw.disconnect()
        cv2 = _optional_cv2()
        if cv2 is not None:
            cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
