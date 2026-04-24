from pathlib import Path
import sys

from lerobot.cameras.configs import ColorMode
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig


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


from lerobot_play.utils.camera_config_parser import parse_camera_configs


def test_parse_camera_configs_accepts_intelrealsense_alias_and_lowercase_color_mode():
    parsed = parse_camera_configs(
        {
            "left_wrist": {
                "type": "intelrealsense",
                "serial_number_or_name": "260322276846",
                "width": 640,
                "height": 480,
                "fps": 30,
                "color_mode": "rgb",
                "use_depth": False,
                "rotation": "NO_ROTATION",
            }
        }
    )

    assert isinstance(parsed["left_wrist"], RealSenseCameraConfig)
    assert parsed["left_wrist"].serial_number_or_name == "260322276846"
    assert parsed["left_wrist"].color_mode == ColorMode.RGB


def test_parse_camera_configs_accepts_lowercase_bgr():
    parsed = parse_camera_configs(
        {
            "right_wrist": {
                "type": "realsense",
                "serial_number_or_name": "260322273018",
                "color_mode": "bgr",
            }
        }
    )

    assert parsed["right_wrist"].color_mode == ColorMode.BGR


def test_parse_camera_configs_passes_opencv_fourcc():
    parsed = parse_camera_configs(
        {
            "top": {
                "type": "opencv",
                "index_or_path": "/dev/video13",
                "width": 640,
                "height": 480,
                "fps": 30,
                "fourcc": "MJPG",
            }
        }
    )

    assert isinstance(parsed["top"], OpenCVCameraConfig)
    assert parsed["top"].fourcc == "MJPG"
