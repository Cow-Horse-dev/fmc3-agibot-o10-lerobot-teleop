from lerobot.teleoperators.utils import (
    make_teleoperator_from_config as make_lerobot_teleoperator_from_config,
)

from lerobot_play._compat import Teleoperator, TeleoperatorConfig


def make_teleoperator_from_config(config: TeleoperatorConfig) -> Teleoperator:
    if config.type == "airbot_replay":
        from .airbot_replay import AirbotReplay

        return AirbotReplay(config)

    elif config.type == "airbot_replay_mini":
        from .airbot_replay_mini import AirbotReplayMini

        return AirbotReplayMini(config)

    elif config.type == "airbot_PTK_leader":
        from .airbot_ptk_leader import AirbotPTKLeader

        return AirbotPTKLeader(config)

    elif config.type == "airbot_TOK4_leader":
        from .airbot_tok4_leader import AirbotTOK4Leader

        return AirbotTOK4Leader(config)

    elif config.type == "airbot_TOK2_leader":
        from .airbot_tok2_leader import AirbotTOK2Leader

        return AirbotTOK2Leader(config)

    elif config.type == "airbot_TOK2_mini_leader":
        from .airbot_tok2_mini_leader import AirbotTOK2MiniLeader

        return AirbotTOK2MiniLeader(config)

    elif config.type == "airbot_play_with_E2_leader":
        from .airbot_play_with_E2_leader import AirbotplaywithE2Leader

        return AirbotplaywithE2Leader(config)

    elif config.type == "quest3_leader":
        from .quest3_leader import Quest3Leader

        return Quest3Leader(config)

    elif config.type == "pico_leader":
        from .pico_leader import PicoLeader

        return PicoLeader(config)

    elif config.type == "pico_leader_single_arm_eef":
        from .pico_leader_single_arm_eef import PicoLeaderSingleArmEEF

        return PicoLeaderSingleArmEEF(config)
    elif config.type == "pico_leader_single_arm_agibot_o10":
        from .pico_leader_single_arm_agibot_o10 import PicoLeaderSingleArmAgibotO10

        return PicoLeaderSingleArmAgibotO10(config)

    else:
        return make_lerobot_teleoperator_from_config(config)
