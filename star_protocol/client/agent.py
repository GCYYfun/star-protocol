"""Agent 客户端"""

from typing import Any, Dict, Optional
import logging

from star_protocol.client.base import BaseClient
from star_protocol.models import Envelope, MessagePayload


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
        logger: Optional[logging.Logger] = None
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
            logger=logger
        )
    
    async def send_action(
        self,
        recipient: str,
        action_name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        发送动作到环境
        
        Args:
            recipient: 目标环境 ID
            action_name: 动作名称
            params: 动作参数
        """
        content = {"name": action_name}
        if params:
            content.update(params)
        
        envelope = Envelope(
            type="message",
            sender=self.client_id,
            recipient=recipient,
            data=MessagePayload(
                type="action",
                content=content
            )
        )
        
        await self.send(envelope)
        self.logger.info(f"Sent action: {action_name} -> {recipient}")
    
    async def send_outcome(
        self,
        recipient: str,
        content: Dict[str, Any]
    ) -> None:
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
            data=MessagePayload(
                type="outcome",
                content=content
            )
        )
        
        await self.send(envelope)
        self.logger.info(f"Sent outcome -> {recipient}")
    
    async def on_message(self, envelope: Envelope) -> None:
        """处理业务消息"""
        payload = envelope.data
        
        if payload.type == "action":
            await self.on_action(envelope.sender, payload.content)
        elif payload.type == "outcome":
            await self.on_outcome(envelope.sender, payload.content)
        elif payload.type == "event":
            await self.on_event(envelope.sender, payload.content)
        elif payload.type == "stream":
            await self.on_stream(envelope.sender, payload.content)
    
    async def on_broadcast(self, envelope: Envelope) -> None:
        """处理广播消息"""
        payload = envelope.data
        
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
