"""Quest3 leader teleoperator package exports.

Keep imports lazy so config-only imports do not require optional WebRTC,
ROS, or hardware dependencies.
"""

__all__ = ["WebRTCServerBase", "QuestWebrtcVRTeleop", "Quest3Leader", "Quest3LeaderConfig"]


def __getattr__(name):
    if name == "WebRTCServerBase":
        from .webrtc_base import WebRTCServerBase

        return WebRTCServerBase
    if name == "QuestWebrtcVRTeleop":
        from .quest_webrtc import QuestWebrtcVRTeleop

        return QuestWebrtcVRTeleop
    if name == "Quest3Leader":
        from .quest3_leader import Quest3Leader

        return Quest3Leader
    if name == "Quest3LeaderConfig":
        from .config_quest3_leader import Quest3LeaderConfig

        return Quest3LeaderConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
