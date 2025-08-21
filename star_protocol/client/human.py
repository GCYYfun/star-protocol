"""
Star Protocol Human 客户端

人类用户客户端实现 - 专注于消息传输
"""

import uuid
from typing import Any, Dict, Optional
from .base import BaseStarClient
from ..protocol import (
    ClientInfo,
    ClientType,
    ActionPayload,
    EventPayload,
    StreamPayload,
)


class HumanClient(BaseStarClient):
    """人类用户客户端 - 消息传输接口"""

    def __init__(
        self,
        user_id: str,
        validate_messages: bool = True,
        base_url: str = "ws://localhost",
        port: int = 9999,
    ):
        client_info = ClientInfo(id=user_id, type=ClientType.HUMAN)
        super().__init__(
            base_url=base_url,
            port=port,
            client_info=client_info,
            validate_messages=validate_messages,
        )

    def get_connection_url(self) -> str:
        """获取 Human 连接 URL"""
        return f"{self.server_url}/human/{self.client_info.id}"

    # -------- Authentication --------
    async def send_authentication(
        self,
        username: str,
        token: str,
        role: str = "observer",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """发送认证请求 - 使用 stream 消息类型"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        auth_id = str(uuid.uuid4())
        hub_info = ClientInfo(id="server", type=ClientType.HUB)

        # 使用流消息进行认证
        payload = StreamPayload(
            id=auth_id,
            stream="authentication",
            data={
                "username": username,
                "token": token,
                "role": role,
                **(metadata or {}),
            },
        )

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=hub_info
        )

        if success:
            self.logger.info(f"Authentication request sent for user {username}")
            self.monitor.update_stats(认证请求=username)
            return auth_id
        else:
            self.logger.error("Failed to send authentication request")
            return None

    # -------- Environment Interaction --------
    async def send_observe_request(
        self,
        env_id: str,
        observe_type: str = "general",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """发送观察环境请求"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        env_info = ClientInfo(id=env_id, type=ClientType.ENVIRONMENT)
        payload = ActionPayload(
            action="observe",
            parameters={
                "observe_type": observe_type,
                **(parameters or {}),
            },
        )

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=env_info
        )

        if success:
            self.logger.info(f"Observe request sent to environment {env_id}")
            return payload.id
        else:
            self.logger.error(f"Failed to send observe request to {env_id}")
            return None

    async def send_join_environment(
        self,
        env_id: str,
        join_mode: str = "spectator",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """发送加入环境请求"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        env_info = ClientInfo(id=env_id, type=ClientType.ENVIRONMENT)
        payload = ActionPayload(
            action="join_environment",
            parameters={
                "join_mode": join_mode,
                **(parameters or {}),
            },
        )

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=env_info
        )

        if success:
            self.logger.info(f"Join environment request sent to {env_id}")
            return payload.id
        else:
            self.logger.error(f"Failed to send join request to {env_id}")
            return None

    async def send_control_request(
        self,
        env_id: str,
        target_id: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """发送控制请求"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        env_info = ClientInfo(id=env_id, type=ClientType.ENVIRONMENT)
        payload = ActionPayload(
            action="control",
            parameters={
                "target_id": target_id,
                "control_action": action,
                **(parameters or {}),
            },
        )

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=env_info
        )

        if success:
            self.logger.info(f"Control request sent: {action} on {target_id}")
            return payload.id
        else:
            self.logger.error(f"Failed to send control request")
            return None

    # -------- Admin Commands --------
    async def send_admin_command(
        self,
        command: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """发送管理员命令 - 使用 stream 消息类型"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        command_id = str(uuid.uuid4())
        hub_info = ClientInfo(id="server", type=ClientType.HUB)

        # 使用流消息发送管理员命令
        payload = StreamPayload(
            id=command_id,
            stream="admin_command",
            data={
                "command": command,
                "parameters": parameters or {},
                "user_id": self.client_info.id,
            },
        )

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=hub_info
        )

        if success:
            self.logger.info(f"Admin command sent: {command}")
            self.monitor.update_stats(管理员命令=command)
            return command_id
        else:
            self.logger.error(f"Failed to send admin command: {command}")
            return None

    async def send_spawn_item_command(
        self,
        env_id: str,
        item_type: str,
        position: Dict[str, float],
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """发送生成物品命令"""
        return await self.send_admin_command(
            "spawn_item",
            {
                "env_id": env_id,
                "item_type": item_type,
                "position": position,
                "properties": properties or {},
            },
        )

    async def send_kick_user_command(
        self, user_id: str, reason: str = "No reason provided"
    ) -> Optional[str]:
        """发送踢出用户命令"""
        return await self.send_admin_command(
            "kick_user", {"user_id": user_id, "reason": reason}
        )

    async def send_broadcast_announcement(
        self, message: str, env_id: Optional[str] = None
    ) -> Optional[str]:
        """发送广播公告命令"""
        return await self.send_admin_command(
            "broadcast_announcement", {"message": message, "env_id": env_id}
        )

    # -------- Information Requests --------
    async def send_get_server_stats(self) -> Optional[str]:
        """发送获取服务器统计请求"""
        return await self.send_admin_command("get_server_stats")

    async def send_get_environment_list(self) -> Optional[str]:
        """发送获取环境列表请求 - 使用 stream 消息"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        request_id = str(uuid.uuid4())
        hub_info = ClientInfo(id="server", type=ClientType.HUB)

        # 使用流消息请求环境列表
        payload = StreamPayload(
            id=request_id,
            stream="get_environments",
            data={"user_id": self.client_info.id},
        )

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=hub_info
        )

        if success:
            self.logger.info("Environment list request sent")
            self.monitor.update_stats(环境列表请求=True)
            return request_id
        else:
            self.logger.error("Failed to send environment list request")
            return None

    # -------- Communication --------
    async def send_chat_message(
        self,
        message: str,
        target_id: Optional[str] = None,
        target_type: str = "environment",
    ) -> Optional[str]:
        """发送聊天消息"""
        if not self.is_connected:
            self.logger.error("Not connected to server")
            return None

        chat_id = str(uuid.uuid4())
        payload = EventPayload(
            id=chat_id,
            event="chat",
            data={
                "message": message,
                "target_id": target_id,
                "target_type": target_type,
            },
        )

        # 根据目标类型确定接收者
        if target_id:
            if target_type == "agent":
                recipient = ClientInfo(id=target_id, type=ClientType.AGENT)
            elif target_type == "environment":
                recipient = ClientInfo(id=target_id, type=ClientType.ENVIRONMENT)
            elif target_type == "human":
                recipient = ClientInfo(id=target_id, type=ClientType.HUMAN)
            else:
                self.logger.error(f"Unknown target type: {target_type}")
                return None
        else:
            # 广播到当前环境或全局
            recipient = ClientInfo(id="all", type=ClientType.HUB)

        success = await self.send_message(
            message_type="message", payload=payload.to_dict(), recipient=recipient
        )

        if success:
            self.logger.info(f"Chat message sent: {message[:50]}...")
            return chat_id
        else:
            self.logger.error("Failed to send chat message")
            return None

    async def send_private_message(
        self, target_user_id: str, message: str
    ) -> Optional[str]:
        """发送私人消息"""
        return await self.send_chat_message(
            message, target_id=target_user_id, target_type="human"
        )

    # -------- 连接生命周期 --------
    async def _on_connected(self) -> None:
        """连接成功后发送心跳消息表示连接"""

        await self.send_heartbeat()
        self.monitor.info("Sent heartbeat to establish connection")
