import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.tools import strip_tactile as strip_tactile_module


def _write_minimal_dataset(root: Path) -> None:
    (root / "meta").mkdir(parents=True)
    (root / "data" / "chunk-000").mkdir(parents=True)
    (root / "meta" / "episodes" / "chunk-000").mkdir(parents=True)
    (root / "videos" / "observation.images.right").mkdir(parents=True)

    info = {
        "features": {
            "observation.state": {
                "dtype": "float32",
                "shape": [7],
                "names": [*(f"joint{i}.pos" for i in range(1, 7)), "gripper.pos"],
            },
            "observation.tactile.right_raw": {
                "dtype": "float32",
                "shape": [130],
                "names": [f"tactile_{i}" for i in range(130)],
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
    }
    (root / "meta" / "info.json").write_text(json.dumps(info), encoding="utf-8")
    (root / "meta" / "stats.json").write_text(
        json.dumps(
            {
                "observation.state": {
                    "min": [0.0] * 7,
                    "max": [1.0] * 7,
                    "mean": [0.5] * 7,
                    "std": [0.1] * 7,
                },
                "observation.tactile.right_raw": {
                    "min": [0.0] * 130,
                    "max": [1.0] * 130,
                },
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        {
            "observation.state": [np.arange(7, dtype=np.float32)],
            "observation.tactile.right_raw": [np.arange(130, dtype=np.float32)],
            "action": [np.arange(7, dtype=np.float32)],
            "timestamp": [0.0],
            "frame_index": [0],
            "episode_index": [0],
            "index": [0],
            "task_index": [0],
        }
    ).to_parquet(root / "data" / "chunk-000" / "file-000.parquet", index=False)
    pd.DataFrame(
        {
            "episode_index": [0],
            "stats/observation.state/min": [[0.0] * 7],
            "stats/observation.tactile.right_raw/min": [[0.0] * 130],
        }
    ).to_parquet(root / "meta" / "episodes" / "chunk-000" / "file-000.parquet", index=False)


def test_infer_tactile_route_from_tactile_feature_keys():
    infer_tactile_route = strip_tactile_module.infer_tactile_route

    assert infer_tactile_route(["observation.tactile.right_raw"]) == "right"
    assert infer_tactile_route(["observation.tactile.left_raw"]) == "left"
    assert infer_tactile_route(["observation.tactile.left_raw", "observation.tactile.right_raw"]) == "dual"


def test_strip_tactile_removes_independent_tactile_features(tmp_path):
    input_dir = tmp_path / "right_raw"
    output_dir = tmp_path / "right_no_tactile"
    _write_minimal_dataset(input_dir)

    strip_tactile_module.strip_tactile(input_dir, output_dir)

    info = json.loads((output_dir / "meta" / "info.json").read_text(encoding="utf-8"))
    assert "observation.tactile.right_raw" not in info["features"]
    assert info["features"]["observation.state"]["shape"] == [7]

    df = pd.read_parquet(output_dir / "data" / "chunk-000" / "file-000.parquet")
    assert "observation.tactile.right_raw" not in df.columns
    assert list(df["observation.state"].iloc[0]) == list(np.arange(7, dtype=np.float32))

    stats = json.loads((output_dir / "meta" / "stats.json").read_text(encoding="utf-8"))
    assert "observation.tactile.right_raw" not in stats

    episode_df = pd.read_parquet(output_dir / "meta" / "episodes" / "chunk-000" / "file-000.parquet")
    assert "stats/observation.tactile.right_raw/min" not in episode_df.columns

    schema = json.loads((output_dir / "meta" / "o10_no_tactile_schema.json").read_text(encoding="utf-8"))
    assert schema["source_tactile_route"] == "right"
