from pathlib import Path
import sys
import types

import numpy as np
from PIL import Image


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

from lerobot_play.utils.image_writer import image_array_to_pil_image, write_image


def test_image_array_to_pil_image_supports_uint16_depth_map():
    depth_map = np.array([[1, 20], [300, 4095]], dtype=np.uint16)

    image = image_array_to_pil_image(depth_map)

    assert image.size == (2, 2)
    assert np.array_equal(np.array(image), depth_map)


def test_image_array_to_pil_image_supports_single_channel_depth_tensor():
    depth_map = np.arange(6, dtype=np.uint16).reshape(2, 3, 1)

    image = image_array_to_pil_image(depth_map)

    assert image.size == (3, 2)
    assert np.array_equal(np.array(image), depth_map[..., 0])


def test_write_image_preserves_uint16_depth_png(tmp_path):
    depth_map = np.array([[0, 128], [1024, 2048]], dtype=np.uint16)
    output_path = tmp_path / "depth.png"

    write_image(depth_map, output_path)

    restored = np.array(Image.open(output_path))
    assert np.array_equal(restored, depth_map)
