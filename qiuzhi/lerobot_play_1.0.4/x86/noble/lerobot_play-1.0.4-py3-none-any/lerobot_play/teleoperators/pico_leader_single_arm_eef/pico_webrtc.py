import argparse
import asyncio
from datetime import datetime
import json
from typing import Optional, Dict
import time
from aiortc.contrib.media import MediaRelay
from aiohttp import web
from aiortc import RTCPeerConnection
import aiohttp_cors

# import rclpy
# from rclpy.node import Node
import threading
import yaml
import numpy as np
import zmq
import threading
from scipy.spatial.transform import Rotation

try:
    from std_msgs.msg import Float32MultiArray
except ImportError:
    class Float32MultiArray:
        def __init__(self):
            self.data = []

from lerobot_play.teleoperators.quest3_leader import WebRTCServerBase


class PicoWebrtcVRTeleop(WebRTCServerBase):
    """处理VR设备的姿态数据和手柄输入"""

    def __init__(
        self,
        arm_device="none",
        host="0.0.0.0",
        port=8080,
        zmq_pose_port=8000,
        zmq_control_port=8001,
    ):
        super().__init__(host, port)

        # ZMQ初始化
        self.zmq_context = zmq.Context()

        # 姿态数据发布socket
        self.pose_socket = self.zmq_context.socket(zmq.PUB)
        self.pose_socket.setsockopt(zmq.SNDHWM, 1)
        self.pose_socket.bind(f"tcp://*:{zmq_pose_port}")

        # 控制器数据发布socket
        self.control_socket = self.zmq_context.socket(zmq.PUB)
        self.control_socket.setsockopt(zmq.SNDHWM, 5)
        self.control_socket.bind(f"tcp://*:{zmq_control_port}")

        # vr 手柄输入
        self.vr_ctrl_data = {
            "A": False,
            "B": False,
            "RThU": False,  # 右手柄主触摸板触摸
            "RJ": False,  # 右手柄主触摸板按压
            "RG": False,  # 右手柄抓握键
            "RTr": False,  # 右手柄扳机键
            "X": False,
            "Y": False,
            "LThU": False,  # 左手柄主触摸板触摸
            "LJ": False,  # 左手柄主触摸板按压
            "LG": False,  # 左手柄抓握键
            "LTr": False,  # 左手柄扳机键
            "leftJS": {
                "ud": 0.0,
                "lr": 0.0,
            },  # 左手柄主触摸板推压程度 ud为上下，lr为左右，ud推压至下极限为-1，推压至上极限为1; lr推压至左极限为-1，推压至右极限为1
            "leftTrig": 0.0,  # 左手柄扳机键按压程度
            "leftGrip": 0.0,  # 左手柄抓握键按压程度
            "rightJS": {
                "ud": 0.0,
                "lr": 0.0,
            },  # 右手柄主触摸板 ud为上下，lr为左右，ud推压至下极限为-1，推压至上极限为1; lr推压至左极限为-1，推压至右极限为1
            "rightTrig": 0.0,  # 右手柄扳机键按压程度
            "rightGrip": 0.0,  # 右手柄抓握键按压程度
        }
        self.vr_ctrl_state = {
            "HBattery": 0.0,
            "RIsTracked": False,  # 右控制器追踪
            "RBattery": 0.0,  # 右控制器电量
            "LIsTracked": False,  # 左控制器追踪
            "LBattery": 0.0,  # 左控制器电量
            # 腕带追踪器状态
            "LWristTracked": False,  # 左腕带追踪
            "LWristBattery": 0.0,  # 左腕带电量
            "RWristTracked": False,  # 右腕带追踪
            "RWristBattery": 0.0,  # 右腕带电量
        }

        # 连接状态相关变量
        self.connection_status = {
            "is_connected": False,  # 是否有客户端连接
            "connected_clients": {},  # 已连接的客户端信息 {pc_id: {"connect_time": timestamp, "status": "connected"}}
            "total_connections": 0,  # 总连接数
            "last_connection_time": 0.0,  # 最后连接时间
            "last_disconnection_time": 0.0,  # 最后断开连接时间
        }

        self.net_delay = 0.0

        self.arm_device = arm_device

        self.vrCmdRecv = False
        self.headInfoRecv = False
        self.leftInfoRecv = False
        self.rightInfoRecv = False
        self._last_pose_device_log_time = 0.0
        self._last_pose_device_summary = None

        self._server_task = None
        self._loop = None
        self._server_thread = None

        # vr 姿态数据
        self.head_info = Float32MultiArray()
        self.head_info.data = [0.0] * 7
        self.left_info = Float32MultiArray()
        self.left_info.data = [0.0] * 7
        self.right_info = Float32MultiArray()
        self.right_info.data = [0.0] * 7

        self.enable_video = False
        self.camera_source = "airbot"
        self.ros_topic = "/camera/camera/color/image_raw"
        self.ros_node = None
        self.ros_thread = None
        self.airbot_camera = None
        self.airbot_task = None
        # self.media_relay = MediaRelay()
        # self.source_video_track = RosVideoStreamTrack(self.frame_queue)
        # 只有启用视频时才初始化视频相关组件
        if self.enable_video:

            from ..camera import (
                RealsenseCamera,
                USBCamera,
                RosVideoStreamTrack,
                RosImageSubscriber,
            )

            self.media_relay = MediaRelay()
            self.source_video_track = RosVideoStreamTrack(self.frame_queue)
            self.log_info(
                f"Video enabled - MediaRelay initialized:{self.media_relay is not None}"
            )
            self.log_info(
                f"Video enabled - Source video track initialized:{self.source_video_track is not None}"
            )
        else:
            self.media_relay = None
            self.source_video_track = None
            self.log_info("Video disabled - No video components initialized")

        self.last_capture_frame_time = 0

        self.log_info(f"MediaRelay initialized:{self.media_relay is not None}")
        self.log_info(
            f"Source video track initialized:{self.source_video_track is not None}"
        )

    async def on_data_channel_message(
        self, pc_id: str, channel_label: str, message: str
    ):
        """处理数据通道消息"""
        client_id = pc_id.split("-")[0] + "-" + pc_id.split("-")[1]

        try:
            data = json.loads(message)
            message_type = data.get("messageType", "unknown")

            if message_type == "test":
                await self._handle_test_message(client_id, channel_label, data)

            if message_type == "pose":
                await self._handle_pose_data(client_id, data)

            elif message_type == "buttons":
                await self._handle_controller_data(client_id, data)

            else:
                self.log_info(f"[{pc_id}] Unknown VR message type: {message_type}")

        except json.JSONDecodeError as e:
            self.log_error(f"[{pc_id}] JSON decode error: {e}")
        except Exception as e:
            self.log_error(f"[{pc_id}] Error processing VR message: {e}")

    async def _handle_test_message(self, client_id: str, channel_label: str, data):
        """处理测试消息"""
        self.log_info(f"[{client_id}] Received test message: {data.get('payload')}")

        response = {
            "messageType": "test_response",
            "payload": "VR Test message received successfully!",
            "server_time": time.time(),
        }

        if self.send_to_data_channel(channel_label, response):
            self.log_info(f"[{client_id}] Sent test response")

    async def _handle_pose_data(self, pc_id: str, data):
        """处理VR姿态数据"""
        try:
            pose_payload_str = data["payload"]
            pose_payload = json.loads(pose_payload_str)
            poses = pose_payload.get("poses", [])
            self._log_pose_device_summary(poses)
            # client_timestamp = pose_payload.get("timeStamp", 0.0)
            # server_timestamp = time.time_ns()//1000000
            # self.net_delay = server_timestamp - client_timestamp
            # print(f"[{pc_id}] Received pose data at {client_timestamp}, server time: {server_timestamp}, delay: {self.net_delay}")
            # print(self.vr_ctrl_state)
            for pose in poses:
                device_type = pose.get("deviceType")
                pos = pose.get("position")
                rot = pose.get("rotation")

                isTracked = pose.get("isTracked")
                batteryLevel = pose.get("batteryLevel")

                # 检查 pos 和 rot 是否为 None
                if pos is None or rot is None:
                    continue

                pos = [pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)]
                rot = [
                    rot.get("x", 0.0),
                    rot.get("y", 0.0),
                    rot.get("z", 0.0),
                    rot.get("w", 1.0),
                ]
                # print("pos", pos)
                if device_type and pos and rot:
                    if device_type == "hmd":
                        for i in range(3):
                            self.head_info.data[i] = pos[i]
                        for i in range(4):
                            self.head_info.data[3 + i] = rot[i]
                        self.vr_ctrl_state["HBattery"] = (batteryLevel or 0) * 100

                    elif self.arm_device == "pico_wrist":
                        if device_type == "left_wrist":
                            trans = [pos[i] for i in range(3)]
                            quat = [rot[i] for i in range(4)]
                            vr_trans, vr_quat = CoordinateCalibration.calibrate(
                                trans, quat
                            )
                            self.left_info.data = [*vr_trans, *vr_quat]
                            self.vr_ctrl_state["LWristTracked"] = isTracked
                            self.vr_ctrl_state["LWristBattery"] = (
                                (batteryLevel or 0) / 10.0 * 100
                            )
                            # print(f"Left wrist pose: {self.left_info.data}")

                        elif device_type == "right_wrist":
                            trans = [pos[i] for i in range(3)]
                            quat = [rot[i] for i in range(4)]
                            vr_trans, vr_quat = CoordinateCalibration.calibrate(
                                trans, quat
                            )
                            self.right_info.data = [*vr_trans, *vr_quat]
                            self.vr_ctrl_state["RWristTracked"] = isTracked
                            self.vr_ctrl_state["RWristBattery"] = (
                                (batteryLevel or 0) / 10.0 * 100
                            )
                            # print(f"Right wrist pose: {self.right_info.data}")

                    elif self.arm_device == "pico" or self.arm_device == "quest":
                        if device_type == "left_controller":
                            for i in range(3):
                                self.left_info.data[i] = pos[i]
                            for i in range(4):
                                self.left_info.data[3 + i] = rot[i]
                            self.vr_ctrl_state["LIsTracked"] = isTracked
                            self.vr_ctrl_state["LBattery"] = (
                                (batteryLevel or 0) / 5.0 * 100
                            )
                        elif device_type == "right_controller":
                            for i in range(3):
                                self.right_info.data[i] = pos[i]
                            for i in range(4):
                                self.right_info.data[3 + i] = rot[i]
                            self.vr_ctrl_state["RIsTracked"] = isTracked
                            self.vr_ctrl_state["RBattery"] = (
                                (batteryLevel or 0) / 5.0 * 100
                            )

                        elif self.arm_device == "none":
                            self.log_error(f"Error arm_device")

                    # print(f"Left pose: {self.left_info.data}")
                    # print(f"Right pose: {self.right_info.data}")
            await self._publish_pose_data()

        except Exception as e:
            self.log_error(f"[{pc_id}] Error processing pose data: {e}")

    def _log_pose_device_summary(self, poses):
        device_summaries = []
        device_types = set()
        for pose in poses:
            device_type = pose.get("deviceType") or "<missing>"
            device_types.add(device_type)
            device_summaries.append(
                f"{device_type}("
                f"tracked={pose.get('isTracked')},"
                f"battery={pose.get('batteryLevel')},"
                f"pos={pose.get('position') is not None},"
                f"rot={pose.get('rotation') is not None}"
                ")"
            )

        summary = ", ".join(device_summaries) if device_summaries else "no pose devices"
        expected_devices = {
            "pico": ("left_controller", "right_controller"),
            "quest": ("left_controller", "right_controller"),
            "pico_wrist": ("left_wrist", "right_wrist"),
        }.get(self.arm_device, ())
        missing_devices = [
            device_type for device_type in expected_devices if device_type not in device_types
        ]
        if missing_devices:
            summary = f"{summary} | missing: {', '.join(missing_devices)}"

        now = time.time()
        last_summary = getattr(self, "_last_pose_device_summary", None)
        last_log_time = getattr(self, "_last_pose_device_log_time", 0.0)
        if summary != last_summary or now - last_log_time >= 1.0:
            self.log_info(f"VR pose devices ({self.arm_device}): {summary}")
            self._last_pose_device_summary = summary
            self._last_pose_device_log_time = now

    async def _handle_controller_data(self, pc_id: str, data):
        """处理VR手柄数据"""
        try:
            controller_payload = data["payload"]
            controller_data = json.loads(controller_payload)

            self.vr_ctrl_data["A"] = controller_data.get("A", False)
            self.vr_ctrl_data["B"] = controller_data.get("B", False)
            self.vr_ctrl_data["X"] = controller_data.get("X", False)
            self.vr_ctrl_data["Y"] = controller_data.get("Y", False)
            self.vr_ctrl_data["LTr"] = controller_data.get("LTr", False)
            self.vr_ctrl_data["RTr"] = controller_data.get("RTr", False)
            self.vr_ctrl_data["LG"] = controller_data.get("LG", False)
            self.vr_ctrl_data["RG"] = controller_data.get("RG", False)
            self.vr_ctrl_data["LJ"] = controller_data.get("LJ", False)
            self.vr_ctrl_data["RJ"] = controller_data.get("RJ", False)
            self.vr_ctrl_data["LThU"] = controller_data.get("LThU", True)
            self.vr_ctrl_data["RThU"] = controller_data.get("RThU", True)
            self.vr_ctrl_data["leftTrig"] = controller_data.get("leftTrig", 0.0)
            self.vr_ctrl_data["rightTrig"] = controller_data.get("rightTrig", 0.0)
            self.vr_ctrl_data["leftGrip"] = controller_data.get("leftGrip", 0.0)
            self.vr_ctrl_data["rightGrip"] = controller_data.get("rightGrip", 0.0)
            left_js = controller_data.get("leftJS", {})
            right_js = controller_data.get("rightJS", {})
            self.vr_ctrl_data["leftJS"]["ud"] = left_js.get("y", 0.0)
            self.vr_ctrl_data["leftJS"]["lr"] = left_js.get("x", 0.0)
            self.vr_ctrl_data["rightJS"]["ud"] = right_js.get("y", 0.0)
            self.vr_ctrl_data["rightJS"]["lr"] = right_js.get("x", 0.0)

            # print("vr_ctrl_data", self.vr_ctrl_data)
            await self._publish_control_data()

        except Exception as e:
            self.log_error(f"[{pc_id}] Error processing controller data: {e}")

    async def _publish_pose_data(self):
        """发布姿态数据到ZMQ"""
        try:
            pose_message = {
                "timestamp": time.time(),
                "head_pose": self.head_info.data.tolist()
                if hasattr(self.head_info.data, "tolist")
                else list(self.head_info.data),
                "left_pose": self.left_info.data.tolist()
                if hasattr(self.left_info.data, "tolist")
                else list(self.left_info.data),
                "right_pose": self.right_info.data.tolist()
                if hasattr(self.right_info.data, "tolist")
                else list(self.right_info.data),
                "tracking_state": {
                    "head_battery": float(self.vr_ctrl_state["HBattery"]),
                    "left_tracked": bool(self.vr_ctrl_state["LIsTracked"]),
                    "left_battery": float(self.vr_ctrl_state["LBattery"]),
                    "right_tracked": bool(self.vr_ctrl_state["RIsTracked"]),
                    "right_battery": float(self.vr_ctrl_state["RBattery"]),
                    "left_wrist_tracked": bool(self.vr_ctrl_state["LWristTracked"]),
                    "left_wrist_battery": float(self.vr_ctrl_state["LWristBattery"]),
                    "right_wrist_tracked": bool(self.vr_ctrl_state["RWristTracked"]),
                    "right_wrist_battery": float(self.vr_ctrl_state["RWristBattery"]),
                },
            }

            # 发送姿态数据
            self.pose_socket.send_json(pose_message)

        except Exception as e:
            self.log_error(f"Error publishing pose data: {e}")

    async def _publish_control_data(self):
        """发布控制器数据到ZMQ"""
        try:
            control_message = {
                "timestamp": time.time(),
                "buttons": {
                    "A": bool(self.vr_ctrl_data["A"]),
                    "B": bool(self.vr_ctrl_data["B"]),
                    "X": bool(self.vr_ctrl_data["X"]),
                    "Y": bool(self.vr_ctrl_data["Y"]),
                    "RThU": bool(self.vr_ctrl_data["RThU"]),
                    "RJ": bool(self.vr_ctrl_data["RJ"]),
                    "RG": bool(self.vr_ctrl_data["RG"]),
                    "RTr": bool(self.vr_ctrl_data["RTr"]),
                    "LThU": bool(self.vr_ctrl_data["LThU"]),
                    "LJ": bool(self.vr_ctrl_data["LJ"]),
                    "LG": bool(self.vr_ctrl_data["LG"]),
                    "LTr": bool(self.vr_ctrl_data["LTr"]),
                },
                "triggers": {
                    "left": float(self.vr_ctrl_data["leftTrig"]),
                    "right": float(self.vr_ctrl_data["rightTrig"]),
                },
                "grips": {
                    "left": float(self.vr_ctrl_data["leftGrip"]),
                    "right": float(self.vr_ctrl_data["rightGrip"]),
                },
                "joysticks": {
                    "left": {
                        "ud": float(self.vr_ctrl_data["leftJS"]["ud"]),
                        "lr": float(self.vr_ctrl_data["leftJS"]["lr"]),
                    },
                    "right": {
                        "ud": float(self.vr_ctrl_data["rightJS"]["ud"]),
                        "lr": float(self.vr_ctrl_data["rightJS"]["lr"]),
                    },
                },
            }

            # 发送控制器数据
            self.control_socket.send_json(control_message)
            # print(control_message)
            # self.log_info("Control data published successfully")

        except Exception as e:
            self.log_error(f"Error publishing control data: {e}")

    async def on_connection_established(self, pc_id: str, pc: RTCPeerConnection):
        print(f"[{pc_id}] VR 已连接到 {self.port} 端口")
        self.log_info(f"[{pc_id}] WebRTC connection established")

        # 更新连接状态
        current_time = time.time()
        self.connection_status["is_connected"] = True
        self.connection_status["connected_clients"][pc_id] = {
            "connect_time": current_time,
            "status": "connected",
        }
        self.connection_status["total_connections"] += 1
        self.connection_status["last_connection_time"] = current_time

        self.log_info(
            f"[{pc_id}] Connection status updated - Total clients: {len(self.connection_status['connected_clients'])}"
        )

    async def on_connection_closed(self, pc_id: str):
        self.log_info(f"[{pc_id}] VR client disconnected")

        # 更新连接状态
        current_time = time.time()
        if pc_id in self.connection_status["connected_clients"]:
            del self.connection_status["connected_clients"][pc_id]

        # 如果没有客户端连接了，更新连接状态
        if len(self.connection_status["connected_clients"]) == 0:
            self.connection_status["is_connected"] = False
            # 重置VR控制器状态
            self.vr_ctrl_state = {
                "HBattery": 0.0,
                "RIsTracked": False,  # 右控制器追踪
                "RBattery": 0.0,  # 右控制器电量
                "LIsTracked": False,  # 左控制器追踪
                "LBattery": 0.0,  # 左控制器电量
                # 腕带追踪器状态
                "LWristTracked": False,  # 左腕带追踪
                "LWristBattery": 0.0,  # 左腕带电量
                "RWristTracked": False,  # 右腕带追踪
                "RWristBattery": 0.0,  # 右腕带电量
            }

        self.connection_status["last_disconnection_time"] = current_time

        self.log_info(
            f"[{pc_id}] Connection status updated - Remaining clients: {len(self.connection_status['connected_clients'])}"
        )

    async def on_server_started(self):
        self.log_info("VR Server initialized!")
        self.log_info("Ready to accept VR client connections...")

        if not self.enable_video:
            self.log_info("Video streaming is disabled")
            return

        self.log_info(f"Starting camera source: {self.camera_source}")

        if self.camera_source == "ros":
            try:
                rclpy.init()
                self.ros_node = RosImageSubscriber(
                    self.ros_topic, self.frame_queue, asyncio.get_running_loop()
                )
                self.ros_thread = threading.Thread(
                    target=rclpy.spin, args=(self.ros_node,), daemon=True
                )
                self.ros_thread.start()
                self.log_info("ROS subscriber started in a background thread.")
            except Exception as e:
                self.log_error(f"Failed to start ROS source: {e}")

        elif self.camera_source == "airbot":
            try:
                with open("configs/camera.yaml") as file:
                    config = yaml.safe_load(file)
                camera_type = config["camera_type"]

                if camera_type == "Realsense":
                    self.airbot_camera = RealsenseCamera()
                elif camera_type == "UsbCam":
                    self.airbot_camera = USBCamera, ()
                else:
                    raise ValueError(f"Unsupported camera_type: {camera_type}")

                self.airbot_task = asyncio.create_task(self._airbot_frame_grabber())
                self.log_info(f"Airbot camera ({camera_type}) frame grabber started.")
            except Exception as e:
                self.log_error(f"Failed to start Airbot source: {e}")

    async def _airbot_frame_grabber(self):
        """Coroutine to continuously grab frames from the airbot camera."""
        loop = asyncio.get_running_loop()
        self.log_info("Starting frame grabber loop...")  # <-- 添加日志1
        while True:
            # Run the blocking get_frame() function in a separate thread
            frame = await loop.run_in_executor(
                None, self.airbot_camera.get_frame, "bgr"
            )

            if frame is not None:
                current_time = time.time()
                if current_time - self.last_capture_frame_time > 5:
                    self.log_info(
                        f"Frame captured, shape: {frame.shape}. Putting into queue..."
                    )  # <-- 添加日志2
                    self.last_capture_frame_time = current_time
                # If the queue is full, discard the oldest frame to make space for the new one
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass  # Should not happen if full() is true, but good practice

                await self.frame_queue.put(frame)

            # A small sleep is still good practice to yield control
            await asyncio.sleep(0.001)

    async def on_server_shutdown(self):
        """Clean up camera resources before the server shuts down."""
        self.log_info("Shutting down camera resources...")

        # 关闭ZMQ socket
        if hasattr(self, "pose_socket"):
            self.pose_socket.close()
        if hasattr(self, "control_socket"):
            self.control_socket.close()
        if hasattr(self, "zmq_context"):
            self.zmq_context.term()

        if self.airbot_task:
            self.airbot_task.cancel()
        if self.airbot_camera and hasattr(self.airbot_camera, "deinit"):
            self.airbot_camera.deinit()
        # if self.ros_node:
        #     rclpy.shutdown()
        self.log_info("Camera resources cleaned up.")

    def run_webrtc_server(self):
        """初始化WebRTC服务器（在后台线程中运行）"""

        def run_server():
            # 创建新的事件循环
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            try:
                # 运行异步服务器
                self._loop.run_until_complete(self.run_forever())
            except Exception as e:
                print(f"WebRTC server error: {e}")
            finally:
                self._loop.close()

        # 在后台线程中启动异步服务器
        self._server_thread = threading.Thread(target=run_server, daemon=True)
        self._server_thread.start()

        print(f"QuestWebrtcVRTeleop server started on {self.host}:{self.port}")

    def stop_server(self):
        """停止WebRTC服务器"""
        if self._loop and not self._loop.is_closed():
            try:
                # 在事件循环中调用停止方法
                future = asyncio.run_coroutine_threadsafe(
                    self.on_server_shutdown(), self._loop
                )
                future.result(timeout=5.0)
            except Exception as e:
                print(f"Error stopping server: {e}")

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5.0)


class CoordinateCalibration:
    def calibrate(position, rotation):
        """
        对 position 和 rotation 施加一个绕动坐标系的坐标变换。
        该变换顺序为：先绕新坐标系的y轴旋转90度，再绕最新的z轴旋转180度。
        """
        rot_input = Rotation.from_quat(rotation)
        rot_y = Rotation.from_euler("y", 90, degrees=True)
        rot_z = Rotation.from_euler("z", 180, degrees=True)
        rot_total = rot_y * rot_z

        # 新旋转
        new_rot = rot_input * rot_total
        new_rotation = new_rot.as_quat().tolist()

        # 新位置
        new_position = position

        return new_position, new_rotation


async def main():
    """主函数"""
    # 添加命令行参数解析
    parser = argparse.ArgumentParser(description="VR Tracking WebRTC Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host IP (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument(
        "--no-video", action="store_true", help="Disable video streaming"
    )
    parser.add_argument("--arm_device", default="none", help="arm_device")
    args = parser.parse_args()
    # rclpy.init()
    # 创建VR服务器实例
    enable_video = not args.no_video
    vr_server = PicoWebrtcVRTeleop(
        host="0.0.0.0", port=8080, arm_device=args.arm_device
    )

    # 运行服务器
    await vr_server.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
