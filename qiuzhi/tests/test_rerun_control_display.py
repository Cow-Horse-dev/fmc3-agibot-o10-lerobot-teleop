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


def test_control_rerun_blueprint_uses_only_current_camera_keys(monkeypatch):
    from lerobot_play.utils.rerun_control_display import send_control_rerun_blueprint

    sent = []

    class FakeSpatial2DView:
        def __init__(self, *, origin, contents, name):
            self.origin = origin
            self.contents = contents
            self.name = name

    class FakeTimeSeriesView:
        def __init__(self, *, origin, contents, name):
            self.origin = origin
            self.contents = contents
            self.name = name

    class FakeGrid:
        def __init__(self, *views, grid_columns, name):
            self.views = views
            self.grid_columns = grid_columns
            self.name = name

    class FakeVertical:
        def __init__(self, *views, row_shares, name):
            self.views = views
            self.row_shares = row_shares
            self.name = name

    class FakeBlueprint:
        def __init__(self, *parts, auto_layout, auto_views, collapse_panels):
            self.parts = parts
            self.auto_layout = auto_layout
            self.auto_views = auto_views
            self.collapse_panels = collapse_panels

    fake_rr = types.ModuleType("rerun")
    fake_rr.__path__ = []
    fake_rr.send_blueprint = lambda *args, **kwargs: sent.append((args, kwargs))
    fake_rrb = types.ModuleType("rerun.blueprint")
    fake_rrb.Blueprint = FakeBlueprint
    fake_rrb.Grid = FakeGrid
    fake_rrb.Spatial2DView = FakeSpatial2DView
    fake_rrb.TimeSeriesView = FakeTimeSeriesView
    fake_rrb.Vertical = FakeVertical
    fake_rr.blueprint = fake_rrb
    monkeypatch.setitem(sys.modules, "rerun", fake_rr)
    monkeypatch.setitem(sys.modules, "rerun.blueprint", fake_rrb)

    send_control_rerun_blueprint(["top", "right_wrist"])

    assert len(sent) == 1
    blueprint = sent[0][0][0]
    assert sent[0][1] == {"make_active": True, "make_default": True}
    assert blueprint.auto_layout is False
    assert blueprint.auto_views is False
    assert blueprint.collapse_panels is False
    layout = blueprint.parts[0]
    assert layout.row_shares == [3, 1]
    grid = layout.views[0]
    trajectory_view = layout.views[1]
    assert grid.grid_columns == 2
    assert [view.name for view in grid.views] == [
        "observation.top",
        "observation.right_wrist",
    ]
    assert [view.origin for view in grid.views] == [
        "observation.top",
        "observation.right_wrist",
    ]
    assert [view.contents for view in grid.views] == ["$origin", "$origin"]
    assert trajectory_view.name == "action/observation trajectories"
    assert trajectory_view.origin == "/"
    assert trajectory_view.contents == "+ /**"


def test_display_camera_keys_keep_configured_order_and_report_missing():
    from lerobot_play.utils.rerun_control_display import get_display_camera_keys

    robot = SimpleNamespace(
        config=SimpleNamespace(cameras={"top": object(), "right_wrist": object()}),
        cameras={"top": object()},
    )

    camera_keys, missing_keys = get_display_camera_keys(robot)

    assert camera_keys == ["top", "right_wrist"]
    assert missing_keys == ["right_wrist"]
