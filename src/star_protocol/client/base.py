"""客户端基类"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict
import websockets

from star_protocol.models import (
    Envelope,
    SystemPayload,
    MessagePayload,
    BroadcastPayload,
    ClientState,
)
from star_protocol.exceptions import (
    ConnectionError as StarConnectionError,
    InvalidStateError,
)
from star_protocol.client.core import (
    ConnectionManager,
    StateManager,
    MessagingManager,
    LifecycleManager,
)
from star_protocol.client.mixins import (
    MonitorableMixin,
    ReconnectableMixin,
)


logger = logging.getLogger(__name__)


class BaseClient(MonitorableMixin, ReconnectableMixin, ABC):
    """
    客户端抽象基类 - 重构版本

    使用核心模块和 Mixin 系统实现模块化架构：
    - ConnectionManager: WebSocket 连接管理
    - StateManager: 状态管理
    - MessagingManager: 消息发送和路由
    - LifecycleManager: 生命周期管理
    - MonitorableMixin: 可监控功能
    - ReconnectableMixin: 自动重连功能
    """

    def __init__(
        self,
        client_id: str,
        role: str,
        auto_reconnect: bool = False,
        reconnect_interval: float = 5.0,
        max_reconnect_attempts: int = 10,
        monitorable: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化客户端

        Args:
            client_id: 客户端唯一标识
            role: 客户端角色 (agent, environment, human, monitor)
            auto_reconnect: 是否自动重连
            reconnect_interval: 重连间隔（秒）
            max_reconnect_attempts: 最大重连次数
            monitorable: 是否启用监控功能
            logger: 日志记录器
        """
        self.client_id = client_id
        self.role = role
        self.logger = logger or logging.getLogger(f"{__name__}.{client_id}")

        # 初始化 Mixins
        super().__init__(
            auto_reconnect=auto_reconnect,
            reconnect_interval=reconnect_interval,
            max_reconnect_attempts=max_reconnect_attempts,
        )

        # 核心模块
        self._connection = ConnectionManager(self.logger)
        self._state = StateManager()
        self._messaging = MessagingManager(self._connection, self.logger)
        self._lifecycle = LifecycleManager(self)

        # 注册消息处理器
        self._messaging.register_handler("system", self._handle_system)
        self._messaging.register_handler("message", self._handle_message)
        self._messaging.register_handler("broadcast", self._handle_broadcast)

        # 监控功能
        self._monitorable = monitorable
        if monitorable and hasattr(self, "_handle_monitor"):
            # 如果启用了监控功能，注册 monitor 消息处理器
            self._messaging.register_handler("monitor", self._handle_monitor)

        # 保存 URL 用于重连
        self._url: Optional[str] = None

    # ==================== 公共 API ====================

    async def connect(self, url: str) -> None:
        """
        连接到 Hub Server

        Args:
            url: WebSocket URL (ws://host:port)

        Raises:
            StarConnectionError: 连接失败
        """
        self._url = url

        try:
            await self._connection.connect(url, self.role, self.client_id)
            old_state = self._state.state
            self._state.update_state(ClientState.HOME)

            # 触发连接回调
            await self.on_connected()

            # 监控钩子
            if self._monitorable:
                await self._on_state_change(old_state.value, ClientState.HOME.value)

        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            raise StarConnectionError(f"Failed to connect: {e}")

    async def disconnect(self) -> None:
        """断开连接"""
        # 禁用监控
        if self._monitorable:
            await self.disable_monitoring()

        # 断开主连接
        await self._connection.disconnect()

        old_state = self._state.state
        self._state.reset()

        # 触发断开回调
        await self.on_disconnected()

        # 监控钩子
        if self._monitorable:
            await self._on_state_change(old_state.value, ClientState.DISCONNECTED.value)

    async def start(self) -> None:
        """
        启动客户端（自动启动消息循环）

        使用示例：
            client = AgentClient("agent_01")
            await client.connect("ws://localhost:8765")
            await client.start()
            # 消息循环已在后台运行
            await client.join_environment("room_1")
            # ... 做其他事情 ...
            await client.stop()
        """
        await self._lifecycle.start()

    async def stop(self) -> None:
        """
        停止客户端（停止消息循环 + 断开连接）
        """
        await self._lifecycle.stop()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return await self._lifecycle.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        return await self._lifecycle.__aexit__(exc_type, exc_val, exc_tb)

    async def join_environment(self, env_id: str) -> None:
        """
        加入环境

        Args:
            env_id: 环境 ID

        Raises:
            InvalidStateError: 未连接或已在环境中
        """
        self._state.validate_join_environment()

        # 发送加入请求
        envelope = Envelope(
            type="system",
            sender=self.client_id,
            recipient="hub",
            payload=SystemPayload(
                type="ctrl", content={"op": "join", "env_id": env_id}
            ),
        )

        await self.send(envelope)

        # 更新状态
        old_state = self._state.state
        self._state.set_environment(env_id)

        self.logger.info(f"Joined environment: {env_id}")

        # 子类钩子（如 AgentClient 自动触发 discover）
        await self.on_joined_environment(env_id)

        # 监控钩子
        if self._monitorable:
            await self._on_state_change(old_state.value, self._state.state.value)

    async def leave_environment(self) -> None:
        """
        离开环境

        Raises:
            InvalidStateError: 不在环境中
        """
        self._state.validate_leave_environment()

        # 发送离开请求
        envelope = Envelope(
            type="system",
            sender=self.client_id,
            recipient="hub",
            payload=SystemPayload(type="ctrl", content={"op": "leave"}),
        )

        await self.send(envelope)

        # 更新状态
        old_state = self._state.state
        env_id = self._state.current_env
        self._state.set_environment(None)

        self.logger.info(f"Left environment: {env_id}")

        # 监控钩子
        if self._monitorable:
            await self._on_state_change(old_state.value, self._state.state.value)

    async def send(self, envelope: Envelope) -> None:
        """
        发送消息

        Args:
            envelope: 消息信封

        Raises:
            StarConnectionError: 未连接
        """
        await self._messaging.send_envelope(envelope)

        # 监控钩子
        if self._monitorable:
            await self._on_message_sent(envelope)

    async def run(self) -> None:
        """
        启动消息接收循环

        持续接收并处理消息，直到连接断开或调用 disconnect()
        """
        if not self._connection.is_connected():
            raise StarConnectionError("Not connected")

        self.logger.info("Message loop started")

        try:
            while self._lifecycle.is_running():
                try:
                    # 接收消息
                    message = await self._connection.receive_raw()

                    # 解析 Envelope
                    envelope = Envelope.model_validate_json(message)
                    self.logger.debug(f"Received: {envelope.type} <- {envelope.sender}")

                    # 监控钩子
                    if self._monitorable:
                        await self._on_message_received(envelope)

                    # 路由到处理器
                    await self._messaging.route_message(envelope)

                except StarConnectionError as e:
                    self.logger.warning(f"Connection closed or lost: {e}")

                    if self.auto_reconnect:
                        success = await self._attempt_reconnect()
                        if success:
                            continue
                    break

                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
                    error_dict = {"code": 500, "msg": str(e)}
                    await self.on_error(error_dict)

                    # 监控钩子
                    if self._monitorable:
                        await self._on_error(error_dict)
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            # traceback.print_exc()
        # finally:
        #     await self.disconnect()

    # ==================== 内部方法 ====================

    async def _handle_system(self, envelope: Envelope) -> None:
        """处理系统消息"""
        payload = envelope.payload

        if payload.type == "error":
            await self.on_error(payload.content)
        elif payload.type == "notify":
            content = payload.content  # TypedDict → 本质是 dict
            event = content.get("event", "") if isinstance(content, dict) else ""
            msg = content.get("msg", "") if isinstance(content, dict) else ""
            log_msg = msg if isinstance(msg, str) else str(msg)
            self.logger.info(f"System notify: {event} - {log_msg}")
            await self.on_system_notify(event, content if isinstance(content, dict) else {})

    async def _handle_message(self, envelope: Envelope) -> None:
        """处理业务消息 - 子类实现"""
        await self.on_message(envelope)

    async def _handle_broadcast(self, envelope: Envelope) -> None:
        """处理广播消息 - 子类实现"""
        await self.on_broadcast(envelope)

    # ==================== 属性 ====================

    @property
    def state(self) -> ClientState:
        """获取当前状态"""
        return self._state.state

    @property
    def current_env(self) -> Optional[str]:
        """获取当前环境"""
        return self._state.current_env

    # ==================== 抽象方法 ====================

    @abstractmethod
    async def on_message(self, envelope: Envelope) -> None:
        """
        处理业务消息

        Args:
            envelope: 消息信封
        """
        pass

    @abstractmethod
    async def on_broadcast(self, envelope: Envelope) -> None:
        """
        处理广播消息

        Args:
            envelope: 消息信封
        """
        pass

    # ==================== 可选回调 ====================

    async def on_connected(self) -> None:
        """连接成功回调"""
        pass

    async def on_disconnected(self) -> None:
        """断开连接回调"""
        pass

    async def on_joined_environment(self, env_id: str) -> None:
        """
        成功加入环境后的回调

        Args:
            env_id: 已加入的环境 ID
        """
        pass

    async def on_system_notify(self, event: str, content: dict) -> None:
        """
        Hub 系统通知回调（子类可重写）

        常见 event 值：
            - "connected"           连接成功
            - "joined"              加入环境成功确认
            - "left"                离开环境确认
            - "environment_closed"  所在环境已断开

        Args:
            event:   事件名称
            content: 完整通知内容 dict
        """
        pass

    async def on_error(self, error: Dict[str, Any]) -> None:
        """
        错误处理回调

        Args:
            error: 错误信息字典
        """
        self.logger.error(f"Error: {error}")

