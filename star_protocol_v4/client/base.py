"""Star Protocol 客户端基类"""

import asyncio
import inspect
import time
import websockets
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from ..protocol import (
    Envelope,
    Message,
    EnvelopeType,
    MessageType,
    ClientType,
    ClientInfo,
)
from ..protocol import ActionMessage, OutcomeMessage, EventMessage, StreamMessage
from ..utils import get_logger


@dataclass
class MessageContext:
    """消息上下文，包含消息和相关元数据"""

    message: Message
    sender: Optional[str] = None
    recipient: Optional[str] = None
    envelope_type: Optional[EnvelopeType] = None
    timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseClient:
    """Star Protocol 客户端基类

    提供7个固定事件处理方法和4个装饰器用于用户自定义处理。

    固定事件：
    - on_heartbeat: 心跳事件
    - on_message: 消息事件（会进一步分发到具体消息类型）
    - on_error: 错误事件
    - on_action: ACTION 消息事件
    - on_outcome: OUTCOME 消息事件
    - on_event: EVENT 消息事件
    - on_stream: STREAM 消息事件

    用户装饰器：
    - @action(): 注册 ACTION 消息处理器
    - @outcome(): 注册 OUTCOME 消息处理器
    - @event(): 注册 EVENT 消息处理器
    - @stream(): 注册 STREAM 消息处理器
    """

    def __init__(
        self,
        client_id: str,
        client_type: ClientType,
        hub_url: str,
        env_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.client_info = ClientInfo(
            client_id=client_id,
            client_type=client_type,
            env_id=env_id,
            metadata=metadata or {},
        )
        self.hub_url = hub_url
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.connected = False

        # 便捷属性
        self.client_id = client_id
        self.client_type = client_type
        self.env_id = env_id
        self.metadata = metadata or {}

        # 上下文管理器
        from .context import ClientContext

        self.context = ClientContext(client_id=client_id)

        # 用户自定义处理器（通过装饰器注册）
        self._action_handlers: List[Callable] = []
        self._outcome_handlers: List[Callable] = []
        self._event_handlers: List[Callable] = []
        self._stream_handlers: List[Callable] = []

        # 日志器
        self.logger = get_logger("star_protocol.client")

        # 监控（可选）
        self._metrics_enabled = False
        self._metrics_collector = None

    # ===========================================
    # 4个装饰器 - 用户自定义处理器注册
    # ===========================================

    def action(self, action_name: Optional[str] = None):
        """ACTION 消息处理器装饰器

        Args:
            action_name: 可选的动作名称过滤，如果指定则只处理该动作

        Usage:
            @client.action()
            async def handle_action(message: ActionMessage):
                print(f"收到动作: {message.action}")

            @client.action("move")
            async def handle_move(message: ActionMessage):
                print(f"收到移动动作: {message.parameters}")
        """

        def decorator(func: Callable):
            # 检查函数签名以决定传递什么参数
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())

            # 包装函数以支持过滤和上下文传递
            async def wrapper(ctx: MessageContext):
                message = ctx.message
                if action_name is None or message.action == action_name:
                    if asyncio.iscoroutinefunction(func):
                        # 根据参数签名决定传递什么
                        if len(params) == 1:
                            # 只接受 message 参数（向后兼容）
                            await func(message)
                        elif len(params) == 2 and "ctx" in params:
                            # 接受 message 和 ctx 参数
                            await func(message, ctx)
                        else:
                            # 默认只传递 message
                            await func(message)
                    else:
                        if len(params) == 1:
                            func(message)
                        elif len(params) == 2 and "ctx" in params:
                            func(message, ctx)
                        else:
                            func(message)

            self._action_handlers.append(wrapper)
            return func

        return decorator

    def outcome(self, action_id: Optional[str] = None):
        """OUTCOME 消息处理器装饰器

        Args:
            action_id: 可选的动作ID过滤，如果指定则只处理该动作的结果

        Usage:
            @client.outcome()
            async def handle_outcome(message: OutcomeMessage):
                print(f"收到结果: {message.status}")
        """

        def decorator(func: Callable):
            async def wrapper(message: OutcomeMessage):
                if action_id is None or message.action_id == action_id:
                    if asyncio.iscoroutinefunction(func):
                        await func(message)
                    else:
                        func(message)

            self._outcome_handlers.append(wrapper)
            return func

        return decorator

    def event(self, event_name: Optional[str] = None):
        """EVENT 消息处理器装饰器

        Args:
            event_name: 可选的事件名称过滤，如果指定则只处理该事件

        Usage:
            @client.event()
            async def handle_event(message: EventMessage):
                print(f"收到事件: {message.event}")

            @client.event("agent_moved")
            async def handle_move_event(message: EventMessage):
                print(f"Agent移动事件: {message.data}")
        """

        def decorator(func: Callable):
            async def wrapper(message: EventMessage):
                if event_name is None or message.event == event_name:
                    if asyncio.iscoroutinefunction(func):
                        await func(message)
                    else:
                        func(message)

            self._event_handlers.append(wrapper)
            return func

        return decorator

    def stream(self, stream_name: Optional[str] = None):
        """STREAM 消息处理器装饰器

        Args:
            stream_name: 可选的流名称过滤，如果指定则只处理该流

        Usage:
            @client.stream()
            async def handle_stream(message: StreamMessage):
                print(f"收到流数据: {message.stream}")

            @client.stream("video_feed")
            async def handle_video(message: StreamMessage):
                print(f"视频流: {message.chunk}")
        """

        def decorator(func: Callable):
            async def wrapper(message: StreamMessage):
                if stream_name is None or message.stream == stream_name:
                    if asyncio.iscoroutinefunction(func):
                        await func(message)
                    else:
                        func(message)

            self._stream_handlers.append(wrapper)
            return func

        return decorator

    # ===========================================
    # 7个固定事件处理方法
    # ===========================================

    async def on_heartbeat(self, envelope: Envelope) -> None:
        """处理心跳事件（默认实现）

        Args:
            envelope: 心跳信封
        """
        self.logger.debug(f"收到心跳: {envelope.sender}")
        # 默认实现：记录日志
        # 子类可以重写此方法

    async def on_error(self, envelope: Envelope) -> None:
        """处理错误事件（默认实现）

        Args:
            envelope: 错误信封
        """
        self.logger.warning(f"收到错误: {envelope.sender}")
        # 默认实现：记录日志
        # 子类可以重写此方法

    async def on_message(self, envelope: Envelope) -> None:
        """处理消息事件（默认实现）

        此方法会进一步分发到具体的消息类型处理方法。

        Args:
            envelope: 消息信封
        """
        message = envelope.message

        # 根据消息类型分发到具体处理方法
        if isinstance(message, ActionMessage):
            await self.on_action(message, envelope)
        elif isinstance(message, OutcomeMessage):
            # 处理 outcome 响应，尝试匹配上下文
            await self._handle_outcome_response(message)
            await self.on_outcome(message)
        elif isinstance(message, EventMessage):
            # 处理 event 响应，尝试匹配上下文
            await self._handle_event_response(message)
            await self.on_event(message)
        elif isinstance(message, StreamMessage):
            await self.on_stream(message)
        else:
            self.logger.warning(f"未知消息类型: {type(message)}")

    async def on_action(self, message: ActionMessage, envelope: Envelope) -> None:
        """处理 ACTION 消息事件（默认实现）

        Args:
            message: ACTION 消息
            envelope: 消息信封（包含发送者等信息）
        """
        self.logger.debug(f"收到动作: {message.action} from {envelope.sender}")

        # 创建消息上下文
        ctx = MessageContext(
            message=message,
            sender=envelope.sender,
            recipient=envelope.recipient,
            envelope_type=envelope.envelope_type,
            timestamp=time.time(),
        )

        # 调用用户注册的处理器
        for handler in self._action_handlers:
            try:
                await handler(ctx)
            except Exception as e:
                self.logger.error(f"ACTION 处理器出错: {e}")

    async def on_outcome(self, message: OutcomeMessage) -> None:
        """处理 OUTCOME 消息事件（默认实现）

        Args:
            message: OUTCOME 消息
        """
        self.logger.debug(f"收到结果: {message.action_id} - {message.status}")

        # 调用用户注册的处理器
        for handler in self._outcome_handlers:
            try:
                await handler(message)
            except Exception as e:
                self.logger.error(f"OUTCOME 处理器出错: {e}")

    async def on_event(self, message: EventMessage) -> None:
        """处理 EVENT 消息事件（默认实现）

        Args:
            message: EVENT 消息
        """
        self.logger.debug(f"收到事件: {message.event}")

        # 调用用户注册的处理器
        for handler in self._event_handlers:
            try:
                await handler(message)
            except Exception as e:
                self.logger.error(f"EVENT 处理器出错: {e}")

    async def on_stream(self, message: StreamMessage) -> None:
        """处理 STREAM 消息事件（默认实现）

        Args:
            message: STREAM 消息
        """
        self.logger.debug(f"收到流数据: {message.stream} #{message.sequence}")

        # 调用用户注册的处理器
        for handler in self._stream_handlers:
            try:
                await handler(message)
            except Exception as e:
                self.logger.error(f"STREAM 处理器出错: {e}")

    # ===========================================
    # 连接和消息发送
    # ===========================================

    async def connect(self) -> None:
        """连接到 Hub"""
        try:
            self.logger.info(f"连接到 Hub: {self.hub_url}")
            self.websocket = await websockets.connect(self.hub_url)
            self.connected = True

            # 启动上下文管理器
            await self.context.start()

            # 发送 connect event 作为第一条消息
            await self._send_connect_event()

            # 启动消息监听
            asyncio.create_task(self.receive_loop())

            self.logger.info("连接成功")

        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            self.connected = False
            raise

    async def _send_connect_event(self) -> None:
        """发送连接事件作为第一条消息"""
        from ..protocol import EventMessage, Envelope, EnvelopeType

        # 获取客户端身份信息
        client_info = self._get_client_identity()

        # 创建 connect event
        connect_event = EventMessage(event="connect", data=client_info)

        # 创建信封
        envelope = Envelope(
            envelope_type=EnvelopeType.MESSAGE,
            sender=self.client_id,
            recipient="hub",
            message=connect_event,
        )

        # 发送连接事件
        json_str = envelope.to_json()
        await self.websocket.send(json_str)
        self.logger.debug(f"已发送 connect event: {client_info}")

    def _get_client_identity(self) -> dict:
        """获取客户端身份信息 - 子类需要重写此方法

        Returns:
            包含客户端身份信息的字典
        """
        return {"client_type": "unknown", "env_id": None, "metadata": {}}

    async def disconnect(self) -> None:
        """断开连接"""
        if self.connected and self.websocket:
            try:
                # 停止上下文管理器
                await self.context.stop()

                # 关闭 WebSocket
                await self.websocket.close()

            except Exception as e:
                self.logger.error(f"断开连接时出错: {e}")
            finally:
                self.connected = False
                self.websocket = None
                self.logger.info("连接已断开")

    async def send_envelope(self, envelope: Envelope) -> None:
        """发送信封消息

        Args:
            envelope: 要发送的信封
        """
        if not self.connected or not self.websocket:
            raise RuntimeError("客户端未连接")

        try:
            json_str = envelope.to_json()
            await self.websocket.send(json_str)

            self.logger.debug(f"发送信封: {envelope.envelope_type.value}")

            # 记录指标（如果启用）
            if self._metrics_enabled and self._metrics_collector:
                await self._metrics_collector.record_envelope_sent(envelope)

        except Exception as e:
            self.logger.error(f"发送信封失败: {e}")
            raise

    async def send_message(self, message: Message, recipient: str) -> None:
        """发送消息（包装在信封中）

        Args:
            message: 要发送的消息
            recipient: 目标客户端ID
        """
        envelope = Envelope(
            envelope_type=EnvelopeType.MESSAGE,
            sender=self.client_info.client_id,
            recipient=recipient,
            message=message,
        )
        await self.send_envelope(envelope)

    async def receive_loop(self) -> None:
        """消息监听循环"""
        try:
            async for raw_message in self.websocket:
                try:
                    envelope = Envelope.from_json(raw_message)
                    await self._handle_envelope(envelope)

                except Exception as e:
                    self.logger.error(f"处理消息失败: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.info("WebSocket 连接已关闭")
            self.connected = False
        except Exception as e:
            self.logger.error(f"消息循环出错: {e}")
            self.connected = False

    async def _handle_envelope(self, envelope: Envelope) -> None:
        """处理接收到的信封"""
        self.logger.debug(f"收到信封: {envelope.envelope_type.value}")

        # 记录指标（如果启用）
        if self._metrics_enabled and self._metrics_collector:
            await self._metrics_collector.record_envelope_received(envelope)

        # 根据信封类型分发到相应的处理方法
        try:
            if envelope.envelope_type == EnvelopeType.HEARTBEAT:
                await self.on_heartbeat(envelope)
            elif envelope.envelope_type == EnvelopeType.MESSAGE:
                await self.on_message(envelope)
            elif envelope.envelope_type == EnvelopeType.ERROR:
                await self.on_error(envelope)
            else:
                self.logger.warning(f"未知信封类型: {envelope.envelope_type}")

        except Exception as e:
            self.logger.error(f"处理信封时出错: {e}")

    # ===========================================
    # 监控支持
    # ===========================================

    def enable_metrics(self, collector=None) -> None:
        """启用监控

        Args:
            collector: 指标收集器，如果为 None 则使用默认收集器
        """
        self._metrics_enabled = True
        if collector is None:
            # 导入默认收集器
            from ..monitor import MetricsCollector

            self._metrics_collector = MetricsCollector()
        else:
            self._metrics_collector = collector

    def disable_metrics(self) -> None:
        """禁用监控"""
        self._metrics_enabled = False
        self._metrics_collector = None

    # ===========================================
    # 上下文响应处理
    # ===========================================

    async def _handle_outcome_response(self, outcome: OutcomeMessage) -> None:
        """处理 outcome 响应，匹配到对应的 action 上下文

        Args:
            outcome: outcome 消息
        """
        # 尝试从 outcome 中提取对应的 action_id
        action_id = getattr(outcome, "action_id", None)
        if not action_id:
            # 如果没有直接的 action_id，尝试从 data 中提取
            if hasattr(outcome, "data") and isinstance(outcome.data, dict):
                action_id = outcome.data.get("action_id") or outcome.data.get(
                    "request_id"
                )

        if action_id:
            # 尝试完成对应的上下文
            success = self.context.complete_request(action_id, outcome)
            if success:
                self.logger.debug(f"匹配到 action 上下文: {action_id}")
            else:
                self.logger.debug(f"未找到匹配的 action 上下文: {action_id}")

    async def _handle_event_response(self, event: EventMessage) -> None:
        """处理 event 响应，匹配到对应的上下文

        Args:
            event: event 消息
        """
        # 尝试从 event 中提取对应的请求ID
        request_id = None
        if hasattr(event, "data") and isinstance(event.data, dict):
            request_id = event.data.get("request_id") or event.data.get("action_id")

        # 特殊处理一些系统事件
        if event.event == "client_registered":
            # 处理客户端注册确认
            self.logger.debug("收到客户端注册确认")
            return
        elif event.event == "agent_joined":
            # 处理 agent 加入通知
            self.logger.debug(f"收到 agent 加入通知: {event.data}")
            return

        if request_id:
            # 尝试完成对应的上下文
            success = self.context.complete_request(request_id, event)
            if success:
                self.logger.debug(f"匹配到 event 上下文: {request_id}")

    # ===========================================
    # 便捷的发送方法（带上下文管理）
    # ===========================================

    async def send_action_with_context(
        self,
        action: str,
        params: Dict[str, Any],
        recipient: str,
        timeout: Optional[float] = None,
        wait_for_outcome: bool = True,
    ) -> Any:
        """发送 action 并等待 outcome（带上下文管理）

        Args:
            action: 动作名称
            params: 动作参数
            recipient: 接收者
            timeout: 超时时间
            wait_for_outcome: 是否等待 outcome

        Returns:
            如果 wait_for_outcome=True，返回 outcome 消息；否则返回 request_id
        """
        from ..protocol import ActionMessage, Envelope, EnvelopeType

        # 创建上下文
        context_item = self.context.create_request_context(
            request_type="action",
            request_data={"action": action, "params": params, "recipient": recipient},
            timeout=timeout,
        )

        request_id = context_item.request_id

        # 创建 action 消息
        action_message = ActionMessage(
            action=action,
            parameters=params,
            action_id=request_id,  # 使用 request_id 作为 action_id
        )

        # 创建信封并发送
        envelope = Envelope(
            envelope_type=EnvelopeType.MESSAGE,
            sender=self.client_id,
            recipient=recipient,
            message=action_message,
        )

        await self.send_envelope(envelope)
        self.logger.debug(f"发送 action: {action} (ID: {request_id})")

        if wait_for_outcome:
            # 等待响应
            try:
                outcome = await self.context.wait_for_response(request_id, timeout)
                return outcome
            except asyncio.TimeoutError:
                self.logger.warning(f"Action {action} (ID: {request_id}) 超时")
                raise
        else:
            return request_id

    async def send_event_with_context(
        self,
        event: str,
        data: Dict[str, Any],
        recipient: str,
        timeout: Optional[float] = None,
        wait_for_response: bool = False,
    ) -> Any:
        """发送 event（带上下文管理）

        Args:
            event: 事件名称
            data: 事件数据
            recipient: 接收者
            timeout: 超时时间
            wait_for_response: 是否等待响应

        Returns:
            如果 wait_for_response=True，返回响应消息；否则返回 request_id
        """
        from ..protocol import EventMessage, Envelope, EnvelopeType

        # 创建上下文（如果需要等待响应）
        request_id = None
        if wait_for_response:
            context_item = self.context.create_request_context(
                request_type="event",
                request_data={"event": event, "data": data, "recipient": recipient},
                timeout=timeout,
            )
            request_id = context_item.request_id
            # 将 request_id 添加到 data 中
            data = {**data, "request_id": request_id}

        # 创建 event 消息
        event_message = EventMessage(event=event, data=data)

        # 创建信封并发送
        envelope = Envelope(
            envelope_type=EnvelopeType.MESSAGE,
            sender=self.client_id,
            recipient=recipient,
            message=event_message,
        )

        await self.send_envelope(envelope)
        self.logger.debug(f"发送 event: {event} (ID: {request_id})")

        if wait_for_response and request_id:
            # 等待响应
            try:
                response = await self.context.wait_for_response(request_id, timeout)
                return response
            except asyncio.TimeoutError:
                self.logger.warning(f"Event {event} (ID: {request_id}) 超时")
                raise
        else:
            return request_id

    def get_context_stats(self) -> Dict[str, Any]:
        """获取上下文统计信息"""
        return self.context.get_stats()
