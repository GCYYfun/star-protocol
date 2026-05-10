"""Agent 客户端"""

import asyncio
import time
from typing import Any, Dict, List, Optional
import logging

from star_protocol.client.base import BaseClient
from star_protocol.models import Envelope, MessagePayload, SystemPayload, gen_id
from star_protocol.models.payloads import ToolDefinition


class AgentClient(BaseClient):
    """
    Agent 客户端

    用于智能体（AI Agent、机器人等）与环境交互。
    主要功能：
    - 发送动作（action）到环境
    - 接收环境返回的结果（outcome）
    - 接收环境事件（event）
    """

    def __init__(
        self,
        client_id: str,
        auto_reconnect: bool = True,
        monitorable: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化 Agent 客户端

        Args:
            client_id: Agent 唯一标识
            auto_reconnect: 是否自动重连
            monitorable: 是否启用监控功能
            logger: 日志记录器
        """
        super().__init__(
            client_id=client_id,
            role="agent",
            auto_reconnect=auto_reconnect,
            monitorable=monitorable,
            logger=logger,
        )

        # 工具清单缓存（join 后由 discover 填充）
        self._tools: List[ToolDefinition] = []

        # 环境生命周期管理
        self._pending_env: Optional[str] = None          # 正在尝试加入的环境 ID
        self._join_confirmed = asyncio.Event()            # Hub 确认 join 成功
        self._join_failed = asyncio.Event()               # Hub 返回 join 失败 (404)
        self._auto_rejoin: bool = False                   # 是否开启自动重连环境
        self._rejoin_timeout: float = 60.0               # 自动重连的总超时
        self._rejoin_interval: float = 3.0               # 重试间隔
        self._rejoin_task: Optional[asyncio.Task] = None # 自动重连后台任务

    # ------------------------------------------------------------------
    # Environment Lifecycle
    # ------------------------------------------------------------------

    def enable_auto_rejoin(
        self, timeout: float = 60.0, retry_interval: float = 3.0
    ) -> None:
        """
        开启自动重连环境功能。

        当所在环境断开时，Agent 会在后台持续尝试重新加入，
        直到成功或超时。

        Args:
            timeout:        尝试重连的总时长（秒），0 表示无限重试
            retry_interval: 每次尝试的间隔（秒）
        """
        self._auto_rejoin = True
        self._rejoin_timeout = timeout
        self._rejoin_interval = retry_interval
        self.logger.info(
            f"Auto-rejoin enabled (timeout={timeout}s, interval={retry_interval}s)"
        )

    async def join_with_retry(
        self,
        env_id: str,
        timeout: float = 30.0,
        retry_interval: float = 2.0,
    ) -> None:
        """
        带重试的加入环境。

        适用场景：
            1. 首次开机：env 可能还未就绪，Agent 等待它启动
            2. 自动重连循环内部使用

        Args:
            env_id:         目标环境 ID
            timeout:        总超时（秒），0 表示无限
            retry_interval: 重试间隔（秒）

        Raises:
            TimeoutError: 超时后仍未成功加入
        """
        deadline = time.monotonic() + timeout if timeout > 0 else float("inf")
        attempt = 0

        while time.monotonic() < deadline:
            attempt += 1
            self.logger.info(f"Joining '{env_id}' (attempt {attempt})...")

            # 如果已在该环境，直接成功
            if self.current_env == env_id:
                return

            # 如果在其他环境，先离开
            if self.current_env and self.current_env != env_id:
                await self.leave_environment()

            # 重置信号
            self._join_confirmed.clear()
            self._join_failed.clear()
            self._pending_env = env_id

            # 发送 join ctrl（不经过乐观设置状态的 join_environment）
            try:
                envelope = Envelope(
                    type="system",
                    sender=self.client_id,
                    recipient="hub",
                    payload=SystemPayload(
                        type="ctrl", content={"op": "join", "env_id": env_id}
                    ),
                )
                await self.send(envelope)
            except Exception as e:
                self.logger.warning(f"Send join failed: {e}")
                self._pending_env = None
                await asyncio.sleep(min(retry_interval, deadline - time.monotonic()))
                continue

            # 等待 Hub 响应（confirmed / failed / timeout）
            wait_secs = min(retry_interval, max(0, deadline - time.monotonic()))
            try:
                done, _ = await asyncio.wait(
                    [
                        asyncio.ensure_future(self._join_confirmed.wait()),
                        asyncio.ensure_future(self._join_failed.wait()),
                    ],
                    timeout=wait_secs,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except Exception:
                done = set()

            self._pending_env = None

            if self._join_confirmed.is_set():
                # Hub 已确认，更新本地状态
                self._state.set_environment(env_id)
                self.logger.info(f"Joined '{env_id}' (confirmed by Hub)")
                await self.on_joined_environment(env_id)
                if self._monitorable:
                    await self._on_state_change("", self._state.state.value)
                return

            if self._join_failed.is_set():
                # env 不存在，稍后重试
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    self.logger.info(
                        f"Env '{env_id}' not found, retrying in {retry_interval}s..."
                    )
                    await asyncio.sleep(min(retry_interval, remaining))
                continue

            # 超时未卫，重试
            self.logger.info(f"No response from Hub for '{env_id}', retrying...")

        raise TimeoutError(f"Failed to join '{env_id}' within {timeout}s")

    async def on_system_notify(self, event: str, content: dict) -> None:
        """
        处理 Hub 系统通知。

        - "joined":              设置 join 确认信号
        - "environment_closed": 重置状态，开启自动重连
        """
        if event == "joined":
            self._join_confirmed.set()

        elif event == "environment_closed":
            closed_env = self.current_env or content.get("env_id", "unknown")
            # 重置到 HOME 状态
            self._state.set_environment(None)
            self._tools = []
            self.logger.warning(f"Environment closed: {closed_env}")
            await self.on_environment_closed(closed_env)

            # 开启自动重连
            if self._auto_rejoin:
                await self._start_rejoin(closed_env)

    async def on_error(self, error: Dict[str, Any]) -> None:
        """Hub 错误回调，拦截 join 过程中的 404 信号。"""
        self.logger.error(f"Error: {error}")
        if error.get("code") == 404 and self._pending_env:
            self._join_failed.set()

    async def _start_rejoin(self, env_id: str) -> None:
        """启动后台重连任务，如果已有任务则先取消旧的。"""
        if self._rejoin_task and not self._rejoin_task.done():
            self._rejoin_task.cancel()
        self._rejoin_task = asyncio.create_task(self._rejoin_loop(env_id))

    async def _rejoin_loop(self, env_id: str) -> None:
        """循环尝试重新加入环境。"""
        self.logger.info(f"Auto-rejoin loop started for '{env_id}'")
        try:
            await self.join_with_retry(
                env_id,
                timeout=self._rejoin_timeout,
                retry_interval=self._rejoin_interval,
            )
            self.logger.info(f"Auto-rejoin succeeded: '{env_id}'")
        except TimeoutError:
            self.logger.error(
                f"Auto-rejoin timed out after {self._rejoin_timeout}s for '{env_id}'"
            )
        except asyncio.CancelledError:
            self.logger.info(f"Auto-rejoin cancelled for '{env_id}'")
        except Exception as e:
            self.logger.error(f"Auto-rejoin error: {e}")

    # ------------------------------------------------------------------
    # Tool Discovery
    # ------------------------------------------------------------------

    @property
    def tools(self) -> List[ToolDefinition]:
        """当前工具清单（只读）"""
        return self._tools

    async def on_joined_environment(self, env_id: str) -> None:
        """加入环境后自动触发 discover"""
        await self._discover(env_id)

    async def _discover(self, env_id: str) -> None:
        """内部：向环境发送 discover 请求"""
        envelope = Envelope(
            type="message",
            sender=self.client_id,
            recipient=env_id,
            payload=MessagePayload(type="discover", content={}),
        )
        await self.send(envelope)
        self.logger.info(f"Discover sent -> {env_id}")

    async def rediscover(self) -> None:
        """
        主动重新获取工具清单。

        主要供 LLM 判断调用（例如遇到 tool_not_found 的 outcome 后）。
        """
        if not self.current_env:
            self.logger.warning("rediscover() called but not in any environment")
            return
        await self._discover(self.current_env)
        self.logger.info(f"Rediscover sent -> {self.current_env}")

    # ------------------------------------------------------------------
    # AgentClient Send 快捷函数
    #   - send_action
    #   - send_outcome
    # ------------------------------------------------------------------

    async def send_action(
        self, recipient: str, action_name: str, params: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        发送动作到环境

        Args:
            recipient: 目标环境 ID
            action_name: 动作名称
            params: 动作参数
        """
        action_id = gen_id("action", action_name)
        content = {"id": action_id, "name": action_name, "params": params or {}}
        envelope = Envelope(
            type="message",
            sender=self.client_id,
            recipient=recipient,
            payload=MessagePayload(type="action", content=content),
        )

        await self.send(envelope)
        self.logger.info(
            f"Sent action: {action_name}(id={action_id}) : {self.client_id} -> {recipient}"
        )
        return action_id

    async def send_event(
        self,
        recipient: str,
        event_name: str,
        data: Dict[str, Any] | None = None,
    ) -> str:
        """向指定 recipient 发送事件消息，遵循 name 和 data 标准包。"""

        data = data or {}
        event_id = gen_id("event", event_name)
        content = {"id": event_id, "name": event_name, "data": data}
        envelope = Envelope(
            type="message",
            sender=self.client_id,
            recipient=recipient,
            payload=MessagePayload(type="event", content=content),
        )
        await self.send(envelope)
        self.logger.info(
            f"Sent event: {event_name}(id={event_id}) : {self.client_id} -> {recipient}"
        )
        return event_id

    async def send_outcome(self, recipient: str, content: Dict[str, Any]) -> None:
        """
        发送结果（Agent 也可以返回结果）

        Args:
            recipient: 目标 ID
            content: 结果内容
        """
        envelope = Envelope(
            type="message",
            sender=self.client_id,
            recipient=recipient,
            payload=MessagePayload(type="outcome", content=content),
        )

        await self.send(envelope)
        self.logger.info(f"Sent outcome -> {recipient}")

    # ------------------------------------------------------------------
    # AgentClient 接收消息回调
    #   - on_action
    #   - on_outcome
    #   - on_event
    #   - on_stream
    # ------------------------------------------------------------------

    async def on_message(self, envelope: Envelope) -> None:
        """处理业务消息"""
        payload = envelope.payload

        if payload.type == "action":
            await self.on_action(envelope.sender, payload.content)
        elif payload.type == "outcome":
            await self.on_outcome(envelope.sender, payload.content)
        elif payload.type == "event":
            await self.on_event(envelope.sender, payload.content)
        elif payload.type == "stream":
            await self.on_stream(envelope.sender, payload.content)
        elif payload.type == "specification":
            tools: List[ToolDefinition] = payload.content.get("tools", [])
            self._tools = tools
            self.logger.info(
                f"Tool specification received from {envelope.sender}: {len(tools)} tool(s)"
            )
            await self.on_tool_specification(envelope.sender, tools)

    async def on_broadcast(self, envelope: Envelope) -> None:
        """处理广播消息"""
        payload = envelope.payload

        if payload.type == "event":
            await self.on_broadcast_event(envelope.sender, payload.content)
        elif payload.type == "stream":
            await self.on_broadcast_stream(envelope.sender, payload.content)

    # 子类可重写的回调方法

    async def on_action(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理动作消息（Agent 也可以接收动作）

        Args:
            sender: 发送者 ID
            content: 动作内容
        """
        self.logger.info(f"Received action from {sender}: {content}")

    async def on_outcome(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理环境返回的结果

        Args:
            sender: 发送者 ID
            content: 结果内容
        """
        self.logger.info(f"Received outcome from {sender}: {content}")

    async def on_event(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理点对点事件

        Args:
            sender: 发送者 ID
            content: 事件内容
        """
        self.logger.info(f"Received event from {sender}: {content}")

    async def on_stream(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理流式数据

        Args:
            sender: 发送者 ID
            content: 数据内容
        """
        self.logger.debug(f"Received stream from {sender}: {content}")

    async def on_tool_specification(
        self, sender: str, tools: List[ToolDefinition]
    ) -> None:
        """
        工具清单回调（discover 和 rediscover 后都会触发）

        子类可重写此方法来进行后续处理，例如：
            - 重建发送给 LLM 的 tool schema
            - 更新内部工具映射表

        Args:
            sender: 环境 ID
            tools: 工具定义列表
        """
        pass

    async def on_environment_closed(self, env_id: str) -> None:
        """
        所在环境断开回调（子类可重写）

        当 Hub 通知环境已断开时调用。Agent 状态已被重置为 HOME。
        如果开启了 enable_auto_rejoin()，将在此之后自动启动重连循环。

        Args:
            env_id: 已关闭的环境 ID
        """
        self.logger.warning(f"Environment '{env_id}' closed, waiting for reconnect...")

    async def on_broadcast_event(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理广播事件

        Args:
            sender: 发送者 ID
            content: 事件内容
        """
        self.logger.info(f"Broadcast event from {sender}: {content}")

    async def on_broadcast_stream(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理广播流

        Args:
            sender: 发送者 ID
            content: 数据内容
        """
        self.logger.debug(f"Broadcast stream from {sender}: {content}")
