from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

import numpy as np


logger = logging.getLogger(__name__)


def camera_uses_depth(camera_config: Any) -> bool:
    return bool(getattr(camera_config, "use_depth", False))


def depth_observation_name(camera_name: str) -> str:
    return f"{camera_name}_depth"


def camera_feature_shapes(
    camera_names: Iterable[str],
    camera_configs: dict[str, Any],
) -> dict[str, tuple[int, int, int]]:
    camera_features: dict[str, tuple[int, int, int]] = {}
    for camera_name in camera_names:
        camera_config = camera_configs[camera_name]
        camera_features[camera_name] = (
            camera_config.height,
            camera_config.width,
            3,
        )
        if camera_uses_depth(camera_config):
            camera_features[depth_observation_name(camera_name)] = (
                camera_config.height,
                camera_config.width,
                1,
            )
    return camera_features


class CameraObservationReader:
    def __init__(
        self,
        camera_configs: dict[str, Any],
        *,
        allow_read_failures: bool,
        timeout_ms: int,
    ) -> None:
        self.camera_configs = camera_configs
        self.allow_read_failures = bool(allow_read_failures)
        self.timeout_ms = int(timeout_ms)
        self.cache: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}
        self.fallback_active: dict[str, bool] = {}

    def read(self, camera_name: str, camera: Any) -> tuple[np.ndarray, np.ndarray | None]:
        uses_depth = camera_uses_depth(self.camera_configs[camera_name])
        try:
            if uses_depth:
                color_frame, depth_frame = camera.async_read_color_and_depth(timeout_ms=self.timeout_ms)
                self.cache[camera_name] = (color_frame, depth_frame)
                self._mark_success(camera_name)
                return color_frame, depth_frame

            color_frame = camera.async_read(timeout_ms=self.timeout_ms)
            self.cache[camera_name] = (color_frame, None)
            self._mark_success(camera_name)
            return color_frame, None
        except Exception as exc:
            if not self.allow_read_failures:
                raise

            cached_frames = self.cache.get(camera_name)
            if cached_frames is not None:
                self._mark_failure(camera_name, exc, using_cached_frame=True)
                return cached_frames

            zero_color_frame = self.zero_color_frame(camera_name)
            zero_depth_frame = self.zero_depth_frame(camera_name) if uses_depth else None
            self.cache[camera_name] = (zero_color_frame, zero_depth_frame)
            self._mark_failure(camera_name, exc, using_cached_frame=False)
            return zero_color_frame, zero_depth_frame

    def read_all(
        self,
        cameras: dict[str, Any],
        *,
        executor: ThreadPoolExecutor | None = None,
        thread_name_prefix: str = "o10-camera",
    ) -> dict[str, tuple[np.ndarray, np.ndarray | None]]:
        if len(cameras) <= 1:
            return {
                camera_name: self.read(camera_name, camera)
                for camera_name, camera in cameras.items()
            }

        shutdown_executor = False
        if executor is None:
            executor = ThreadPoolExecutor(
                max_workers=len(cameras),
                thread_name_prefix=thread_name_prefix,
            )
            shutdown_executor = True

        futures = {
            executor.submit(self.read, camera_name, camera): camera_name
            for camera_name, camera in cameras.items()
        }
        camera_results: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}
        try:
            for future in as_completed(futures):
                camera_results[futures[future]] = future.result()
        finally:
            if shutdown_executor:
                executor.shutdown(wait=True)

        return {
            camera_name: camera_results[camera_name]
            for camera_name in cameras
        }

    def zero_color_frame(self, camera_name: str) -> np.ndarray:
        camera_config = self.camera_configs[camera_name]
        return np.zeros((camera_config.height, camera_config.width, 3), dtype=np.uint8)

    def zero_depth_frame(self, camera_name: str) -> np.ndarray:
        camera_config = self.camera_configs[camera_name]
        return np.zeros((camera_config.height, camera_config.width), dtype=np.uint16)

    def _mark_success(self, camera_name: str) -> None:
        if self.fallback_active.pop(camera_name, False):
            logger.info("Camera %s recovered.", camera_name)

    def _mark_failure(
        self,
        camera_name: str,
        exc: Exception,
        *,
        using_cached_frame: bool,
    ) -> None:
        if self.fallback_active.get(camera_name):
            return
        self.fallback_active[camera_name] = True
        fallback_mode = "reusing last frame" if using_cached_frame else "using zero frame"
        logger.warning("Camera read failed for %s, %s: %s", camera_name, fallback_mode, exc)
