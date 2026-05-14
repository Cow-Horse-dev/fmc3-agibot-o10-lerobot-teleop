import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ARM_HAND_TELEOP_ROOT = REPO_ROOT.parent
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))
if str(ARM_HAND_TELEOP_ROOT) not in sys.path:
    sys.path.insert(0, str(ARM_HAND_TELEOP_ROOT))


fake_airbot_hardware = types.ModuleType("airbot_hardware_py")
fake_airbot_hardware.MotorType = SimpleNamespace(OD=object(), DM=object(), NA=object())
fake_airbot_hardware.EEFType = SimpleNamespace(NA=object())
fake_airbot_hardware.MotorControlMode = SimpleNamespace(PVT=object())
fake_airbot_hardware.create_asio_executor = lambda *args, **kwargs: SimpleNamespace(
    get_io_context=lambda: SimpleNamespace()
)
fake_airbot_hardware.Play = SimpleNamespace(
    create=lambda *args, **kwargs: SimpleNamespace(
        init=lambda *args, **kwargs: True,
        uninit=lambda *args, **kwargs: None,
        enable=lambda *args, **kwargs: None,
        disable=lambda *args, **kwargs: None,
        set_param=lambda *args, **kwargs: None,
        pvt=lambda *args, **kwargs: None,
        state=lambda: SimpleNamespace(pos=[0.0] * 6),
    )
)
fake_mmk2_kdl = types.ModuleType("mmk2_kdl_py")
fake_mmk2_kdl.ArmKdlNumerical = lambda *args, **kwargs: SimpleNamespace()

sys.modules.setdefault("airbot_hardware_py", fake_airbot_hardware)
sys.modules.setdefault("mmk2_kdl_py", fake_mmk2_kdl)


from lerobot_play.utils.multi_lora import (  # noqa: E402
    SwitchablePeftPolicy,
    TaskProfileRegistry,
    TaskSwitchCommandStore,
    TaskSwitchCoordinator,
)


def _write_profile_config(tmp_path: Path) -> Path:
    adapter_a = tmp_path / "adapter_a"
    adapter_b = tmp_path / "adapter_b"
    adapter_a.mkdir()
    adapter_b.mkdir()
    config_path = tmp_path / "profiles.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "base_model_path": str(tmp_path / "base_pi05"),
                "default_profile": "black_to_yellow",
                "command_file": str(tmp_path / "switch.json"),
                "profiles": {
                    "black_to_yellow": {
                        "adapter_path": str(adapter_a),
                        "task_description": "move tissue from black paper to yellow paper",
                    },
                    "yellow_to_black": {
                        "adapter_path": str(adapter_b),
                        "task_description": "move tissue from yellow paper to black paper",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_task_profile_registry_loads_profiles_and_resolves_task_text(tmp_path):
    registry = TaskProfileRegistry.from_path(_write_profile_config(tmp_path))

    assert registry.default_profile.profile_id == "black_to_yellow"
    assert registry.default_profile.task_description == "move tissue from black paper to yellow paper"
    assert registry.command_file == tmp_path / "switch.json"
    assert registry.profile_for_task_description(
        "move tissue from yellow paper to black paper"
    ).profile_id == "yellow_to_black"
    assert registry.effective_pretrained_path == registry.default_profile.adapter_path


def test_task_profile_registry_allows_text_only_profiles_for_fullft_switching(tmp_path):
    config_path = tmp_path / "fullft_tasks.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "default_profile": "black_to_yellow",
                "command_file": str(tmp_path / "fullft_switch.json"),
                "profiles": {
                    "black_to_yellow": {
                        "task_description": "move tissue from black paper to yellow paper",
                    },
                    "yellow_to_black": {
                        "task_description": "move tissue from yellow paper to black paper",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    registry = TaskProfileRegistry.from_path(config_path)

    assert registry.default_profile.profile_id == "black_to_yellow"
    assert registry.default_profile.adapter_path is None
    assert registry.profile_for_id("yellow_to_black").task_description == (
        "move tissue from yellow paper to black paper"
    )


def test_task_switch_command_store_writes_and_reads_atomically(tmp_path):
    registry = TaskProfileRegistry.from_path(_write_profile_config(tmp_path))
    store = TaskSwitchCommandStore(registry.command_file)

    store.write("yellow_to_black")

    payload = json.loads(registry.command_file.read_text(encoding="utf-8"))
    assert payload["profile_id"] == "yellow_to_black"
    assert store.read_latest_profile_id() == "yellow_to_black"
    assert store.read_latest_profile_id() is None


def test_switch_coordinator_waits_until_boundary_before_switching(tmp_path):
    registry = TaskProfileRegistry.from_path(_write_profile_config(tmp_path))
    store = TaskSwitchCommandStore(registry.command_file)
    switched = []

    coordinator = TaskSwitchCoordinator(
        registry=registry,
        command_store=store,
        initial_profile_id="black_to_yellow",
        switch_callback=lambda profile: switched.append(profile.profile_id),
    )

    store.write("yellow_to_black")

    assert coordinator.maybe_switch(is_switch_boundary=False).profile_id == "black_to_yellow"
    assert switched == []
    assert coordinator.maybe_switch(is_switch_boundary=True).profile_id == "yellow_to_black"
    assert switched == ["yellow_to_black"]


class _FakePeftPolicy:
    def __init__(self):
        self.config = SimpleNamespace(device="cpu")
        self.loaded_adapters = []
        self.set_adapters = []
        self.reset_count = 0
        self.rtc_init_count = 0

    def load_adapter(self, model_id, adapter_name, is_trainable=False, **kwargs):
        self.loaded_adapters.append((str(model_id), adapter_name, is_trainable, kwargs))

    def set_adapter(self, adapter_name, inference_mode=False):
        self.set_adapters.append((adapter_name, inference_mode))

    def reset(self):
        self.reset_count += 1

    def init_rtc_processor(self):
        self.rtc_init_count += 1


def test_switchable_peft_policy_preloads_and_switches_adapters(tmp_path):
    registry = TaskProfileRegistry.from_path(_write_profile_config(tmp_path))
    fake_policy = _FakePeftPolicy()

    policy = SwitchablePeftPolicy(fake_policy, registry)
    policy.preload_remaining_adapters()

    assert fake_policy.loaded_adapters == [
        (
            str(registry.profile_for_id("yellow_to_black").adapter_path),
            "yellow_to_black",
            False,
            {},
        )
    ]

    changed = policy.switch_to_profile("yellow_to_black")

    assert changed is True
    assert policy.active_profile.profile_id == "yellow_to_black"
    assert fake_policy.set_adapters == [("yellow_to_black", True)]
    assert fake_policy.reset_count == 1
    assert fake_policy.rtc_init_count == 1


def test_infer_load_policy_uses_single_base_and_preloads_multi_lora_adapters(
    tmp_path, monkeypatch
):
    from lerobot_play.infer import _load_policy

    config_path = _write_profile_config(tmp_path)
    base_model = tmp_path / "base_pi05"
    base_model.mkdir()

    loaded_base_paths = []
    wrapped = []

    class DummyConfig:
        device = "cpu"

    class DummyBasePolicy:
        def __init__(self):
            self.config = DummyConfig()
            self.loaded_adapters = []

        def to(self, device):
            self.config.device = device
            return self

        def load_adapter(self, model_id, adapter_name, is_trainable=False, **kwargs):
            self.loaded_adapters.append((str(model_id), adapter_name, is_trainable))

    class DummyPeftConfig:
        base_model_name_or_path = str(base_model)

    class DummyPeftModel:
        @staticmethod
        def from_pretrained(policy, adapter_path, adapter_name="default", config=None, **kwargs):
            wrapped.append((policy, str(adapter_path), adapter_name, config))
            return policy

    fake_peft = types.ModuleType("peft")
    fake_peft.PeftConfig = SimpleNamespace(from_pretrained=lambda adapter_path: DummyPeftConfig())
    fake_peft.PeftModel = DummyPeftModel
    monkeypatch.setitem(sys.modules, "peft", fake_peft)

    def fake_from_pretrained(model_path, **kwargs):
        loaded_base_paths.append(model_path)
        return DummyBasePolicy()

    monkeypatch.setattr("lerobot_play.infer.PI05Policy.from_pretrained", fake_from_pretrained)

    policy = _load_policy("pi05", str(config_path), "cuda")

    assert isinstance(policy, SwitchablePeftPolicy)
    assert loaded_base_paths == [str(base_model)]
    assert wrapped[0][1] == str(policy.registry.default_profile.adapter_path)
    assert wrapped[0][2] == "black_to_yellow"
    assert policy.policy.loaded_adapters == [
        (str(policy.registry.profile_for_id("yellow_to_black").adapter_path), "yellow_to_black", False)
    ]
    assert policy.config.device == "cuda"


def test_async_policy_server_switches_adapter_from_task_and_resets_rtc(monkeypatch):
    from lerobot.async_inference.configs import PolicyServerConfig
    from lerobot_play.async_inference.policy_server import PolicyServer

    switched_tasks = []

    class DummySwitchablePolicy:
        def switch_to_task_description(self, task_description):
            switched_tasks.append(task_description)
            return True

    server = PolicyServer(PolicyServerConfig())
    server.policy = DummySwitchablePolicy()
    server._rtc_previous_action_chunk = object()
    server._rtc_previous_timestep = 42

    server._switch_policy_for_task("move tissue from yellow paper to black paper")

    assert switched_tasks == ["move tissue from yellow paper to black paper"]
    assert server._rtc_previous_action_chunk is None
    assert server._rtc_previous_timestep is None


def test_switch_lora_task_tool_writes_profile_command(tmp_path):
    from scripts.tools.switch_lora_task import switch_lora_task

    config_path = _write_profile_config(tmp_path)

    command_file = switch_lora_task(config_path, "yellow_to_black")

    assert command_file == tmp_path / "switch.json"
    payload = json.loads(command_file.read_text(encoding="utf-8"))
    assert payload["profile_id"] == "yellow_to_black"
