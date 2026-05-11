import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.tools import convert_o10_tactile_heatmap as heatmap_module


def _read_heatmap_cell(value) -> np.ndarray:
    return np.stack(value).astype(np.float32)


def _raw_feature_names(prefix: str | None = None) -> list[str]:
    names = (
        [f"tactile.thumb_{index}" for index in range(16)]
        + [f"tactile.index_{index}" for index in range(16)]
        + [f"tactile.middle_{index}" for index in range(16)]
        + [f"tactile.ring_{index}" for index in range(16)]
        + [f"tactile.little_{index}" for index in range(16)]
        + [f"tactile.palm_{index}" for index in range(25)]
        + [f"tactile.dorsum_{index}" for index in range(25)]
    )
    if prefix is None:
        return names
    return [f"{prefix}.{name}" for name in names]


def _write_minimal_dataset(root: Path, tactile_keys: tuple[str, ...]) -> None:
    (root / "meta").mkdir(parents=True)
    (root / "data" / "chunk-000").mkdir(parents=True)
    (root / "meta" / "episodes" / "chunk-000").mkdir(parents=True)
    (root / "videos" / "observation.images.right").mkdir(parents=True)

    features = {
        "observation.state": {
            "dtype": "float32",
            "shape": [7],
            "names": [*(f"joint{i}.pos" for i in range(1, 7)), "gripper.pos"],
        },
        "action": {
            "dtype": "float32",
            "shape": [7],
            "names": [*(f"joint{i}.pos" for i in range(1, 7)), "gripper.pos"],
        },
        "timestamp": {"dtype": "float32", "shape": [1], "names": None},
        "frame_index": {"dtype": "int64", "shape": [1], "names": None},
        "episode_index": {"dtype": "int64", "shape": [1], "names": None},
        "index": {"dtype": "int64", "shape": [1], "names": None},
        "task_index": {"dtype": "int64", "shape": [1], "names": None},
    }
    stats = {
        "observation.state": {
            "min": [0.0] * 7,
            "max": [1.0] * 7,
            "mean": [0.5] * 7,
            "std": [0.1] * 7,
        }
    }
    data = {
        "observation.state": [np.arange(7, dtype=np.float32)],
        "action": [np.arange(7, dtype=np.float32)],
        "timestamp": [0.0],
        "frame_index": [0],
        "episode_index": [0],
        "index": [0],
        "task_index": [0],
    }
    episode_stats = {"episode_index": [0]}

    for key in tactile_keys:
        hand = key.removeprefix("observation.tactile.").removesuffix("_raw")
        features[key] = {
            "dtype": "float32",
            "shape": [130],
            "names": _raw_feature_names(hand if hand in {"left", "right"} else None),
        }
        offset = 1000 if hand == "left" else 0
        data[key] = [np.arange(offset, offset + 130, dtype=np.float32)]
        stats[key] = {
            "min": [float(offset)] * 130,
            "max": [float(offset + 129)] * 130,
        }
        episode_stats[f"stats/{key}/min"] = [[float(offset)] * 130]

    (root / "meta" / "info.json").write_text(json.dumps({"features": features}), encoding="utf-8")
    (root / "meta" / "stats.json").write_text(json.dumps(stats), encoding="utf-8")
    pd.DataFrame(data).to_parquet(root / "data" / "chunk-000" / "file-000.parquet", index=False)
    pd.DataFrame(episode_stats).to_parquet(
        root / "meta" / "episodes" / "chunk-000" / "file-000.parquet",
        index=False,
    )


def test_convert_right_raw_130d_to_lerobot_tactile_heatmap(tmp_path):
    input_dir = tmp_path / "right_raw"
    output_dir = tmp_path / "right_heatmap"
    _write_minimal_dataset(input_dir, ("observation.tactile.right_raw",))

    heatmap_module.convert_o10_tactile_heatmap(input_dir, output_dir)

    info = json.loads((output_dir / "meta" / "info.json").read_text(encoding="utf-8"))
    assert info["features"]["observation.tactile.right"] == {
        "dtype": "float32",
        "shape": [12, 32],
        "names": ["height", "width"],
    }
    assert "observation.tactile.right_raw" in info["features"]

    df = pd.read_parquet(output_dir / "data" / "chunk-000" / "file-000.parquet")
    heatmap = _read_heatmap_cell(df["observation.tactile.right"].iloc[0])
    assert heatmap.shape == (12, 32)
    assert heatmap[0, 0] == 0.0
    assert heatmap[3, 3] == 15.0
    assert heatmap[0, 7] == 16.0
    assert heatmap[0, 14] == 32.0
    assert heatmap[0, 21] == 48.0
    assert heatmap[0, 28] == 64.0
    assert heatmap[6, 6] == 80.0
    assert heatmap[10, 10] == 104.0
    assert heatmap[6, 21] == 105.0
    assert heatmap[10, 25] == 129.0
    assert heatmap[11, 31] == 0.0

    schema = json.loads((output_dir / "meta" / "o10_tactile_heatmap_schema.json").read_text(encoding="utf-8"))
    assert schema["source_tactile_route"] == "right"
    assert schema["heatmap_shape"] == [12, 32]
    assert schema["raw_to_heatmap_features"] == {
        "observation.tactile.right_raw": "observation.tactile.right"
    }


def test_convert_dual_raw_130d_to_left_and_right_heatmaps(tmp_path):
    input_dir = tmp_path / "dual_raw"
    output_dir = tmp_path / "dual_heatmap"
    _write_minimal_dataset(
        input_dir,
        ("observation.tactile.left_raw", "observation.tactile.right_raw"),
    )

    heatmap_module.convert_o10_tactile_heatmap(input_dir, output_dir)

    info = json.loads((output_dir / "meta" / "info.json").read_text(encoding="utf-8"))
    assert "observation.tactile.left" in info["features"]
    assert "observation.tactile.right" in info["features"]

    df = pd.read_parquet(output_dir / "data" / "chunk-000" / "file-000.parquet")
    left = _read_heatmap_cell(df["observation.tactile.left"].iloc[0])
    right = _read_heatmap_cell(df["observation.tactile.right"].iloc[0])
    assert left[0, 0] == 1000.0
    assert left[10, 25] == 1129.0
    assert right[0, 0] == 0.0
    assert right[10, 25] == 129.0


def test_convert_heatmap_can_drop_raw_features(tmp_path):
    input_dir = tmp_path / "right_raw"
    output_dir = tmp_path / "right_heatmap_only"
    _write_minimal_dataset(input_dir, ("observation.tactile.right_raw",))

    heatmap_module.convert_o10_tactile_heatmap(input_dir, output_dir, drop_raw=True)

    info = json.loads((output_dir / "meta" / "info.json").read_text(encoding="utf-8"))
    assert "observation.tactile.right" in info["features"]
    assert "observation.tactile.right_raw" not in info["features"]

    df = pd.read_parquet(output_dir / "data" / "chunk-000" / "file-000.parquet")
    assert "observation.tactile.right" in df.columns
    assert "observation.tactile.right_raw" not in df.columns

    stats = json.loads((output_dir / "meta" / "stats.json").read_text(encoding="utf-8"))
    assert "observation.tactile.right" in stats
    assert "observation.tactile.right_raw" not in stats

    episode_df = pd.read_parquet(output_dir / "meta" / "episodes" / "chunk-000" / "file-000.parquet")
    assert "stats/observation.tactile.right_raw/min" not in episode_df.columns
