"""AgentClient 实现"""

import asyncio
from typing import Any, Dict, Optional, List

from star_protocol.protocol.messages import Envelope, OutcomeMessage
from .base import BaseClient
from ..protocol import ActionMessage, MessageType, ClientType


class AgentClient(BaseClient):
    """Agent 客户端

    用于 AI Agent 连接环境，执行动作并接收结果
    """

    def __init__(
        self,
        agent_id: str,
        env_id: str,
        hub_url: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            client_id=agent_id,
            client_type=ClientType.AGENT,
            hub_url=hub_url,
            env_id=env_id,
            metadata=metadata,
        )
        self.env_id = env_id

    def _get_client_identity(self) -> dict:
        """获取 Agent 客户端身份信息

        Returns:
            包含 Agent 身份信息的字典
        """
        return {
            "client_type": "agent",
            "env_id": self.env_id,
            "metadata": self.metadata or {},
        }

    # async def send_action(
    #     self,
    #     action,  # 可以是 str 或 ActionMessage
    #     parameters: Optional[Dict[str, Any]] = None,
    #     action_id: Optional[str] = None,
    #     recipient: Optional[str] = None,
    # ) -> str:
    #     """发送动作到环境

    #     Args:
    #         action: 动作名称(str) 或 ActionMessage 对象
    #         parameters: 动作参数
    #         action_id: 动作ID，如果不提供会自动生成
    #         recipient: 目标环境ID，默认使用初始化时的 env_id

    #     Returns:
    #         动作ID（用于跟踪结果）
    #     """
    #     target = recipient or f"{self.env_id}"

    #     # 兼容性处理：支持直接传递 ActionMessage
    #     if isinstance(action, ActionMessage):
    #         action_message = action
    #     else:
    #         # 传统方式：传递动作名称和参数
    #         action_message = ActionMessage(
    #             action=action,
    #             action_id=action_id,  # 如果为 None，ActionMessage 会自动生成
    #             parameters=parameters or {},
    #         )

    #     await self.send_message(action_message, target)

    #     self.logger.info(f"发送动作: {action_message.action} -> {target}")
    #     return action_message.action_id

    # async def on_action(self, envelope: Envelope) -> None:
    #     """处理 ACTION 消息事件（默认实现）

    #     Args:
    #         message: ACTION 消息
    #         envelope: 消息信封（包含发送者等信息）
    #     """
    #     message = envelope.message
    #     self.logger.debug(f"收到动作: {message.action} from {envelope.sender}")

    #     # 调用用户注册的处理器
    #     for handler in self._action_handlers:
    #         try:
    #             result = await handler(message)
    #             await self.send_outcome(
    #                 data=result,
    #                 recipient=envelope.sender,
    #                 action=message.action,
    #                 action_id=message.action_id,
    #             )
    #         except Exception as e:
    #             self.logger.error(f"ACTION 处理器出错: {e}")

    async def send_action(
        self,
        action: str,
        parameters: Dict[str, Any],
        recipient: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """发送动作并等待结果（使用上下文管理）

        Args:
            action: 动作名称
            parameters: 动作参数
            recipient: 目标环境ID，默认使用初始化时的 env_id
            timeout: 超时时间（秒）

        Returns:
            OutcomeMessage: 动作结果

        Raises:
            asyncio.TimeoutError: 超时
        """
        recipient = recipient or f"{self.env_id}"

        outcome = await self.send_action_with_context(
            action=action,
            params=parameters,
            recipient=recipient,
            timeout=timeout,
        )

        return outcome

    # async def send_outcome(
    #     self,
    #     data: str,
    #     recipient: Optional[str] = None,
    #     action: Optional[str] = None,
    #     action_id: Optional[str] = None,
    # ) -> Any:
    #     """发送动作并等待结果（使用上下文管理）

    #     Args:
    #         action: 动作名称
    #         parameters: 动作参数
    #         recipient: 目标环境ID，默认使用初始化时的 env_id
    #         timeout: 超时时间（秒）

    #     Returns:
    #         OutcomeMessage: 动作结果

    #     Raises:
    #         asyncio.TimeoutError: 超时
    #     """
    #     recipient = recipient or f"{self.env_id}"

    #     message = OutcomeMessage(outcome=action, action_id=action_id, data=data)
    #     await self.send_message(
    #         message=message,
    #         recipient=recipient,
    #     )

    async def get_outcome(self, action_id):

        try:
            outcome = await self.context.wait_for_response(action_id)
            return outcome
        except asyncio.TimeoutError:
            self.logger.warning(f"Action (ID: {action_id}) 超时")
            raise

    async def execute_action_sequence(
        self,
        actions: List[Dict[str, Any]],
        recipient: Optional[str] = None,
        timeout_per_action: Optional[float] = None,
    ) -> List[Any]:
        """执行动作序列（批量操作）

        Args:
            actions: 动作列表，每个元素包含 'action' 和 'parameters'
            recipient: 目标环境ID
            timeout_per_action: 每个动作的超时时间

        Returns:
            List[OutcomeMessage]: 所有动作的结果列表
        """
        results = []
        target = recipient or f"{self.env_id}"

        for action_data in actions:
            try:
                outcome = await self.send_action_and_wait(
                    action=action_data["action"],
                    parameters=action_data.get("parameters", {}),
                    recipient=target,
                    timeout=timeout_per_action,
                )
                results.append(outcome)
                self.logger.debug(f"动作 {action_data['action']} 执行成功")
            except Exception as e:
                self.logger.error(f"动作 {action_data['action']} 执行失败: {e}")
                results.append(None)

        return results
