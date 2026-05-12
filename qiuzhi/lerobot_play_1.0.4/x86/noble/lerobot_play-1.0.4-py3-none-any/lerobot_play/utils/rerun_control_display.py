from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any


logger = logging.getLogger(__name__)


def _camera_keys_from_mapping(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value.keys()]
    return []


def get_display_camera_keys(robot: Any) -> tuple[list[str], list[str]]:
    configured_keys = _camera_keys_from_mapping(
        getattr(getattr(robot, "config", None), "cameras", None)
    )
    connected_keys = _camera_keys_from_mapping(getattr(robot, "cameras", None))

    camera_keys = configured_keys or connected_keys
    missing_keys = [key for key in configured_keys if key not in connected_keys]
    return camera_keys, missing_keys


def send_control_rerun_blueprint(camera_keys: Sequence[str]) -> None:
    camera_keys = [str(key) for key in camera_keys]
    if not camera_keys:
        return

    try:
        import rerun as rr
        import rerun.blueprint as rrb
    except Exception as exc:
        logger.debug("Skipping Rerun blueprint setup: %s", exc)
        return

    views = [
        rrb.Spatial2DView(
            origin=f"observation.{camera_key}",
            contents="$origin",
            name=f"observation.{camera_key}",
        )
        for camera_key in camera_keys
    ]
    blueprint = rrb.Blueprint(
        rrb.Vertical(
            rrb.Grid(
                *views,
                grid_columns=min(len(views), 3),
                name="O10 camera views",
            ),
            rrb.TimeSeriesView(
                origin="/",
                contents="+ /**",
                name="action/observation trajectories",
            ),
            row_shares=[3, 1],
            name="O10 control",
        ),
        auto_layout=False,
        auto_views=False,
        collapse_panels=False,
    )
    rr.send_blueprint(blueprint, make_active=True, make_default=True)


def configure_control_rerun_display(robot: Any) -> list[str]:
    camera_keys, missing_keys = get_display_camera_keys(robot)
    connected_keys = _camera_keys_from_mapping(getattr(robot, "cameras", None))
    logger.info("Rerun camera views: configured=%s connected=%s", camera_keys, connected_keys)
    if missing_keys:
        logger.warning("Configured cameras not connected and will not stream frames: %s", missing_keys)
    send_control_rerun_blueprint(camera_keys)
    return connected_keys or camera_keys
