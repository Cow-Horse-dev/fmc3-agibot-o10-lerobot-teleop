import io
import logging
import os
import pickle  # nosec
import time
from concurrent import futures
from dataclasses import asdict
from inspect import signature
from pprint import pformat

import draccus
import grpc
import torch

from lerobot.async_inference.configs import PolicyServerConfig
from lerobot.async_inference.constants import SUPPORTED_POLICIES
from lerobot.async_inference.helpers import RemotePolicyConfig
import lerobot.async_inference.policy_server as base_policy_server
from lerobot.async_inference.policy_server import PolicyServer as BasePolicyServer
from lerobot.async_inference.policy_server import make_pre_post_processors
from lerobot.configs.types import RTCAttentionSchedule
from lerobot.policies.rtc.configuration_rtc import RTCConfig
from lerobot.transport import services_pb2, services_pb2_grpc
from lerobot_play.utils.multi_lora import TaskProfileRegistry, is_multi_lora_config_path


RTC_ENABLED_ENV = "ARM_HAND_TELEOP_RTC_ENABLED"
RTC_EXECUTION_HORIZON_ENV = "ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON"
RTC_MAX_GUIDANCE_WEIGHT_ENV = "ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT"
RTC_PREFIX_ATTENTION_SCHEDULE_ENV = "ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE"
RTC_DEBUG_ENV = "ARM_HAND_TELEOP_RTC_DEBUG"
TransferState = services_pb2.TransferState  # type: ignore[attr-defined]


def _effective_pretrained_path(model_path: str) -> str:
    if is_multi_lora_config_path(model_path):
        return str(TaskProfileRegistry.from_path(model_path).effective_pretrained_path)
    return model_path


def _load_policy(policy_type: str, model_path: str, device: str):
    from lerobot_play.infer import _load_policy as load_policy

    return load_policy(policy_type, model_path, device)


def _build_policy_preprocessor_overrides(
    policy_type: str,
    device: str,
    observation_rename_map: dict[str, str] | None = None,
):
    from lerobot_play.infer import (
        _build_policy_preprocessor_overrides as build_overrides,
    )

    return build_overrides(policy_type, device, observation_rename_map)


def _build_policy_postprocessor_overrides(
    policy_type: str,
    device: str | None = None,
):
    from lerobot_play.infer import (
        _build_policy_postprocessor_overrides as build_overrides,
    )

    return build_overrides(policy_type, device=device)


def _policy_action_dim_from_model_path(model_path: str) -> int | None:
    from lerobot_play.infer import (
        _policy_action_dim_from_model_path as action_dim_from_model_path,
    )

    return action_dim_from_model_path(model_path)


def _trim_action_tensor_to_action_dim(action_tensor: torch.Tensor, action_dim: int | None):
    from lerobot_play.infer import (
        _trim_action_tensor_to_action_dim as trim_action_tensor,
    )

    return trim_action_tensor(action_tensor, action_dim)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _apply_rtc_env_config(policy) -> None:
    if not _env_flag(RTC_ENABLED_ENV):
        return

    rtc_config = RTCConfig(
        enabled=True,
        execution_horizon=int(os.environ.get(RTC_EXECUTION_HORIZON_ENV, "10")),
        max_guidance_weight=float(os.environ.get(RTC_MAX_GUIDANCE_WEIGHT_ENV, "10.0")),
        prefix_attention_schedule=RTCAttentionSchedule(
            os.environ.get(RTC_PREFIX_ATTENTION_SCHEDULE_ENV, "EXP")
        ),
        debug=_env_flag(RTC_DEBUG_ENV),
    )
    policy.config.rtc_config = rtc_config
    if hasattr(policy, "init_rtc_processor"):
        policy.init_rtc_processor()


def _rename_observation_inputs_for_legacy_helper(
    raw_observation: dict,
    lerobot_features: dict,
    observation_rename_map: dict[str, str],
) -> tuple[dict, dict]:
    if not observation_rename_map:
        return raw_observation, lerobot_features

    renamed_observation = dict(raw_observation)
    renamed_features = dict(lerobot_features)

    for source_key, target_key in observation_rename_map.items():
        if source_key not in renamed_features:
            continue

        renamed_features[target_key] = renamed_features.pop(source_key)

        image_prefix = "observation.images."
        if source_key.startswith(image_prefix) and target_key.startswith(image_prefix):
            source_raw_key = source_key.removeprefix(image_prefix)
            target_raw_key = target_key.removeprefix(image_prefix)
            if source_raw_key in renamed_observation:
                renamed_observation[target_raw_key] = renamed_observation[source_raw_key]

    return renamed_observation, renamed_features


def _raw_observation_to_observation_compat(
    raw_observation: dict,
    lerobot_features: dict,
    policy_image_features: dict,
    observation_rename_map: dict[str, str],
):
    helper = base_policy_server.raw_observation_to_observation
    if "observation_rename_map" in signature(helper).parameters:
        return helper(
            raw_observation,
            lerobot_features,
            policy_image_features,
            observation_rename_map=observation_rename_map,
        )

    raw_observation, lerobot_features = _rename_observation_inputs_for_legacy_helper(
        raw_observation,
        lerobot_features,
        observation_rename_map,
    )
    return helper(raw_observation, lerobot_features, policy_image_features)


def _receive_bytes_in_chunks_quiet(request_iterator, shutdown_event):
    bytes_buffer = io.BytesIO()
    step = 0

    logging.debug("[POLICY_SERVER] Observation receiver starting")
    for item in request_iterator:
        logging.debug("[POLICY_SERVER] Received observation chunk")
        if shutdown_event.is_set():
            logging.debug("[POLICY_SERVER] Observation receiver shutting down")
            return None

        if item.transfer_state == TransferState.TRANSFER_BEGIN:
            bytes_buffer.seek(0)
            bytes_buffer.truncate(0)
            bytes_buffer.write(item.data)
            step = 0
        elif item.transfer_state == TransferState.TRANSFER_MIDDLE:
            bytes_buffer.write(item.data)
            step += 1
            logging.debug("[POLICY_SERVER] Received observation chunk %s", step)
        elif item.transfer_state == TransferState.TRANSFER_END:
            bytes_buffer.write(item.data)
            return bytes_buffer.getvalue()
        else:
            raise ValueError(f"Received unknown transfer state {item.transfer_state}")

    return None


class PolicyServer(BasePolicyServer):
    def SendObservations(self, request_iterator, context):  # noqa: N802
        """Receive observations from the robot client without per-frame INFO spam."""
        client_id = context.peer()
        self.logger.debug(f"Receiving observations from {client_id}")

        receive_time = time.time()
        start_deserialize = time.perf_counter()
        received_bytes = _receive_bytes_in_chunks_quiet(
            request_iterator,
            self.shutdown_event,
        )
        if received_bytes is None:
            return services_pb2.Empty()

        timed_observation = pickle.loads(received_bytes)  # nosec
        deserialize_time = time.perf_counter() - start_deserialize

        self.logger.debug(f"Received observation #{timed_observation.get_timestep()}")

        obs_timestep = timed_observation.get_timestep()
        obs_timestamp = timed_observation.get_timestamp()
        fps_metrics = self.fps_tracker.calculate_fps_metrics(obs_timestamp)

        self.logger.debug(
            f"Received observation #{obs_timestep} | "
            f"Avg FPS: {fps_metrics['avg_fps']:.2f} | "
            f"Target: {fps_metrics['target_fps']:.2f} | "
            f"One-way latency: {(receive_time - obs_timestamp) * 1000:.2f}ms"
        )
        self.logger.debug(
            f"Server timestamp: {receive_time:.6f} | "
            f"Client timestamp: {obs_timestamp:.6f} | "
            f"Deserialization time: {deserialize_time:.6f}s"
        )

        if not self._enqueue_observation(timed_observation):
            self.logger.debug(f"Observation #{obs_timestep} has been filtered out")

        return services_pb2.Empty()

    def SendPolicyInstructions(self, request, context):  # noqa: N802
        """Receive policy instructions and load policies with local PEFT support."""
        if not self.running:
            self.logger.warning("Server is not running. Ignoring policy instructions.")
            return services_pb2.Empty()

        client_id = context.peer()
        policy_specs = pickle.loads(request.data)  # nosec

        if not isinstance(policy_specs, RemotePolicyConfig):
            raise TypeError(
                f"Policy specs must be a RemotePolicyConfig. Got {type(policy_specs)}"
            )

        if policy_specs.policy_type not in SUPPORTED_POLICIES:
            raise ValueError(
                f"Policy type {policy_specs.policy_type} not supported. "
                f"Supported policies: {SUPPORTED_POLICIES}"
            )

        self.logger.info(
            f"Receiving policy instructions from {client_id} | "
            f"Policy type: {policy_specs.policy_type} | "
            f"Pretrained name or path: {policy_specs.pretrained_name_or_path} | "
            f"Actions per chunk: {policy_specs.actions_per_chunk} | "
            f"Device: {policy_specs.device}"
        )

        self.device = policy_specs.device
        self.policy_type = policy_specs.policy_type
        self.lerobot_features = policy_specs.lerobot_features
        self.actions_per_chunk = policy_specs.actions_per_chunk
        self.observation_rename_map = dict(policy_specs.rename_map)

        start = time.perf_counter()
        self.policy = _load_policy(
            self.policy_type,
            policy_specs.pretrained_name_or_path,
            self.device,
        )
        _apply_rtc_env_config(self.policy)
        effective_pretrained_path = _effective_pretrained_path(
            policy_specs.pretrained_name_or_path
        )
        self.postprocess_action_dim = _policy_action_dim_from_model_path(
            effective_pretrained_path
        )

        self.preprocessor, self.postprocessor = make_pre_post_processors(
            self.policy.config,
            pretrained_path=effective_pretrained_path,
            preprocessor_overrides=_build_policy_preprocessor_overrides(
                self.policy_type,
                self.device,
                policy_specs.rename_map,
            ),
            postprocessor_overrides=_build_policy_postprocessor_overrides(
                self.policy_type,
                device=self.device,
            ),
        )

        end = time.perf_counter()
        self.logger.info(
            f"Time taken to put policy on {self.device}: {end - start:.4f} seconds"
        )

        return services_pb2.Empty()

    def _switch_policy_for_task(self, task_description: str | None) -> None:
        if not task_description or not hasattr(self.policy, "switch_to_task_description"):
            return

        changed = self.policy.switch_to_task_description(task_description)
        if not changed:
            return

        self._rtc_previous_action_chunk = None
        self._rtc_previous_timestep = None
        self.logger.info("Switched active LoRA adapter for task: %s", task_description)

    def _rtc_enabled(self) -> bool:
        rtc_config = getattr(getattr(self.policy, "config", None), "rtc_config", None)
        return bool(rtc_config is not None and getattr(rtc_config, "enabled", False))

    def _rtc_predict_kwargs(self, observation_timestep: int) -> dict[str, object]:
        if not self._rtc_enabled():
            return {}

        previous_chunk = getattr(self, "_rtc_previous_action_chunk", None)
        previous_timestep = getattr(self, "_rtc_previous_timestep", None)
        if previous_chunk is None or previous_timestep is None:
            return {}

        consumed_actions = max(observation_timestep - previous_timestep, 0)
        if consumed_actions >= previous_chunk.shape[1]:
            return {}

        rtc_config = self.policy.config.rtc_config
        inference_delay = max(
            1,
            round(float(getattr(self.config, "inference_latency", 0.0)) * self.config.fps),
        )
        return {
            "prev_chunk_left_over": previous_chunk[:, consumed_actions:, :],
            "inference_delay": inference_delay,
            "execution_horizon": rtc_config.execution_horizon,
        }

    def _get_action_chunk(
        self,
        observation: dict[str, torch.Tensor],
        observation_timestep: int | None = None,
    ) -> torch.Tensor:
        predict_kwargs = (
            self._rtc_predict_kwargs(observation_timestep)
            if observation_timestep is not None
            else {}
        )
        chunk = self.policy.predict_action_chunk(observation, **predict_kwargs)
        if chunk.ndim != 3:
            chunk = chunk.unsqueeze(0)

        chunk = chunk[:, : self.actions_per_chunk, :]
        if self._rtc_enabled() and observation_timestep is not None:
            self._rtc_previous_action_chunk = chunk.detach()
            self._rtc_previous_timestep = observation_timestep

        return chunk

    def _predict_action_chunk(self, observation_t):
        start_prepare = time.perf_counter()
        self._switch_policy_for_task(observation_t.get_observation().get("task"))
        observation = _raw_observation_to_observation_compat(
            observation_t.get_observation(),
            self.lerobot_features,
            self.policy_image_features,
            self.observation_rename_map,
        )
        prepare_time = time.perf_counter() - start_prepare

        start_preprocess = time.perf_counter()
        observation = self.preprocessor(observation)
        self.last_processed_obs = observation_t
        preprocessing_time = time.perf_counter() - start_preprocess

        start_inference = time.perf_counter()
        action_tensor = self._get_action_chunk(
            observation,
            observation_t.get_timestep(),
        )
        inference_time = time.perf_counter() - start_inference
        self.logger.info(
            f"Preprocessing and inference took {inference_time:.4f}s, "
            f"action shape: {action_tensor.shape}"
        )

        start_postprocess = time.perf_counter()
        postprocess_action_tensor = _trim_action_tensor_to_action_dim(
            action_tensor,
            getattr(self, "postprocess_action_dim", None),
        )
        _, chunk_size, _ = postprocess_action_tensor.shape
        processed_actions = []
        for index in range(chunk_size):
            single_action = postprocess_action_tensor[:, index, :]
            processed_actions.append(self.postprocessor(single_action))

        action_tensor = torch.stack(processed_actions, dim=1).squeeze(0)
        self.logger.debug(f"Postprocessed action shape: {action_tensor.shape}")
        action_tensor = action_tensor.detach().cpu()

        action_chunk = self._time_action_chunk(
            observation_t.get_timestamp(),
            list(action_tensor),
            observation_t.get_timestep(),
        )
        postprocess_stops = time.perf_counter()
        postprocessing_time = postprocess_stops - start_postprocess

        self.logger.info(
            f"Observation {observation_t.get_timestep()} | "
            f"Total time: {1000 * (postprocess_stops - start_prepare):.2f}ms"
        )
        self.logger.debug(
            f"Observation {observation_t.get_timestep()} | "
            f"Prepare time: {1000 * prepare_time:.2f}ms | "
            f"Preprocessing time: {1000 * preprocessing_time:.2f}ms | "
            f"Inference time: {1000 * inference_time:.2f}ms | "
            f"Postprocessing time: {1000 * postprocessing_time:.2f}ms | "
            f"Total time: {1000 * (postprocess_stops - start_prepare):.2f}ms"
        )

        return action_chunk


@draccus.wrap()
def serve(cfg: PolicyServerConfig):
    logging.info(pformat(asdict(cfg)))

    policy_server = PolicyServer(cfg)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    services_pb2_grpc.add_AsyncInferenceServicer_to_server(policy_server, server)
    server.add_insecure_port(f"{cfg.host}:{cfg.port}")

    policy_server.logger.info(f"PolicyServer started on {cfg.host}:{cfg.port}")
    server.start()
    server.wait_for_termination()

    policy_server.logger.info("Server terminated")


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
