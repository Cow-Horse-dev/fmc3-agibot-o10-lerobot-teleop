import importlib.util
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


def _load_o10_single_arm_config_class():
    from lerobot.robots.config import RobotConfig

    robot_type = "pico_follower_single_arm_agibot_o10"
    registered_class = RobotConfig._choice_registry.get(robot_type)
    if registered_class is not None:
        return registered_class, False

    config_path = (
        LEROBOT_PLAY_PACKAGE_ROOT
        / "lerobot_play"
        / "robots"
        / "pico_follower_single_arm_agibot_o10"
        / "config_pico_follower_single_arm_agibot_o10.py"
    )
    spec = importlib.util.spec_from_file_location("test_o10_single_arm_config", config_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.PicoFollowerSingleArmAgibotO10Config, True


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


def test_shared_camera_config_resolves_repo_relative_path_from_absolute_yaml(monkeypatch, tmp_path):
    from lerobot_play.utils.shared_camera_config import load_yaml_with_shared_camera_config

    monkeypatch.chdir(tmp_path)

    config = load_yaml_with_shared_camera_config(
        WORKSPACE_ROOT / "configs" / "right_arm" / "o10_right_record.yaml"
    )

    assert set(config["robot"]["cameras"]) == {"right", "top"}
    assert config["robot"]["camera_controls"]["right"]["exposure_us"] == 14000


def test_o10_robot_config_classes_materialize_shared_cameras():
    from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
    from lerobot.robots.config import RobotConfig

    config_class, loaded_for_test = _load_o10_single_arm_config_class()
    try:
        config = config_class(
            port="can1",
            camera_config_path="configs/cameras/o10_cameras.yaml",
            camera_profile="right_arm_control",
        )

        assert set(config.cameras) == {"top", "right_wrist"}
        assert isinstance(config.cameras["right_wrist"], RealSenseCameraConfig)
        assert config.camera_controls["right_wrist"]["exposure_us"] == 14000
    finally:
        if loaded_for_test:
            RobotConfig._choice_registry.pop("pico_follower_single_arm_agibot_o10", None)
