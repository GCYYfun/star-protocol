"""
Star Protocol 客户端基类

提供 WebSocket 客户端的基础功能
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from ..protocol.types import ClientType
from ..protocol import (
    ClientInfo,
    Message,
    MessageBuilder,
    MessageParser,
    MessageValidationService,
    ValidationError,
)
from ..monitor import get_monitor, BaseMonitor, set_rich_mode


# 事件处理器类型
EventHandler = Callable[[Message], None]
AsyncEventHandler = Callable[[Message], Any]  # 支持异步


class BaseStarClient(ABC):
    """Star Protocol 客户端基类"""

    def __init__(
        self,
        client_info: ClientInfo,
        validate_messages: bool = True,
        base_url: str = "ws://localhost",
        port: int = 8000,
    ):
        self.server_url = f"{base_url}:{port}"
        self.client_info = client_info
        self.session: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False

        # 消息验证
        self.validator = (
            MessageValidationService(enable_permission_check=False)
            if validate_messages
            else None
        )

        # 监控器
        self.monitor = get_monitor(f"{client_info.type.value}_{client_info.id}")

        # 内部状态
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None

        # 初始化消息处理器
        self._setup_message_handlers()

    @abstractmethod
    def get_connection_url(self) -> str:
        """获取连接 URL - 子类必须实现"""
        pass

    async def connect(self) -> bool:
        """连接到服务器"""
        if self.is_connected:
            self.monitor.warning("Already connected")
            return True

        try:
            url = self.get_connection_url()
            self.monitor.info(f"Connecting to {url}")
            self.monitor.set_status("连接中")

            self.session = await websockets.connect(url)
            self.is_connected = True
            self._running = True

            # 启动消息接收任务
            self._receive_task = asyncio.create_task(self._receive_messages())

            self.monitor.success("Connected successfully")
            self.monitor.set_status("已连接")
            self.monitor.update_stats(连接状态="已连接", 服务器地址=url)

            await self._on_connected()

            return True

        except Exception as e:
            self.monitor.error(f"Connection failed: {e}")
            self.monitor.set_status("连接失败")
            self.is_connected = False
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if not self.is_connected:
            return

        self.monitor.info("Disconnecting...")
        self.monitor.set_status("断开连接中")
        self._running = False

        # 取消接收任务
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # 关闭 session 连接
        if self.session:
            await self.session.close()
            self.session = None

        self.is_connected = False
        await self._on_disconnected()
        self.monitor.info("Disconnected")
        self.monitor.set_status("已断开")
        self.monitor.update_stats(连接状态="已断开")

    async def send_message(
        self,
        message_type: str,
        payload: Any,
        recipient: Optional[ClientInfo] = None,
        validate: bool = True,
    ) -> bool:
        """发送消息"""
        if not self.is_connected or not self.session:
            self.monitor.error("Not connected")
            return False

        try:
            # 设置默认接收者为 Hub
            if recipient is None:
                recipient = ClientInfo(id="hub", type=ClientType.HUB)

            # 创建消息
            message = Message(
                type=message_type,
                sender=self.client_info,
                recipient=recipient,
                payload=payload,
            )

            # 验证消息（如果启用）
            if validate and self.validator:
                try:
                    self.validator.validate_message(message.to_dict())
                except ValidationError as e:
                    self.monitor.error(f"Message validation failed: {e}")
                    return False

            # 发送消息
            message_json = MessageParser.to_json(message)
            await self.session.send(message_json)

            self.monitor.debug(f"Sent {message.type} message to {recipient.id}")
            # 更新统计信息
            current_stats = getattr(self.monitor, "_stats", {})
            sent_count = current_stats.get("已发送消息", 0) + 1
            self.monitor.update_stats(已发送消息=sent_count)

            return True

        except Exception as e:
            self.monitor.error(f"Failed to send message: {e}")
            return False

    async def _receive_messages(self) -> None:
        """接收消息的后台任务"""
        while self._running and self.session:
            try:
                message_json = await self.session.recv()
                await self._handle_received_message(message_json)

            except ConnectionClosed:
                self.monitor.info("Connection closed by server")
                break
            except WebSocketException as e:
                self.monitor.error(f"Session error: {e}")
                break
            except Exception as e:
                self.monitor.error(f"Error receiving message: {e}")
                await asyncio.sleep(0.1)  # 避免紧密循环

        # 连接断开
        if self._running:
            self.is_connected = False
            await self._on_disconnected()

    async def _handle_received_message(self, message_json: str) -> None:
        """处理接收到的消息"""
        try:
            # 解析消息
            message = MessageParser.parse_json(message_json)

            self.monitor.debug(
                f"Received message: {message.type} from {message.sender.id}"
            )

            # 验证消息（如果启用）
            if self.validator:
                try:
                    self.validator.validate_message(message.to_dict())
                except ValidationError as e:
                    self.monitor.warning(f"Received invalid message: {e}")
                    return

            # 更新接收统计
            current_stats = getattr(self.monitor, "_stats", {})
            received_count = current_stats.get("已接收消息", 0) + 1
            self.monitor.update_stats(已接收消息=received_count)

            # 分发消息到处理器
            await self._dispatch_message(message)

        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    async def _dispatch_message(self, message: Message) -> None:
        """分发消息到相应的处理器"""
        message_type = message.type

        # 根据外层协议类型分发
        if message_type == "message":
            await self.on_message(message)
        elif message_type == "error":
            await self.on_error(message)
        elif message_type == "heartbeat":
            await self.on_heartbeat(message)
        else:
            self.monitor.warning(f"Unknown message type: {message_type}")

    # -------- 协议处理方法（子类应该覆盖） --------
    async def on_message(self, message: Message) -> None:
        """
        处理 message 协议

        子类应该覆盖此方法来实现自定义的消息处理逻辑
        """
        self.monitor.info(f"Received message from {message.sender.id}")

    async def on_error(self, message: Message) -> None:
        """
        处理 error 协议

        子类应该覆盖此方法来实现自定义的错误处理逻辑
        """
        self.monitor.error(f"Received error: {message.payload}")

    async def on_heartbeat(self, message: Message) -> None:
        """
        处理 heartbeat 协议

        子类应该覆盖此方法来实现自定义的心跳处理逻辑
        """
        self.monitor.debug("Received heartbeat")

    # -------- 消息处理器设置（子类可以覆盖） --------
    def _setup_message_handlers(self) -> None:
        """
        设置消息处理器

        子类可以覆盖此方法来设置自定义的消息处理器
        """
        pass

    # 生命周期钩子
    async def _on_connected(self) -> None:
        """连接成功后的回调"""
        pass

    async def _on_disconnected(self) -> None:
        """断开连接后的回调"""
        pass

    # 上下文管理器支持
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"<{self.__class__.__name__} {self.client_info.id} ({status})>"

    async def heartbeat(self) -> bool:
        """发送心跳消息"""
        if not self.is_connected or not self.session:
            self.monitor.error("Not connected")
            return False

        try:
            heartbeat_message = Message(
                type="heartbeat",
                sender=self.client_info,
                recipient=ClientInfo(id="hub", type=ClientType.HUB),
                payload={},
            )
            message_json = MessageParser.to_json(heartbeat_message)
            await self.session.send(message_json)

            self.monitor.debug("Sent heartbeat message")
            return True

        except Exception as e:
            self.monitor.error(f"Failed to send heartbeat: {e}")
            return False
