from pathlib import Path
import sys
import types


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


fake_airbot_hardware = types.ModuleType("airbot_hardware_py")
fake_mmk2_kdl = types.ModuleType("mmk2_kdl_py")
fake_mmk2_kdl.ArmKdlNumerical = object

sys.modules.setdefault("airbot_hardware_py", fake_airbot_hardware)
sys.modules.setdefault("mmk2_kdl_py", fake_mmk2_kdl)

from lerobot_play.infer import (
    _create_dataset,
    _create_save_directory,
    _validate_model_path,
)


class _DummyRobot:
    name = "dummy_robot"
    cameras = {}
    action_features = {}
    observation_features = {}


def test_create_save_directory_leaves_new_dataset_path_uncreated(tmp_path):
    dataset_root = tmp_path / "diffusion_infer_123"

    returned_path = _create_save_directory(str(dataset_root))

    assert returned_path == str(dataset_root)
    assert not dataset_root.exists()


def test_create_save_directory_expands_user_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    returned_path = _create_save_directory("~/diffusion_infer_123")

    assert returned_path == str(tmp_path / "diffusion_infer_123")
    assert not Path(returned_path).exists()


def test_create_dataset_uses_dataset_root_directly(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("lerobot_play.infer.LeRobotDataset.create", fake_create)

    dataset_root = tmp_path / "diffusion_infer_123"
    robot = _DummyRobot()

    _create_dataset(robot, fps=15, save_path=str(dataset_root))

    assert captured["repo_id"] == "diffusion_infer_123"
    assert captured["root"] == str(dataset_root)


def test_validate_model_path_expands_user_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    model_root = tmp_path / "models" / "agi_arm_bot"
    model_root.mkdir(parents=True)
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    (model_root / "model.safetensors").write_text("weights", encoding="utf-8")

    assert _validate_model_path("~/models/agi_arm_bot") is True
