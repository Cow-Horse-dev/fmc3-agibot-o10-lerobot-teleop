import asyncio
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import types
from types import SimpleNamespace


def _new_stub_module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
    return module


def _install_optional_dependency_stubs() -> None:
    try:
        import aiortc  # noqa: F401
    except ImportError:
        aiortc_module = _new_stub_module("aiortc")

        class _DummyPeerConnection:
            pass

        class _DummySessionDescription:
            def __init__(self, *args, **kwargs):
                pass

        class _DummyIceCandidate:
            def __init__(self, *args, **kwargs):
                pass

        class _DummyIceServer:
            def __init__(self, *args, **kwargs):
                pass

        class _DummyConfiguration:
            def __init__(self, *args, **kwargs):
                pass

        class _DummyRtpSender:
            pass

        aiortc_module.RTCPeerConnection = _DummyPeerConnection
        aiortc_module.RTCSessionDescription = _DummySessionDescription
        aiortc_module.RTCIceCandidate = _DummyIceCandidate
        aiortc_module.RTCIceServer = _DummyIceServer
        aiortc_module.RTCConfiguration = _DummyConfiguration
        aiortc_module.RTCRtpSender = _DummyRtpSender
        sys.modules["aiortc"] = aiortc_module

        aiortc_contrib_module = _new_stub_module("aiortc.contrib")
        aiortc_contrib_media_module = _new_stub_module("aiortc.contrib.media")

        class _DummyMediaRelay:
            pass

        aiortc_contrib_media_module.MediaRelay = _DummyMediaRelay
        sys.modules["aiortc.contrib"] = aiortc_contrib_module
        sys.modules["aiortc.contrib.media"] = aiortc_contrib_media_module

    try:
        import aiohttp_cors  # noqa: F401
    except ImportError:
        aiohttp_cors_module = _new_stub_module("aiohttp_cors")
        aiohttp_cors_module.ResourceOptions = lambda **kwargs: kwargs
        aiohttp_cors_module.setup = (
            lambda *args, **kwargs: types.SimpleNamespace(add=lambda route: None)
        )
        sys.modules["aiohttp_cors"] = aiohttp_cors_module

    try:
        import zmq  # noqa: F401
    except ImportError:
        zmq_module = _new_stub_module("zmq")
        zmq_module.PUB = 1
        zmq_module.SUB = 2
        zmq_module.SNDHWM = 3
        zmq_module.CONFLATE = 4
        zmq_module.RCVTIMEO = 5

        class _DummyAgain(Exception):
            pass

        class _DummySocket:
            def setsockopt(self, *args, **kwargs):
                pass

            def setsockopt_string(self, *args, **kwargs):
                pass

            def bind(self, *args, **kwargs):
                pass

            def connect(self, *args, **kwargs):
                pass

            def close(self, *args, **kwargs):
                pass

            def recv_json(self):
                raise _DummyAgain

        class _DummyContext:
            def socket(self, *_args, **_kwargs):
                return _DummySocket()

            def term(self):
                pass

        zmq_module.Again = _DummyAgain
        zmq_module.Context = _DummyContext
        sys.modules["zmq"] = zmq_module

    try:
        from scipy.spatial.transform import Rotation  # noqa: F401
    except ImportError:
        scipy_module = _new_stub_module("scipy")
        scipy_spatial_module = _new_stub_module("scipy.spatial")
        scipy_transform_module = _new_stub_module("scipy.spatial.transform")

        class _DummyRotation:
            @staticmethod
            def from_quat(_rotation):
                return _DummyRotation()

            @staticmethod
            def from_euler(*_args, **_kwargs):
                return _DummyRotation()

            def __mul__(self, _other):
                return self

            def as_quat(self):
                return [0.0, 0.0, 0.0, 1.0]

        scipy_transform_module.Rotation = _DummyRotation
        sys.modules["scipy"] = scipy_module
        sys.modules["scipy.spatial"] = scipy_spatial_module
        sys.modules["scipy.spatial.transform"] = scipy_transform_module


_install_optional_dependency_stubs()


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

PICO_WEBRTC_PATH = (
    LEROBOT_PLAY_PACKAGE_ROOT
    / "lerobot_play"
    / "teleoperators"
    / "pico_leader_single_arm_eef"
    / "pico_webrtc.py"
)

spec = importlib.util.spec_from_file_location(
    "pico_webrtc_test_module",
    PICO_WEBRTC_PATH,
)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

PicoWebrtcVRTeleop = module.PicoWebrtcVRTeleop


def test_on_connection_established_prints_port_message(capsys):
    server = object.__new__(PicoWebrtcVRTeleop)
    server.port = 8080
    server.connection_status = {
        "is_connected": False,
        "connected_clients": {},
        "total_connections": 0,
        "last_connection_time": 0.0,
        "last_disconnection_time": 0.0,
    }
    server.log_info = lambda _message: None

    asyncio.run(
        PicoWebrtcVRTeleop.on_connection_established(server, "PC-test", object())
    )

    captured = capsys.readouterr()

    assert "VR 已连接到 8080 端口" in captured.out
    assert server.connection_status["is_connected"] is True
    assert server.connection_status["total_connections"] == 1
    assert "PC-test" in server.connection_status["connected_clients"]


def test_handle_pose_data_logs_pose_device_summary(monkeypatch):
    server = object.__new__(PicoWebrtcVRTeleop)
    server.arm_device = "pico"
    server.head_info = SimpleNamespace(data=[0.0] * 7)
    server.left_info = SimpleNamespace(data=[0.0] * 7)
    server.right_info = SimpleNamespace(data=[0.0] * 7)
    server.vr_ctrl_state = {
        "HBattery": 0.0,
        "RIsTracked": False,
        "RBattery": 0.0,
        "LIsTracked": False,
        "LBattery": 0.0,
        "LWristTracked": False,
        "LWristBattery": 0.0,
        "RWristTracked": False,
        "RWristBattery": 0.0,
    }
    log_messages = []
    server.log_info = log_messages.append
    server.log_error = lambda _message: None

    async def fake_publish_pose_data():
        return None

    server._publish_pose_data = fake_publish_pose_data
    monkeypatch.setattr(module.time, "time", lambda: 100.0)

    asyncio.run(
        PicoWebrtcVRTeleop._handle_pose_data(
            server,
            "PC-test",
            {
                "payload": json.dumps(
                    {
                        "poses": [
                            {
                                "deviceType": "right_controller",
                                "position": {"x": 0.1, "y": 0.2, "z": 0.3},
                                "rotation": {
                                    "x": 0.0,
                                    "y": 0.0,
                                    "z": 0.0,
                                    "w": 1.0,
                                },
                                "isTracked": True,
                                "batteryLevel": 4.0,
                            }
                        ]
                    }
                )
            },
        )
    )

    assert len(log_messages) == 1
    assert "right_controller(tracked=True,battery=4.0,pos=True,rot=True)" in log_messages[0]
    assert "missing: left_controller" in log_messages[0]
