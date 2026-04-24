from pathlib import Path
import importlib.util
import sys
import types
from types import SimpleNamespace

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

try:
    spec = importlib.util.spec_from_file_location(
        "test_rerecord_lerobot_dataset_module",
        LEROBOT_PLAY_PACKAGE_ROOT
        / "lerobot_play"
        / "utils"
        / "lerobot_dataset.py",
    )
    dataset_module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(dataset_module)
    LeRobotDataset = dataset_module.LeRobotDataset
except ImportError as exc:
    LeRobotDataset = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


pytestmark = pytest.mark.skipif(
    LeRobotDataset is None,
    reason=f"lerobot_play dataset dependencies unavailable in this test environment: {_IMPORT_ERROR}",
)


class _FakeWriter:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1

    def wait_until_done(self):
        return None


def test_clear_episode_buffer_rerecord_handles_scalar_episode_index(tmp_path):
    class FakeDataset:
        clear_episode_buffer = LeRobotDataset.clear_episode_buffer
        create_episode_buffer = LeRobotDataset.create_episode_buffer
        _get_image_file_path = LeRobotDataset._get_image_file_path
        _get_image_file_dir = LeRobotDataset._get_image_file_dir
        _get_mcap_file_path = LeRobotDataset._get_mcap_file_path
        _restart_image_writer = LeRobotDataset._restart_image_writer
        stop_image_writer = LeRobotDataset.stop_image_writer
        _wait_image_writer = LeRobotDataset._wait_image_writer

    dataset = FakeDataset()
    dataset.root = tmp_path
    dataset.meta = SimpleNamespace(
        total_episodes=0,
        features={
            "episode_index": {"dtype": "int64"},
            "frame_index": {"dtype": "int64"},
            "timestamp": {"dtype": "float32"},
            "observation.images.right": {"dtype": "video"},
            "observation.images.top": {"dtype": "video"},
        },
        camera_keys=["observation.images.right", "observation.images.top"],
        image_keys=["observation.images.right", "observation.images.top"],
    )
    dataset.online_encoding = False
    dataset.image_buffer = {"stale": True}
    dataset.episode_buffer = dataset.create_episode_buffer(episode_index=0)
    dataset.episode_buffer["size"] = 1
    dataset.image_writer = _FakeWriter()
    dataset._image_writer_mode = "image"
    dataset._image_writer_processes = 0
    dataset._image_writer_threads = 2

    restarted = []

    def fake_start_image_writer(num_processes=0, num_threads=4):
        restarted.append((num_processes, num_threads))
        dataset.image_writer = _FakeWriter()

    dataset.start_image_writer = fake_start_image_writer

    for camera_key in dataset.meta.camera_keys:
        image_dir = dataset._get_image_file_dir(0, camera_key)
        image_dir.mkdir(parents=True, exist_ok=True)
        (image_dir / "frame-000313.png").write_bytes(b"stale")

        mcap_dir = dataset._get_mcap_file_path(0, camera_key, 0).parent
        mcap_dir.mkdir(parents=True, exist_ok=True)
        (mcap_dir / "frame-000313.mcap").write_bytes(b"stale")

    dataset.clear_episode_buffer(restart_image_writer=True)

    assert dataset.episode_buffer["episode_index"] == 0
    assert dataset.episode_buffer["size"] == 0
    assert dataset.image_buffer is None
    assert restarted == [(0, 2)]

    for camera_key in dataset.meta.camera_keys:
        assert not dataset._get_image_file_dir(0, camera_key).exists()
        assert not dataset._get_mcap_file_path(0, camera_key, 0).parent.exists()
