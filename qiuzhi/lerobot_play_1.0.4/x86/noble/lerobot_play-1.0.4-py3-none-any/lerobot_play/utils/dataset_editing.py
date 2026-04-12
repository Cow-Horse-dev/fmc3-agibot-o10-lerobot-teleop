from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import datasets
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from lerobot.datasets.feature_utils import get_hf_features_from_features
from lerobot.datasets.io_utils import embed_images

from .agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AGIBOT_O10_POSE_FEATURE_NAMES,
    AGIBOT_O10_TACTILE_FEATURE_NAMES,
)


OBSERVATION_STATE_KEY = "observation.state"
OBSERVATION_STATE_VECTOR_STAT_KEYS = (
    "min",
    "max",
    "mean",
    "std",
    "q01",
    "q10",
    "q50",
    "q90",
    "q99",
)
AGIBOT_O10_BASE_OBSERVATION_STATE_NAMES = (
    *AGIBOT_O10_ARM_FEATURE_NAMES,
    *AGIBOT_O10_HAND_FEATURE_NAMES,
    *AGIBOT_O10_POSE_FEATURE_NAMES,
)


@dataclass(frozen=True, slots=True)
class ObservationStateTrimPlan:
    keep_indices: tuple[int, ...]
    kept_names: tuple[str, ...]
    removed_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatasetExportSummary:
    source_root: Path
    output_root: Path
    removed_state_names: tuple[str, ...]
    new_state_dim: int


def build_agibot_o10_tactile_trim_plan(
    state_feature_info: Mapping[str, Any],
) -> ObservationStateTrimPlan:
    state_shape = tuple(int(dim) for dim in state_feature_info.get("shape", ()))
    state_names = state_feature_info.get("names")
    expected_base_names = tuple(AGIBOT_O10_BASE_OBSERVATION_STATE_NAMES)
    tactile_names = tuple(AGIBOT_O10_TACTILE_FEATURE_NAMES)
    tactile_name_set = set(tactile_names)

    if state_names is not None:
        state_names = tuple(str(name) for name in state_names)
        if len(state_shape) == 1 and state_shape[0] != len(state_names):
            raise ValueError(
                "observation.state shape and names length do not match: "
                f"{state_shape[0]} vs {len(state_names)}"
            )

        keep_indices = tuple(
            index for index, feature_name in enumerate(state_names) if feature_name not in tactile_name_set
        )
        kept_names = tuple(state_names[index] for index in keep_indices)
        removed_names = tuple(
            feature_name for feature_name in state_names if feature_name in tactile_name_set
        )

        if not removed_names:
            if kept_names == expected_base_names:
                raise ValueError("This dataset already excludes Agibot O10 tactile values.")
            raise ValueError(
                "Could not find Agibot O10 tactile feature names inside observation.state."
            )

        missing_tactile_names = [
            feature_name for feature_name in tactile_names if feature_name not in removed_names
        ]
        if missing_tactile_names:
            raise ValueError(
                "observation.state does not contain the full Agibot O10 tactile layout. "
                f"Missing tactile names: {missing_tactile_names}"
            )

        if kept_names != expected_base_names:
            raise ValueError(
                "The remaining observation.state names do not match the expected "
                "Agibot O10 arm + hand + pose layout."
            )

        return ObservationStateTrimPlan(
            keep_indices=keep_indices,
            kept_names=kept_names,
            removed_names=removed_names,
        )

    if len(state_shape) != 1:
        raise ValueError("observation.state must be a 1D vector feature.")

    expected_base_dim = len(expected_base_names)
    expected_raw_dim = expected_base_dim + len(tactile_names)

    if state_shape[0] == expected_base_dim:
        raise ValueError("This dataset already excludes Agibot O10 tactile values.")
    if state_shape[0] != expected_raw_dim:
        raise ValueError(
            "Cannot infer Agibot O10 tactile slice without state names. "
            f"Expected observation.state dim {expected_raw_dim}, got {state_shape[0]}."
        )

    return ObservationStateTrimPlan(
        keep_indices=tuple(range(expected_base_dim)),
        kept_names=expected_base_names,
        removed_names=tactile_names,
    )


def export_agibot_o10_dataset_without_tactile(
    source_root: str | Path,
    output_root: str | Path | None = None,
    overwrite: bool = False,
) -> DatasetExportSummary:
    source_root = Path(source_root).expanduser().resolve()
    if output_root is None:
        output_root = source_root.with_name(source_root.name + "_no_tactile")
    output_root = Path(output_root).expanduser().resolve()

    _validate_export_paths(source_root, output_root, overwrite=overwrite)

    source_info = _load_json(source_root / "meta" / "info.json")
    state_feature_info = source_info.get("features", {}).get(OBSERVATION_STATE_KEY)
    if state_feature_info is None:
        raise ValueError("The source dataset does not contain observation.state.")

    trim_plan = build_agibot_o10_tactile_trim_plan(state_feature_info)

    shutil.copytree(source_root, output_root)

    output_info = _load_json(output_root / "meta" / "info.json")
    output_features = output_info["features"]
    output_features[OBSERVATION_STATE_KEY]["shape"] = [len(trim_plan.kept_names)]
    if output_features[OBSERVATION_STATE_KEY].get("names") is not None:
        output_features[OBSERVATION_STATE_KEY]["names"] = list(trim_plan.kept_names)
    _write_json(output_root / "meta" / "info.json", output_info)

    _rewrite_data_files(
        output_root=output_root,
        output_features=output_features,
        keep_indices=trim_plan.keep_indices,
    )
    _rewrite_episode_metadata(output_root=output_root, keep_indices=trim_plan.keep_indices)
    _rewrite_dataset_stats(output_root=output_root, keep_indices=trim_plan.keep_indices)

    return DatasetExportSummary(
        source_root=source_root,
        output_root=output_root,
        removed_state_names=trim_plan.removed_names,
        new_state_dim=len(trim_plan.kept_names),
    )


def _validate_export_paths(source_root: Path, output_root: Path, overwrite: bool) -> None:
    if not source_root.exists():
        raise FileNotFoundError(f"Source dataset does not exist: {source_root}")
    if not source_root.is_dir():
        raise NotADirectoryError(f"Source dataset is not a directory: {source_root}")
    if not (source_root / "meta" / "info.json").exists():
        raise FileNotFoundError(f"Source dataset is missing meta/info.json: {source_root}")
    if source_root == output_root:
        raise ValueError("Source and output dataset paths must be different.")
    if _is_relative_to(output_root, source_root):
        raise ValueError("Output dataset path cannot live inside the source dataset path.")

    if output_root.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output dataset already exists: {output_root}. Use --overwrite to replace it."
            )
        shutil.rmtree(output_root)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4, ensure_ascii=False)


def _rewrite_data_files(
    output_root: Path,
    output_features: Mapping[str, dict[str, Any]],
    keep_indices: Sequence[int],
) -> None:
    data_paths = sorted((output_root / "data").glob("*/*.parquet"))
    for data_path in data_paths:
        frame_df = pd.read_parquet(data_path).reset_index(drop=True)
        if OBSERVATION_STATE_KEY not in frame_df.columns:
            raise ValueError(f"{data_path} is missing {OBSERVATION_STATE_KEY}")
        frame_df[OBSERVATION_STATE_KEY] = frame_df[OBSERVATION_STATE_KEY].map(
            lambda value: _slice_vector(value, keep_indices)
        )
        _write_data_parquet(frame_df, data_path, output_features)


def _rewrite_episode_metadata(output_root: Path, keep_indices: Sequence[int]) -> None:
    episode_paths = sorted((output_root / "meta" / "episodes").glob("*/*.parquet"))
    for episode_path in episode_paths:
        episode_df = pd.read_parquet(episode_path).reset_index(drop=True)
        for stat_key in OBSERVATION_STATE_VECTOR_STAT_KEYS:
            column_name = f"stats/{OBSERVATION_STATE_KEY}/{stat_key}"
            if column_name in episode_df.columns:
                episode_df[column_name] = episode_df[column_name].map(
                    lambda value: _slice_vector(value, keep_indices)
                )
        _write_plain_parquet(episode_df, episode_path)


def _rewrite_dataset_stats(output_root: Path, keep_indices: Sequence[int]) -> None:
    stats_path = output_root / "meta" / "stats.json"
    stats_payload = _load_json(stats_path)
    state_stats = stats_payload.get(OBSERVATION_STATE_KEY)
    if state_stats is None:
        raise ValueError(f"{stats_path} does not contain {OBSERVATION_STATE_KEY}")

    for stat_key in OBSERVATION_STATE_VECTOR_STAT_KEYS:
        if stat_key in state_stats:
            state_stats[stat_key] = _slice_vector(state_stats[stat_key], keep_indices).tolist()

    _write_json(stats_path, stats_payload)


def _slice_vector(value: Any, keep_indices: Sequence[int]) -> np.ndarray:
    vector = np.asarray(value)
    if vector.ndim != 1:
        raise ValueError(f"Expected a 1D vector, got shape {vector.shape}")
    return vector[list(keep_indices)]


def _write_data_parquet(
    frame_df: pd.DataFrame,
    path: Path,
    features: Mapping[str, dict[str, Any]],
) -> None:
    normalized_features = _normalize_feature_shapes(features)
    hf_features = get_hf_features_from_features(normalized_features)
    dataset = datasets.Dataset.from_dict(
        frame_df.to_dict(orient="list"),
        features=hf_features,
        split="train",
    )
    if any(feature_info["dtype"] == "image" for feature_info in normalized_features.values()):
        dataset = embed_images(dataset)

    table = dataset.with_format("arrow")[:]
    _write_arrow_table(path, table)


def _write_plain_parquet(frame_df: pd.DataFrame, path: Path) -> None:
    with tempfile.NamedTemporaryFile(
        suffix=".parquet",
        dir=path.parent,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        frame_df.to_parquet(temp_path, index=False)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_arrow_table(path: Path, table: Any) -> None:
    with tempfile.NamedTemporaryFile(
        suffix=".parquet",
        dir=path.parent,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        writer = pq.ParquetWriter(
            temp_path,
            schema=table.schema,
            compression="snappy",
            use_dictionary=True,
        )
        writer.write_table(table)
        writer.close()
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _normalize_feature_shapes(
    features: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    normalized_features: dict[str, dict[str, Any]] = {}
    for feature_name, feature_info in features.items():
        normalized_info = dict(feature_info)
        if "shape" in normalized_info and normalized_info["shape"] is not None:
            normalized_info["shape"] = tuple(normalized_info["shape"])
        normalized_features[feature_name] = normalized_info
    return normalized_features
