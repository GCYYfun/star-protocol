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
    Message,
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

        self.actions = {}

    def get_connection_url(self) -> str:
        """获取 Agent 连接 URL"""
        return f"{self.server_url}/env/{self.env_id}/agent/{self.client_info.id}"

    # -------- 协议处理（可被覆盖） --------
    async def on_message(self, message: Message) -> None:
        """
        处理接收到的业务消息

        默认实现：分发内层消息到具体的处理方法
        子类可以覆盖此方法来实现完全自定义的消息处理逻辑
        """
        self.monitor.info(
            f"Received message from {message.sender.id} "
            f"(type: {message.sender.type.value})"
        )

        # 更新监控统计
        self.monitor.update_stats(
            最后接收消息时间=(
                message.timestamp if hasattr(message, "timestamp") else "unknown"
            ),
            最后发送者=message.sender.id,
        )

        # 分发内层消息
        await self._dispatch_inner_message(message)

    async def _dispatch_inner_message(self, message: Message) -> None:
        """分发内层消息到对应的处理方法"""
        try:
            payload = message.payload
            message_type = self._get_message_type(payload)

            # 使用方法映射简化分发逻辑
            dispatch_map = {
                "outcome": self.on_outcome,
                "event": self.on_event,
                "action": self.on_action,
                "stream": self.on_stream,
            }

            handler = dispatch_map.get(message_type)
            if handler:
                await handler(payload, message)
            else:
                await self.on_unknown_message(payload, message)

        except Exception as e:
            self.monitor.error(f"Error dispatching inner message: {e}")

    def _get_message_type(self, payload: Any) -> Optional[str]:
        """提取消息类型"""
        if isinstance(payload, dict):
            return payload.get("type")
        elif hasattr(payload, "type"):
            return payload.type
        return None

    # -------- 内层消息处理方法（可被覆盖） --------
    async def on_outcome(self, payload: Dict[str, Any], message: Message) -> None:
        """
        处理动作结果消息

        子类可以覆盖此方法来实现自定义的结果处理逻辑
        """
        action_id = payload.get("id", "unknown")
        outcome = payload.get("outcome", {})
        outcome_type = payload.get("outcome_type", "unknown")

        self.monitor.info(f"Received outcome for action {action_id}: {outcome_type}")
        self.monitor.update_stats(最后动作结果=action_id, 结果类型=outcome_type)

        # 默认处理：记录成功或失败
        if isinstance(outcome, dict):
            success = outcome.get("success", False)
            if success:
                self.monitor.info(f"Action {action_id} completed successfully")
            else:
                error_msg = outcome.get("error", "Unknown error")
                self.monitor.warning(f"Action {action_id} failed: {error_msg}")

    async def on_event(self, payload: Dict[str, Any], message: Message) -> None:
        """
        处理环境事件消息

        子类可以覆盖此方法来实现自定义的事件处理逻辑
        """
        event_id = payload.get("id", "unknown")
        event_type = payload.get("event", "unknown")
        event_data = payload.get("data", {})

        self.monitor.info(f"Received event {event_type} (ID: {event_id})")
        self.monitor.update_stats(最后事件=event_type, 事件ID=event_id)

        # 使用事件映射简化处理
        event_handlers = {
            "dialogue": self._handle_dialogue,
            "environment_update": self._handle_environment_update,
            "agent_joined": self._handle_agent_joined,
            "agent_left": self._handle_agent_left,
        }

        handler = event_handlers.get(event_type)
        if handler:
            await handler(event_data, message)
        else:
            self.monitor.debug(f"Unhandled event type: {event_type}")

    async def on_action(self, payload: Dict[str, Any], message: Message) -> None:
        """
        处理动作消息

        注意：Agent 通常不处理其他 Agent 的动作消息
        子类可以覆盖此方法来实现自定义的动作处理逻辑
        """
        action_id = payload.get("id", "unknown")
        action_name = payload.get("action", "unknown")
        self.monitor.debug(f"Received action message: {action_name} (ID: {action_id})")

    async def on_stream(self, payload: Dict[str, Any], message: Message) -> None:
        """
        处理流数据消息

        子类可以覆盖此方法来实现自定义的流处理逻辑
        """
        stream_id = payload.get("id", "unknown")
        stream_type = payload.get("stream_type", "unknown")
        self.monitor.debug(f"Received stream message: {stream_type} (ID: {stream_id})")
        self.monitor.update_stats(最后流消息=stream_type, 流ID=stream_id)

    async def on_unknown_message(
        self, payload: Dict[str, Any], message: Message
    ) -> None:
        """
        处理未知类型的消息

        子类可以覆盖此方法来处理自定义的消息类型
        """
        message_type = self._get_message_type(payload) or "unknown"
        self.logger.warning(f"Received unknown message type: {message_type}")
        self.monitor.update_stats(未知消息类型=message_type)

    async def on_error(self, message: Message) -> None:
        """
        处理错误消息

        子类可以覆盖此方法来实现自定义的错误处理逻辑
        """
        error_info = message.payload
        error_code, error_type, error_message = self._parse_error_info(error_info)

        self.monitor.error(
            f"Received error from {message.sender.id}: "
            f"[{error_code}] {error_type} - {error_message}"
        )

        # 更新监控统计
        self.monitor.update_stats(
            最后错误时间=(
                message.timestamp if hasattr(message, "timestamp") else "unknown"
            ),
            最后错误代码=error_code,
            最后错误类型=error_type,
        )

        # 错误恢复策略
        if error_type in ["connection_lost", "session_timeout"]:
            self.monitor.warning("Connection error detected, may need to reconnect")

    async def on_heartbeat(self, message: Message) -> None:
        """
        处理心跳消息

        子类可以覆盖此方法来实现自定义的心跳处理逻辑
        """
        self.monitor.debug(f"Received heartbeat from {message.sender.id}")
        self.monitor.update_stats(
            最后心跳时间=(
                message.timestamp if hasattr(message, "timestamp") else "unknown"
            ),
            心跳发送者=message.sender.id,
        )

    # -------- 默认事件处理器 --------
    async def _handle_dialogue(
        self, event_data: Dict[str, Any], message: Message
    ) -> None:
        """处理对话事件"""
        from_agent = event_data.get("from", message.sender.id)
        topic = event_data.get("topic", "")
        content = event_data.get("message", "")

        self.monitor.info(f"Received dialogue from {from_agent}: {topic}")
        if content:
            self.monitor.info(f"Message content: {content}")

    async def _handle_environment_update(
        self, event_data: Dict[str, Any], message: Message
    ) -> None:
        """处理环境更新事件"""
        update_type = event_data.get("update_type", "unknown")
        self.monitor.info(f"Environment update: {update_type}")

        # 更新本地状态
        if update_type == "position" and "position" in event_data:
            self.current_position = event_data["position"]
            self.monitor.info(f"Position updated to: {self.current_position}")

    async def _handle_agent_joined(
        self, event_data: Dict[str, Any], message: Message
    ) -> None:
        """处理 Agent 加入事件"""
        agent_id = event_data.get("agent_id", "unknown")
        self.monitor.info(f"Agent {agent_id} joined the environment")

    async def _handle_agent_left(
        self, event_data: Dict[str, Any], message: Message
    ) -> None:
        """处理 Agent 离开事件"""
        agent_id = event_data.get("agent_id", "unknown")
        self.monitor.info(f"Agent {agent_id} left the environment")

    # -------- 辅助方法 --------
    def _parse_error_info(self, error_info: Any) -> tuple[str, str, str]:
        """解析错误信息"""
        if isinstance(error_info, dict):
            return (
                error_info.get("error_code", "unknown"),
                error_info.get("error_type", "unknown"),
                error_info.get("message", "No message provided"),
            )
        else:
            return ("unknown", "unknown", str(error_info))

    # -------- 业务方法 --------
    async def send_action(
        self, action: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """发送动作到环境"""
        if not self.is_connected:
            self.monitor.error("Not connected to server")
            return None

        action_id = str(uuid.uuid4())
        payload = ActionPayload(
            id=action_id, action=action, parameters=parameters or {}
        )
        env_info = ClientInfo(id=self.env_id, type=ClientType.ENVIRONMENT)

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=env_info
        )

        if success:
            self.monitor.info(f"Action '{action}' sent with ID {action_id}")
            self.monitor.update_stats(已发送动作=action, 动作ID=action_id)
            return action_id
        else:
            self.monitor.error(f"Failed to send action '{action}'")
            return None

    async def send_outcome(
        self, outcome: Any, outcome_type: str = "dict", action_id: str = ""
    ) -> Optional[str]:
        """发送动作结果"""
        if not self.is_connected:
            self.monitor.error("Not connected to server")
            return None

        payload = OutcomePayload(
            id=action_id, outcome=outcome, outcome_type=outcome_type
        )
        env_info = ClientInfo(id=self.env_id, type=ClientType.ENVIRONMENT)

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=env_info
        )

        if success:
            self.monitor.info(f"Outcome sent with ID {payload.id}")
            return payload.id
        else:
            self.monitor.error("Failed to send outcome")
            return None

    async def send_event(
        self,
        event_name: str,
        event_data: Optional[Dict[str, Any]] = None,
        target_id: Optional[str] = None,
        target_type: str = "environment",
    ) -> Optional[str]:
        """发送事件消息"""
        if not self.is_connected:
            self.monitor.error("Not connected to server")
            return None

        event_id = str(uuid.uuid4())
        payload = EventPayload(
            id=event_id,
            event=event_name,
            data={"from_agent": self.client_info.id, **(event_data or {})},
        )

        # 确定目标
        recipient = self._get_recipient(target_id, target_type)
        if not recipient:
            return None

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=recipient
        )

        if success:
            self.monitor.info(f"Sent event '{event_name}' with ID {event_id}")
            self.monitor.update_stats(已发送事件=event_name)
            return event_id
        else:
            self.monitor.error(f"Failed to send event '{event_name}'")
            return None

    async def send_stream():
        pass

    def _get_recipient(
        self, target_id: Optional[str], target_type: str
    ) -> Optional[ClientInfo]:
        """获取消息接收者信息"""
        if target_id:
            type_mapping = {
                "environment": ClientType.ENVIRONMENT,
                "agent": ClientType.AGENT,
                "human": ClientType.HUMAN,
            }
            client_type = type_mapping.get(target_type)
            if client_type:
                return ClientInfo(id=target_id, type=client_type)
            else:
                self.logger.error(f"Unknown target type: {target_type}")
                return None
        else:
            # 默认发送给环境
            return ClientInfo(id=self.env_id, type=ClientType.ENVIRONMENT)

    # -------- 连接生命周期 --------
    async def _on_connected(self) -> None:
        """连接成功后发送心跳消息表示连接"""
        await self.heartbeat()
        self.monitor.info("Sent heartbeat to establish connection")
