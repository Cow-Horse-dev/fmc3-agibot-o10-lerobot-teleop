from .config_pico_follower_dual_arm_agibot_o10 import (
    PicoFollowerDualArmAgibotO10Config,
)

__all__ = [
    "PicoFollowerDualArmAgibotO10Config",
    "PicoFollowerDualArmAgibotO10",
]


def __getattr__(name: str):
    if name == "PicoFollowerDualArmAgibotO10":
        from .airbot_pico_follower_dual_arm_agibot_o10 import (
            PicoFollowerDualArmAgibotO10,
        )

        return PicoFollowerDualArmAgibotO10
    raise AttributeError(name)
