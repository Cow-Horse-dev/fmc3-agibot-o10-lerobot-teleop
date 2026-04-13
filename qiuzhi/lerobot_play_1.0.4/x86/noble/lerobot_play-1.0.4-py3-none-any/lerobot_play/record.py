import argparse
import json
import threading
import time

import yaml

from lerobot.cameras.configs import ColorMode, Cv2Rotation
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from .utils.lerobot_dataset import LeRobotDataset
from .utils.control_utils import init_keyboard_listener
from lerobot.utils.utils import init_logging
from lerobot.processor import make_default_processors

# from lerobot.record import record_loop
# from lerobot.scripts.lerobot_record import record_loop
from .utils.lerobot_record import record_loop

from .robots.airbot_play_follower.config_play_follower import AirbotPlayFollowerConfig
from .robots.airbot_ptk_follower.config_PTK_follower import AirbotPTKFollowerConfig
from .robots.airbot_tok2_follower.config_TOK2_follower import AirbotTOK2FollowerConfig
from .robots.airbot_tok4_follower.config_TOK4_follower import AirbotTOK4FollowerConfig
from .robots.quest3_follower.config_quest3_follower import Quest3FollowerConfig
from .robots.pico_follower.config_pico_follower import PicoFollowerConfig
from .robots.pico_follower_single_arm_eef.config_pico_follower_single_arm_eef import (
    PicoFollowerSingleArmEEFConfig,
)
from .robots.pico_follower_single_arm_agibot_o10.config_pico_follower_single_arm_agibot_o10 import (
    PicoFollowerSingleArmAgibotO10Config,
)
from .robots.utils import make_robot_from_config
from .teleoperators.airbot_replay.config_replay import AirbotReplayConfig
from .teleoperators.airbot_replay_mini.config_replay_mini import AirbotReplayMiniConfig
from .teleoperators.airbot_play_with_E2_leader.config_play_with_E2_leader import (
    AirbotPlaywithE2LeaderConfig,
)
from .teleoperators.airbot_tok2_leader.config_TOK2_leader import AirbotTOK2LeaderConfig
from .teleoperators.airbot_tok2_mini_leader.config_TOK2_mini_leader import (
    AirbotTOK2MiniLeaderConfig,
)
from .teleoperators.airbot_ptk_leader.config_PTK_leader import AirbotPTKLeaderConfig
from .teleoperators.airbot_tok4_leader.config_TOK4_leader import AirbotTOK4LeaderConfig
from .teleoperators.quest3_leader.config_quest3_leader import Quest3LeaderConfig
from .teleoperators.pico_leader.config_pico_leader import PicoLeaderConfig
from .teleoperators.pico_leader_single_arm_eef.config_pico_leader_single_arm_eef import (
    PicoLeaderSingleArmEEFConfig,
)
from .teleoperators.pico_leader_single_arm_agibot_o10.config_pico_leader_single_arm_agibot_o10 import (
    PicoLeaderSingleArmAgibotO10Config,
)
from .teleoperators.utils import make_teleoperator_from_config
from lerobot.utils.visualization_utils import init_rerun

from .utils.utils import print_green, print_red, print_yellow
from .utils.runtime_helpers import (
    build_dataset_features,
    is_incomplete_dataset_root,
    prepare_dataset_root_for_recording,
    resolve_record_dataset_target,
)


def _parse_cameras(cameras_obj: dict) -> dict:
    parsed: dict = {}
    for name, cfg in (cameras_obj or {}).items():
        cam_type = cfg.get("type")
        if cam_type == "opencv":
            parsed[name] = OpenCVCameraConfig(
                index_or_path=cfg.get("index_or_path", cfg.get("camera_index")),
                fps=int(cfg.get("fps", 30)),
                width=int(cfg.get("width", 640)),
                height=int(cfg.get("height", 480)),
                rotation=Cv2Rotation[cfg.get("rotation", "NO_ROTATION")],
            )
        elif cam_type == "realsense":
            parsed[name] = RealSenseCameraConfig(
                serial_number_or_name=str(cfg.get("serial_number_or_name", "")),
                fps=int(cfg.get("fps", 30)),
                width=int(cfg.get("width", 640)),
                height=int(cfg.get("height", 480)),
                color_mode=ColorMode[cfg.get("color_mode", "RGB")],
                use_depth=bool(cfg.get("use_depth", False)),
                rotation=Cv2Rotation[cfg.get("rotation", "NO_ROTATION")],
            )
        else:
            raise ValueError(f"Unsupported camera type: {cam_type}")
    return parsed


def _load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIRBOT Play/PTK data recording entrypoint"
    )
    parser.add_argument(
        "--yaml", type=str, default=None, help="Path to YAML config file"
    )

    # Robot
    parser.add_argument(
        "--robot.type", dest="robot_type", type=str, default="airbot_play_follower"
    )
    parser.add_argument("--robot.port", dest="robot_port", type=str, default="can0")
    parser.add_argument(
        "--robot.left_arm_port", dest="robot_left_arm_port", type=str, default=None
    )
    parser.add_argument(
        "--robot.right_arm_port", dest="robot_right_arm_port", type=str, default=None
    )
    parser.add_argument("--robot.id", dest="robot_id", type=str, default="airbot_play")
    parser.add_argument(
        "--robot.cameras",
        dest="robot_cameras",
        type=str,
        default=None,
        help="JSON/YAML string for cameras map",
    )
    parser.add_argument(
        "--robot.eef_device",
        dest="robot_eef_device",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--robot.hand_id",
        dest="robot_hand_id",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--robot.handedness",
        dest="robot_handedness",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--robot.channel_mode",
        dest="robot_channel_mode",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--robot.device_id",
        dest="robot_device_id",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--robot.canfd_id",
        dest="robot_canfd_id",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--robot.channel_id",
        dest="robot_channel_id",
        type=int,
        default=None,
    )

    # Teleop
    parser.add_argument(
        "--teleop.type", dest="teleop_type", type=str, default="airbot_replay"
    )
    parser.add_argument("--teleop.port", dest="teleop_port", type=str, default="can1")
    parser.add_argument(
        "--teleop.left_arm_port", dest="teleop_left_arm_port", type=str, default=None
    )
    parser.add_argument(
        "--teleop.right_arm_port", dest="teleop_right_arm_port", type=str, default=None
    )
    parser.add_argument(
        "--teleop.id", dest="teleop_id", type=str, default="airbot_replay"
    )
    parser.add_argument(
        "--teleop.eef_device",
        dest="teleop_eef_device",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--teleop.handedness",
        dest="teleop_handedness",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--teleop.vr_pose_port",
        dest="teleop_vr_pose_port",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--teleop.vr_ctrl_port",
        dest="teleop_vr_ctrl_port",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--teleop.vr_device",
        dest="teleop_vr_device",
        type=str,
        default=None,
    )

    # Run
    parser.add_argument("--fps", dest="fps", type=int, default=30)
    parser.add_argument(
        "--display_data",
        dest="display_data",
        type=lambda v: str(v).lower() == "true",
        default=False,
    )
    parser.add_argument(
        "--dataset.num_episodes", dest="num_episodes", type=int, default=25
    )
    parser.add_argument(
        "--episode_time_sec", dest="episode_time_sec", type=int, default=60
    )
    parser.add_argument("--reset_time_sec", dest="reset_time_sec", type=int, default=10)
    parser.add_argument("--single_task", dest="single_task", type=str, default="")

    # Dataset
    parser.add_argument("--dataset.repo_id", dest="repo_id", type=str, required=False)
    parser.add_argument(
        "--dataset.root",
        dest="dataset_root",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--dataset.num_image_writer_threads_per_camera",
        dest="num_threads",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--dataset.num_image_writer_processes",
        dest="num_processes",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--dataset.video_encoding_batch_size",
        dest="video_batch_size",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--dataset.video",
        dest="use_videos",
        type=lambda v: str(v).lower() == "true",
        default=True,
    )

    parser.add_argument(
        "--dataset.mcap",
        dest="use_mcap",
        type=lambda v: str(v).lower() == "true",
        default=False,
    )
    parser.add_argument(
        "--dataset.online_encoding",
        dest="online_encoding",
        type=lambda v: str(v).lower() == "true",
        default=False,
    )

    parser.add_argument(
        "--dataset.is_ssh",
        dest="use_ssh",
        type=lambda v: str(v).lower() == "true",
        default=False,
    )

    return parser.parse_args()


def _load_config(cli: argparse.Namespace) -> dict:
    if cli.yaml:
        cfg = _load_yaml(cli.yaml)
        if cli.repo_id:
            cfg.setdefault("dataset", {})
            cfg["dataset"]["repo_id"] = cli.repo_id
        if cli.dataset_root:
            cfg.setdefault("dataset", {})
            cfg["dataset"]["root"] = cli.dataset_root
        return cfg or {}

    cameras = None
    if cli.robot_cameras:
        try:
            cameras = json.loads(cli.robot_cameras)
        except Exception:
            cameras = yaml.safe_load(cli.robot_cameras)

    robot_config = {
        "type": cli.robot_type,
        "id": cli.robot_id,
        "cameras": cameras or {},
    }

    # Add port configuration based on robot type
    if cli.robot_type == "airbot_play_follower":
        robot_config["port"] = cli.robot_port
    elif cli.robot_type == "pico_follower_single_arm_eef":
        robot_config["port"] = cli.robot_port
        if cli.robot_eef_device is not None:
            robot_config["eef_device"] = cli.robot_eef_device
        if cli.robot_hand_id is not None:
            robot_config["hand_id"] = cli.robot_hand_id
    elif cli.robot_type == "pico_follower_single_arm_agibot_o10":
        robot_config["port"] = cli.robot_port
        if cli.robot_handedness is not None:
            robot_config["handedness"] = cli.robot_handedness
        if cli.robot_channel_mode is not None:
            robot_config["channel_mode"] = cli.robot_channel_mode
        if cli.robot_device_id is not None:
            robot_config["device_id"] = cli.robot_device_id
        if cli.robot_canfd_id is not None:
            robot_config["canfd_id"] = cli.robot_canfd_id
        if cli.robot_channel_id is not None:
            robot_config["channel_id"] = cli.robot_channel_id
    elif (
        cli.robot_type == "airbot_PTK_follower"
        or cli.robot_type == "airbot_TOK4_follower"
        or cli.robot_type == "airbot_TOK2_follower"
    ):
        if cli.robot_left_arm_port:
            robot_config["left_arm_port"] = cli.robot_left_arm_port
        if cli.robot_right_arm_port:
            robot_config["right_arm_port"] = cli.robot_right_arm_port

    teleop_config = {
        "type": cli.teleop_type,
        "id": cli.teleop_id,
    }

    # Add port configuration based on teleop type
    if (
        cli.teleop_type == "airbot_replay"
        or cli.teleop_type == "airbot_play_with_E2_leader"
        or cli.teleop_type == "pico_leader_single_arm_eef"
    ):
        teleop_config["port"] = cli.teleop_port
    elif (
        cli.teleop_type == "airbot_PTK_leader"
        or cli.teleop_type == "airbot_TOK4_leader"
        or cli.teleop_type == "airbot_TOK2_leader"
        or cli.teleop_type == "quest3_leader"
        or cli.teleop_type == "pico_leader"
    ):
        if cli.teleop_left_arm_port:
            teleop_config["left_arm_port"] = cli.teleop_left_arm_port
        if cli.teleop_right_arm_port:
            teleop_config["right_arm_port"] = cli.teleop_right_arm_port

    if cli.teleop_type == "pico_leader_single_arm_eef":
        if cli.teleop_eef_device is not None:
            teleop_config["eef_device"] = cli.teleop_eef_device
        if cli.teleop_handedness is not None:
            teleop_config["handedness"] = cli.teleop_handedness
        if cli.teleop_vr_pose_port is not None:
            teleop_config["vr_pose_port"] = cli.teleop_vr_pose_port
        if cli.teleop_vr_ctrl_port is not None:
            teleop_config["vr_ctrl_port"] = cli.teleop_vr_ctrl_port
        if cli.teleop_vr_device is not None:
            teleop_config["vr_device"] = cli.teleop_vr_device
    elif cli.teleop_type == "pico_leader_single_arm_agibot_o10":
        if cli.teleop_handedness is not None:
            teleop_config["handedness"] = cli.teleop_handedness
        if cli.teleop_vr_pose_port is not None:
            teleop_config["vr_pose_port"] = cli.teleop_vr_pose_port
        if cli.teleop_vr_ctrl_port is not None:
            teleop_config["vr_ctrl_port"] = cli.teleop_vr_ctrl_port
        if cli.teleop_vr_device is not None:
            teleop_config["vr_device"] = cli.teleop_vr_device

    return {
        "robot": robot_config,
        "teleop": teleop_config,
        "run": {
            "fps": cli.fps,
            "display_data": cli.display_data,
            "num_episodes": cli.num_episodes,
            "episode_time_sec": cli.episode_time_sec,
            "reset_time_sec": cli.reset_time_sec,
            "single_task": cli.single_task,
        },
        "dataset": {
            "repo_id": cli.repo_id,
            "root": cli.dataset_root,
            "video": cli.use_videos,
            "mcap": cli.use_mcap,
            "online_encoding": cli.online_encoding,
            "is_ssh": cli.use_ssh,
            "num_image_writer_threads_per_camera": cli.num_threads,
            "num_image_writer_processes": cli.num_processes,
            "video_encoding_batch_size": cli.video_batch_size,
        },
    }


def _validate_config(cfg: dict):
    for key in ["robot", "teleop", "dataset", "run"]:
        if key not in cfg:
            raise ValueError(f"Missing required section: {key}")
    r, t, d, run = cfg["robot"], cfg["teleop"], cfg["dataset"], cfg["run"]

    # Validate robot config based on type
    if (
        r["type"] == "airbot_play_follower"
        or r["type"] == "pico_follower_single_arm_eef"
        or r["type"] == "pico_follower_single_arm_agibot_o10"
    ):
        for k in ["type", "port", "id"]:
            if k not in r:
                raise ValueError(f"robot.{k} is required")
    elif (
        r["type"] == "airbot_PTK_follower"
        or r["type"] == "airbot_TOK2_follower"
        or r["type"] == "airbot_TOK4_follower"
        or r["type"] == "quest3_follower"
        or r["type"] == "pico_follower"
    ):
        for k in ["type", "left_arm_port", "right_arm_port", "id"]:
            if k not in r:
                raise ValueError(f"robot.{k} is required")

    # Validate teleop config based on type
    if t["type"] == "airbot_replay":
        for k in ["type", "port", "id"]:
            if k not in t:
                raise ValueError(f"teleop.{k} is required")
    elif (
        t["type"] == "airbot_PTK_leader"
        or t["type"] == "airbot_TOK2_leader"
        or t["type"] == "airbot_TOK4_leader"
    ):
        for k in ["type", "left_arm_port", "right_arm_port", "id"]:
            if k not in t:
                raise ValueError(f"teleop.{k} is required")

    auto_name_from_task_date = bool(d.get("auto_name_from_task_date", False))
    if not auto_name_from_task_date and not d.get("repo_id"):
        raise ValueError(
            "dataset.repo_id is required when dataset.auto_name_from_task_date is false"
        )
    for k in ["num_episodes", "episode_time_sec", "reset_time_sec", "fps"]:
        if k not in run:
            raise ValueError(f"run.{k} is required")
def _start_events_thread(
    teleop, events, pause_event: threading.Event, stop_event: threading.Event
):
    def quest3_event():
        while not stop_event.is_set():
            pause_event.wait()
            if stop_event.is_set():
                break

            if hasattr(teleop, "ctrl"):
                vr_ctrl = teleop.ctrl
                # print(vr_ctrl)
                if vr_ctrl["A"]:
                    print("start record")
                    events["start"] = True
                if vr_ctrl["B"]:
                    print("B pressed. Stopping data recording...")
                    events["stop_recording"] = True
                    events["exit_early"] = True
                if vr_ctrl["X"]:
                    print("X key pressed. Exiting loop...")
                    events["exit_early"] = True
                if vr_ctrl["Y"]:
                    print(
                        "Y key pressed. Exiting loop and rerecord the last episode..."
                    )
                    events["rerecord_episode"] = True
                    events["exit_early"] = True
            else:
                events["start"] = False
                events["exit_early"] = False
                events["rerecord_episode"] = False
                events["stop_recording"] = False
            time.sleep(0.1)

    pause_event.set()
    thread = threading.Thread(target=quest3_event, daemon=True)
    thread.start()
    return thread


def init_stdin_listener():
    """
    Initializes a stdin-based input listener for headless environments.

    Allows users to control recording via terminal commands:
    - Press Enter or type 'start' to start recording
    - Press Escape or type 'stop' to stop recording
    - Type 'exit' or 'quit' to exit early
    - Type 'rerecord' to rerecord last episode

    This runs in a separate thread to avoid blocking the main program.

    Returns:
        A tuple containing:
        - The threading.Thread instance for the stdin listener
        - A dictionary of event flags
    """
    import sys

    events = {}
    events["start"] = False
    events["exit_early"] = False
    events["rerecord_episode"] = False
    events["stop_recording"] = False

    def listen_stdin():
        """Listen for stdin input in a background thread"""
        print("\n" + "=" * 50)
        print("Waiting for user input...")
        print("Commands: [Enter]/start, next/n, stop/q, rerecord/r, exit, help/h")
        print("=" * 50 + "\n")

        while True:
            try:
                # Read input from stdin
                user_input = input().strip().lower()

                if user_input in ["start", "", " "]:  # Empty input or 'start'
                    print("▶ Starting recording...")
                    events["start"] = True

                elif user_input in ["next", "n"]:  # Move to next episode
                    print("⏭ Moving to next episode...")
                    events["exit_early"] = True  # Exit current episode to save it
                    events["start"] = True  # Auto-start next episode

                elif user_input in ["stop", "esc", "q"]:
                    print("⏹ Stopping recording...")
                    events["stop_recording"] = True
                    events["exit_early"] = True
                    break

                elif user_input in ["rerecord", "r"]:
                    print("🔄 Rerecording last episode...")
                    events["rerecord_episode"] = True
                    events["exit_early"] = True

                elif user_input in ["exit", "quit"]:
                    print("❌ Exiting...")
                    events["stop_recording"] = True
                    events["exit_early"] = True
                    break

                elif user_input in ["help", "h", "?"]:
                    print("\n=== Terminal Control Help ===")
                    print("Commands:")
                    print("  [Enter] or 'start' - Start recording episode")
                    print("  'next' or 'n'     - Move to next episode")
                    print("  'stop' or 'q'     - Stop recording")
                    print("  'rerecord' or 'r' - Rerecord last episode")
                    print("  'exit' or 'quit'  - Exit program")
                    print("  'help' or 'h'     - Show this help")
                    print("=============================\n")

                else:
                    print(
                        f"Unknown command: {user_input}. Type 'help' for available commands."
                    )

            except EOFError:
                # stdin closed
                break
            except Exception as e:
                print(f"Error reading stdin: {e}")
                break

    # Start stdin listener in daemon thread
    stdin_thread = threading.Thread(target=listen_stdin, daemon=True)
    stdin_thread.start()

    return stdin_thread, events

def main():
    init_logging()
    cli = _parse_cli_args()
    cfg = _load_config(cli)
    _validate_config(cfg)

    # Cameras optional, but if provided and any fails to connect, exit with error.
    camera_cfgs = _parse_cameras(cfg["robot"].get("cameras", {}))

    # Build robot config and instance via factory
    robot_type = cfg["robot"]["type"]
    if robot_type == "airbot_play_follower":
        robot_cfg = AirbotPlayFollowerConfig(
            can_port=cfg["robot"]["port"],
            cameras=camera_cfgs,
            id=cfg["robot"]["id"],
        )
    elif robot_type == "airbot_PTK_follower":
        robot_cfg = AirbotPTKFollowerConfig(
            left_arm_port=cfg["robot"]["left_arm_port"],
            right_arm_port=cfg["robot"]["right_arm_port"],
            cameras=camera_cfgs,
            id=cfg["robot"]["id"],
        )
    elif robot_type == "airbot_TOK4_follower":
        robot_cfg = AirbotTOK4FollowerConfig(
            left_arm_port=cfg["robot"]["left_arm_port"],
            right_arm_port=cfg["robot"]["right_arm_port"],
            cameras=camera_cfgs,
            id=cfg["robot"]["id"],
        )
    elif robot_type == "airbot_TOK2_follower":
        robot_cfg = AirbotTOK2FollowerConfig(
            left_arm_port=cfg["robot"]["left_arm_port"],
            right_arm_port=cfg["robot"]["right_arm_port"],
            cameras=camera_cfgs,
            id=cfg["robot"]["id"],
        )
    elif robot_type == "quest3_follower":
        robot_cfg = Quest3FollowerConfig(
            left_arm_port=cfg["robot"]["left_arm_port"],
            right_arm_port=cfg["robot"]["right_arm_port"],
            cameras=camera_cfgs,
            id=cfg["robot"]["id"],
        )
    elif robot_type == "pico_follower":
        robot_cfg = PicoFollowerConfig(
            left_arm_port=cfg["robot"]["left_arm_port"],
            right_arm_port=cfg["robot"]["right_arm_port"],
            cameras=camera_cfgs,
            id=cfg["robot"]["id"],
        )
    elif robot_type == "pico_follower_single_arm_eef":
        robot_cfg = PicoFollowerSingleArmEEFConfig(
            port=cfg["robot"]["port"],
            eef_device=cfg["robot"].get("eef_device", "G2"),
            hand_id=cfg["robot"].get("hand_id", 1),
            cameras=camera_cfgs,
            id=cfg["robot"]["id"],
        )
    elif robot_type == "pico_follower_single_arm_agibot_o10":
        robot_cfg = PicoFollowerSingleArmAgibotO10Config(
            port=cfg["robot"]["port"],
            handedness=cfg["robot"].get("handedness", "right"),
            channel_mode=cfg["robot"].get("channel_mode", "multiChannel"),
            device_id=cfg["robot"].get("device_id", 1),
            canfd_id=cfg["robot"].get("canfd_id", 0),
            channel_id=cfg["robot"].get("channel_id"),
            cameras=camera_cfgs,
            id=cfg["robot"]["id"],
        )
    else:
        raise ValueError(f"Unsupported robot type: {robot_type}")

    robot = make_robot_from_config(robot_cfg)

    # Build teleop config and instance via factory
    teleop_type = cfg["teleop"]["type"]
    if teleop_type == "airbot_replay":
        teleop_cfg = AirbotReplayConfig(
            can_port=cfg["teleop"]["port"],
            id=cfg["teleop"]["id"],
        )
    # elif teleop_type == "airbot_replay_mini":
    #     teleop_cfg = AirbotReplayMiniConfig(
    #         can_port=cfg["teleop"]["port"],
    #         id=cfg["teleop"]["id"],
    #     )
    elif teleop_type == "airbot_play_with_E2_leader":
        teleop_cfg = AirbotPlaywithE2LeaderConfig(
            can_port=cfg["teleop"]["port"],
            id=cfg["teleop"]["id"],
        )
    elif teleop_type == "airbot_PTK_leader":
        teleop_cfg = AirbotPTKLeaderConfig(
            left_arm_port=cfg["teleop"]["left_arm_port"],
            right_arm_port=cfg["teleop"]["right_arm_port"],
            id=cfg["teleop"]["id"],
        )
    elif teleop_type == "airbot_TOK4_leader":
        teleop_cfg = AirbotTOK4LeaderConfig(
            left_arm_port=cfg["teleop"]["left_arm_port"],
            right_arm_port=cfg["teleop"]["right_arm_port"],
            id=cfg["teleop"]["id"],
        )
    elif teleop_type == "airbot_TOK2_leader":
        teleop_cfg = AirbotTOK2LeaderConfig(
            left_arm_port=cfg["teleop"]["left_arm_port"],
            right_arm_port=cfg["teleop"]["right_arm_port"],
            id=cfg["teleop"]["id"],
        )
    # elif teleop_type == "airbot_TOK2_mini_leader":
    #     teleop_cfg = AirbotTOK2MiniLeaderConfig(
    #         left_arm_port=cfg["teleop"]["left_arm_port"],
    #         right_arm_port=cfg["teleop"]["right_arm_port"],
    #         id=cfg["teleop"]["id"],
    #     )
    elif teleop_type == "quest3_leader":
        teleop_cfg = Quest3LeaderConfig()
    elif teleop_type == "pico_leader":
        teleop_cfg = PicoLeaderConfig()
    elif teleop_type == "pico_leader_single_arm_eef":
        teleop_cfg = PicoLeaderSingleArmEEFConfig(
            vr_pose_port=cfg["teleop"].get("vr_pose_port", 8000),
            vr_ctrl_port=cfg["teleop"].get("vr_ctrl_port", 8001),
            vr_device=cfg["teleop"].get("vr_device", "pico_wrist"),
            eef_device=cfg["teleop"].get("eef_device", "G2"),
            handedness=cfg["teleop"].get("handedness", "left"),
            wrist_pose_source=cfg["teleop"].get("wrist_pose_source", "auto"),
            cameras=camera_cfgs,
            id=cfg["teleop"]["id"],
        )
    elif teleop_type == "pico_leader_single_arm_agibot_o10":
        teleop_cfg = PicoLeaderSingleArmAgibotO10Config(
            vr_pose_port=cfg["teleop"].get("vr_pose_port", 8000),
            vr_ctrl_port=cfg["teleop"].get("vr_ctrl_port", 8001),
            vr_device=cfg["teleop"].get("vr_device", "pico_wrist"),
            handedness=cfg["teleop"].get("handedness", "right"),
            wrist_pose_source=cfg["teleop"].get("wrist_pose_source", "auto"),
            enable_hand=cfg["teleop"].get("enable_hand", True),
            hand_reset_joints_path=cfg["teleop"].get("hand_reset_joints_path"),
            cameras=camera_cfgs,
            id=cfg["teleop"]["id"],
        )
    else:
        raise ValueError(f"Unsupported teleop type: {teleop_type}")

    teleop = None
    dataset = None
    events = None
    pause_flag_events = None
    stop_flag_events = None
    events_thread = None

    try:

        teleop = make_teleoperator_from_config(teleop_cfg)

        (
            teleop_action_processor,
            robot_action_processor,
            robot_observation_processor,
        ) = make_default_processors()

        # Features and dataset
        use_videos = bool(cfg["dataset"].get("video", True) and len(camera_cfgs) > 0)
        dataset_features = build_dataset_features(robot, use_videos=use_videos)
        if cfg["dataset"].get("video", True) and len(camera_cfgs) == 0:
            print_yellow(
                "No cameras configured; recording an action/state-only dataset."
            )

        # Create dataset (local repo_id)
        dataset_target = resolve_record_dataset_target(
            repo_id=cfg["dataset"].get("repo_id"),
            root=cfg["dataset"].get("root"),
            task_name=cfg["run"].get("single_task"),
            auto_name_from_task_date=bool(
                cfg["dataset"].get("auto_name_from_task_date", False)
            ),
            date_format=str(cfg["dataset"].get("date_format", "%Y%m%d")),
        )
        cfg["dataset"]["repo_id"] = dataset_target.repo_id
        dataset_root = dataset_target.root
        had_incomplete_dataset = is_incomplete_dataset_root(dataset_root)
        prepare_dataset_root_for_recording(
            cfg["dataset"]["repo_id"],
            cfg["dataset"].get("root"),
        )
        if had_incomplete_dataset:
            print_yellow(f"Removed stale incomplete dataset directory: {dataset_root}")
        print_green(f"Dataset will be saved to: {dataset_root}")

        dataset = LeRobotDataset.create(
            repo_id=cfg["dataset"]["repo_id"],
            fps=int(cfg["run"]["fps"]),
            robot_type=robot.name,
            features=dataset_features,
            root=dataset_root,
            use_videos=use_videos,
            use_mcap=bool(cfg["dataset"].get("mcap", False)),
            image_writer_processes=int(
                cfg["dataset"].get("num_image_writer_processes", 0)
            ),
            image_writer_threads=int(
                cfg["dataset"].get("num_image_writer_threads_per_camera", 4)
            )
            * max(1, len(getattr(robot, "cameras", {}))),
            batch_encoding_size=int(cfg["dataset"].get("video_encoding_batch_size", 1)),
            online_encoding=bool(cfg["dataset"].get("online_encoding", False)),
        )

        use_mcap = bool(cfg["dataset"].get("mcap", False))
        use_ssh = bool(cfg["dataset"].get("is_ssh", False))

        # Keyboard listener
        if teleop_type == "quest3_leader" or teleop_type == "pico_leader":
            events = {}
            events["start"] = False
            events["exit_early"] = False
            events["rerecord_episode"] = False
            events["stop_recording"] = False

            pause_flag_events = threading.Event()
            stop_flag_events = threading.Event()
            pause_flag_events.set()
            events_thread = _start_events_thread(
                teleop, events, pause_flag_events, stop_flag_events
            )
        else:
            # Keyboard listener
            if not use_ssh:
                print_green("not use ssh, init keyboard listener")
                _, events = init_keyboard_listener()
            else:
                print_green("use ssh, init stdin listener")
                _, events = init_stdin_listener()

        if bool(cfg["run"].get("display_data", False)):
            init_rerun(session_name="recording")

        # Connect devices
        robot.connect()
        teleop.connect()

        if robot.name == "airbot_play_follower":
            robot.reset_zero()
            if teleop.name == "airbot_play_with_E2_leader":
                teleop.return_init()
        elif robot.name == "airbot_PTK_follower":
            robot.reset_init()
        elif robot.name == "airbot_TOK4_follower":
            robot.reset_zero()
            teleop.return_init()
        elif robot.name == "airbot_TOK2_follower":
            robot.reset_zero()
        elif robot.name == "quest3_follower":
            robot.reset_zero()
        elif robot.name == "pico_follower":
            robot.reset_zero()
        elif (
            robot.name == "pico_follower_single_arm_eef"
            or robot.name == "pico_follower_single_arm_agibot_o10"
        ):
            robot.reset_zero()

        recorded = 0

        while (
            recorded < int(cfg["run"]["num_episodes"]) and not events["stop_recording"]
        ):
            is_continue = False
            if teleop.name == "quest3_leader" or teleop.name == "pico_leader":
                print_green(
                    f"Recording episode {recorded + 1}, please press A to start or press B to exit"
                )
                while not events["start"]:
                    time.sleep(0.1)
                    if events["stop_recording"]:
                        is_continue = True
                        break
                if is_continue:
                    continue

                for lpf in teleop.lpfs_left:
                    lpf.set_zero_mode(False)
                for lpf in teleop.lpfs_right:
                    lpf.set_zero_mode(False)

            elif (
                teleop.name == "pico_leader_single_arm_eef"
                or teleop.name == "pico_leader_single_arm_agibot_o10"
            ):
                if not use_ssh:
                    print_green(
                        f"Recording episode {recorded + 1}, press space/enter to start recording or press ESC to exit"
                    )
                    print_green(
                        "After recording starts, use VR controls: X starts arm control, hold left trigger to move, Y resets."
                    )
                else:
                    print_green(
                        f"Recording episode {recorded + 1}, please press [enter] to start or input 'stop' to exit"
                    )
                while not events["start"]:
                    time.sleep(0.1)
                    if events["stop_recording"]:
                        is_continue = True
                        break
                if is_continue:
                    continue

                print_green(
                    f"Episode {recorded + 1} started. Keyboard controls the recording flow; VR controls the arm and hand."
                )
                for lpf in teleop.lpfs:
                    lpf.set_zero_mode(False)

            else:
                if not use_ssh:
                    print_green(
                        f"Recording episode {recorded + 1}, please press space to start or press ESC to exit"
                    )
                else:
                    print_green(
                        f"Recording episode {recorded + 1}, please press [enter] to start or input 'stop' to exit"
                    )

                while not events["start"]:
                    time.sleep(0.1)
                    # print(events["stop_recording"])
                    if events["stop_recording"]:
                        is_continue = True
                        break
                if is_continue:
                    continue

            events["exit_early"] = False

            # Keep recording on a single command path so executed motion matches saved data.
            record_loop(
                robot=robot,
                events=events,
                fps=int(cfg["run"]["fps"]),
                teleop=teleop,
                dataset=dataset,
                control_time_s=int(cfg["run"]["episode_time_sec"]),
                single_task=cfg["run"].get("single_task"),
                display_data=bool(cfg["run"].get("display_data", False)),
                teleop_action_processor=teleop_action_processor,
                robot_action_processor=robot_action_processor,
                robot_observation_processor=robot_observation_processor,
                use_mcap=use_mcap,
                online_encoding=bool(cfg["dataset"].get("online_encoding", False)),
                episode_index=recorded + 1,
                total_episodes=int(cfg["run"]["num_episodes"]),
            )

            if robot.name == "airbot_play_follower":
                robot.reset_zero()
                if teleop.name == "airbot_play_with_E2_leader":
                    teleop.return_init()
            elif robot.name == "airbot_PTK_follower":
                robot.reset_init()
            elif robot.name == "airbot_TOK4_follower":
                robot.reset_zero()
                teleop.return_init()
            elif robot.name == "airbot_TOK2_follower":
                robot.reset_zero()
            elif robot.name == "quest3_follower":
                robot.reset_zero()
            elif robot.name == "pico_follower":
                robot.reset_zero()
            elif (
                robot.name == "pico_follower_single_arm_eef"
                or robot.name == "pico_follower_single_arm_agibot_o10"
            ):
                robot.reset_zero()

            if teleop.name == "quest3_leader" or teleop.name == "pico_leader":
                pause_flag_events.clear()
                teleop.pause_event.clear()
                events["start"] = False
                events["exit_early"] = False
                # events["rerecord_episode"] = False
                # events["stop_recording"] = False

                for lpf in teleop.lpfs_left:
                    lpf.set_zero_mode(True)
                for lpf in teleop.lpfs_right:
                    lpf.set_zero_mode(True)
                teleop.return_init()
            elif (
                teleop.name == "pico_leader_single_arm_eef"
                or teleop.name == "pico_leader_single_arm_agibot_o10"
            ):
                # pause_flag_events.clear()
                teleop.pause_event.clear()
                events["start"] = False
                events["exit_early"] = False

                for lpf in teleop.lpfs:
                    lpf.set_zero_mode(True)
                teleop.return_init()

            if events["rerecord_episode"]:
                print("Re-recording episode")
                events["rerecord_episode"] = False
                events["exit_early"] = False
                events["start"] = False
                for attempt in range(3):
                    try:
                        dataset.clear_episode_buffer(restart_image_writer=True)
                        break  # 成功则退出
                    except OSError as e:
                        if "Directory not empty" in str(e) and attempt < 2:
                            time.sleep(0.1 * (attempt + 1))
                            continue
                        raise RuntimeError(
                            "Re-record cleanup failed; stopping to avoid corrupting the dataset."
                        ) from e
                    except Exception as e:
                        raise RuntimeError(
                            "Re-record cleanup failed; stopping to avoid corrupting the dataset."
                        ) from e
            else:
                dataset.save_episode(use_mcap=use_mcap)
                recorded += 1
            events["start"] = False
            # events["start"] = False
            # pause_flag.set()
            if teleop.name == "quest3_leader" or teleop.name == "pico_leader":
                teleop.pause_event.set()
                pause_flag_events.set()
                events["exit_early"] = False
            elif (
                teleop.name == "pico_leader_single_arm_eef"
                or teleop.name == "pico_leader_single_arm_agibot_o10"
            ):
                teleop.pause_event.set()
                # pause_flag_events.set()
                events["exit_early"] = False

    finally:
        # Cleanup
        if (
            teleop is not None
            and (teleop.name == "quest3_leader" or teleop.name == "pico_leader")
            and stop_flag_events is not None
            and pause_flag_events is not None
            and events_thread is not None
        ):
            stop_flag_events.set()
            pause_flag_events.set()
            events_thread.join(timeout=1.0)

        # Final reset at the end
        try:
            if robot.name == "airbot_play_follower":
                robot.reset_zero()
                if teleop is not None and teleop.name == "airbot_play_with_E2_leader":
                    teleop.return_init()
            elif robot.name == "airbot_PTK_follower":
                robot.reset_init()
            elif robot.name == "airbot_TOK4_follower":
                robot.reset_zero()
                if teleop is not None:
                    teleop.return_init()
            elif robot.name == "airbot_TOK2_follower":
                robot.reset_zero()
            elif robot.name == "quest3_follower":
                robot.reset_zero()
            elif robot.name == "pico_follower":
                robot.reset_zero()
            elif (
                robot.name == "pico_follower_single_arm_eef"
                or robot.name == "pico_follower_single_arm_agibot_o10"
            ):
                robot.reset_zero()
        except Exception as e:
            print(f"Warning: robot reset failed: {e}")

        print("Stop recording")
        try:
            for cam in getattr(robot, "cameras", {}).values():
                cam.disconnect()
        except Exception:
            pass
        print("cam disconnected")
        try:
            import cv2

            cv2.destroyAllWindows()
        except Exception:
            pass
        if dataset is not None:
            dataset.wait_all_async_tasks()
        try:
            robot.disconnect()
            print("robot disconnected")
        except Exception as e:
            print(f"Warning: robot disconnect failed: {e}")
        if teleop is not None:
            try:
                teleop.disconnect()
                print("teleop disconnected")
            except Exception as e:
                print(f"Warning: teleop disconnect failed: {e}")


if __name__ == "__main__":
    main()
