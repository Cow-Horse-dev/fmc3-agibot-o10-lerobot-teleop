from lerobot.cameras.configs import ColorMode, Cv2Rotation
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig


def _parse_color_mode(value) -> ColorMode:
    if isinstance(value, ColorMode):
        return value

    normalized = str(value or "RGB").strip()
    if not normalized:
        normalized = "RGB"

    try:
        return ColorMode[normalized.upper()]
    except KeyError:
        normalized_value = normalized.lower()
        for mode in ColorMode:
            if mode.value == normalized_value:
                return mode

    raise ValueError(
        f"Unsupported color_mode: {value}. Expected one of: "
        + ", ".join(mode.value for mode in ColorMode)
    )


def parse_camera_configs(cameras_obj: dict) -> dict:
    parsed: dict = {}
    for name, cfg in (cameras_obj or {}).items():
        cam_type = str(cfg.get("type", "")).strip().lower()
        if cam_type == "intelrealsense":
            cam_type = "realsense"

        if cam_type == "opencv":
            parsed[name] = OpenCVCameraConfig(
                index_or_path=cfg.get("index_or_path", cfg.get("camera_index")),
                fps=int(cfg.get("fps", 30)),
                width=int(cfg.get("width", 640)),
                height=int(cfg.get("height", 480)),
                rotation=Cv2Rotation[cfg.get("rotation", "NO_ROTATION")],
                fourcc=cfg.get("fourcc"),
            )
        elif cam_type == "realsense":
            parsed[name] = RealSenseCameraConfig(
                serial_number_or_name=str(cfg.get("serial_number_or_name", "")),
                fps=int(cfg.get("fps", 30)),
                width=int(cfg.get("width", 640)),
                height=int(cfg.get("height", 480)),
                color_mode=_parse_color_mode(cfg.get("color_mode", "RGB")),
                use_depth=bool(cfg.get("use_depth", False)),
                rotation=Cv2Rotation[cfg.get("rotation", "NO_ROTATION")],
            )
        else:
            raise ValueError(f"Unsupported camera type: {cam_type}")

    return parsed
