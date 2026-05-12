from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def _get_control_value(controls: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in controls:
            return controls[name]
    return None


def _set_supported_option(sensor: Any, option: Any, value: float) -> bool:
    if not sensor.supports(option):
        return False
    sensor.set_option(option, float(value))
    return True


def _set_option_on_any_sensor(profile: Any, option: Any, value: float) -> bool:
    device = profile.get_device()
    for sensor in device.query_sensors():
        if _set_supported_option(sensor, option, value):
            return True
    return False


def apply_realsense_controls(
    camera_name: str,
    camera: Any,
    controls_by_camera: dict[str, dict[str, Any]] | None,
) -> None:
    controls = (controls_by_camera or {}).get(camera_name)
    if not controls:
        return

    profile = getattr(camera, "rs_profile", None)
    if profile is None:
        logger.warning("Cannot apply RealSense controls for %s before pipeline starts.", camera_name)
        return

    try:
        import pyrealsense2 as rs
    except Exception as exc:
        logger.warning("Cannot apply RealSense controls for %s: %s", camera_name, exc)
        return

    option_values = []
    auto_exposure = _get_control_value(controls, "auto_exposure", "enable_auto_exposure")
    if auto_exposure is not None:
        option_values.append((rs.option.enable_auto_exposure, 1.0 if bool(auto_exposure) else 0.0))

    exposure = _get_control_value(controls, "exposure_us", "exposure")
    if exposure is not None:
        option_values.append((rs.option.exposure, float(exposure)))

    gain = _get_control_value(controls, "gain")
    if gain is not None:
        option_values.append((rs.option.gain, float(gain)))

    for option, value in option_values:
        if not _set_option_on_any_sensor(profile, option, value):
            logger.warning("RealSense camera %s does not support option %s.", camera_name, option)
