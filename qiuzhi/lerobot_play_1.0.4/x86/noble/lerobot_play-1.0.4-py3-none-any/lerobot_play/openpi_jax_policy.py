from __future__ import annotations

import os
import pickle
import struct
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch

from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_GRIPPER_FEATURE_NAMES,
)


OPENPI_CONFIG_ENV = "ARM_HAND_TELEOP_OPENPI_CONFIG"
OPENPI_DEFAULT_PROMPT_ENV = "ARM_HAND_TELEOP_OPENPI_DEFAULT_PROMPT"
OPENPI_ACTION_DIM_ENV = "ARM_HAND_TELEOP_OPENPI_ACTION_DIM"
OPENPI_JAX_PYTHON_ENV = "ARM_HAND_TELEOP_OPENPI_JAX_PYTHON"
OPENPI_ROOT_ENV = "ARM_HAND_TELEOP_OPENPI_ROOT"
DEFAULT_OPENPI_CONFIG = "pi05_parcel_sorting"
DEFAULT_OPENPI_PROMPT = "sort the express parcels"
DEFAULT_ROBOT_ACTION_DIM = 14
DEFAULT_OPENPI_ROOT = "~/workspace/openpi"
RTC_CONTROL_KEY = "openpi_rtc"


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


def _write_message(stream, payload: Any) -> None:
    data = pickle.dumps(payload)
    stream.write(struct.pack(">I", len(data)))
    stream.write(data)
    stream.flush()


def _read_message(stream) -> Any:
    size_bytes = stream.read(4)
    if len(size_bytes) != 4:
        raise RuntimeError("OpenPI JAX worker exited before sending a response")
    size = struct.unpack(">I", size_bytes)[0]
    payload = stream.read(size)
    if len(payload) != size:
        raise RuntimeError("OpenPI JAX worker sent an incomplete response")
    return pickle.loads(payload)  # nosec


def _to_numpy(value: Any) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _sample_kwarg_value(value: Any) -> Any:
    if isinstance(value, torch.Tensor):
        value = value.detach().cpu().numpy()
    if isinstance(value, np.ndarray) and np.issubdtype(value.dtype, np.floating):
        return value.astype(np.float32, copy=False)
    return value


def _openpi_client_source_path() -> str:
    openpi_root = os.path.expanduser(os.environ.get(OPENPI_ROOT_ENV, DEFAULT_OPENPI_ROOT))
    return os.path.join(openpi_root, "packages", "openpi-client", "src")


def _ensure_openpi_client_source_path() -> None:
    source_path = _openpi_client_source_path()
    if source_path not in sys.path:
        sys.path.insert(0, source_path)


def _import_websocket_client_policy():
    _ensure_openpi_client_source_path()
    from openpi_client.websocket_client_policy import WebsocketClientPolicy

    return WebsocketClientPolicy


def _split_server_address(server_address: str) -> tuple[str, int | None]:
    if server_address.startswith("ws://") or server_address.startswith("wss://"):
        return server_address, None
    host, separator, port = server_address.rpartition(":")
    if separator and port.isdigit():
        return host, int(port)
    return server_address, None


def _first_present(raw_observation: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw_observation and raw_observation[key] is not None:
            return raw_observation[key]
    raise KeyError(f"Missing required OpenPI observation key; tried: {', '.join(keys)}")


def _state_vector(raw_observation: dict[str, Any]) -> np.ndarray:
    if "observation.state" not in raw_observation and "state" not in raw_observation:
        return _o10_dual_arm_state_vector(raw_observation)

    state = _to_numpy(_first_present(raw_observation, ("observation.state", "state")))
    if state.ndim == 2 and state.shape[0] == 1:
        state = state[0]
    return state.astype(np.float32, copy=False)


def _o10_dual_arm_state_vector(raw_observation: dict[str, Any]) -> np.ndarray:
    names: list[str] = []
    gripper_feature = AGIBOT_O10_GRIPPER_FEATURE_NAMES[0]
    for side in ("left", "right"):
        names.extend(f"{side}.{feature}" for feature in AGIBOT_O10_ARM_FEATURE_NAMES)
        names.append(f"{side}.{gripper_feature}")

    missing_names = [name for name in names if name not in raw_observation]
    if missing_names:
        raise KeyError(
            "Missing OpenPI O10 state keys: " + ", ".join(missing_names)
        )
    return np.asarray([raw_observation[name] for name in names], dtype=np.float32)


def _image_chw(raw_observation: dict[str, Any], *keys: str) -> np.ndarray:
    image = _to_numpy(_first_present(raw_observation, tuple(keys)))
    if image.ndim == 4 and image.shape[0] == 1:
        image = image[0]
    if image.ndim != 3:
        raise ValueError(f"OpenPI image must be rank 3, got shape {image.shape}")
    if np.issubdtype(image.dtype, np.floating):
        image = np.clip(image, 0.0, 1.0) * 255.0
        image = image.astype(np.uint8)
    if image.shape[-1] == 3:
        image = np.transpose(image, (2, 0, 1))
    if image.shape[0] != 3:
        raise ValueError(f"OpenPI image must be CHW or HWC RGB, got shape {image.shape}")
    return image.astype(np.uint8, copy=False)


def _prompt(raw_observation: dict[str, Any], default_prompt: str) -> str:
    prompt = raw_observation.get("task") or raw_observation.get("prompt") or default_prompt
    if isinstance(prompt, bytes):
        return prompt.decode("utf-8")
    return str(prompt)


class OpenPIJaxWorkerPolicy:
    def __init__(
        self,
        *,
        checkpoint_dir: str,
        config_name: str,
        default_prompt: str,
    ) -> None:
        self._process = self._start_worker(
            checkpoint_dir=checkpoint_dir,
            config_name=config_name,
            default_prompt=default_prompt,
        )

    @staticmethod
    def _start_worker(
        *,
        checkpoint_dir: str,
        config_name: str,
        default_prompt: str,
    ):
        openpi_root = os.path.expanduser(os.environ.get(OPENPI_ROOT_ENV, DEFAULT_OPENPI_ROOT))
        openpi_python = os.path.expanduser(
            os.environ.get(
                OPENPI_JAX_PYTHON_ENV,
                "~/miniconda3/envs/openpi-jax/bin/python",
            )
        )
        worker_path = os.path.join(os.path.dirname(__file__), "openpi_jax_worker.py")
        env = dict(os.environ)
        env[OPENPI_CONFIG_ENV] = config_name
        env[OPENPI_DEFAULT_PROMPT_ENV] = default_prompt
        env["PYTHONPATH"] = ":".join(
            part
            for part in (
                os.path.join(openpi_root, "src"),
                os.path.join(openpi_root, "packages", "openpi-client", "src"),
                env.get("PYTHONPATH", ""),
            )
            if part
        )
        return subprocess.Popen(
            [
                openpi_python,
                worker_path,
                "--checkpoint-dir",
                checkpoint_dir,
                "--config",
                config_name,
                "--default-prompt",
                default_prompt,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            env=env,
            bufsize=0,
        )

    def infer(self, observation: dict[str, Any], **sample_kwargs: Any) -> dict[str, Any]:
        if self._process.poll() is not None:
            raise RuntimeError("OpenPI JAX worker is not running")
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("OpenPI JAX worker pipes are not available")

        request = {
            "observation": observation,
            "sample_kwargs": sample_kwargs,
        }
        _write_message(self._process.stdin, request)
        response = _read_message(self._process.stdout)
        if isinstance(response, dict) and "error" in response:
            raise RuntimeError(f"OpenPI JAX worker failed:\n{response['error']}")
        return response

    def close(self) -> None:
        process = getattr(self, "_process", None)
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)


class OpenPIJaxWebsocketPolicy:
    def __init__(self, policy: Any) -> None:
        self._policy = policy

    @classmethod
    def from_server_address(cls, server_address: str) -> "OpenPIJaxWebsocketPolicy":
        _ensure_openpi_client_source_path()
        WebsocketClientPolicy = _import_websocket_client_policy()
        host, port = _split_server_address(server_address)
        return cls(WebsocketClientPolicy(host=host, port=port))

    def infer(self, observation: dict[str, Any]) -> dict[str, Any]:
        return self._policy.infer(observation)


class OpenPIJaxPolicyAdapter:
    """Adapter exposing an OpenPI JAX policy as an async LeRobot action source."""

    def __init__(
        self,
        policy: Any,
        *,
        config_name: str,
        default_prompt: str,
        action_dim: int = DEFAULT_ROBOT_ACTION_DIM,
        policy_accepts_kwargs: bool = True,
    ) -> None:
        self._policy = policy
        self.config_name = config_name
        self.default_prompt = default_prompt
        self.action_dim = action_dim
        self.policy_accepts_kwargs = policy_accepts_kwargs
        self._last_rtc_action_chunk: torch.Tensor | None = None
        self.config = SimpleNamespace(
            device="jax",
            image_features={},
            rtc_config=None,
        )

    @classmethod
    def from_server_address(cls, server_address: str) -> "OpenPIJaxPolicyAdapter":
        config_name = os.environ.get(OPENPI_CONFIG_ENV, DEFAULT_OPENPI_CONFIG)
        default_prompt = os.environ.get(OPENPI_DEFAULT_PROMPT_ENV, DEFAULT_OPENPI_PROMPT)
        action_dim = _env_int(OPENPI_ACTION_DIM_ENV, DEFAULT_ROBOT_ACTION_DIM)
        policy = OpenPIJaxWebsocketPolicy.from_server_address(server_address)
        return cls(
            policy,
            config_name=config_name,
            default_prompt=default_prompt,
            action_dim=action_dim,
            policy_accepts_kwargs=False,
        )

    @classmethod
    def from_checkpoint(cls, checkpoint_dir: str) -> "OpenPIJaxPolicyAdapter":
        config_name = os.environ.get(OPENPI_CONFIG_ENV, DEFAULT_OPENPI_CONFIG)
        default_prompt = os.environ.get(OPENPI_DEFAULT_PROMPT_ENV, DEFAULT_OPENPI_PROMPT)
        action_dim = _env_int(OPENPI_ACTION_DIM_ENV, DEFAULT_ROBOT_ACTION_DIM)

        policy = OpenPIJaxWorkerPolicy(
            checkpoint_dir=checkpoint_dir,
            config_name=config_name,
            default_prompt=default_prompt,
        )
        return cls(
            policy,
            config_name=config_name,
            default_prompt=default_prompt,
            action_dim=action_dim,
        )

    def _build_openpi_observation(self, raw_observation: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": _state_vector(raw_observation),
            "images": {
                "cam_high": _image_chw(
                    raw_observation,
                    "observation.images.top",
                    "top",
                    "cam_high",
                ),
                "cam_left_wrist": _image_chw(
                    raw_observation,
                    "observation.images.left_wrist",
                    "left_wrist",
                    "cam_left_wrist",
                ),
                "cam_right_wrist": _image_chw(
                    raw_observation,
                    "observation.images.right_wrist",
                    "right_wrist",
                    "cam_right_wrist",
                ),
            },
            "prompt": _prompt(raw_observation, self.default_prompt),
        }

    def _build_sample_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        sample_kwargs = {
            key: _sample_kwarg_value(value)
            for key, value in kwargs.items()
            if value is not None
        }
        if not sample_kwargs:
            return {}

        rtc_config = getattr(self.config, "rtc_config", None)
        if rtc_config is None or not getattr(rtc_config, "enabled", False):
            return sample_kwargs

        sample_kwargs.setdefault(
            "execution_horizon",
            getattr(rtc_config, "execution_horizon", None),
        )
        sample_kwargs["max_guidance_weight"] = getattr(
            rtc_config,
            "max_guidance_weight",
            10.0,
        )
        sample_kwargs["prefix_attention_schedule"] = _enum_value(
            getattr(rtc_config, "prefix_attention_schedule", "EXP")
        )
        return {
            key: value
            for key, value in sample_kwargs.items()
            if value is not None
        }

    def _build_rtc_control(self, sample_kwargs: dict[str, Any]) -> dict[str, Any]:
        rtc_config = getattr(self.config, "rtc_config", None)
        if rtc_config is None or not getattr(rtc_config, "enabled", False):
            return {}

        control = {
            key: value
            for key, value in sample_kwargs.items()
            if key
            in {
                "inference_delay",
                "execution_horizon",
                "max_guidance_weight",
                "prefix_attention_schedule",
                "timestep",
                "actions_per_chunk",
            }
            and value is not None
        }
        control.setdefault(
            "execution_horizon",
            getattr(rtc_config, "execution_horizon", None),
        )
        control.setdefault(
            "max_guidance_weight",
            getattr(rtc_config, "max_guidance_weight", 10.0),
        )
        control.setdefault(
            "prefix_attention_schedule",
            _enum_value(getattr(rtc_config, "prefix_attention_schedule", "EXP")),
        )
        return {
            key: value
            for key, value in control.items()
            if value is not None
        }

    def predict_action_chunk_from_raw(
        self,
        raw_observation: dict[str, Any],
        **kwargs: Any,
    ) -> torch.Tensor:
        observation = self._build_openpi_observation(raw_observation)
        sample_kwargs = self._build_sample_kwargs(kwargs)
        if self.policy_accepts_kwargs:
            result = self._policy.infer(
                observation,
                **sample_kwargs,
                return_raw_actions=True,
            )
        else:
            rtc_control = self._build_rtc_control(sample_kwargs)
            if rtc_control:
                observation[RTC_CONTROL_KEY] = rtc_control
            result = self._policy.infer(observation)
        if "actions" not in result:
            raise KeyError("OpenPI policy result did not contain 'actions'")

        actions = _to_numpy(result["actions"])
        if actions.ndim == 3 and actions.shape[0] == 1:
            actions = actions[0]
        if actions.ndim == 1:
            actions = actions[np.newaxis, :]
        if actions.ndim != 2:
            raise ValueError(f"OpenPI actions must be rank 2, got shape {actions.shape}")

        actions = actions[:, : self.action_dim].astype(np.float32, copy=False)
        if "raw_actions" not in result and self._rtc_enabled():
            raise KeyError("OpenPI policy result did not contain 'raw_actions'")
        raw_actions = _to_numpy(result.get("raw_actions", actions))
        if raw_actions.ndim == 3 and raw_actions.shape[0] == 1:
            raw_actions = raw_actions[0]
        if raw_actions.ndim == 1:
            raw_actions = raw_actions[np.newaxis, :]
        if raw_actions.ndim != 2:
            raise ValueError(f"OpenPI raw actions must be rank 2, got shape {raw_actions.shape}")
        self._last_rtc_action_chunk = torch.from_numpy(
            raw_actions.astype(np.float32, copy=True)
        ).unsqueeze(0)
        return torch.from_numpy(actions).unsqueeze(0)

    def get_last_rtc_action_chunk(self) -> torch.Tensor:
        if self._last_rtc_action_chunk is None:
            raise RuntimeError("OpenPI JAX policy has not produced an RTC action chunk yet")
        return self._last_rtc_action_chunk

    def _rtc_enabled(self) -> bool:
        rtc_config = getattr(self.config, "rtc_config", None)
        return bool(rtc_config is not None and getattr(rtc_config, "enabled", False))

    def close(self) -> None:
        close = getattr(self._policy, "close", None)
        if close is not None:
            close()
