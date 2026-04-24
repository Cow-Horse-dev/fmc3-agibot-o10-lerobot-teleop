"""Pico single-arm EEF teleoperator package exports.

Keep imports lazy so config-only imports do not require optional WebRTC,
ROS, or hardware dependencies.
"""

__all__ = [
    "WebRTCServerBase",
    "PicoWebrtcVRTeleop",
    "PicoLeaderSingleArmEEF",
    "PicoLeaderSingleArmEEFConfig",
    "BaseHandTeleoperator",
    "UdexrealTeleoperator",
]


def __getattr__(name):
    if name == "WebRTCServerBase":
        from .webrtc_base import WebRTCServerBase

        return WebRTCServerBase
    if name == "PicoWebrtcVRTeleop":
        from .pico_webrtc import PicoWebrtcVRTeleop

        return PicoWebrtcVRTeleop
    if name == "PicoLeaderSingleArmEEF":
        from .pico_leader_single_arm_eef import PicoLeaderSingleArmEEF

        return PicoLeaderSingleArmEEF
    if name == "PicoLeaderSingleArmEEFConfig":
        from .config_pico_leader_single_arm_eef import PicoLeaderSingleArmEEFConfig

        return PicoLeaderSingleArmEEFConfig
    if name == "BaseHandTeleoperator":
        from .base_hand import BaseHandTeleoperator

        return BaseHandTeleoperator
    if name == "UdexrealTeleoperator":
        from .udexreal_hand import UdexrealTeleoperator

        return UdexrealTeleoperator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
