import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent / "test_ude_glove_hand_control.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("ude_glove_hand_control", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_single_mode_builds_one_hand_runtime_config():
    module = _load_script_module()

    args = module.parse_args(
        [
            "--mode",
            "single",
            "--hand",
            "left",
            "--device-id",
            "3",
            "--canfd-id",
            "2",
            "--channel-id",
            "4",
        ]
    )

    configs = module.build_hand_runtime_configs(args)

    assert [config.handedness for config in configs] == ["left"]
    assert configs[0].device_id == 3
    assert configs[0].canfd_id == 2
    assert configs[0].channel_id == 4


def test_dual_mode_builds_left_and_right_runtime_configs_with_defaults():
    module = _load_script_module()

    args = module.parse_args(["--mode", "dual"])

    configs = module.build_hand_runtime_configs(args)

    assert [config.handedness for config in configs] == ["left", "right"]
    assert [config.channel_id for config in configs] == [0, 1]
    assert [config.device_id for config in configs] == [1, 1]
    assert [config.canfd_id for config in configs] == [0, 0]


def test_dual_mode_allows_per_side_channel_overrides():
    module = _load_script_module()

    args = module.parse_args(
        [
            "--mode",
            "dual",
            "--left-channel-id",
            "5",
            "--right-channel-id",
            "6",
        ]
    )

    configs = module.build_hand_runtime_configs(args)

    assert [config.channel_id for config in configs] == [5, 6]


def test_dual_mode_uses_one_shared_glove_receiver(monkeypatch):
    module = _load_script_module()
    init_calls = []

    class FakeGlove:
        def __init__(self):
            init_calls.append("glove")

        def initialize(self):
            return None

        def start_listening(self):
            return None

        def end_listening(self):
            return None

        def get_role_name_list(self):
            return []

        def get_vec_finger_data(self, role_name):
            return []

    monkeypatch.setattr(module, "UDEGloveSDK", FakeGlove)

    args = module.parse_args(["--mode", "dual"])
    receiver = module.GloveDataReceiver(args)

    receiver.start()
    receiver.stop()

    assert init_calls == ["glove"]


def test_dual_mode_can_share_one_unclassified_glove_role():
    module = _load_script_module()

    args = module.parse_args(["--mode", "dual"])
    receiver = module.GloveDataReceiver(args)

    assert receiver._select_role_name(["main"], "left") == "main"
    assert receiver._select_role_name(["main"], "right") == "main"
