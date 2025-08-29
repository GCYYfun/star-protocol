"""EnvironmentClient 实现"""

from typing import Any, Dict, Optional
from .base import BaseClient
from ..protocol import OutcomeMessage, EventMessage, MessageType, ClientType


class EnvironmentClient(BaseClient):
    """环境客户端

    用于提供环境服务，接收 Agent 动作并返回结果
    """

    def __init__(
        self, env_id: str, hub_url: str, metadata: Optional[Dict[str, Any]] = None
    ):
        # 环境客户端ID格式：env_{env_id}
        client_id = f"{env_id}"

        super().__init__(
            client_id=client_id,
            client_type=ClientType.ENVIRONMENT,
            hub_url=hub_url,
            env_id=env_id,
            metadata=metadata,
        )
        self.env_id = env_id

    def _get_client_identity(self) -> dict:
        """获取 Environment 客户端身份信息

        Returns:
            包含 Environment 身份信息的字典
        """
        return {
            "client_type": "environment",
            "env_id": self.env_id,
            "metadata": self.metadata or {},
        }

    async def send_outcome(
        self, action_id: str, status: str, outcome: Dict[str, Any], recipient: str
    ) -> None:
        """发送动作结果给 Agent

        Args:
            action_id: 对应的动作ID
            status: 执行状态 (success/failure)
            outcome: 结果数据
            recipient: 目标 Agent ID
        """
        outcome_message = OutcomeMessage(
            action_id=action_id, status=status, outcome=outcome
        )

        await self.send_message(outcome_message, recipient)

        self.logger.info(f"发送结果: {action_id} -> {recipient}")

    async def send_event(
        self,
        event: str,
        data: Dict[str, Any],
        event_id: Optional[str] = None,
        recipient: Optional[str] = None,
    ) -> str:
        """发送环境事件

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
            self.logger.info(f"发送事件: {event} -> {recipient}")
        else:
            # 广播逻辑（这里简化，实际需要 Hub 支持）
            await self.send_message(event_message, "broadcast")
            self.logger.info(f"广播事件: {event}")

        return event_message.event_id
