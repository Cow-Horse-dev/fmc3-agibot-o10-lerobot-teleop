#!/usr/bin/env python3

import logging
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
from .robots.pico_follower_single_arm_eef.config_pico_follower_single_arm_eef import (  # noqa: F401
    PicoFollowerSingleArmEEFConfig,
)
from .robots.utils import make_robot_from_config
from .teleoperators.pico_leader_single_arm_agibot_o10.config_pico_leader_single_arm_agibot_o10 import (  # noqa: F401
    PicoLeaderSingleArmAgibotO10Config,
)
from .teleoperators.pico_leader_single_arm_eef.config_pico_leader_single_arm_eef import (  # noqa: F401
    PicoLeaderSingleArmEEFConfig,
)
from .teleoperators.utils import make_teleoperator_from_config
from .utils.display_filter import filter_display_observation


@dataclass
class TeleoperateConfig:
    teleop: TeleoperatorConfig
    robot: RobotConfig
    fps: int = 60
    teleop_time_s: float | None = None
    display_data: bool = False
    display_ip: str | None = None
    display_port: int | None = None
    display_compressed_images: bool = False


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
    duration: float | None = None,
    display_compressed_images: bool = False,
):
    display_len = max(len(key) for key in robot.action_features)
    camera_keys = list(getattr(robot, "cameras", {}).keys())
    start = time.perf_counter()

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

            print("\n" + "-" * (display_len + 10))
            print(f"{'NAME':<{display_len}} | {'VALUE':>7}")
            for motor, value in robot_action_to_send.items():
                print(f"{motor:<{display_len}} | {value:>7.2f}")
            move_cursor_up(len(robot_action_to_send) + 3)

        dt_s = time.perf_counter() - loop_start
        precise_sleep(max(1 / fps - dt_s, 0.0))
        loop_s = time.perf_counter() - loop_start
        print(f"Teleop loop time: {loop_s * 1e3:.2f}ms ({1 / loop_s:.0f} Hz)")
        move_cursor_up(1)

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
    (
        teleop_action_processor,
        robot_action_processor,
        robot_observation_processor,
    ) = make_default_processors()

    teleop.connect()
    robot.connect()

    try:
        teleop_loop(
            teleop=teleop,
            robot=robot,
            fps=cfg.fps,
            teleop_action_processor=teleop_action_processor,
            robot_action_processor=robot_action_processor,
            robot_observation_processor=robot_observation_processor,
            display_data=cfg.display_data,
            duration=cfg.teleop_time_s,
            display_compressed_images=display_compressed_images,
        )
    finally:
        if getattr(teleop, "is_connected", False):
            teleop.disconnect()
        if getattr(robot, "is_connected", False):
            robot.disconnect()


def main():
    register_third_party_plugins()
    teleoperate()


if __name__ == "__main__":
    main()
