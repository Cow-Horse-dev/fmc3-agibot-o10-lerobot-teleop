#!/usr/bin/env python3

import logging
import sys
import time
from dataclasses import asdict, dataclass
from pprint import pformat

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig  # noqa: F401
from lerobot.configs import parser
from lerobot.processor import (
    RobotAction,
    RobotObservation,
    RobotProcessorPipeline,
    make_default_processors,
)
from lerobot.robots import (  # noqa: F401
    Robot,
    RobotConfig,
    bi_so_follower,
    earthrover_mini_plus,
    hope_jr,
    koch_follower,
    omx_follower,
    reachy2,
    so_follower,
)
from lerobot.teleoperators import (  # noqa: F401
    bi_so_leader,
    gamepad,
    homunculus,
    keyboard,
    koch_leader,
    omx_leader,
    reachy2_teleoperator,
    so_leader,
)
from lerobot.utils.import_utils import register_third_party_plugins
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import init_logging, move_cursor_up
from lerobot.utils.visualization_utils import init_rerun, log_rerun_data

from ._compat import Teleoperator, TeleoperatorConfig
from .robots.pico_follower_single_arm_agibot_o10.config_pico_follower_single_arm_agibot_o10 import (  # noqa: F401
    PicoFollowerSingleArmAgibotO10Config,
)
from .robots.pico_follower_dual_arm_agibot_o10.config_pico_follower_dual_arm_agibot_o10 import (  # noqa: F401
    PicoFollowerDualArmAgibotO10Config,
)
from .robots.pico_follower_single_arm_eef.config_pico_follower_single_arm_eef import (  # noqa: F401
    PicoFollowerSingleArmEEFConfig,
)
from .robots.utils import make_robot_from_config
from .teleoperators.pico_leader_single_arm_agibot_o10.config_pico_leader_single_arm_agibot_o10 import (  # noqa: F401
    PicoLeaderSingleArmAgibotO10Config,
)
from .teleoperators.pico_leader_dual_arm_agibot_o10.config_pico_leader_dual_arm_agibot_o10 import (  # noqa: F401
    PicoLeaderDualArmAgibotO10Config,
)
from .teleoperators.pico_leader_single_arm_eef.config_pico_leader_single_arm_eef import (  # noqa: F401
    PicoLeaderSingleArmEEFConfig,
)
from .teleoperators.utils import make_teleoperator_from_config
from .utils.display_filter import filter_display_observation
from .utils.rerun_control_display import configure_control_rerun_display


@dataclass
class TeleoperateConfig:
    teleop: TeleoperatorConfig
    robot: RobotConfig
    fps: int = 60
    teleop_time_s: float | None = None
    display_data: bool = False
    display_terminal: bool = True
    display_ip: str | None = None
    display_port: int | None = None
    display_compressed_images: bool = False


def _disconnect_best_effort(
    device,
    label: str,
    *,
    startup_attempted: bool = False,
) -> None:
    if not (getattr(device, "is_connected", False) or startup_attempted):
        return

    was_connected = getattr(device, "_is_connected", None)
    if startup_attempted and was_connected is False:
        device._is_connected = True

    try:
        device.disconnect()
    except Exception:
        logging.exception("Failed to disconnect %s", label)
    finally:
        if startup_attempted and was_connected is False:
            device._is_connected = False


def teleop_loop(
    teleop: Teleoperator,
    robot: Robot,
    fps: int,
    teleop_action_processor: RobotProcessorPipeline[
        tuple[RobotAction, RobotObservation], RobotAction
    ],
    robot_action_processor: RobotProcessorPipeline[
        tuple[RobotAction, RobotObservation], RobotAction
    ],
    robot_observation_processor: RobotProcessorPipeline[
        RobotObservation, RobotObservation
    ],
    display_data: bool = False,
    display_terminal: bool = True,
    duration: float | None = None,
    display_compressed_images: bool = False,
):
    display_len = max(len(key) for key in robot.action_features)
    camera_keys = list(getattr(robot, "cameras", {}).keys())
    start = time.perf_counter()
    supports_cursor_control = sys.stdout.isatty()
    last_status_update = 0.0
    status_refresh_interval_s = 1.0

    while True:
        loop_start = time.perf_counter()

        obs = robot.get_observation()
        raw_action = teleop.get_action()
        teleop_action = teleop_action_processor((raw_action, obs))
        robot_action_to_send = robot_action_processor((teleop_action, obs))
        robot.send_action(robot_action_to_send)

        if display_data:
            obs_transition = robot_observation_processor(obs)
            display_observation = filter_display_observation(obs_transition, camera_keys)
            log_rerun_data(
                observation=display_observation,
                action=teleop_action,
                compress_images=display_compressed_images,
            )

        dt_s = time.perf_counter() - loop_start
        precise_sleep(max(1 / fps - dt_s, 0.0))
        loop_s = time.perf_counter() - loop_start
        now = time.perf_counter()
        if display_data and display_terminal and now - last_status_update >= status_refresh_interval_s:
            status_lines = [
                "",
                f"Teleop loop time: {loop_s * 1e3:.2f}ms ({1 / loop_s:.0f} Hz)",
                "-" * (display_len + 10),
                f"{'NAME':<{display_len}} | {'VALUE':>7}",
            ]
            status_lines.extend(
                f"{motor:<{display_len}} | {value:>7.2f}"
                for motor, value in robot_action_to_send.items()
            )
            print("\n".join(status_lines))
            if supports_cursor_control:
                move_cursor_up(len(status_lines))
            last_status_update = now

        if duration is not None and time.perf_counter() - start >= duration:
            return


@parser.wrap()
def teleoperate(cfg: TeleoperateConfig):
    init_logging()
    logging.info(pformat(asdict(cfg)))
    if cfg.display_data:
        init_rerun(
            session_name="teleoperation",
            ip=cfg.display_ip,
            port=cfg.display_port,
        )
    display_compressed_images = (
        True
        if (cfg.display_data and cfg.display_ip is not None and cfg.display_port is not None)
        else cfg.display_compressed_images
    )

    teleop = make_teleoperator_from_config(cfg.teleop)
    robot = make_robot_from_config(cfg.robot)
    if cfg.display_data:
        configure_control_rerun_display(robot)
    (
        teleop_action_processor,
        robot_action_processor,
        robot_observation_processor,
    ) = make_default_processors()

    startup_complete = False
    teleop_startup_attempted = False
    robot_startup_attempted = False

    try:
        teleop_startup_attempted = True
        teleop.connect()
        robot_startup_attempted = True
        robot.connect()
        startup_complete = True
    finally:
        if not startup_complete:
            _disconnect_best_effort(
                robot,
                "robot",
                startup_attempted=robot_startup_attempted,
            )
            _disconnect_best_effort(
                teleop,
                "teleoperator",
                startup_attempted=teleop_startup_attempted,
            )

    try:
        teleop_loop(
            teleop=teleop,
            robot=robot,
            fps=cfg.fps,
            teleop_action_processor=teleop_action_processor,
            robot_action_processor=robot_action_processor,
            robot_observation_processor=robot_observation_processor,
            display_data=cfg.display_data,
            display_terminal=cfg.display_terminal,
            duration=cfg.teleop_time_s,
            display_compressed_images=display_compressed_images,
        )
    finally:
        _disconnect_best_effort(teleop, "teleoperator")
        _disconnect_best_effort(robot, "robot")


def main():
    register_third_party_plugins()
    teleoperate()


if __name__ == "__main__":
    main()
