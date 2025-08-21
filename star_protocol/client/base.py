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
        set_rich_mode()
        self.monitor = get_monitor(f"{client_info.type.value}_{client_info.id}")

        # 外层协议处理器 (message, error, heartbeat)
        self._protocol_handlers: Dict[
            str, Optional[Union[EventHandler, AsyncEventHandler]]
        ] = {"message": None, "error": None, "heartbeat": None}

        # 内层消息处理器 (action, outcome, event, stream)
        self._message_handlers: Dict[
            str, Dict[str, Union[EventHandler, AsyncEventHandler]]
        ] = {
            "action": {},  # key: action名称, value: handler
            "outcome": {},  # key: action_id或action名称, value: handler
            "event": {},  # key: event名称, value: handler
            "stream": {},  # key: stream名称, value: handler
        }

        # 日志
        self.logger = logging.getLogger(
            f"star_client.{client_info.type.value}.{client_info.id}"
        )

        # 内部状态
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None

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

            # 分发消息到处理器
            await self._dispatch_message(message)

        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    async def _dispatch_message(self, message: Message) -> None:
        """分发消息到相应的处理器"""
        message_type = message.type

        # 更新接收统计
        current_stats = getattr(self.monitor, "_stats", {})
        received_count = current_stats.get("已接收消息", 0) + 1
        self.monitor.update_stats(已接收消息=received_count)

        # 根据外层协议类型分发
        if message_type == "message":
            # 业务消息 - 调用message处理器，然后分发到内层处理器
            await self._handle_protocol_message(message)
        elif message_type == "error":
            # 错误消息 - 调用error处理器
            await self._handle_protocol_error(message)
        elif message_type == "heartbeat":
            # 心跳消息 - 调用heartbeat处理器
            await self._handle_protocol_heartbeat(message)
        else:
            # 未知消息类型
            self.logger.warning(f"Unhandled message type: {message_type}")
            self.monitor.warning(f"Unknown message type: {message_type}")

    async def _handle_protocol_message(self, message: Message) -> None:
        """处理外层message协议"""
        # 调用外层message处理器
        if self._protocol_handlers["message"]:
            await self._call_single_handler(self._protocol_handlers["message"], message)

        # 分发到内层处理器
        await self._dispatch_inner_message(message)

    async def _handle_protocol_error(self, message: Message) -> None:
        """处理外层error协议"""
        # 调用外层error处理器
        if self._protocol_handlers["error"]:
            await self._call_single_handler(self._protocol_handlers["error"], message)
        else:
            # 默认错误处理
            self.monitor.error(f"Received error: {message.payload}")

    async def _handle_protocol_heartbeat(self, message: Message) -> None:
        """处理外层heartbeat协议"""
        # 调用外层heartbeat处理器
        if self._protocol_handlers["heartbeat"]:
            await self._call_single_handler(
                self._protocol_handlers["heartbeat"], message
            )
        else:
            # 默认心跳处理
            self.monitor.debug("Received heartbeat")

    async def _dispatch_inner_message(self, message: Message) -> None:
        """分发内层消息到具体的处理器"""
        payload = message.payload

        # 确定内层消息类型
        inner_type = None
        if isinstance(payload, dict):
            inner_type = payload.get("type")
        elif hasattr(payload, "type"):
            inner_type = payload.type

        if not inner_type:
            self.logger.warning("Message payload missing type field")
            return

        # 根据内层类型分发
        if inner_type == "action":
            await self._handle_action_message(message, payload)
        elif inner_type == "outcome":
            await self._handle_outcome_message(message, payload)
        elif inner_type == "event":
            await self._handle_event_message(message, payload)
        elif inner_type == "stream":
            await self._handle_stream_message(message, payload)
        else:
            self.logger.warning(f"Unknown inner message type: {inner_type}")

    async def _handle_action_message(self, message: Message, payload: Any) -> None:
        """处理action消息"""
        action_name = None
        if isinstance(payload, dict):
            action_name = payload.get("action")
        elif hasattr(payload, "action"):
            action_name = payload.action

        if action_name and action_name in self._message_handlers["action"]:
            handler = self._message_handlers["action"][action_name]
            await self._call_single_handler(handler, message)

    async def _handle_outcome_message(self, message: Message, payload: Any) -> None:
        """处理outcome消息"""
        # 可以根据action_id或action名称查找handler
        action_id = None
        if isinstance(payload, dict):
            action_id = payload.get("id")
        elif hasattr(payload, "id"):
            action_id = payload.id

        if action_id and action_id in self._message_handlers["outcome"]:
            handler = self._message_handlers["outcome"][action_id]
            await self._call_single_handler(handler, message)

    async def _handle_event_message(self, message: Message, payload: Any) -> None:
        """处理event消息"""
        event_name = None
        if isinstance(payload, dict):
            event_name = payload.get("event")
        elif hasattr(payload, "event"):
            event_name = payload.event

        if event_name and event_name in self._message_handlers["event"]:
            handler = self._message_handlers["event"][event_name]
            await self._call_single_handler(handler, message)

    async def _handle_stream_message(self, message: Message, payload: Any) -> None:
        """处理stream消息"""
        stream_name = None
        if isinstance(payload, dict):
            stream_name = payload.get("stream")
        elif hasattr(payload, "stream"):
            stream_name = payload.stream

        if stream_name and stream_name in self._message_handlers["stream"]:
            handler = self._message_handlers["stream"][stream_name]
            await self._call_single_handler(handler, message)

    async def _call_single_handler(
        self, handler: Union[EventHandler, AsyncEventHandler], message: Message
    ) -> None:
        """调用单个处理器"""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(message)
            else:
                handler(message)
        except Exception as e:
            self.logger.error(f"Error in message handler: {e}")

    # 外层协议处理器注册方法
    def set_message_handler(
        self, handler: Union[EventHandler, AsyncEventHandler]
    ) -> None:
        """设置message协议处理器"""
        self._protocol_handlers["message"] = handler

    def set_error_handler(
        self, handler: Union[EventHandler, AsyncEventHandler]
    ) -> None:
        """设置error协议处理器"""
        self._protocol_handlers["error"] = handler

    def set_heartbeat_handler(
        self, handler: Union[EventHandler, AsyncEventHandler]
    ) -> None:
        """设置heartbeat协议处理器"""
        self._protocol_handlers["heartbeat"] = handler

    # 内层消息处理器注册方法
    def add_action_handler(
        self, action: str, handler: Union[EventHandler, AsyncEventHandler]
    ) -> None:
        """添加action处理器"""
        self._message_handlers["action"][action] = handler

    def add_outcome_handler(
        self, key: str, handler: Union[EventHandler, AsyncEventHandler]
    ) -> None:
        """添加outcome处理器 (key可以是action_id或action名称)"""
        self._message_handlers["outcome"][key] = handler

    def add_event_handler(
        self, event: str, handler: Union[EventHandler, AsyncEventHandler]
    ) -> None:
        """添加event处理器"""
        self._message_handlers["event"][event] = handler

    def add_stream_handler(
        self, stream: str, handler: Union[EventHandler, AsyncEventHandler]
    ) -> None:
        """添加stream处理器"""
        self._message_handlers["stream"][stream] = handler

    # 移除处理器方法
    def remove_action_handler(self, action: str) -> None:
        """移除action处理器"""
        self._message_handlers["action"].pop(action, None)

    def remove_outcome_handler(self, key: str) -> None:
        """移除outcome处理器"""
        self._message_handlers["outcome"].pop(key, None)

    def remove_event_handler(self, event: str) -> None:
        """移除event处理器"""
        self._message_handlers["event"].pop(event, None)

    def remove_stream_handler(self, stream: str) -> None:
        """移除stream处理器"""
        self._message_handlers["stream"].pop(stream, None)

    # 内层消息处理器注册表
    def add_action_handlers(
        self, actions: Dict[str, Union[EventHandler, AsyncEventHandler]]
    ) -> None:
        """添加action处理器"""
        self._message_handlers["action"].update(actions)

    # 装饰器方法
    def on_action(self, action: str):
        """action处理器装饰器"""

        def decorator(func: Union[EventHandler, AsyncEventHandler]):
            self.add_action_handler(action, func)
            return func

        return decorator

    def on_outcome(self, key: str):
        """outcome处理器装饰器"""

        def decorator(func: Union[EventHandler, AsyncEventHandler]):
            self.add_outcome_handler(key, func)
            return func

        return decorator

    def on_event(self, event: str):
        """event处理器装饰器"""

        def decorator(func: Union[EventHandler, AsyncEventHandler]):
            self.add_event_handler(event, func)
            return func

        return decorator

    def on_stream(self, stream: str):
        """stream处理器装饰器"""

        def decorator(func: Union[EventHandler, AsyncEventHandler]):
            self.add_stream_handler(stream, func)
            return func

        return decorator

    def on_message(self):
        """message协议处理器装饰器"""

        def decorator(func: Union[EventHandler, AsyncEventHandler]):
            self.set_message_handler(func)
            return func

        return decorator

    def on_error(self):
        """error协议处理器装饰器"""

        def decorator(func: Union[EventHandler, AsyncEventHandler]):
            self.set_error_handler(func)
            return func

        return decorator

    def on_heartbeat(self):
        """heartbeat协议处理器装饰器"""

        def decorator(func: Union[EventHandler, AsyncEventHandler]):
            self.set_heartbeat_handler(func)
            return func

        return decorator

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

    async def send_heartbeat(self) -> bool:
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
