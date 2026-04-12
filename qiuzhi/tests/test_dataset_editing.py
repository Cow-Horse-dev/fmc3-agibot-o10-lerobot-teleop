from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

from lerobot.datasets.feature_utils import create_empty_dataset_info
from lerobot.datasets.utils import DEFAULT_FEATURES


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))

from lerobot_play.utils import agibot_o10
from lerobot_play.utils.dataset_editing import (
    AGIBOT_O10_BASE_OBSERVATION_STATE_NAMES,
    OBSERVATION_STATE_KEY,
    export_agibot_o10_dataset_without_tactile,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4, ensure_ascii=False)


def _build_test_dataset(root: Path) -> Path:
    tactile_state_names = [
        *AGIBOT_O10_BASE_OBSERVATION_STATE_NAMES,
        *agibot_o10.AGIBOT_O10_TACTILE_FEATURE_NAMES,
    ]
    action_names = [
        *agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES,
        *agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES,
    ]
    state_dim = len(tactile_state_names)

    features = {
        **DEFAULT_FEATURES,
        OBSERVATION_STATE_KEY: {
            "dtype": "float32",
            "shape": (state_dim,),
            "names": tactile_state_names,
        },
        "action": {
            "dtype": "float32",
            "shape": (len(action_names),),
            "names": action_names,
        },
    }
    info = create_empty_dataset_info(
        codebase_version="v3.0",
        fps=30,
        features=features,
        use_videos=False,
        robot_type="pico_follower_single_arm_agibot_o10",
    )
    info["total_episodes"] = 1
    info["total_frames"] = 2
    info["total_tasks"] = 1
    info["splits"] = {"train": "0:1"}
    _write_json(root / "meta" / "info.json", info)

    state_row_0 = np.arange(state_dim, dtype=np.float32)
    state_row_1 = np.arange(state_dim, dtype=np.float32) + 100.0
    action_row_0 = np.arange(len(action_names), dtype=np.float32)
    action_row_1 = np.arange(len(action_names), dtype=np.float32) + 10.0

    data_df = pd.DataFrame(
        {
            "timestamp": [0.0, 1.0 / 30.0],
            "frame_index": [0, 1],
            "episode_index": [0, 0],
            "index": [0, 1],
            "task_index": [0, 0],
            OBSERVATION_STATE_KEY: [state_row_0, state_row_1],
            "action": [action_row_0, action_row_1],
        }
    )
    data_path = root / "data" / "chunk-000" / "file-000.parquet"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_df.to_parquet(data_path, index=False)

    stats_payload = {
        OBSERVATION_STATE_KEY: {
            "min": state_row_0.tolist(),
            "max": state_row_1.tolist(),
            "mean": ((state_row_0 + state_row_1) / 2.0).tolist(),
            "std": np.ones(state_dim, dtype=np.float32).tolist(),
            "count": [2],
            "q01": state_row_0.tolist(),
            "q10": state_row_0.tolist(),
            "q50": ((state_row_0 + state_row_1) / 2.0).tolist(),
            "q90": state_row_1.tolist(),
            "q99": state_row_1.tolist(),
        }
    }
    _write_json(root / "meta" / "stats.json", stats_payload)

    episodes_df = pd.DataFrame(
        {
            "episode_index": [0],
            "tasks": [["pick camera"]],
            "dataset_from_index": [0],
            "dataset_to_index": [2],
            "data/chunk_index": [0],
            "data/file_index": [0],
            "stats/observation.state/min": [state_row_0],
            "stats/observation.state/max": [state_row_1],
            "stats/observation.state/mean": [(state_row_0 + state_row_1) / 2.0],
            "stats/observation.state/std": [np.ones(state_dim, dtype=np.float32)],
            "stats/observation.state/count": [np.array([2], dtype=np.int64)],
            "stats/observation.state/q01": [state_row_0],
            "stats/observation.state/q10": [state_row_0],
            "stats/observation.state/q50": [(state_row_0 + state_row_1) / 2.0],
            "stats/observation.state/q90": [state_row_1],
            "stats/observation.state/q99": [state_row_1],
        }
    )
    episodes_path = root / "meta" / "episodes" / "chunk-000" / "file-000.parquet"
    episodes_path.parent.mkdir(parents=True, exist_ok=True)
    episodes_df.to_parquet(episodes_path, index=False)

    return root


def test_export_agibot_o10_dataset_without_tactile_rewrites_dataset(tmp_path):
    source_root = _build_test_dataset(tmp_path / "source_dataset")
    output_root = tmp_path / "source_dataset_no_tactile"

    summary = export_agibot_o10_dataset_without_tactile(source_root, output_root)

    expected_state_dim = len(AGIBOT_O10_BASE_OBSERVATION_STATE_NAMES)
    assert summary.output_root == output_root.resolve()
    assert summary.new_state_dim == expected_state_dim
    assert len(summary.removed_state_names) == len(agibot_o10.AGIBOT_O10_TACTILE_FEATURE_NAMES)

    output_info = json.loads((output_root / "meta" / "info.json").read_text(encoding="utf-8"))
    assert output_info["features"][OBSERVATION_STATE_KEY]["shape"] == [expected_state_dim]
    assert output_info["features"][OBSERVATION_STATE_KEY]["names"] == list(
        AGIBOT_O10_BASE_OBSERVATION_STATE_NAMES
    )

    output_data = pd.read_parquet(output_root / "data" / "chunk-000" / "file-000.parquet")
    assert len(output_data.iloc[0][OBSERVATION_STATE_KEY]) == expected_state_dim
    np.testing.assert_allclose(
        output_data.iloc[0][OBSERVATION_STATE_KEY],
        np.arange(expected_state_dim, dtype=np.float32),
    )

    output_stats = json.loads((output_root / "meta" / "stats.json").read_text(encoding="utf-8"))
    assert len(output_stats[OBSERVATION_STATE_KEY]["min"]) == expected_state_dim
    assert output_stats[OBSERVATION_STATE_KEY]["count"] == [2]
    assert output_stats[OBSERVATION_STATE_KEY]["max"][-1] == float(100 + expected_state_dim - 1)

    output_episodes = pd.read_parquet(
        output_root / "meta" / "episodes" / "chunk-000" / "file-000.parquet"
    )
    assert len(output_episodes.iloc[0]["stats/observation.state/min"]) == expected_state_dim
    np.testing.assert_array_equal(
        output_episodes.iloc[0]["stats/observation.state/count"],
        np.array([2], dtype=np.int64),
    )

    source_info = json.loads((source_root / "meta" / "info.json").read_text(encoding="utf-8"))
    assert source_info["features"][OBSERVATION_STATE_KEY]["shape"] == [
        expected_state_dim + len(agibot_o10.AGIBOT_O10_TACTILE_FEATURE_NAMES)
    ]
