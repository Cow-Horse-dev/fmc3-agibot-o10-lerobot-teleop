import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.tools import convert_o10_tactile_heatmap as heatmap_module
from scripts.tools import visualize_o10_tactile_heatmap as visualization


def test_render_dual_o10_tactile_heatmap_preview(tmp_path):
    left_raw = np.zeros(130, dtype=np.float32)
    right_raw = np.zeros(130, dtype=np.float32)
    left_raw[0:16] = np.linspace(0, 120, 16, dtype=np.float32)
    left_raw[80:105] = 80.0
    right_raw[16:32] = np.linspace(20, 160, 16, dtype=np.float32)
    right_raw[105:130] = 100.0

    preview = visualization.render_heatmap_panel(
        {
            "left": heatmap_module.raw_130d_to_heatmap(left_raw),
            "right": heatmap_module.raw_130d_to_heatmap(right_raw),
        },
        scale=8,
    )

    assert preview.dtype == np.uint8
    assert preview.ndim == 3
    assert preview.shape[2] == 3
    assert preview.shape[0] >= 12 * 8
    assert preview.shape[1] >= 32 * 8 * 2
    assert int(preview.max()) > int(preview.min())

    output_path = tmp_path / "dual_o10_tactile_heatmap.png"
    visualization.save_rgb_image(output_path, preview)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_physical_layout_mirrors_left_and_right_finger_indices():
    raw = np.arange(130, dtype=np.float32)

    left = visualization.raw_130d_to_visual_heatmap(raw, hand="left", layout="physical")
    right = visualization.raw_130d_to_visual_heatmap(raw, hand="right", layout="physical")

    assert left.shape == visualization.PHYSICAL_HEATMAP_SHAPE
    assert right.shape == visualization.PHYSICAL_HEATMAP_SHAPE
    assert left[0, 0] == 15.0
    assert left[0, 1] == 14.0
    assert left[7, 0] == 1.0
    assert left[7, 1] == 0.0
    assert right[0, 0] == 14.0
    assert right[0, 1] == 15.0
    assert right[7, 0] == 0.0
    assert right[7, 1] == 1.0
    assert right[10, 6] == 80.0
    assert right[10, 21] == 105.0


def test_apply_tactile_baseline_and_deadband_clips_noise():
    raw = np.array([0.0, 10.0, 15.0], dtype=np.float32)
    baseline = np.array([5.0, 5.0, 5.0], dtype=np.float32)

    processed = visualization.apply_tactile_baseline(raw, baseline=baseline, deadband=6.0)

    assert processed.tolist() == [0.0, 0.0, 10.0]


def test_cli_defaults_to_sensor_sampling_interval():
    args = visualization.build_arg_parser().parse_args(["--demo"])

    assert args.interval == 0.1


def test_load_dataset_frame_from_raw_tactile_columns(tmp_path):
    dataset_dir = tmp_path / "dataset"
    data_dir = dataset_dir / "data" / "chunk-000"
    data_dir.mkdir(parents=True)
    left_raw = np.arange(1000, 1130, dtype=np.float32)
    right_raw = np.arange(130, dtype=np.float32)
    pd.DataFrame(
        {
            "episode_index": [0],
            "frame_index": [3],
            "observation.tactile.left_raw": [left_raw],
            "observation.tactile.right_raw": [right_raw],
        }
    ).to_parquet(data_dir / "file-000.parquet", index=False)

    heatmaps = visualization.load_heatmaps_from_dataset_frame(
        dataset_dir,
        episode_index=0,
        frame_index=3,
        layout="physical",
    )

    assert list(heatmaps) == ["left", "right"]
    assert heatmaps["left"].shape == visualization.PHYSICAL_HEATMAP_SHAPE
    assert heatmaps["left"][0, 0] == 1015.0
    assert heatmaps["right"][0, 0] == 14.0
