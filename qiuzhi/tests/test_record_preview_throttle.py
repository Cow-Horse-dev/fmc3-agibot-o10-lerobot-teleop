from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_RECORD_SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/utils/lerobot_record.py"
)
RECORD_ENTRYPOINT_SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/record.py"
)


def test_record_display_source_uses_async_worker_for_rerun_only():
    source = LEROBOT_RECORD_SRC_FILE.read_text(encoding="utf-8")

    assert "class _RecordPreviewWorker" in source
    assert "threading.Thread(" in source
    assert "preview_worker.submit(" in source
    assert "log_rerun_data(" in source
    assert "preview_worker.stop()" in source
    assert "def render_latest(" not in source
    assert "preview_worker.render_latest()" not in source
    assert "def _pump_record_preview_events(" not in source
    assert "cv2.imshow" not in source
    assert "cv2.waitKey" not in source


def test_record_display_does_not_pump_gui_events_on_main_thread():
    source = LEROBOT_RECORD_SRC_FILE.read_text(encoding="utf-8")

    assert "class _RecordPreviewPump" not in source
    assert "preview_pump" not in source


def test_record_entrypoint_configures_rerun_blueprint_from_current_cameras():
    source = RECORD_ENTRYPOINT_SRC_FILE.read_text(encoding="utf-8")

    assert "from .utils.rerun_control_display import configure_control_rerun_display" in source
    assert "configure_control_rerun_display(robot)" in source


def test_wrapped_record_configures_rerun_blueprint_from_current_cameras():
    source = LEROBOT_RECORD_SRC_FILE.read_text(encoding="utf-8")

    assert (
        "from lerobot_play.utils.rerun_control_display import configure_control_rerun_display"
        in source
    )
    assert "configure_control_rerun_display(robot)" in source
