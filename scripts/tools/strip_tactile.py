#!/usr/bin/env python3
"""从 LeRobot v3.0 数据集中删除 O10 触觉信息。

支持两种 raw 格式：
- 新格式：删除 observation.tactile.left_raw / right_raw 独立列。
- 旧格式：把 observation.state 里名字包含 "tactile" 的维度切掉。

写到输出目录后，videos / images 目录用符号链接代替复制以节省磁盘空间。

用法：
    python scripts/tools/strip_tactile.py --input ~/workspace/dataset/.../my_dataset
    python scripts/tools/strip_tactile.py --input /path/to/ds --output /path/to/ds_no_tactile
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TACTILE_FEATURE_PREFIX = "observation.tactile"
NO_TACTILE_SCHEMA = "o10_no_tactile_schema.json"


def _is_tactile_feature_key(key: str) -> bool:
    return key.startswith(TACTILE_FEATURE_PREFIX)


def _mentions_hand(text: str, hand: str) -> bool:
    return (
        text.startswith(f"{hand}.")
        or f".{hand}." in text
        or f".{hand}_" in text
        or f"/{hand}_" in text
    )


def infer_tactile_route(keys_or_names: list[str]) -> str:
    has_left = any(_mentions_hand(item, "left") for item in keys_or_names)
    has_right = any(_mentions_hand(item, "right") for item in keys_or_names)
    if has_left and has_right:
        return "dual"
    if has_left:
        return "left"
    if has_right:
        return "right"
    if any("tactile" in item for item in keys_or_names):
        return "single"
    return "none"


def _tactile_keep_indices(names: list[str]) -> tuple[list[int], list[int]]:
    """返回 (keep_indices, drop_indices)，keep 为非 tactile 的维度索引。"""
    keep, drop = [], []
    for i, name in enumerate(names):
        if "tactile" in name:
            drop.append(i)
        else:
            keep.append(i)
    return keep, drop


def _slice_stat(value, keep: list[int]):
    """把 stats.json 里某个统计量（list 或标量）按 keep 索引切片。"""
    if isinstance(value, list):
        return [value[i] for i in keep]
    return value


def _drop_tactile_columns(df: pd.DataFrame, tactile_feature_keys: list[str]) -> pd.DataFrame:
    columns_to_drop = [
        column
        for column in df.columns
        if column in tactile_feature_keys or TACTILE_FEATURE_PREFIX in column
    ]
    if columns_to_drop:
        df = df.drop(columns=columns_to_drop)
    return df


def _uses_video_observation_storage(info: dict) -> bool:
    image_features = [
        feature
        for key, feature in info.get("features", {}).items()
        if key.startswith("observation.images.")
    ]
    return bool(image_features) and all(feature.get("dtype") == "video" for feature in image_features)


def _copy_meta_without_tactile(input_meta: Path, output_meta: Path, tactile_feature_keys: list[str]) -> None:
    for item in input_meta.iterdir():
        if item.name in ("info.json", "stats.json", NO_TACTILE_SCHEMA):
            continue
        dest = output_meta / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
            for pq_path in dest.rglob("*.parquet"):
                df = pd.read_parquet(pq_path)
                df = _drop_tactile_columns(df, tactile_feature_keys)
                df.to_parquet(pq_path, index=False)
        else:
            shutil.copy2(item, dest)
            if dest.suffix == ".parquet":
                df = pd.read_parquet(dest)
                df = _drop_tactile_columns(df, tactile_feature_keys)
                df.to_parquet(dest, index=False)


def _write_no_tactile_schema(
    output_meta: Path,
    *,
    input_dir: Path,
    route: str,
    removed_tactile_features: list[str],
    removed_state_names: list[str],
    info: dict,
) -> None:
    state_feature = info["features"].get("observation.state", {})
    action_feature = info["features"].get("action", {})
    schema = {
        "schema_version": "o10_no_tactile_v1",
        "source_dataset": input_dir.name,
        "source_tactile_route": route,
        "removed_tactile_features": removed_tactile_features,
        "removed_state_tactile_names": removed_state_names,
        "state_key": "observation.state",
        "state_dim": state_feature.get("shape", [None])[0],
        "action_key": "action",
        "action_dim": action_feature.get("shape", [None])[0],
    }
    (output_meta / NO_TACTILE_SCHEMA).write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def strip_tactile(input_dir: Path, output_dir: Path) -> None:
    # ------------------------------------------------------------------
    # 读 meta/info.json
    # ------------------------------------------------------------------
    info_path = input_dir / "meta" / "info.json"
    info = json.loads(info_path.read_text())

    state_feat = info["features"].get("observation.state")
    if state_feat is None:
        raise ValueError("info.json 里没有 observation.state 特征")

    names: list[str] = state_feat.get("names") or []
    keep_idx, drop_idx = _tactile_keep_indices(names)
    tactile_feature_keys = [
        key for key in list(info["features"]) if _is_tactile_feature_key(key)
    ]
    tactile_route = infer_tactile_route(tactile_feature_keys + [names[i] for i in drop_idx])

    if not drop_idx and not tactile_feature_keys:
        logger.warning("数据集里没有 tactile 特征，无需处理，退出。")
        return

    logger.info(
        "识别到 %s 触觉数据；将删除 %d 个独立 tactile 特征、%d 个 state 触觉维度",
        tactile_route, len(tactile_feature_keys), len(drop_idx),
    )
    if drop_idx:
        logger.info("state 内删除的列名: %s", [names[i] for i in drop_idx])
    if tactile_feature_keys:
        logger.info("删除的独立 tactile 特征: %s", tactile_feature_keys)

    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 处理 data/ 下的所有 parquet
    # ------------------------------------------------------------------
    data_dir = input_dir / "data"
    out_data_dir = output_dir / "data"
    parquets = sorted(data_dir.rglob("*.parquet"))
    logger.info("共找到 %d 个 parquet 文件", len(parquets))

    for pq_path in parquets:
        rel = pq_path.relative_to(data_dir)
        out_path = out_data_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)

        df = pd.read_parquet(pq_path)
        if drop_idx and "observation.state" in df.columns:
            df["observation.state"] = df["observation.state"].apply(
                lambda arr: np.array(arr, dtype=np.float32)[keep_idx]
            )
        df = _drop_tactile_columns(df, tactile_feature_keys)
        df.to_parquet(out_path, index=False)
        logger.info("  写出 %s", rel)

    # ------------------------------------------------------------------
    # 更新 meta/info.json
    # ------------------------------------------------------------------
    if drop_idx:
        new_names = [names[i] for i in keep_idx]
        state_feat["names"] = new_names
        state_feat["shape"] = [len(keep_idx)]
    for key in tactile_feature_keys:
        info["features"].pop(key, None)

    out_meta = output_dir / "meta"
    out_meta.mkdir(parents=True, exist_ok=True)
    (out_meta / "info.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("meta/info.json 已更新：observation.state shape=%s", state_feat["shape"])

    # ------------------------------------------------------------------
    # 更新 meta/stats.json（切片所有统计量）
    # ------------------------------------------------------------------
    stats_path = input_dir / "meta" / "stats.json"
    if stats_path.exists():
        stats = json.loads(stats_path.read_text())
        if drop_idx and "observation.state" in stats:
            s = stats["observation.state"]
            for key in ("min", "max", "mean", "std", "q01", "q10", "q50", "q90", "q99"):
                if key in s:
                    s[key] = _slice_stat(s[key], keep_idx)
        for key in tactile_feature_keys:
            stats.pop(key, None)
        (out_meta / "stats.json").write_text(
            json.dumps(stats, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info("meta/stats.json 已更新")

    # ------------------------------------------------------------------
    # 复制其他 meta 文件（episodes/, tasks.parquet 等）
    # ------------------------------------------------------------------
    _copy_meta_without_tactile(input_dir / "meta", out_meta, tactile_feature_keys)
    _write_no_tactile_schema(
        out_meta,
        input_dir=input_dir,
        route=tactile_route,
        removed_tactile_features=tactile_feature_keys,
        removed_state_names=[names[i] for i in drop_idx],
        info=info,
    )
    logger.info("meta/ 其余文件已复制")

    # ------------------------------------------------------------------
    # 复制视频资源；video 数据集不再额外保留空 images/ 壳目录
    # ------------------------------------------------------------------
    videos_src = input_dir / "videos"
    videos_dst = output_dir / "videos"
    if videos_src.exists():
        if videos_dst.exists() or videos_dst.is_symlink():
            videos_dst.unlink() if videos_dst.is_symlink() else shutil.rmtree(videos_dst)
        shutil.copytree(videos_src, videos_dst)
        logger.info("videos/ 已复制到 %s", videos_dst)

    images_src = input_dir / "images"
    images_dst = output_dir / "images"
    if images_dst.exists() or images_dst.is_symlink():
        images_dst.unlink() if images_dst.is_symlink() else shutil.rmtree(images_dst)
    if images_src.exists() and not _uses_video_observation_storage(info):
        shutil.copytree(images_src, images_dst)
        logger.info("images/ 已复制到 %s", images_dst)
    elif images_src.exists():
        logger.info("检测到 video 数据集，跳过 images/ 目录")

    logger.info(
        "完成。输出目录: %s\nobservation.state: %dD → %dD",
        output_dir, len(names), len(keep_idx),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="从 LeRobot v3.0 数据集删除触觉列")
    parser.add_argument("--input", required=True, help="输入数据集路径")
    parser.add_argument(
        "--output",
        default=None,
        help="输出路径（默认：<input>_no_tactile）",
    )
    args = parser.parse_args()

    input_dir = Path(args.input).expanduser().resolve()
    if not input_dir.exists():
        raise SystemExit(f"输入路径不存在: {input_dir}")

    if args.output:
        output_dir = Path(args.output).expanduser().resolve()
    else:
        output_dir = input_dir.parent / (input_dir.name + "_no_tactile")

    if output_dir == input_dir:
        raise SystemExit("输出路径不能与输入相同")

    logger.info("输入: %s", input_dir)
    logger.info("输出: %s", output_dir)
    strip_tactile(input_dir, output_dir)


if __name__ == "__main__":
    main()
