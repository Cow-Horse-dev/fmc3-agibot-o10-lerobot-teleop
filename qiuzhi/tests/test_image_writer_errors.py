from pathlib import Path
import sys
import types

import numpy as np
import pytest


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

fake_mcap = types.ModuleType("mcap")
fake_mcap_writer = types.ModuleType("mcap.writer")
fake_mcap_reader = types.ModuleType("mcap.reader")
fake_mcap_writer.Writer = object
fake_mcap_reader.make_reader = object
sys.modules.setdefault("mcap", fake_mcap)
sys.modules.setdefault("mcap.writer", fake_mcap_writer)
sys.modules.setdefault("mcap.reader", fake_mcap_reader)

from lerobot_play.utils.image_writer import AsyncImageWriter, write_image


def test_write_image_raises_when_image_shape_is_invalid(tmp_path):
    bad_image = np.array([0, 1, 2], dtype=np.uint8)

    with pytest.raises(RuntimeError, match="Failed to write image"):
        write_image(bad_image, tmp_path / "bad.png")


def test_async_image_writer_reports_worker_write_errors(tmp_path):
    writer = AsyncImageWriter(num_processes=0, num_threads=1)
    try:
        bad_image = np.array([0, 1, 2], dtype=np.uint8)
        writer.save_image(bad_image, tmp_path / "bad.png")

        with pytest.raises(RuntimeError, match="Async image writer failed"):
            writer.wait_until_done()
    finally:
        writer.stop()
