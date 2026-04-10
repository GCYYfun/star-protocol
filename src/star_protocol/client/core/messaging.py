"""消息发送和路由管理"""

import logging
from typing import Callable, Dict, Any
from star_protocol.models import Envelope, SystemPayload
from star_protocol.client.core.connection import ConnectionManager
from star_protocol.exceptions import ConnectionError as StarConnectionError


class MessagingManager:
    """
    消息管理器

    职责：
    - 发送 Envelope
    - 路由接收到的消息
    - 管理消息处理器
    """

    def __init__(self, connection: ConnectionManager, logger: logging.Logger):
        self.connection = connection
        self.logger = logger
        self._handlers: Dict[str, Callable] = {}

    async def send_envelope(self, envelope: Envelope) -> None:
        """
        发送消息信封

        Args:
            envelope: 消息信封

        Raises:
            StarConnectionError: 未连接
        """
        if not self.connection.is_connected():
            raise StarConnectionError("Not connected")

        try:
            json_str = envelope.model_dump_json()
            await self.connection.send_raw(json_str)
            self.logger.debug(f"Sent: {envelope.type} -> {envelope.recipient}")
        except Exception as e:
            self.logger.error(f"Send failed: {e}")
            raise StarConnectionError(f"Failed to send message: {e}")

    async def send_system_message(
        self, client_id: str, recipient: str, msg_type: str, content: Dict[str, Any]
    ) -> None:
        """
        发送系统消息

        Args:
            client_id: 发送者 ID
            recipient: 接收者 ID
            msg_type: 消息类型
            content: 消息内容
        """
        envelope = Envelope(
            type="system",
            sender=client_id,
            recipient=recipient,
            payload=SystemPayload(type=msg_type, content=content),
        )
        await self.send_envelope(envelope)

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """
        注册消息处理器

        Args:
            message_type: 消息类型（system/message/broadcast）
            handler: 处理函数
        """
        self._handlers[message_type] = handler

    async def route_message(self, envelope: Envelope) -> None:
        """
        路由消息到对应的处理器

        Args:
            envelope: 消息信封
        """
        handler = self._handlers.get(envelope.type)
        if handler:
            try:
                await handler(envelope)
            except Exception as e:
                self.logger.error(f"Error routing message: {e}")
        else:
            self.logger.warning(f"No handler for message type: {envelope.type}")
