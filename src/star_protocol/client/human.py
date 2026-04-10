"""Human 客户端"""

from typing import Any, Dict, Optional
import logging

from star_protocol.client.base import BaseClient
from star_protocol.models import Envelope, MessagePayload


class HumanClient(BaseClient):
    """
    Human 客户端
    
    用于人类用户（观察者、玩家、管理员）参与系统。
    主要功能：
    - 观察环境事件
    - 与 Agent 或 Environment 交互
    - 发送控制指令
    """
    
    def __init__(
        self,
        client_id: str,
        auto_reconnect: bool = True,
        monitorable: bool = False,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化 Human 客户端
        
        Args:
            client_id: Human 唯一标识
            auto_reconnect: 是否自动重连
            monitorable: 是否启用监控功能
            logger: 日志记录器
        """
        super().__init__(
            client_id=client_id,
            role="human",
            auto_reconnect=auto_reconnect,
            monitorable=monitorable,
            logger=logger
        )
    
    # async def send_message(
    #     self,
    #     recipient: str,
    #     content: Dict[str, Any]
    # ) -> None:
    #     """
    #     发送消息给其他客户端
        
    #     Args:
    #         recipient: 目标客户端 ID
    #         content: 消息内容
    #     """
    #     envelope = Envelope(
    #         type="message",
    #         sender=self.client_id,
    #         recipient=recipient,
    #         payload=MessagePayload(
    #             type="event",
    #             content=content
    #         )
    #     )
        
    #     await self.send(envelope)
    #     self.logger.info(f"Sent message -> {recipient}")
    
    async def send_event(
        self,
        recipient: str,
        event_name: str,
        event_data: Dict[str, Any]
    ) -> None:
        """
        发送点对点事件给其他客户端
        
        Args:
            recipient: 目标客户端 ID
            event_name: 事件名称
            event_data: 事件的具体参数与数据
        """
        envelope = Envelope(
            type="message",
            sender=self.client_id,
            recipient=recipient,
            payload=MessagePayload(
                type="event",
                content={
                    "name": event_name,
                    "data": event_data
                }
            )
        )
        
        await self.send(envelope)
        self.logger.info(f"Sent event: {event_name} -> {recipient}")
    
    async def send_action(
        self,
        recipient: str,
        action_name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        发送动作（类似 Agent）
        
        Args:
            recipient: 目标 ID
            action_name: 动作名称
            params: 动作参数
        """
        content = {"name": action_name, "params": params or {}}
        
        envelope = Envelope(
            type="message",
            sender=self.client_id,
            recipient=recipient,
            payload=MessagePayload(
                type="action",
                content=content
            )
        )
        
        await self.send(envelope)
        self.logger.info(f"Sent action: {action_name} -> {recipient}")
    
    async def on_message(self, envelope: Envelope) -> None:
        """处理业务消息"""
        payload = envelope.payload
        
        if payload.type == "outcome":
            await self.on_outcome(envelope.sender, payload.content)
        elif payload.type == "event":
            await self.on_event(envelope.sender, payload.content)
        elif payload.type == "stream":
            await self.on_stream(envelope.sender, payload.content)
    
    async def on_broadcast(self, envelope: Envelope) -> None:
        """处理广播消息"""
        payload = envelope.payload
        
        if payload.type == "event":
            await self.on_broadcast_event(envelope.sender, payload.content)
        elif payload.type == "stream":
            await self.on_broadcast_stream(envelope.sender, payload.content)
    
    # 子类可重写的回调方法
    
    async def on_outcome(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理结果消息
        
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
    
    async def on_broadcast_event(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理广播事件
        
        Args:
            sender: 发送者 ID
            content: 事件内容
        """
        self.logger.info(f"[观察] Broadcast event from {sender}: {content}")
    
    async def on_broadcast_stream(self, sender: str, content: Dict[str, Any]) -> None:
        """
        处理广播流
        
        Args:
            sender: 发送者 ID
            content: 数据内容
        """
        self.logger.debug(f"[观察] Broadcast stream from {sender}: {content}")
