#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))

from lerobot_play.utils.dataset_editing import export_agibot_o10_dataset_without_tactile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export a new LeRobot dataset with Agibot O10 tactile values removed "
            "from observation.state."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Source dataset directory containing meta/, data/, and optional videos/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output dataset directory. Defaults to <source>_no_tactile.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Delete the output directory first if it already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = export_agibot_o10_dataset_without_tactile(
        source_root=args.source,
        output_root=args.output,
        overwrite=args.overwrite,
    )

    print("Agibot O10 dataset export completed.")
    print(f"Source: {summary.source_root}")
    print(f"Output: {summary.output_root}")
    print(f"Removed tactile dims: {len(summary.removed_state_names)}")
    print(f"New observation.state dim: {summary.new_state_dim}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
