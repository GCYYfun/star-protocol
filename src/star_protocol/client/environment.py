"""Environment 客户端"""

from typing import Any, Dict, List, Optional
import logging

from star_protocol.client.base import BaseClient
from star_protocol.models import Envelope, MessagePayload, BroadcastPayload
from star_protocol.models.payloads import ToolDefinition


class EnvironmentClient(BaseClient):
    """
    Environment 客户端

    用于环境（游戏世界、仿真环境等）管理和与 Agent 交互。
    主要功能：
    - 接收 Agent 的动作（action）
    - 返回执行结果（outcome）
    - 广播环境事件（event）
    """

    def __init__(
        self,
        client_id: str,
        auto_reconnect: bool = True,
        monitorable: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化 Environment 客户端

        Args:
            client_id: Environment 唯一标识
            auto_reconnect: 是否自动重连
            monitorable: 是否启用监控功能
            logger: 日志记录器
        """
        super().__init__(
            client_id=client_id,
            role="environment",
            auto_reconnect=auto_reconnect,
            monitorable=monitorable,
            logger=logger,
        )

    async def send_outcome(self, recipient: str, content: Dict[str, Any]) -> None:
        """
        发送执行结果给 Agent

        Args:
            recipient: 目标 Agent ID
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

    async def send_specification(
        self, recipient: str, tools: List[ToolDefinition]
    ) -> None:
        """
        发送工具清单给指定 Agent

        通常由 on_discover() 自动调用，也可在工具发生内容层变化时手动调用。

        Args:
            recipient: 目标 Agent ID
            tools: 工具定义列表
        """
        envelope = Envelope(
            type="message",
            sender=self.client_id,
            recipient=recipient,
            payload=MessagePayload(type="specification", content={"tools": tools}),
        )
        await self.send(envelope)
        self.logger.info(f"Sent specification to {recipient}: {len(tools)} tool(s)")

    async def broadcast_event(
        self, event_name: str, content: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        广播环境事件

        Args:
            event_name: 事件名称
            content: 事件内容
        """
        event_content = {"name": event_name, "data": content or {}}

        envelope = Envelope(
            type="broadcast",
            sender=self.client_id,
            recipient="@all",
            payload=BroadcastPayload(type="event", content=event_content),
        )

        await self.send(envelope)
        self.logger.info(f"Broadcast event: {event_name}")

    async def broadcast_to_env(
        self, env_id: str, event_name: str, content: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        向特定环境广播事件

        Args:
            env_id: 目标环境 ID
            event_name: 事件名称
            content: 事件内容
        """
        event_content = {"name": event_name, "data": content or {}}

        envelope = Envelope(
            type="broadcast",
            sender=self.client_id,
            recipient=f"@env:{env_id}",
            payload=BroadcastPayload(type="event", content=event_content),
        )

        await self.send(envelope)
        self.logger.info(f"Broadcast to {env_id}: {event_name}")

    async def on_message(self, envelope: Envelope) -> None:
        """处理业务消息"""
        payload = envelope.payload

        if payload.type == "action":
            await self.on_action(envelope.sender, payload.content)
        elif payload.type == "event":
            await self.on_event(envelope.sender, payload.content)
        elif payload.type == "discover":
            tools = await self.on_discover(envelope.sender)
            await self.send_specification(envelope.sender, tools)

    async def on_broadcast(self, envelope: Envelope) -> None:
        """处理广播消息"""
        # Environment 通常不需要处理广播
        pass

    # 子类可重写的回调方法

    async def on_action(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理 Agent 的动作

        Args:
            sender: Agent ID
            content: 动作内容
        """
        self.logger.info(f"Received action from {sender}: {content}")

        # 默认返回成功
        await self.send_outcome(
            recipient=sender, content={"success": True, "message": "Action received"}
        )

    async def on_event(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理点对点事件

        Args:
            sender: 发送者 ID
            content: 事件内容
        """
        self.logger.info(f"Received event from {sender}: {content}")

    async def on_discover(self, sender: str) -> List[ToolDefinition]:
        """
        处理 Agent 的工具发现请求

        子类应重写此方法返回工具定义列表。
        默认返回空列表。

        Args:
            sender: 请求方 Agent ID

        Returns:
            工具定义列表
        """
        return []

    async def on_system_notify(self, event: str, content: dict) -> None:
        """
        处理 Hub 系统通知，路由成员变化事件。

        协议约定：msg 字段为 dict 时携带结构化数据：
            - "client_joined": msg = {"client_id": "..."}
            - "client_left":   msg = {"client_id": "...", "reason": "leave|disconnected"}
        """
        msg = content.get("msg", {})

        if event == "client_joined":
            client_id = msg.get("client_id", "unknown") if isinstance(msg, dict) else "unknown"
            self.logger.info(f"Client joined: {client_id}")
            await self.on_client_joined(client_id)
        elif event == "client_left":
            client_id = msg.get("client_id", "unknown") if isinstance(msg, dict) else "unknown"
            reason = msg.get("reason", "leave") if isinstance(msg, dict) else "leave"
            self.logger.info(f"Client left: {client_id} (reason={reason})")
            await self.on_client_left(client_id, reason)


    async def on_client_joined(self, client_id: str) -> None:
        """
        Agent 加入环境回调（子类可重写）

        Args:
            client_id: 加入的 Agent ID
        """
        pass

    async def on_client_left(self, client_id: str, reason: str = "leave") -> None:
        """
        Agent 离开环境回调（子类可重写）

        Args:
            client_id: 离开的 Agent ID
            reason:   离开原因（"leave" = 主动离开，"disconnected" = 连接断开）
        """
        pass
