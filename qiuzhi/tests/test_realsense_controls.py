import sys
import types
from pathlib import Path
from types import SimpleNamespace


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


def test_apply_realsense_controls_sets_color_sensor_options(monkeypatch):
    from lerobot_play.utils.realsense_controls import apply_realsense_controls

    calls = []

    class FakeSensor:
        def supports(self, option):
            return True

        def set_option(self, option, value):
            calls.append((option, value))

    fake_rs = types.ModuleType("pyrealsense2")
    fake_rs.option = SimpleNamespace(
        enable_auto_exposure="enable_auto_exposure",
        exposure="exposure",
        gain="gain",
    )
    monkeypatch.setitem(sys.modules, "pyrealsense2", fake_rs)

    profile = SimpleNamespace(
        get_device=lambda: SimpleNamespace(query_sensors=lambda: [FakeSensor()])
    )
    camera = SimpleNamespace(rs_profile=profile)

    apply_realsense_controls(
        "right_wrist",
        camera,
        {
            "right_wrist": {
                "auto_exposure": False,
                "exposure_us": 4000,
                "gain": 16,
            }
        },
    )

    assert calls == [
        ("enable_auto_exposure", 0.0),
        ("exposure", 4000.0),
        ("gain", 16.0),
    ]


def test_apply_realsense_controls_ignores_cameras_without_controls(monkeypatch):
    from lerobot_play.utils.realsense_controls import apply_realsense_controls

    monkeypatch.delitem(sys.modules, "pyrealsense2", raising=False)

    apply_realsense_controls("top", SimpleNamespace(), {"right_wrist": {"gain": 16}})
