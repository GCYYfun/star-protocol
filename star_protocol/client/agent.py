"""
Star Protocol Agent 客户端

智能体客户端实现
"""

import uuid
from typing import Any, Dict, List, Optional
from .base import BaseStarClient
from ..protocol import (
    ClientInfo,
    ClientType,
    ActionPayload,
    OutcomePayload,
    EventPayload,
)


class AgentClient(BaseStarClient):
    """智能体客户端"""

    def __init__(
        self,
        agent_id: str,
        env_id: str,
        validate_messages: bool = True,
        base_url: str = "ws://localhost",
        port: int = 9999,
    ):
        client_info = ClientInfo(id=agent_id, type=ClientType.AGENT)
        super().__init__(
            base_url=base_url,
            port=port,
            client_info=client_info,
            validate_messages=validate_messages,
        )
        self.env_id = env_id

        # Agent 特有的状态
        # self.is_registered = False
        self.current_position: Optional[Dict[str, Any]] = None
        self.capabilities: List[str] = []

    def get_connection_url(self) -> str:
        """获取 Agent 连接 URL"""
        return f"{self.server_url}/env/{self.env_id}/agent/{self.client_info.id}"

    # -------- Action --------
    async def send_action(
        self, action: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """发送动作到环境"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        # 生成动作 ID
        action_id = str(uuid.uuid4())

        # 创建动作载荷
        payload = ActionPayload(
            id=action_id, action=action, parameters=parameters or {}
        )

        # 目标环境信息
        env_info = ClientInfo(id=self.env_id, type=ClientType.ENVIRONMENT)

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=env_info
        )

        if success:
            self.logger.info(f"Action '{action}' sent with ID {action_id}")
            self.monitor.update_stats(已发送动作=action, 动作ID=action_id)
            return action_id
        else:
            self.logger.error(f"Failed to send action '{action}'")
            return None

    async def send_outcome(
        self, outcome: Any, outcome_type: str = "dict", action_id: str = ""
    ) -> Optional[str]:
        """发送动作结果"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        # 创建结果载荷
        payload = OutcomePayload(
            id=action_id, outcome=outcome, outcome_type=outcome_type
        )

        # 目标环境信息
        env_info = ClientInfo(id=self.env_id, type=ClientType.ENVIRONMENT)

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=env_info
        )

        if success:
            self.logger.info(f"Outcome sent with ID {payload.id}")
            return payload.id
        else:
            self.logger.error("Failed to send outcome")
            return None

    async def conversation(self, target_agent: str, data: dict) -> Optional[str]:
        """与其他 Agent 对话"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        target_info = ClientInfo(id=target_agent, type=ClientType.AGENT)

        # 生成对话 ID
        conversation_id = str(uuid.uuid4())

        # 使用事件载荷进行对话
        payload = EventPayload(
            id=conversation_id,
            event="dialogue",
            data=data,
        )

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=target_info
        )

        if success:
            self.logger.info(f"Sent conversation message to {target_agent}")
            self.monitor.update_stats(对话发送=target_agent)
            return conversation_id
        else:
            self.logger.error(f"Failed to send conversation to {target_agent}")
            return None

    # -------- Event 发送 --------
    async def send_event(
        self,
        event_name: str,
        event_data: Optional[Dict[str, Any]] = None,
        target_id: Optional[str] = None,
        target_type: str = "environment",
    ) -> Optional[str]:
        """发送事件消息"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        event_id = str(uuid.uuid4())
        payload = EventPayload(
            id=event_id,
            event=event_name,
            data={"from_agent": self.client_info.id, **(event_data or {})},
        )

        # 确定目标
        if target_id:
            if target_type == "environment":
                recipient = ClientInfo(id=target_id, type=ClientType.ENVIRONMENT)
            elif target_type == "agent":
                recipient = ClientInfo(id=target_id, type=ClientType.AGENT)
            elif target_type == "human":
                recipient = ClientInfo(id=target_id, type=ClientType.HUMAN)
            else:
                self.logger.error(f"Unknown target type: {target_type}")
                return None
        else:
            # 默认发送给环境
            recipient = ClientInfo(id=self.env_id, type=ClientType.ENVIRONMENT)

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=recipient
        )

        if success:
            self.logger.info(f"Sent event '{event_name}' with ID {event_id}")
            self.monitor.update_stats(已发送事件=event_name)
            return event_id
        else:
            self.logger.error(f"Failed to send event '{event_name}'")
            return None

    # -------- 连接生命周期 --------
    async def _on_connected(self) -> None:
        """连接成功后发送心跳消息表示连接"""

        await self.send_heartbeat()
        self.monitor.info("Sent heartbeat to establish connection")
