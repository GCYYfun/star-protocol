"""
Star Protocol Environment 客户端

环境客户端实现 - 专注于消息传输
"""

import uuid
from typing import Any, Dict, Optional
from .base import BaseStarClient
from ..protocol import (
    ClientInfo,
    ClientType,
    OutcomePayload,
    EventPayload,
    BroadcastHelper,
)


class EnvironmentClient(BaseStarClient):
    """环境客户端 - 消息传输接口"""

    def __init__(
        self,
        env_id: str,
        validate_messages: bool = True,
        base_url: str = "ws://localhost",
        port: int = 9999,
    ):
        client_info = ClientInfo(id=env_id, type=ClientType.ENVIRONMENT)
        super().__init__(
            base_url=base_url,
            port=port,
            client_info=client_info,
            validate_messages=validate_messages,
        )

    def get_connection_url(self) -> str:
        """获取环境连接 URL"""
        return f"{self.server_url}/env/{self.client_info.id}"

    # -------- Outcome --------
    async def send_outcome(
        self, agent_id: str, action_id: str, outcome: Any, outcome_type: str = "dict"
    ) -> bool:
        """向 Agent 发送动作结果"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return False

        agent_info = ClientInfo(id=agent_id, type=ClientType.AGENT)
        payload = OutcomePayload(
            id=action_id, outcome=outcome, outcome_type=outcome_type
        )

        success = await self.send_message(
            message_type="message",
            payload=payload.to_dict(),
            recipient=agent_info,
        )

        if success:
            self.logger.debug(
                f"Sent outcome to agent {agent_id} for action {action_id}"
            )
            self.monitor.update_stats(已发送结果=f"{agent_id}:{action_id}")

        return success

    # -------- Event --------
    async def send_event(
        self,
        event_name: str,
        event_data: Optional[Dict[str, Any]] = None,
        target_agent: Optional[str] = None,
    ) -> Optional[str]:
        """发送环境事件"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        event_id = str(uuid.uuid4())
        payload = EventPayload(id=event_id, event=event_name, data=event_data or {})

        # 如果指定了目标 Agent，则直接发送
        if target_agent:
            target_info = ClientInfo(id=target_agent, type=ClientType.AGENT)
            success = await self.send_message(
                message_type="message",
                payload=payload.to_dict(),
                recipient=target_info,
            )
        else:
            # 否则发送到环境广播
            broadcast_recipient = BroadcastHelper.create_env_broadcast_target(
                self.client_info.id
            )
            success = await self.send_message(
                message_type="message",
                payload=payload.to_dict(),
                recipient=broadcast_recipient,
            )

        if success:
            self.logger.info(f"Sent event '{event_name}' with ID {event_id}")
            self.monitor.update_stats(已发送事件=event_name)
            return event_id
        else:
            self.logger.error(f"Failed to send event '{event_name}'")
            return None

    # -------- Broadcast --------
    async def broadcast_to_env(
        self,
        event_name: str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """向环境内所有客户端广播事件"""
        return await self.send_event(event_name, event_data, target_agent=None)

    async def broadcast_globally(
        self,
        event_name: str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """全局广播事件"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        event_id = str(uuid.uuid4())
        payload = EventPayload(id=event_id, event=event_name, data=event_data or {})

        # 使用广播助手创建全局广播目标
        broadcast_recipient = BroadcastHelper.create_broadcast_target()

        success = await self.send_message(
            message_type="message",
            payload=payload.to_dict(),
            recipient=broadcast_recipient,
        )

        if success:
            self.logger.info(
                f"Globally broadcasted event '{event_name}' with ID {event_id}"
            )
            self.monitor.update_stats(全局广播=event_name)
            return event_id
        else:
            self.logger.error(f"Failed to globally broadcast event '{event_name}'")
            return None

    # -------- Agent 管理 --------
    async def send_agent_joined(
        self,
        agent_id: str,
        agent_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """发送 Agent 加入环境事件"""
        event_data = {"agent_id": agent_id, **(agent_data or {})}
        return await self.broadcast_to_env("agent_joined", event_data)

    async def send_agent_left(
        self,
        agent_id: str,
        reason: str = "disconnected",
    ) -> Optional[str]:
        """发送 Agent 离开环境事件"""
        event_data = {"agent_id": agent_id, "reason": reason}
        return await self.broadcast_to_env("agent_left", event_data)

    async def send_world_update(
        self,
        world_state: Dict[str, Any],
        target_agent: Optional[str] = None,
    ) -> Optional[str]:
        """发送世界状态更新事件"""
        return await self.send_event("world_update", world_state, target_agent)

    # -------- 连接生命周期 --------
    async def _on_connected(self) -> None:
        """连接成功后发送心跳消息表示连接"""

        await self.send_heartbeat()
        self.monitor.info("Sent heartbeat to establish connection")
