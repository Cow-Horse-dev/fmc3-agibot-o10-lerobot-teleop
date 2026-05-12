from pathlib import Path
import sys

import yaml


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


def test_shared_camera_config_materializes_profile_with_aliases(tmp_path):
    from lerobot_play.utils.shared_camera_config import apply_shared_camera_config

    shared_config = tmp_path / "o10_cameras.yaml"
    shared_config.write_text(
        """
cameras:
  top:
    type: opencv
    index_or_path: /dev/top
    width: 640
    height: 480
    fps: 30
    fourcc: MJPG
    rotation: ROTATE_180
  right_wrist:
    type: realsense
    serial_number_or_name: "260322273018"
    width: 640
    height: 480
    fps: 30
    use_depth: false
    color_mode: RGB
    rotation: NO_ROTATION
camera_controls:
  right_wrist:
    auto_exposure: false
    exposure_us: 14000
    gain: 16
profiles:
  right_arm_dataset:
    cameras:
      right: right_wrist
      top: top
    camera_controls:
      right: right_wrist
""",
        encoding="utf-8",
    )
    config = {
        "robot": {
            "camera_config_path": str(shared_config),
            "camera_profile": "right_arm_dataset",
            "cameras": {"right": {"fps": 15}},
            "camera_controls": {"right": {"gain": 8}},
        }
    }

    materialized = apply_shared_camera_config(config)

    assert materialized["robot"]["cameras"]["top"]["index_or_path"] == "/dev/top"
    assert materialized["robot"]["cameras"]["right"]["serial_number_or_name"] == "260322273018"
    assert materialized["robot"]["cameras"]["right"]["fps"] == 15
    assert materialized["robot"]["camera_controls"]["right"] == {
        "auto_exposure": False,
        "exposure_us": 14000,
        "gain": 8,
    }


def test_o10_configs_reference_shared_camera_file():
    config_paths = [
        "configs/left_arm/o10_left_control.yaml",
        "configs/left_arm/o10_left_record.yaml",
        "configs/left_arm/o10_left_infer.yaml",
        "configs/right_arm/o10_right_control.yaml",
        "configs/right_arm/o10_right_record.yaml",
        "configs/right_arm/o10_right_infer.yaml",
        "configs/right_arm/o10_right_infer_cpu.yaml",
        "configs/dual_arm/o10_dual_control.yaml",
        "configs/dual_arm/o10_dual_record.yaml",
        "configs/dual_arm/o10_dual_infer.yaml",
    ]

    for path in config_paths:
        config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        robot = config["robot"]
        assert robot["camera_config_path"] == "configs/cameras/o10_cameras.yaml"
        assert "camera_profile" in robot
        assert "cameras" not in robot
        assert "camera_controls" not in robot
