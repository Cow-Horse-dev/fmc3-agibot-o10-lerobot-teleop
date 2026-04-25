from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
YUDIE_ROOT = REPO_ROOT / "yudie"
LEROBOT_PLAY_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
for _path in (str(LEROBOT_PLAY_ROOT), str(YUDIE_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

O12_MODULE_PATH = YUDIE_ROOT / "AGIBOT" / "Omnihand_o12_yudie.py"
O10_MODULE_PATH = YUDIE_ROOT / "AGIBOT" / "Omnihand_o10_yudie.py"


def _load_o10_module_with_fake_sdk(monkeypatch):
    fake_sdk = types.ModuleType("omnihand_2025")
    fake_sdk.AgibotHandO10 = object
    fake_sdk.EFinger = object
    fake_sdk.EControlMode = object
    fake_sdk.EHandType = object
    monkeypatch.setitem(sys.modules, "omnihand_2025", fake_sdk)

    spec = importlib.util.spec_from_file_location("test_yudie_o10_module", O10_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_o12_module_with_fake_sdk(monkeypatch):
    class FakeEHandType:
        LEFT = "left"
        RIGHT = "right"

    class FakeAgibotHandO12:
        instances = []

        def __init__(self, hand_type):
            self.hand_type = hand_type
            self.joint_positions_calls = []
            self.active_joint_angles_calls = []
            FakeAgibotHandO12.instances.append(self)

        def get_vendor_info(self):
            return "fake vendor"

        def get_device_info(self):
            return "fake device"

        def set_all_joint_positions(self, positions):
            self.joint_positions_calls.append(list(positions))

        def set_all_active_joint_angles(self, angles):
            self.active_joint_angles_calls.append(list(angles))

    fake_sdk = types.ModuleType("agibot_hand")
    fake_sdk.AgibotHandO12 = FakeAgibotHandO12
    fake_sdk.EHandType = FakeEHandType
    monkeypatch.setitem(sys.modules, "agibot_hand", fake_sdk)

    spec = importlib.util.spec_from_file_location("test_yudie_o12_module", O12_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module, FakeAgibotHandO12


def test_dexhand_rejects_unimplemented_zklx_mode_before_control_loop(monkeypatch):
    import DexHand_Motion_Control_Program as dexhand

    class FakeGloveReceiver:
        def initialize(self, *_args, **_kwargs):
            pass

        def start_listening(self):
            pass

        def get_data_valid(self):
            return True

        def end_listening(self):
            pass

    monkeypatch.setattr(dexhand, "GloveReceiver", FakeGloveReceiver)
    monkeypatch.setattr(sys, "argv", ["dexhand", "--mode", "ZKLX_Hand"])

    with pytest.raises(SystemExit) as exc_info:
        dexhand.main()

    assert exc_info.value.code == 2


def test_dexhand_stops_when_udp_receiver_initialization_fails(monkeypatch):
    import DexHand_Motion_Control_Program as dexhand
    from Data_Receiver import ServerStatus

    class FakeGloveReceiver:
        start_called = False

        def initialize(self, *_args, **_kwargs):
            self.cur_status = ServerStatus.NO_INIT

        def start_listening(self):
            FakeGloveReceiver.start_called = True

        def get_data_valid(self):
            raise KeyboardInterrupt

        def end_listening(self):
            pass

    fake_o10 = types.ModuleType("AGIBOT.Omnihand_o10_yudie")
    fake_o10.init_hand_Omni_multiCan = lambda *_args, **_kwargs: [None, object()]
    fake_o10.init_hand_OmnimultiChannel = lambda *_args, **_kwargs: [None, object()]
    fake_o10.is_hand_ready = lambda *_args, **_kwargs: True
    fake_o10.set_hand_position = lambda *_args, **_kwargs: None

    monkeypatch.setitem(sys.modules, "AGIBOT.Omnihand_o10_yudie", fake_o10)
    monkeypatch.setattr(dexhand, "GloveReceiver", FakeGloveReceiver)
    monkeypatch.setattr(sys, "argv", ["dexhand", "--mode", "agibotHand_O10", "--hand", "right"])

    dexhand.main()

    assert FakeGloveReceiver.start_called is False


def test_o12_reset_positions_reuses_initial_reset_target(monkeypatch):
    module, fake_hand_cls = _load_o12_module_with_fake_sdk(monkeypatch)

    hand = module.Agibot_HandO12(hand_type="left")
    hand.reset_positions()

    fake_hand = fake_hand_cls.instances[-1]
    assert fake_hand.joint_positions_calls == [[2000] * 12, [2000] * 12]


def test_o12_left_set_angles_uses_left_hand_mapping(monkeypatch):
    module, fake_hand_cls = _load_o12_module_with_fake_sdk(monkeypatch)
    hand = module.Agibot_HandO12(hand_type="left")
    glove_data = [0.0] * 24
    glove_data[20] = 45.0

    hand.set_angles(glove_data)

    fake_hand = fake_hand_cls.instances[-1]
    assert fake_hand.active_joint_angles_calls[-1][0] == pytest.approx(0.942)


def test_o10_set_hand_position_routes_through_o10_hand_mapper(monkeypatch):
    """Smoke test: yudie's set_hand_position must drive the hand via O10HandMapper
    (deadband / EMA / curve behavior is covered separately in the mapper unit tests)."""
    module = _load_o10_module_with_fake_sdk(monkeypatch)

    class FakeHand:
        def __init__(self):
            self.calls = []

        def set_all_active_joint_angles(self, positions):
            self.calls.append(list(positions))

    hand = FakeHand()
    baseline = [0.0] * 24
    module.set_hand_position(hand, baseline, "right")

    assert len(hand.calls) == 1
    assert len(hand.calls[0]) == 10
    # Right-hand thumb_cm_roll has a fixed -10° offset even at zero glove input.
    import math as _math
    assert hand.calls[0][0] == pytest.approx(_math.radians(-10.0), abs=1e-9)


def test_o10_set_hand_position_keeps_per_hand_mapper_state(monkeypatch):
    """Two distinct hand instances must not share mapper state."""
    module = _load_o10_module_with_fake_sdk(monkeypatch)

    class FakeHand:
        def __init__(self):
            self.calls = []

        def set_all_active_joint_angles(self, positions):
            self.calls.append(list(positions))

    hand_a = FakeHand()
    hand_b = FakeHand()
    glove = [0.0] * 24
    glove[6] = 40.0  # drive index_pitch on hand_a only

    for _ in range(20):
        module.set_hand_position(hand_a, glove, "right")
    module.set_hand_position(hand_b, [0.0] * 24, "right")

    # hand_a is at steady state (channel 4 nonzero); hand_b is fresh (channel 4 ≈ 0)
    assert hand_a.calls[-1][4] != 0.0
    assert hand_b.calls[-1][4] == 0.0


def test_json_receiver_preserves_valid_fields_when_parameter_names_are_malformed():
    from Data_Receiver import GloveReceiver

    receiver = GloveReceiver()
    receiver.dataType = "Json"
    receiver.requestedRole = "teleop"
    receiver.targetRole = "teleop"

    receiver.process_data(
        json.dumps(
            {
                "teleop": {
                    "Parameter": [
                        {"Name": "x", "Value": 99.0},
                        {"Value": 88.0},
                        {"Name": "l_button", "Value": 1.0},
                        {"Name": "r0", "Value": 12.5},
                    ]
                }
            }
        )
    )

    assert receiver.get_data_valid()
    assert receiver.controller_data_list[0]["controllerDatas"] == {"l_button": 1.0}
    assert receiver.get_hand_data("right")[0] == 12.5
