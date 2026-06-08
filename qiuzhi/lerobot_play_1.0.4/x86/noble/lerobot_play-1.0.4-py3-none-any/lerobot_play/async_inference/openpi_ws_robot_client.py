from __future__ import annotations

import threading
import time
from typing import Any

import torch

from lerobot.async_inference.helpers import TimedAction
from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

from .robot_client import RobotClient


class OpenPIWebsocketRobotClient(RobotClient):
    """Robot client that gets action chunks from the official OpenPI websocket server."""

    def __init__(self, config):
        super().__init__(config)
        self.policy = OpenPIJaxPolicyAdapter.from_server_address(config.server_address)
        from .policy_server import _apply_rtc_env_config

        _apply_rtc_env_config(self.policy)
        self._observation_queue: list[Any] = []
        self._observation_queue_lock = threading.Lock()
        self._receiver_started = threading.Event()

    def start(self):
        self.shutdown_event.clear()
        self.logger.info("Connected to OpenPI websocket policy server at %s", self.server_address)
        return True

    def stop(self):
        super().stop()
        close = getattr(self.policy, "close", None)
        if close is not None:
            close()

    def send_observation(self, obs) -> bool:
        if not self.running:
            raise RuntimeError(
                "Client not running. Run OpenPIWebsocketRobotClient.start() before sending observations."
            )
        with self._observation_queue_lock:
            self._observation_queue.append(obs)
            if len(self._observation_queue) > 1:
                self._observation_queue = self._observation_queue[-1:]
        return True

    def _pop_latest_observation(self):
        with self._observation_queue_lock:
            if not self._observation_queue:
                return None
            observation = self._observation_queue[-1]
            self._observation_queue.clear()
            return observation

    def _time_action_chunk(self, timestamp: float, action_tensor: torch.Tensor, timestep: int) -> list[TimedAction]:
        return [
            TimedAction(
                timestamp=timestamp + index * self.config.environment_dt,
                timestep=timestep + index,
                action=action,
            )
            for index, action in enumerate(action_tensor)
        ]

    def _predict_timed_actions(self, observation_t, verbose: bool = False) -> list[TimedAction]:
        start = time.perf_counter()
        action_tensor = self.policy.predict_action_chunk_from_raw(
            observation_t.get_observation(),
            timestep=observation_t.get_timestep(),
            actions_per_chunk=int(getattr(self.config, "actions_per_chunk", 50)),
            inference_delay=max(
                1,
                round(
                    float(getattr(self.config, "inference_latency", 0.0))
                    * self.config.fps
                ),
            ),
        )
        if not isinstance(action_tensor, torch.Tensor):
            action_tensor = torch.as_tensor(action_tensor, dtype=torch.float32)
        if action_tensor.ndim == 3:
            action_tensor = action_tensor.squeeze(0)
        chunk_size = int(getattr(self.config, "actions_per_chunk", 0) or action_tensor.shape[0])
        action_tensor = action_tensor[:chunk_size].detach().cpu()
        self.action_chunk_size = max(self.action_chunk_size, action_tensor.shape[0])
        timed_actions = self._time_action_chunk(
            observation_t.get_timestamp(),
            action_tensor,
            observation_t.get_timestep(),
        )
        if verbose:
            self.logger.info(
                "OpenPI websocket observation %s | total %.2fms | action shape %s",
                observation_t.get_timestep(),
                1000 * (time.perf_counter() - start),
                tuple(action_tensor.shape),
            )
        return timed_actions

    def receive_actions(self, verbose: bool = False):
        self.start_barrier.wait()
        self._receiver_started.set()
        self.logger.info("OpenPI websocket action receiver starting")

        while self.running:
            observation_t = self._pop_latest_observation()
            if observation_t is None:
                time.sleep(min(self.config.environment_dt, 0.01))
                continue

            try:
                timed_actions = self._predict_timed_actions(observation_t, verbose=verbose)
                self._aggregate_action_queues(timed_actions, self.config.aggregate_fn)
                self.must_go.set()
            except Exception as exc:
                self.logger.error("OpenPI websocket action receiver failed: %s", exc)
                self.shutdown_event.set()
