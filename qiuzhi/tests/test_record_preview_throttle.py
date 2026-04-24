from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_RECORD_SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/utils/lerobot_record.py"
)


def test_record_preview_source_uses_async_worker_for_local_preview():
    source = LEROBOT_RECORD_SRC_FILE.read_text(encoding="utf-8")

    assert "class _RecordPreviewWorker" in source
    assert "threading.Thread(" in source
    assert "preview_worker.submit(" in source
    assert "def render_latest(" in source
    assert "def _pump_record_preview_events(events: dict[str, Any])" in source
    assert "_pump_record_preview_events(events)" in source
    assert 'events["stop_recording"] = True' in source
    assert 'events["exit_early"] = True' in source
    assert "preview_worker.render_latest()" in source
    assert "preview_worker.stop()" in source
