import json
from pathlib import Path
import sys


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

from lerobot_play.utils.agibot_o10 import AGIBOT_O10_HAND_FEATURE_NAMES
from lerobot_play.utils.joint_target_store import PersistentJointTargetStore
from lerobot_play.utils.o10_hand_pose_capture import (
    capture_glove_o10_hand_joint_pos,
    capture_robot_o10_hand_joint_pos,
    default_o10_hand_pose_path,
    save_o10_hand_joint_target,
)


def test_joint_target_store_save_preserves_existing_description(tmp_path):
    output_path = tmp_path / "pose.json"
    output_path.write_text(
        json.dumps(
            {
                "description": "keep me",
                "feature_names": list(AGIBOT_O10_HAND_FEATURE_NAMES),
                "joint_values": {
                    feature_name: 0.0
                    for feature_name in AGIBOT_O10_HAND_FEATURE_NAMES
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    store = PersistentJointTargetStore(
        feature_names=AGIBOT_O10_HAND_FEATURE_NAMES,
        path=output_path,
        label="test store",
    )
    store.save([float(index) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))])

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["description"] == "keep me"


def test_save_o10_hand_joint_target_writes_description(tmp_path):
    output_path = tmp_path / "pose.json"

    save_o10_hand_joint_target(
        output_path,
        [float(index) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))],
        description="custom description",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["description"] == "custom description"
    assert payload["joint_values"]["thumb_cm_roll.pos"] == 0.0
    assert payload["joint_values"]["pinky_mp_pitch.pos"] == 9.0


def test_capture_robot_o10_hand_joint_pos_reads_and_disconnects():
    created: dict[str, object] = {}

    class FakeHand:
        def __init__(self, **kwargs):
            created["kwargs"] = kwargs
            created["instance"] = self
            self.disconnected = False

        def connect(self):
            created["connected"] = True

        def read_active_joint_angles(self):
            return [float(index) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]

        def disconnect(self):
            self.disconnected = True

    joint_values = capture_robot_o10_hand_joint_pos(
        handedness="right",
        channel_mode="multiChannel",
        device_id=1,
        canfd_id=0,
        channel_id=1,
        hand_factory=FakeHand,
    )

    assert joint_values == [float(index) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]
    assert created["kwargs"] == {
        "handedness": "right",
        "channel_mode": "multiChannel",
        "device_id": 1,
        "canfd_id": 0,
        "channel_id": 1,
    }
    assert created["connected"] is True
    assert created["instance"].disconnected is True


def test_capture_glove_o10_hand_joint_pos_reads_and_stops():
    created: dict[str, object] = {}

    class FakeGlove:
        def __init__(self, *, handedness):
            created["handedness"] = handedness
            created["instance"] = self
            self.stopped = False

        def init(self):
            return True

        def start_listening(self):
            created["started"] = True

        def wait_until_ready(self, timeout_s):
            created["timeout_s"] = timeout_s
            return True

        def get_hand_data(self):
            return [float(index + 100) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]

        def stop(self):
            self.stopped = True

    joint_values = capture_glove_o10_hand_joint_pos(
        handedness="right",
        timeout_s=3.0,
        glove_factory=FakeGlove,
    )

    assert joint_values == [float(index + 100) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]
    assert created["handedness"] == "right"
    assert created["started"] is True
    assert created["timeout_s"] == 3.0
    assert created["instance"].stopped is True


def test_default_o10_hand_pose_path_uses_new_split_json_names():
    repo_root = Path("/tmp/repo")

    assert default_o10_hand_pose_path(repo_root, "right", "full_reset") == (
        repo_root / "configs" / "o10_right_hand_full_reset_pose.json"
    )
    assert default_o10_hand_pose_path(repo_root, "right", "grasp_preset") == (
        repo_root / "configs" / "o10_right_hand_grasp_preset_pose.json"
    )
