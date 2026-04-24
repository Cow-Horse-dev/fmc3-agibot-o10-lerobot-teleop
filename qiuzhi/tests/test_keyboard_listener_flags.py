from pathlib import Path
import sys
import types


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

fake_lerobot_dataset = types.ModuleType("lerobot_play.utils.lerobot_dataset")
fake_lerobot_dataset.LeRobotDataset = object
sys.modules.setdefault("lerobot_play.utils.lerobot_dataset", fake_lerobot_dataset)

from lerobot_play.utils import control_utils


class _FakeKey:
    space = object()
    enter = object()
    right = object()
    left = object()
    esc = object()


class _FakeListener:
    def __init__(self, on_press):
        self.on_press = on_press

    def start(self):
        return None


def _install_fake_keyboard(monkeypatch):
    fake_keyboard_module = types.SimpleNamespace(
        Key=_FakeKey,
        Listener=_FakeListener,
    )
    fake_pynput_module = types.SimpleNamespace(keyboard=fake_keyboard_module)

    monkeypatch.setattr(control_utils, "is_headless", lambda: False)
    monkeypatch.setitem(sys.modules, "pynput", fake_pynput_module)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_keyboard_module)


def test_keyboard_listener_right_arrow_does_not_stop_recording(monkeypatch):
    _install_fake_keyboard(monkeypatch)

    listener, events = control_utils.init_keyboard_listener()
    assert listener is not None

    listener.on_press(_FakeKey.space)
    listener.on_press(_FakeKey.right)

    assert events["start"] is True
    assert events["exit_early"] is True
    assert events["rerecord_episode"] is False
    assert events["stop_recording"] is False


def test_keyboard_listener_left_arrow_marks_rerecord_only(monkeypatch):
    _install_fake_keyboard(monkeypatch)

    listener, events = control_utils.init_keyboard_listener()
    assert listener is not None

    listener.on_press(_FakeKey.space)
    listener.on_press(_FakeKey.left)

    assert events["start"] is True
    assert events["exit_early"] is True
    assert events["rerecord_episode"] is True
    assert events["stop_recording"] is False


def test_keyboard_listener_ignores_duplicate_exit_keys_after_first_request(monkeypatch):
    _install_fake_keyboard(monkeypatch)

    listener, events = control_utils.init_keyboard_listener()
    assert listener is not None

    listener.on_press(_FakeKey.space)
    listener.on_press(_FakeKey.left)
    listener.on_press(_FakeKey.right)
    listener.on_press(_FakeKey.esc)

    assert events["keyboard_exit_requested"] is True
    assert events["rerecord_episode"] is True
    assert events["exit_early"] is True
    assert events["stop_recording"] is False
