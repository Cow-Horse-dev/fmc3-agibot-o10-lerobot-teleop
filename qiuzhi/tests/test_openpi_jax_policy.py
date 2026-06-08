import io
import sys
from pathlib import Path

import numpy as np
import pytest
import torch


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


def test_openpi_jax_adapter_builds_aloha_request_and_trims_padded_actions():
    from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

    captured = {}

    class FakeOpenPIPolicy:
        def infer(self, observation, **kwargs):
            captured["observation"] = observation
            return {
                "actions": np.arange(50 * 32, dtype=np.float32).reshape(50, 32),
            }

    adapter = OpenPIJaxPolicyAdapter(
        FakeOpenPIPolicy(),
        config_name="pi05_parcel_sorting",
        default_prompt="sort the express parcels",
        action_dim=14,
    )
    top_image = np.zeros((4, 5, 3), dtype=np.uint8)
    left_wrist_image = np.ones((4, 5, 3), dtype=np.uint8)
    right_wrist_image = np.full((4, 5, 3), 2, dtype=np.uint8)

    action_chunk = adapter.predict_action_chunk_from_raw(
        {
            "observation.state": np.arange(14, dtype=np.float32),
            "observation.images.top": top_image,
            "observation.images.left_wrist": left_wrist_image,
            "observation.images.right_wrist": right_wrist_image,
        }
    )

    assert tuple(action_chunk.shape) == (1, 50, 14)
    assert action_chunk.dtype == torch.float32
    assert torch.equal(
        action_chunk[0, 0],
        torch.arange(14, dtype=torch.float32),
    )
    observation = captured["observation"]
    assert observation["prompt"] == "sort the express parcels"
    assert observation["state"].shape == (14,)
    assert observation["images"]["cam_high"].shape == (3, 4, 5)
    assert observation["images"]["cam_left_wrist"].shape == (3, 4, 5)
    assert observation["images"]["cam_right_wrist"].shape == (3, 4, 5)


def test_openpi_jax_adapter_prefers_runtime_task_prompt():
    from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

    captured = {}

    class FakeOpenPIPolicy:
        def infer(self, observation, **kwargs):
            captured["prompt"] = observation["prompt"]
            return {"actions": np.zeros((2, 14), dtype=np.float32)}

    adapter = OpenPIJaxPolicyAdapter(
        FakeOpenPIPolicy(),
        config_name="pi05_parcel_sorting",
        default_prompt="sort the express parcels",
        action_dim=14,
    )
    image = np.zeros((3, 2, 2), dtype=np.uint8)

    adapter.predict_action_chunk_from_raw(
        {
            "state": np.zeros(14, dtype=np.float32),
            "top": image,
            "left_wrist": image,
            "right_wrist": image,
            "task": "sort the blue parcel",
        }
    )

    assert captured["prompt"] == "sort the blue parcel"


def test_openpi_jax_adapter_forwards_rtc_kwargs_to_worker():
    from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

    captured = {}

    class FakeOpenPIPolicy:
        def infer(self, observation, **kwargs):
            captured["observation"] = observation
            captured["kwargs"] = kwargs
            return {
                "actions": np.zeros((4, 14), dtype=np.float32),
                "raw_actions": np.zeros((4, 32), dtype=np.float32),
            }

    adapter = OpenPIJaxPolicyAdapter(
        FakeOpenPIPolicy(),
        config_name="pi05_parcel_sorting",
        default_prompt="sort the express parcels",
        action_dim=14,
    )
    adapter.config.rtc_config = type(
        "FakeRTCConfig",
        (),
        {
            "enabled": True,
            "execution_horizon": 3,
            "max_guidance_weight": 7.5,
            "prefix_attention_schedule": "EXP",
        },
    )()
    image = np.zeros((3, 2, 2), dtype=np.uint8)
    previous_chunk = torch.arange(6, dtype=torch.float32).reshape(1, 3, 2)

    adapter.predict_action_chunk_from_raw(
        {
            "state": np.zeros(14, dtype=np.float32),
            "top": image,
            "left_wrist": image,
            "right_wrist": image,
        },
        prev_chunk_left_over=previous_chunk,
        inference_delay=2,
        execution_horizon=3,
    )

    assert captured["observation"]["state"].shape == (14,)
    assert captured["kwargs"]["inference_delay"] == 2
    assert captured["kwargs"]["execution_horizon"] == 3
    assert captured["kwargs"]["max_guidance_weight"] == 7.5
    assert captured["kwargs"]["prefix_attention_schedule"] == "EXP"
    np.testing.assert_array_equal(
        captured["kwargs"]["prev_chunk_left_over"],
        previous_chunk.numpy(),
    )


def test_openpi_jax_adapter_keeps_raw_model_actions_for_rtc_leftover():
    from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

    captured = {}
    raw_actions = np.arange(4 * 32, dtype=np.float32).reshape(4, 32)
    robot_actions = np.zeros((4, 14), dtype=np.float32)

    class FakeOpenPIPolicy:
        def infer(self, observation, **kwargs):
            captured["kwargs"] = kwargs
            return {
                "actions": robot_actions,
                "raw_actions": raw_actions,
            }

    adapter = OpenPIJaxPolicyAdapter(
        FakeOpenPIPolicy(),
        config_name="pi05_parcel_sorting",
        default_prompt="sort the express parcels",
        action_dim=14,
    )
    image = np.zeros((3, 2, 2), dtype=np.uint8)

    action_chunk = adapter.predict_action_chunk_from_raw(
        {
            "state": np.zeros(14, dtype=np.float32),
            "top": image,
            "left_wrist": image,
            "right_wrist": image,
        }
    )

    assert captured["kwargs"]["return_raw_actions"] is True
    assert tuple(action_chunk.shape) == (1, 4, 14)
    rtc_chunk = adapter.get_last_rtc_action_chunk()
    assert tuple(rtc_chunk.shape) == (1, 4, 32)
    np.testing.assert_array_equal(rtc_chunk.squeeze(0).numpy(), raw_actions)


def test_openpi_jax_adapter_requires_raw_model_actions_when_rtc_enabled():
    from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

    class FakeOpenPIPolicy:
        def infer(self, observation, **kwargs):
            return {"actions": np.zeros((4, 14), dtype=np.float32)}

    adapter = OpenPIJaxPolicyAdapter(
        FakeOpenPIPolicy(),
        config_name="pi05_parcel_sorting",
        default_prompt="sort the express parcels",
        action_dim=14,
    )
    adapter.config.rtc_config = type(
        "FakeRTCConfig",
        (),
        {"enabled": True},
    )()
    image = np.zeros((3, 2, 2), dtype=np.uint8)

    with pytest.raises(KeyError, match="raw_actions"):
        adapter.predict_action_chunk_from_raw(
            {
                "state": np.zeros(14, dtype=np.float32),
                "top": image,
                "left_wrist": image,
                "right_wrist": image,
            }
        )


def test_openpi_jax_adapter_builds_state_from_o10_flat_joint_keys():
    from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

    captured = {}

    class FakeOpenPIPolicy:
        def infer(self, observation, **kwargs):
            captured["state"] = observation["state"]
            return {"actions": np.zeros((1, 14), dtype=np.float32)}

    raw_observation = {
        "top": np.zeros((3, 2, 2), dtype=np.uint8),
        "left_wrist": np.zeros((3, 2, 2), dtype=np.uint8),
        "right_wrist": np.zeros((3, 2, 2), dtype=np.uint8),
    }
    names = [
        *(f"left.joint{index}.pos" for index in range(1, 7)),
        "left.gripper.pos",
        *(f"right.joint{index}.pos" for index in range(1, 7)),
        "right.gripper.pos",
    ]
    for index, name in enumerate(names):
        raw_observation[name] = float(index)

    adapter = OpenPIJaxPolicyAdapter(
        FakeOpenPIPolicy(),
        config_name="pi05_parcel_sorting",
        default_prompt="sort the express parcels",
        action_dim=14,
    )

    adapter.predict_action_chunk_from_raw(raw_observation)

    np.testing.assert_array_equal(
        captured["state"],
        np.arange(14, dtype=np.float32),
    )


def test_openpi_jax_from_checkpoint_starts_worker_with_openpi_environment(monkeypatch):
    from lerobot_play import openpi_jax_policy
    from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

    captured = {}

    class FakeProcess:
        stdin = io.BytesIO()
        stdout = io.BytesIO()

        def poll(self):
            return None

    def fake_popen(cmd, *, stdin, stdout, stderr, env, bufsize):
        captured["cmd"] = cmd
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["env"] = env
        captured["bufsize"] = bufsize
        return FakeProcess()

    monkeypatch.setenv("ARM_HAND_TELEOP_OPENPI_JAX_PYTHON", "/tmp/openpi-python")
    monkeypatch.setenv("ARM_HAND_TELEOP_OPENPI_ROOT", "/tmp/openpi")
    monkeypatch.setattr(openpi_jax_policy.subprocess, "Popen", fake_popen)

    adapter = OpenPIJaxPolicyAdapter.from_checkpoint("/tmp/checkpoint/10000")

    assert adapter.config_name == "pi05_parcel_sorting"
    assert captured["cmd"][0] == "/tmp/openpi-python"
    assert captured["cmd"][1].endswith("openpi_jax_worker.py")
    assert "--checkpoint-dir" in captured["cmd"]
    assert "/tmp/checkpoint/10000" in captured["cmd"]
    assert captured["env"]["ARM_HAND_TELEOP_OPENPI_CONFIG"] == "pi05_parcel_sorting"
    assert captured["env"]["ARM_HAND_TELEOP_OPENPI_DEFAULT_PROMPT"] == "sort the express parcels"
    assert captured["env"]["PYTHONPATH"].startswith(
        "/tmp/openpi/src:/tmp/openpi/packages/openpi-client/src"
    )
    assert captured["bufsize"] == 0


def test_openpi_jax_worker_policy_close_terminates_subprocess():
    from lerobot_play.openpi_jax_policy import OpenPIJaxWorkerPolicy

    calls = []

    class FakePipe:
        def close(self):
            calls.append("stdin.close")

    class FakeProcess:
        stdin = FakePipe()

        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout=None):
            calls.append(("wait", timeout))

    policy = OpenPIJaxWorkerPolicy.__new__(OpenPIJaxWorkerPolicy)
    policy._process = FakeProcess()

    policy.close()

    assert calls == ["stdin.close", "terminate", ("wait", 5.0)]


def test_openpi_jax_websocket_policy_adds_openpi_client_source_path(monkeypatch):
    from lerobot_play import openpi_jax_policy
    from lerobot_play.openpi_jax_policy import OpenPIJaxWebsocketPolicy

    captured = {}

    class FakeClientPolicy:
        def __init__(self, host, port):
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setenv("ARM_HAND_TELEOP_OPENPI_ROOT", "/tmp/openpi")
    monkeypatch.setattr(
        openpi_jax_policy,
        "_import_websocket_client_policy",
        lambda: FakeClientPolicy,
    )

    policy = OpenPIJaxWebsocketPolicy.from_server_address("127.0.0.1:8000")

    assert policy._policy.__class__ is FakeClientPolicy
    assert captured == {"host": "127.0.0.1", "port": 8000}
    assert sys.path[0] == "/tmp/openpi/packages/openpi-client/src"


def test_openpi_jax_websocket_adapter_sends_rtc_control_in_observation():
    from lerobot_play.openpi_jax_policy import OpenPIJaxPolicyAdapter

    captured = {}

    class FakeWebsocketPolicy:
        def infer(self, observation):
            captured["observation"] = observation
            return {
                "actions": np.zeros((50, 14), dtype=np.float32),
                "raw_actions": np.zeros((50, 32), dtype=np.float32),
            }

    adapter = OpenPIJaxPolicyAdapter(
        FakeWebsocketPolicy(),
        config_name="pi05_parcel_sorting",
        default_prompt="sort the express parcels",
        action_dim=14,
        policy_accepts_kwargs=False,
    )
    adapter.config.rtc_config = type(
        "FakeRTCConfig",
        (),
        {
            "enabled": True,
            "execution_horizon": 10,
            "max_guidance_weight": 7.5,
            "prefix_attention_schedule": "EXP",
        },
    )()
    image = np.zeros((3, 2, 2), dtype=np.uint8)

    adapter.predict_action_chunk_from_raw(
        {
            "state": np.zeros(14, dtype=np.float32),
            "top": image,
            "left_wrist": image,
            "right_wrist": image,
        },
        inference_delay=3,
        execution_horizon=8,
        timestep=42,
        actions_per_chunk=50,
    )

    assert captured["observation"]["openpi_rtc"] == {
        "inference_delay": 3,
        "execution_horizon": 8,
        "max_guidance_weight": 7.5,
        "prefix_attention_schedule": "EXP",
        "timestep": 42,
        "actions_per_chunk": 50,
    }


def test_openpi_websocket_robot_client_enables_rtc_and_sends_control(monkeypatch):
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot_play.async_inference import openpi_ws_robot_client
    from lerobot_play.async_inference.policy_server import _apply_rtc_env_config

    captured = {}

    class FakeAdapter:
        def __init__(self):
            self.config = type("FakePolicyConfig", (), {"rtc_config": None})()

        def predict_action_chunk_from_raw(self, raw_observation, **kwargs):
            captured["raw_observation"] = raw_observation
            captured["kwargs"] = kwargs
            return torch.zeros((1, 2, 14), dtype=torch.float32)

    monkeypatch.setenv("ARM_HAND_TELEOP_RTC_ENABLED", "1")
    monkeypatch.setenv("ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON", "10")

    policy = FakeAdapter()
    _apply_rtc_env_config(policy)
    client = openpi_ws_robot_client.OpenPIWebsocketRobotClient.__new__(
        openpi_ws_robot_client.OpenPIWebsocketRobotClient
    )
    client.policy = policy
    client.config = type(
        "FakeConfig",
        (),
        {
            "environment_dt": 1 / 30,
            "actions_per_chunk": 2,
            "fps": 30,
            "inference_latency": 0.1,
        },
    )()
    client.action_chunk_size = -1
    client.logger = type("FakeLogger", (), {"info": lambda *args, **kwargs: None})()

    timed_actions = client._predict_timed_actions(
        TimedObservation(
            timestamp=123.0,
            timestep=7,
            observation={"state": np.zeros(14, dtype=np.float32)},
        )
    )

    assert client.policy.config.rtc_config.enabled is True
    assert captured["kwargs"]["timestep"] == 7
    assert captured["kwargs"]["actions_per_chunk"] == 2
    assert captured["kwargs"]["inference_delay"] == 3
    assert [action.get_timestep() for action in timed_actions] == [7, 8]
