from pathlib import Path
import sys

import pytest


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

from lerobot_play.utils.runtime_helpers import (
    build_task_date_repo_id,
    dataset_root_from_repo_id,
    decode_replay_action,
    prepare_dataset_root_for_recording,
    resolve_record_dataset_target,
    resolve_dataset_target,
)


def test_dataset_root_from_repo_id_appends_repo_id_for_parent_root(tmp_path):
    repo_id = "agi_arm_bot"
    assert dataset_root_from_repo_id(repo_id, tmp_path) == tmp_path / repo_id


def test_dataset_root_from_repo_id_reuses_explicit_dataset_directory(tmp_path):
    dataset_root = tmp_path / "agi_arm_bot"
    assert dataset_root_from_repo_id("agi_arm_bot", dataset_root) == dataset_root


def test_resolve_dataset_target_derives_repo_id_from_dataset_path(tmp_path):
    dataset_root = tmp_path / "agi_arm_bot_20260410"
    target = resolve_dataset_target(path=dataset_root)

    assert target.repo_id == "agi_arm_bot_20260410"
    assert target.root == dataset_root


def test_resolve_dataset_target_expands_tilde_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    target = resolve_dataset_target(path="~/datasets/agi_arm_bot_20260410")

    assert target.repo_id == "agi_arm_bot_20260410"
    assert target.root == (tmp_path / "datasets" / "agi_arm_bot_20260410")


def test_build_task_date_repo_id_uses_normalized_task_name():
    repo_id = build_task_date_repo_id("Pick And Place", date_format="%Y%m%d")

    assert repo_id.endswith("_" + repo_id.split("_")[-1])
    assert repo_id.startswith("pick_and_place_")


def test_resolve_record_dataset_target_auto_names_from_task_and_date(tmp_path):
    target = resolve_record_dataset_target(
        repo_id="ignored_name",
        root=tmp_path / "agi_arm_bot",
        task_name="Pick And Place",
        auto_name_from_task_date=True,
        date_format="%Y%m%d",
    )

    assert target.repo_id.startswith("pick_and_place_")
    assert target.root == (tmp_path / "agi_arm_bot" / target.repo_id)


def test_prepare_dataset_root_for_recording_removes_incomplete_dataset(tmp_path):
    dataset_root = tmp_path / "agi_arm_bot"
    (dataset_root / "meta").mkdir(parents=True)

    prepared_root = prepare_dataset_root_for_recording("agi_arm_bot", dataset_root)

    assert prepared_root == dataset_root
    assert not dataset_root.exists()


def test_decode_replay_action_for_agibot_o10_uses_joint_only_layout():
    action = decode_replay_action(
        "pico_follower_single_arm_agibot_o10",
        list(range(23)),
    )

    assert action == {
        "joints": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        "hand_joints": [6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
    }


def test_decode_replay_action_rejects_short_agibot_o10_actions():
    with pytest.raises(ValueError, match="at least 16 values"):
        decode_replay_action("pico_follower_single_arm_agibot_o10", list(range(12)))
