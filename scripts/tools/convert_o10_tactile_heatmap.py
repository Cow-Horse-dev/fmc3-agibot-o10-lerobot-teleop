#!/usr/bin/env python3
"""把 O10 raw 130D 触觉数据转成 LeRobot tactile heatmap 数据集。

输入数据集应使用当前 O10 raw schema：
- observation.tactile.left_raw  float32[130]
- observation.tactile.right_raw float32[130]

输出会增加与 lerobot_tactile 兼容的二维触觉字段：
- observation.tactile.left  float32[12, 32]
- observation.tactile.right float32[12, 32]

默认保留 raw 130D 字段，便于后续重新映射；加 --drop-raw 可只保留 heatmap。

用法：
    python scripts/tools/convert_o10_tactile_heatmap.py --input /path/to/raw_dataset
    python scripts/tools/convert_o10_tactile_heatmap.py --input /path/to/raw_dataset --drop-raw
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RAW_TACTILE_FEATURES = (
    "observation.tactile.left_raw",
    "observation.tactile.right_raw",
)
HEATMAP_SCHEMA = "o10_tactile_heatmap_schema.json"
HEATMAP_SHAPE = (12, 32)


@dataclass(frozen=True)
class LayoutBlock:
    name: str
    raw_start: int
    raw_stop: int
    row_start: int
    row_stop: int
    col_start: int
    col_stop: int

    @property
    def shape(self) -> tuple[int, int]:
        return (self.row_stop - self.row_start, self.col_stop - self.col_start)

    def to_json(self) -> dict:
        return {
            "raw": [self.raw_start, self.raw_stop],
            "rows": [self.row_start, self.row_stop],
            "cols": [self.col_start, self.col_stop],
            "shape": list(self.shape),
        }


O10_130D_TO_HEATMAP_LAYOUT = (
    LayoutBlock("thumb", 0, 16, 0, 4, 0, 4),
    LayoutBlock("index", 16, 32, 0, 4, 7, 11),
    LayoutBlock("middle", 32, 48, 0, 4, 14, 18),
    LayoutBlock("ring", 48, 64, 0, 4, 21, 25),
    LayoutBlock("little", 64, 80, 0, 4, 28, 32),
    LayoutBlock("palm", 80, 105, 6, 11, 6, 11),
    LayoutBlock("dorsum", 105, 130, 6, 11, 21, 26),
)


class HeatmapStats:
    def __init__(self) -> None:
        self.count = 0
        self.min = np.full(HEATMAP_SHAPE, np.inf, dtype=np.float64)
        self.max = np.full(HEATMAP_SHAPE, -np.inf, dtype=np.float64)
        self.sum = np.zeros(HEATMAP_SHAPE, dtype=np.float64)
        self.sumsq = np.zeros(HEATMAP_SHAPE, dtype=np.float64)

    def update(self, heatmaps: list[np.ndarray]) -> None:
        if not heatmaps:
            return
        batch = np.stack(heatmaps).astype(np.float64)
        self.count += int(batch.shape[0])
        self.min = np.minimum(self.min, batch.min(axis=0))
        self.max = np.maximum(self.max, batch.max(axis=0))
        self.sum += batch.sum(axis=0)
        self.sumsq += np.square(batch).sum(axis=0)

    def to_json(self) -> dict:
        if self.count == 0:
            zeros = np.zeros(HEATMAP_SHAPE, dtype=np.float32)
            return {
                "min": zeros.tolist(),
                "max": zeros.tolist(),
                "mean": zeros.tolist(),
                "std": zeros.tolist(),
            }

        mean = self.sum / self.count
        variance = np.maximum(self.sumsq / self.count - np.square(mean), 0.0)
        return {
            "min": self.min.astype(np.float32).tolist(),
            "max": self.max.astype(np.float32).tolist(),
            "mean": mean.astype(np.float32).tolist(),
            "std": np.sqrt(variance).astype(np.float32).tolist(),
        }


def raw_130d_to_heatmap(raw: object) -> np.ndarray:
    """把单手 raw 130D tactile 向量映射到 12x32 heatmap。"""
    values = np.asarray(raw, dtype=np.float32).reshape(-1)
    if values.shape != (130,):
        raise ValueError(f"O10 tactile raw 必须是 130D，实际 shape={values.shape}")

    heatmap = np.zeros(HEATMAP_SHAPE, dtype=np.float32)
    for block in O10_130D_TO_HEATMAP_LAYOUT:
        patch = values[block.raw_start : block.raw_stop].reshape(block.shape)
        heatmap[block.row_start : block.row_stop, block.col_start : block.col_stop] = patch
    return heatmap


def _heatmap_key_for_raw(raw_key: str) -> str:
    if raw_key == "observation.tactile.left_raw":
        return "observation.tactile.left"
    if raw_key == "observation.tactile.right_raw":
        return "observation.tactile.right"
    raise ValueError(f"不支持的 O10 tactile raw 字段: {raw_key}")


def _infer_tactile_route(raw_keys: list[str]) -> str:
    has_left = "observation.tactile.left_raw" in raw_keys
    has_right = "observation.tactile.right_raw" in raw_keys
    if has_left and has_right:
        return "dual"
    if has_left:
        return "left"
    if has_right:
        return "right"
    return "none"


def _find_raw_tactile_features(info: dict) -> list[str]:
    features = info.get("features", {})
    return [key for key in RAW_TACTILE_FEATURES if key in features]


def _drop_raw_columns(df: pd.DataFrame, raw_keys: list[str]) -> pd.DataFrame:
    columns_to_drop = [
        column
        for column in df.columns
        if column in raw_keys or any(column.startswith(f"stats/{raw_key}/") for raw_key in raw_keys)
    ]
    if columns_to_drop:
        return df.drop(columns=columns_to_drop)
    return df


def _copy_meta_files(
    input_meta: Path,
    output_meta: Path,
    *,
    raw_keys: list[str],
    drop_raw: bool,
) -> None:
    for item in input_meta.iterdir():
        if item.name in ("info.json", "stats.json", HEATMAP_SCHEMA):
            continue
        dest = output_meta / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
            if drop_raw:
                for pq_path in dest.rglob("*.parquet"):
                    df = pd.read_parquet(pq_path)
                    _drop_raw_columns(df, raw_keys).to_parquet(pq_path, index=False)
        else:
            shutil.copy2(item, dest)
            if drop_raw and dest.suffix == ".parquet":
                df = pd.read_parquet(dest)
                _drop_raw_columns(df, raw_keys).to_parquet(dest, index=False)


def _link_large_dirs(input_dir: Path, output_dir: Path) -> None:
    for big_dir_name in ("videos", "images"):
        src = input_dir / big_dir_name
        if not src.exists():
            continue
        dst = output_dir / big_dir_name
        if dst.exists() or dst.is_symlink():
            dst.unlink() if dst.is_symlink() else shutil.rmtree(dst)
        dst.symlink_to(src.resolve())
        logger.info("%s/ -> 符号链接到 %s", big_dir_name, src.resolve())


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    if output_dir.exists():
        if overwrite:
            if output_dir.is_symlink() or output_dir.is_file():
                output_dir.unlink()
            else:
                shutil.rmtree(output_dir)
        elif any(output_dir.iterdir()):
            raise FileExistsError(f"输出目录已存在且非空: {output_dir}；需要覆盖请加 --overwrite")
    output_dir.mkdir(parents=True, exist_ok=True)


def _write_heatmap_schema(
    output_meta: Path,
    *,
    input_dir: Path,
    raw_to_heatmap: dict[str, str],
    drop_raw: bool,
) -> None:
    route = _infer_tactile_route(list(raw_to_heatmap))
    schema = {
        "schema_version": "o10_tactile_heatmap_v1",
        "source_dataset": input_dir.name,
        "source_tactile_route": route,
        "heatmap_shape": list(HEATMAP_SHAPE),
        "raw_features_dropped": drop_raw,
        "raw_to_heatmap_features": raw_to_heatmap,
        "layout": {block.name: block.to_json() for block in O10_130D_TO_HEATMAP_LAYOUT},
    }
    (output_meta / HEATMAP_SCHEMA).write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def convert_o10_tactile_heatmap(
    input_dir: Path,
    output_dir: Path,
    *,
    drop_raw: bool = False,
    overwrite: bool = False,
) -> None:
    """生成带 12x32 tactile heatmap 的新 LeRobot 数据集。"""
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir == input_dir:
        raise ValueError("输出路径不能与输入路径相同")

    info_path = input_dir / "meta" / "info.json"
    if not info_path.exists():
        raise FileNotFoundError(f"找不到 meta/info.json: {info_path}")

    info = json.loads(info_path.read_text(encoding="utf-8"))
    raw_keys = _find_raw_tactile_features(info)
    if not raw_keys:
        raise ValueError("数据集没有 observation.tactile.left_raw/right_raw，无法生成 heatmap")
    raw_to_heatmap = {raw_key: _heatmap_key_for_raw(raw_key) for raw_key in raw_keys}

    _prepare_output_dir(output_dir, overwrite=overwrite)
    out_data_dir = output_dir / "data"
    out_meta_dir = output_dir / "meta"
    out_meta_dir.mkdir(parents=True, exist_ok=True)

    stats_accumulators = {heatmap_key: HeatmapStats() for heatmap_key in raw_to_heatmap.values()}
    parquets = sorted((input_dir / "data").rglob("*.parquet"))
    logger.info("共找到 %d 个 data parquet 文件", len(parquets))
    for pq_path in parquets:
        rel = pq_path.relative_to(input_dir / "data")
        out_path = out_data_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)

        df = pd.read_parquet(pq_path)
        for raw_key, heatmap_key in raw_to_heatmap.items():
            if raw_key not in df.columns:
                raise ValueError(f"{pq_path} 缺少字段 {raw_key}")
            heatmaps = [raw_130d_to_heatmap(raw) for raw in df[raw_key]]
            stats_accumulators[heatmap_key].update(heatmaps)
            df[heatmap_key] = [heatmap.tolist() for heatmap in heatmaps]

        if drop_raw:
            df = _drop_raw_columns(df, raw_keys)
        df.to_parquet(out_path, index=False)
        logger.info("写出 data/%s", rel)

    features = info.setdefault("features", {})
    for heatmap_key in raw_to_heatmap.values():
        features[heatmap_key] = {
            "dtype": "float32",
            "shape": list(HEATMAP_SHAPE),
            "names": ["height", "width"],
        }
    if drop_raw:
        for raw_key in raw_keys:
            features.pop(raw_key, None)

    (out_meta_dir / "info.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    stats_path = input_dir / "meta" / "stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    for heatmap_key, accumulator in stats_accumulators.items():
        stats[heatmap_key] = accumulator.to_json()
    if drop_raw:
        for raw_key in raw_keys:
            stats.pop(raw_key, None)
    (out_meta_dir / "stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    _copy_meta_files(input_dir / "meta", out_meta_dir, raw_keys=raw_keys, drop_raw=drop_raw)
    _write_heatmap_schema(
        out_meta_dir,
        input_dir=input_dir,
        raw_to_heatmap=raw_to_heatmap,
        drop_raw=drop_raw,
    )
    _link_large_dirs(input_dir, output_dir)
    logger.info("完成。输出目录: %s", output_dir)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="把 O10 raw 130D 触觉数据转成 12x32 heatmap")
    parser.add_argument("--input", required=True, help="输入 LeRobot 数据集路径")
    parser.add_argument(
        "--output",
        default=None,
        help="输出路径（默认：<input>_tactile_heatmap）",
    )
    parser.add_argument(
        "--drop-raw",
        action="store_true",
        help="输出数据集中删除 observation.tactile.left_raw/right_raw，只保留 heatmap",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="允许覆盖已有输出目录",
    )
    args = parser.parse_args()

    input_dir = Path(args.input).expanduser().resolve()
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else input_dir.parent / f"{input_dir.name}_tactile_heatmap"
    )

    logger.info("输入: %s", input_dir)
    logger.info("输出: %s", output_dir)
    convert_o10_tactile_heatmap(
        input_dir,
        output_dir,
        drop_raw=args.drop_raw,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
