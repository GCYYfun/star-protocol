"""HumanClient 实现"""

from typing import Any, Dict, Optional
from .base import BaseClient
from ..protocol import EventMessage, StreamMessage, MessageType, ClientType


class HumanClient(BaseClient):
    """人类客户端

    用于人类观察者，监控环境和 Agent 的交互
    """

    def __init__(
        self,
        human_id: str,
        hub_url: str,
        env_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            client_id=human_id,
            client_type=ClientType.HUMAN,
            hub_url=hub_url,
            env_id=env_id,
            metadata=metadata,
        )

    def _get_client_identity(self) -> dict:
        """获取 Human 客户端身份信息

        Returns:
            包含 Human 身份信息的字典
        """
        return {
            "client_type": "human",
            "env_id": self.env_id,
            "metadata": self.metadata or {},
        }

    async def send_event(
        self,
        event: str,
        data: Dict[str, Any],
        event_id: Optional[str] = None,
        recipient: Optional[str] = None,
    ) -> str:
        """发送观察事件

        Args:
            event: 事件类型
            data: 事件数据
            event_id: 事件ID，如果不提供会自动生成
            recipient: 目标客户端ID，如果为 None 则广播

        Returns:
            事件ID
        """
        event_message = EventMessage(event=event, event_id=event_id, data=data)

        if recipient:
            await self.send_message(event_message, recipient)
            self.logger.info(f"发送观察事件: {event} -> {recipient}")
        else:
            # 广播逻辑
            await self.send_message(event_message, "broadcast")
            self.logger.info(f"广播观察事件: {event}")

        return event_message.event_id

    async def send_stream(
        self,
        stream: str,
        chunk: Dict[str, Any],
        stream_id: Optional[str] = None,
        sequence: Optional[int] = None,
        recipient: Optional[str] = None,
    ) -> str:
        """发送流数据（如视频流、音频流等）

        Args:
            stream: 流类型
            chunk: 流数据块
            stream_id: 流ID，如果不提供会自动生成
            sequence: 序列号，如果不提供会自动生成
            recipient: 目标客户端ID，如果为 None 则广播

        Returns:
            流ID
        """
        stream_message = StreamMessage(
            stream=stream, stream_id=stream_id, sequence=sequence or 0, chunk=chunk
        )

        if recipient:
            await self.send_message(stream_message, recipient)
            self.logger.info(f"发送流数据: {stream} -> {recipient}")
        else:
            # 广播逻辑
            await self.send_message(stream_message, "broadcast")
            self.logger.info(f"广播流数据: {stream}")

        return stream_message.stream_id
