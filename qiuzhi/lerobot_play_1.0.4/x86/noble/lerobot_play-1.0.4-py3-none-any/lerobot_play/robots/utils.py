"""
Copyright: qiuzhi.tech
Author: hanyang
Date: 2025-09-10 17:34:34
LastEditTime: 2025-09-10 17:55:52
"""
from lerobot.robots.utils import (
    make_robot_from_config as make_lerobot_robot_from_config,
)
from lerobot.robots.config import RobotConfig
from lerobot.robots.robot import Robot


def make_robot_from_config(config: RobotConfig) -> Robot:
    if config.type == "airbot_play_follower":
        from .airbot_play_follower import AirbotPlayFollower

        return AirbotPlayFollower(config)

    elif config.type == "airbot_PTK_follower":
        from .airbot_ptk_follower import AirbotPTKFollower

        return AirbotPTKFollower(config)

    elif config.type == "airbot_TOK4_follower":
        from .airbot_tok4_follower import AirbotTOK4Follower

        return AirbotTOK4Follower(config)

    elif config.type == "airbot_TOK2_follower":
        from .airbot_tok2_follower import AirbotTOK2Follower

        return AirbotTOK2Follower(config)

    elif config.type == "quest3_follower":
        from .quest3_follower import Quest3Follower

        return Quest3Follower(config)

    elif config.type == "pico_follower":
        from .pico_follower.airbot_pico_follower import PicoFollower

        return PicoFollower(config)

    elif config.type == "pico_follower_single_arm_eef":
        from .pico_follower_single_arm_eef.airbot_pico_follower_single_arm_eef import (
            PicoFollowerSingleArmEEF,
        )

        return PicoFollowerSingleArmEEF(config)
    elif config.type == "pico_follower_single_arm_agibot_o10":
        from .pico_follower_single_arm_agibot_o10 import (
            PicoFollowerSingleArmAgibotO10,
        )

        return PicoFollowerSingleArmAgibotO10(config)

    elif config.type == "pico_follower_dual_arm_agibot_o10":
        from .pico_follower_dual_arm_agibot_o10.airbot_pico_follower_dual_arm_agibot_o10 import (
            PicoFollowerDualArmAgibotO10,
        )

        return PicoFollowerDualArmAgibotO10(config)

    else:
        return make_lerobot_robot_from_config(config)
