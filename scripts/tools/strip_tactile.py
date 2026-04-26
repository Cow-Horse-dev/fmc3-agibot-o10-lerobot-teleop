#!/usr/bin/env python3
"""从 LeRobot v3.0 数据集的 observation.state 中删除触觉列。

读输入数据集，把 observation.state 里名字包含 "tactile" 的维度去掉，
写到输出目录。videos / images 目录用符号链接代替复制以节省磁盘空间。

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


def strip_tactile(input_dir: Path, output_dir: Path) -> None:
    # ------------------------------------------------------------------
    # 读 meta/info.json
    # ------------------------------------------------------------------
    info_path = input_dir / "meta" / "info.json"
    info = json.loads(info_path.read_text())

    state_feat = info["features"].get("observation.state")
    if state_feat is None:
        raise ValueError("info.json 里没有 observation.state 特征")

    names: list[str] = state_feat.get("names", [])
    keep_idx, drop_idx = _tactile_keep_indices(names)

    if not drop_idx:
        logger.warning("observation.state 里没有 tactile 列，无需处理，退出。")
        return

    logger.info(
        "将删除 %d 个 tactile 维度（索引 %s），保留 %d 维",
        len(drop_idx), drop_idx, len(keep_idx),
    )
    logger.info("删除的列名: %s", [names[i] for i in drop_idx])

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
        if "observation.state" in df.columns:
            df["observation.state"] = df["observation.state"].apply(
                lambda arr: np.array(arr, dtype=np.float32)[keep_idx]
            )
        df.to_parquet(out_path, index=False)
        logger.info("  写出 %s", rel)

    # ------------------------------------------------------------------
    # 更新 meta/info.json
    # ------------------------------------------------------------------
    new_names = [names[i] for i in keep_idx]
    state_feat["names"] = new_names
    state_feat["shape"] = [len(keep_idx)]

    out_meta = output_dir / "meta"
    out_meta.mkdir(parents=True, exist_ok=True)
    (out_meta / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False))
    logger.info("meta/info.json 已更新：observation.state shape=%s", state_feat["shape"])

    # ------------------------------------------------------------------
    # 更新 meta/stats.json（切片所有统计量）
    # ------------------------------------------------------------------
    stats_path = input_dir / "meta" / "stats.json"
    if stats_path.exists():
        stats = json.loads(stats_path.read_text())
        if "observation.state" in stats:
            s = stats["observation.state"]
            for key in ("min", "max", "mean", "std", "q01", "q10", "q50", "q90", "q99"):
                if key in s:
                    s[key] = _slice_stat(s[key], keep_idx)
        (out_meta / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        logger.info("meta/stats.json 已更新")

    # ------------------------------------------------------------------
    # 复制其他 meta 文件（episodes/, tasks.parquet 等）
    # ------------------------------------------------------------------
    for item in (input_dir / "meta").iterdir():
        if item.name in ("info.json", "stats.json"):
            continue
        dest = out_meta / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    logger.info("meta/ 其余文件已复制")

    # ------------------------------------------------------------------
    # videos/ 和 images/ 用符号链接，不复制大文件
    # ------------------------------------------------------------------
    for big_dir_name in ("videos", "images"):
        src = input_dir / big_dir_name
        if not src.exists():
            continue
        dst = output_dir / big_dir_name
        if dst.exists() or dst.is_symlink():
            dst.unlink() if dst.is_symlink() else shutil.rmtree(dst)
        dst.symlink_to(src.resolve())
        logger.info("%s/ → 符号链接到 %s", big_dir_name, src.resolve())

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
