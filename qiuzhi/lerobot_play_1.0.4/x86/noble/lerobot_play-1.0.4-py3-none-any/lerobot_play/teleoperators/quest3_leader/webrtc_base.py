import asyncio
import json
import logging
import uuid
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any, List
from aiohttp import web, WSMsgType
import aiohttp_cors
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
    RTCIceServer,
    RTCConfiguration,
    RTCRtpSender,
)
from collections import deque
import weakref

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class WebRTCServerBase(ABC):
    """WebRTC服务器基类，提供基础的连接管理和信令处理功能"""

    def __init__(
        self, host: str = "0.0.0.0", port: int = 8080, ice_servers: List[str] = None
    ):
        """
        初始化WebRTC服务器

        Args:
            host: 服务器主机地址
            port: 服务器端口
            ice_servers: ICE服务器列表，默认使用Google STUN服务器
        """
        self.host = host
        self.port = port

        # WebRTC配置
        if ice_servers is None:
            ice_servers = ["stun:stun.l.google.com:19302"]

        self.configuration = RTCConfiguration(
            iceServers=[RTCIceServer(url) for url in ice_servers]
        )

        # 连接管理
        self.peer_connections = set()
        self.signaling_messages = deque(maxlen=100)
        self.pc_manager: Optional[PeerConnectionManager] = None

        # 应用实例
        self.app: Optional[web.Application] = None

        self.frame_queue = asyncio.Queue(maxsize=1)

        # 为子类将要定义的属性占位
        self.media_relay = None
        self.source_video_track = None

    def normalize_sdp_type(self, sdp_type):
        """将SDP类型转换为Unity期望的首字母大写格式"""
        if isinstance(sdp_type, str):
            return sdp_type.capitalize()
        return str(sdp_type).capitalize()

    async def start_server(self):
        """启动服务器"""
        self.app = await self._init_app()

        self.log_info(f"Starting WebRTC server on http://{self.host}:{self.port}")
        self.log_info("Available endpoints:")
        self.log_info("  POST /signal  - WebRTC signaling")
        self.log_info("  GET  /poll    - Poll for signaling messages")
        self.log_info("  GET  /status  - Server status")

        # 启动服务器
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        self.log_info("Server started successfully!")

        # 调用子类的初始化后回调
        await self.on_server_started()

        return runner

    async def run_forever(self):
        """运行服务器直到收到中断信号"""
        runner = await self.start_server()

        try:
            while True:
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            self.log_info("Received shutdown signal")
        finally:
            await runner.cleanup()
            await self.on_server_shutdown()
            self.log_info("Server shutdown complete")

    # ==================== 抽象方法 - 子类必须实现 ====================

    @abstractmethod
    async def on_data_channel_message(
        self, pc_id: str, channel_label: str, message: str
    ):
        """
        当收到数据通道消息时调用

        Args:
            pc_id: 连接ID
            channel_label: 数据通道标签
            message: 消息内容
        """
        pass

    # ==================== 可选重写的方法 ====================
    async def on_connection_established(self, pc_id: str, pc: RTCPeerConnection):
        """
        当WebRTC连接建立时调用

        Args:
            pc_id: 连接ID
            pc: RTCPeerConnection实例
        """
        pass

    async def on_server_started(self):
        """服务器启动后回调"""
        pass

    async def on_server_shutdown(self):
        """服务器关闭前回调"""
        pass

    async def on_connection_closed(self, pc_id: str):
        """当连接关闭时调用"""
        pass

    async def on_data_channel_opened(self, pc_id: str, channel_label: str, channel):
        """当数据通道打开时调用"""
        pass

    async def on_data_channel_closed(self, pc_id: str, channel_label: str):
        """当数据通道关闭时调用"""
        pass

    def setup_custom_routes(self, app: web.Application, cors):
        """
        设置自定义路由，子类可以重写此方法添加额外的API端点

        Args:
            app: aiohttp应用实例
            cors: CORS配置
        """
        pass

    # ==================== 内部实现 ====================

    async def _init_app(self):
        """初始化应用"""
        app = web.Application()

        # 配置CORS
        cors = aiohttp_cors.setup(
            app,
            defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods="*",
                )
            },
        )

        # 添加默认路由
        app.router.add_post("/signal", self._handle_signal)
        app.router.add_get("/poll", self._handle_poll)
        app.router.add_get("/poll/{client_id}", self._handle_poll_with_client_id)
        app.router.add_get("/status", self._handle_status)

        # 让子类添加自定义路由
        self.setup_custom_routes(app, cors)

        # 为所有路由添加CORS
        for route in list(app.router.routes()):
            cors.add(route)

        # 设置清理处理器
        async def cleanup_handler(app):
            await self._cleanup_connections()

        app.on_cleanup.append(cleanup_handler)

        return app

    async def _handle_signal(self, request):
        """处理信令消息"""
        try:
            data = await request.json()
            message_type = data.get("type")

            self.log_info(f"Received signaling message: {message_type}")

            if message_type == "offer":
                await self._handle_offer(data)
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"status": "offer_received"}),
                )

            elif message_type == "ice-candidate":
                await self._handle_ice_candidate(data)
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"status": "ice_candidate_received"}),
                )

            else:
                self.log_warning(f"Unknown signaling message type: {message_type}")
                return web.Response(status=400, text="Unknown message type")

        except Exception as e:
            self.log_error(f"Error handling signaling message: {e}")
            return web.Response(status=500, text=str(e))

    async def _handle_offer(self, offer_data):
        """处理WebRTC offer"""
        try:
            self.log_info(
                f"Received full offer data: {json.dumps(offer_data, indent=2)}"
            )
            self.pc_manager = PeerConnectionManager(self)
            pc_id = await self.pc_manager.create_peer_connection()

            offer_sdp_type = offer_data["sdpType"].lower()
            offer = RTCSessionDescription(sdp=offer_data["sdp"], type=offer_sdp_type)

            # 解析SDP offer
            sdp_info = self.parse_sdp_offer(offer_data["sdp"])

            # 只有当客户端请求视频时才添加视频轨道
            if sdp_info["has_video"]:
                if not self.media_relay or not self.source_video_track:
                    self.log_error(
                        "MediaRelay or source video track is not initialized in the subclass!"
                    )
                    return

                # 根据客户端支持的编解码器选择合适的视频轨道
                video_track = self.create_video_track_for_client(sdp_info)
                self.pc_manager.pc.addTrack(video_track)

                self.log_info(
                    f"[{pc_id}] Added video track based on client requirements."
                )
            else:
                self.log_info(
                    f"[{pc_id}] Client doesn't request video, skipping video track."
                )

            await self.pc_manager.pc.setRemoteDescription(offer)
            self.log_info(f"[{pc_id}] Set remote description (offer)")

            answer = await self.pc_manager.pc.createAnswer()
            self.log_info(f"[{pc_id}] The final Answer SDP includes:\n{answer.sdp}")
            await self.pc_manager.pc.setLocalDescription(answer)
            self.log_info(f"[{pc_id}] Created and set local description (answer)")

            answer_message = {
                "type": "answer",
                "sdp": answer.sdp,
                "sdpType": self.normalize_sdp_type(answer.type),
            }
            self.signaling_messages.append(answer_message)

            self.log_info(f"[{pc_id}] Answer added to signaling queue")

        except Exception as e:
            self.log_error(f"Error handling offer: {e}")
            raise

    def parse_sdp_offer(self, sdp):
        """解析SDP offer，提取媒体需求"""
        lines = sdp.split("\n")
        has_video = False
        video_codecs = []

        for line in lines:
            if line.startswith("m=video"):
                has_video = True
            elif line.startswith("a=rtpmap:") and "video" in line:
                # 提取支持的视频编解码器
                codec_info = line.split(" ")[1]
                video_codecs.append(codec_info)

        return {"has_video": has_video, "video_codecs": video_codecs}

    def create_video_track_for_client(self, sdp_info):
        # 根据客户端支持的编解码器和参数创建视频轨道
        if "H264" in sdp_info["video_codecs"]:
            # 创建H264视频轨道
            return self.media_relay.subscribe(self.source_video_track)
        else:
            # 默认轨道
            return self.media_relay.subscribe(self.source_video_track)

    async def _handle_ice_candidate(self, candidate_data):
        """处理客户端发送的ICE候选"""
        try:
            if not self.pc_manager or not self.pc_manager.pc:
                self.log_warning("Received ICE candidate but no active PeerConnection")
                return

            if "candidate" in candidate_data and candidate_data["candidate"]:
                candidate_str = candidate_data["candidate"]
                parts = candidate_str.split()

                if len(parts) >= 8:
                    foundation = parts[0]
                    component = int(parts[1])
                    protocol = parts[2].lower()
                    priority = int(parts[3])
                    address = parts[4]
                    port = int(parts[5])
                    typ = parts[7]

                    ice_candidate = RTCIceCandidate(
                        component=component,
                        foundation=foundation,
                        ip=address,
                        port=port,
                        priority=priority,
                        protocol=protocol,
                        type=typ,
                        sdpMid=candidate_data.get("sdpMid"),
                        sdpMLineIndex=candidate_data.get("sdpMLineIndex"),
                    )

                    await self.pc_manager.pc.addIceCandidate(ice_candidate)
                    self.log_info(
                        f"[{self.pc_manager.pc_id}] Added client ICE candidate"
                    )
                else:
                    self.log_warning(f"Invalid candidate format: {candidate_str}")
            else:
                self.log_warning("No candidate string in data")

        except Exception as e:
            self.log_error(f"Error handling ICE candidate: {e}")

    async def _handle_poll(self, request):
        """处理信令消息轮询"""
        try:
            if self.signaling_messages:
                message = self.signaling_messages.popleft()
                return web.Response(
                    content_type="application/json", text=json.dumps(message)
                )
            else:
                return web.Response(content_type="application/json", text="")
        except Exception as e:
            self.log_error(f"Error handling poll: {e}")
            return web.Response(status=500, text=str(e))

    async def _handle_status(self, request):
        """返回服务器状态"""
        status = {
            "active_connections": len(self.peer_connections),
            "pending_messages": len(self.signaling_messages),
            "server_time": time.time(),
        }

        return web.Response(content_type="application/json", text=json.dumps(status))

    async def _cleanup_connections(self):
        """清理所有连接"""
        self.log_info("Cleaning up all connections...")

        cleanup_tasks = []
        for pc in list(self.peer_connections):
            cleanup_tasks.append(pc.close())

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        self.peer_connections.clear()
        self.signaling_messages.clear()
        self.log_info("All connections cleaned up")

    # ==================== 工具方法 ====================

    def send_to_data_channel(self, channel_label: str, message: dict) -> bool:
        """
        向指定数据通道发送消息

        Args:
            channel_label: 数据通道标签
            message: 要发送的消息字典

        Returns:
            bool: 发送是否成功
        """
        if not self.pc_manager:
            return False

        channel = self.pc_manager.data_channels.get(channel_label)
        if not channel:
            return False

        try:
            channel.send(json.dumps(message))
            return True
        except Exception as e:
            self.log_error(f"Failed to send message to channel {channel_label}: {e}")
            return False

    def log_info(self, message):
        """打印信息日志"""
        logging.info(f"\033[92m{message}\033[0m")

    def log_error(self, message):
        """打印错误日志"""
        logging.error(f"\033[91m{message}\033[0m")

    def log_warning(self, message):
        """打印警告日志"""
        logging.warning(f"\033[93m{message}\033[0m")

    async def _handle_poll(self, request):
        """处理ICE候选者轮询请求"""
        try:
            if not self.pc_manager or not self.pc_manager.pc:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"error": "No active connection"}),
                    status=404,
                )

            # 获取待发送的信令消息
            if self.signaling_messages:
                message = self.signaling_messages.popleft()
                self.log_info(
                    f"Sending signaling message via poll: {message.get('type', 'unknown')}"
                )
                return web.Response(
                    content_type="application/json", text=json.dumps(message)
                )
            else:
                # 没有待发送的消息，返回空响应
                return web.Response(
                    content_type="application/json", text=json.dumps({"type": "empty"})
                )

        except Exception as e:
            self.log_error(f"Error in poll handler: {e}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"error": str(e)}),
                status=500,
            )

    async def _handle_poll_with_client_id(self, request):
        """处理带客户端ID的ICE候选者轮询请求"""
        try:
            client_id = request.match_info.get("client_id", "")
            self.log_info(f"Poll request from client: {client_id}")

            if not self.pc_manager or not self.pc_manager.pc:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"error": "No active connection"}),
                    status=404,
                )

            # 获取待发送的信令消息
            if self.signaling_messages:
                message = self.signaling_messages.popleft()
                self.log_info(
                    f"Sending signaling message via poll to {client_id}: {message.get('type', 'unknown')}"
                )
                return web.Response(
                    content_type="application/json", text=json.dumps(message)
                )
            else:
                # 没有待发送的消息，返回空响应
                return web.Response(
                    content_type="application/json", text=json.dumps({"type": "empty"})
                )

        except Exception as e:
            self.log_error(f"Error in poll handler for client {client_id}: {e}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"error": str(e)}),
                status=500,
            )


class PeerConnectionManager:
    """PeerConnection管理器"""

    def __init__(self, server: WebRTCServerBase):
        self.server = server
        self.pc = None
        self.pc_id = None
        self.data_channels = {}
        self.message_count = 0

    async def create_peer_connection(self):
        """创建新的PeerConnection"""
        self.pc = RTCPeerConnection(self.server.configuration)
        self.pc_id = f"PC-{uuid.uuid4().hex[:8]}"
        self.server.peer_connections.add(self.pc)

        self._setup_event_handlers()

        self.server.log_info(f"[{self.pc_id}] Created new PeerConnection")
        return self.pc_id

    def _setup_event_handlers(self):
        """设置PeerConnection事件处理器"""

        @self.pc.on("connectionstatechange")
        async def on_connection_state_change():
            self.server.log_info(
                f"[{self.pc_id}] Connection state: {self.pc.connectionState}"
            )

            if self.pc.connectionState == "connected":
                self.server.log_info(
                    f"[{self.pc_id}] WebRTC connection fully established!"
                )
                await self.server.on_connection_established(self.pc_id, self.pc)
            elif self.pc.connectionState in ["failed", "closed"]:
                await self.cleanup()

        @self.pc.on("iceconnectionstatechange")
        def on_ice_connection_state_change():
            self.server.log_info(
                f"[{self.pc_id}] ICE connection state: {self.pc.iceConnectionState}"
            )

        @self.pc.on("icegatheringstatechange")
        def on_ice_gathering_state_change():
            self.server.log_info(
                f"[{self.pc_id}] ICE gathering state: {self.pc.iceGatheringState}"
            )

        @self.pc.on("icecandidate")
        def on_ice_candidate(candidate):
            if candidate:
                message = {
                    "type": "ice-candidate",
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                }
                self.server.signaling_messages.append(message)
                self.server.log_info(f"[{self.pc_id}] Generated ICE candidate")

        @self.pc.on("datachannel")
        def on_data_channel(channel):
            self.server.log_info(
                f"[{self.pc_id}] Received data channel: {channel.label}"
            )
            self._setup_data_channel(channel)

    def _setup_data_channel(self, channel):
        """设置数据通道事件处理器"""
        self.data_channels[channel.label] = channel

        @channel.on("open")
        async def on_open():
            self.server.log_info(
                f"[{self.pc_id}] Data channel '{channel.label}' opened"
            )
            await self.server.on_data_channel_opened(self.pc_id, channel.label, channel)

        @channel.on("close")
        async def on_close():
            self.server.log_info(
                f"[{self.pc_id}] Data channel '{channel.label}' closed"
            )
            if channel.label in self.data_channels:
                del self.data_channels[channel.label]
            await self.server.on_data_channel_closed(self.pc_id, channel.label)

        @channel.on("message")
        async def on_message(message):
            self.message_count += 1
            await self.server.on_data_channel_message(
                self.pc_id, channel.label, message
            )

    async def cleanup(self):
        """清理资源"""
        self.server.log_info(f"[{self.pc_id}] Cleaning up...")

        for channel in self.data_channels.values():
            channel.close()
        self.data_channels.clear()

        if self.pc:
            await self.pc.close()
            self.server.peer_connections.discard(self.pc)

        await self.server.on_connection_closed(self.pc_id)
        self.server.log_info(f"[{self.pc_id}] Cleanup completed")
