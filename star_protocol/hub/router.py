"""
Star Protocol 消息路由器

负责消息的智能路由和分发
"""

import logging
from typing import Dict, List, Optional, Set
from ..protocol import Message, ClientInfo, ClientType, MessageParser, BroadcastHelper
from .session import SessionManager


class MessageRouter:
    """消息路由器"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.logger = logging.getLogger("message_router")

        # 路由规则配置
        self.routing_rules = {
            "agent_to_env": "direct",
            "env_to_agents": "broadcast_to_env",
            "human_to_env": "direct",
            "admin_commands": "privileged_only",
            "ping_pong": "echo_back",
        }

    async def route_message(self, message: Message) -> bool:
        """路由消息到目标"""
        try:
            sender = message.sender
            recipient = message.recipient

            self.logger.debug(
                f"Routing message from {sender.type.value}:{sender.id} "
                f"to {recipient.type.value}:{recipient.id}"
            )

            # 检查是否是广播消息
            if BroadcastHelper.is_broadcast_message(message):
                return await self._handle_broadcast_message(message)

            # 检查是否是 Hub 内部消息
            if recipient.type == ClientType.HUB:
                return await self._handle_hub_message(message)

            # 直接路由到目标客户端
            return await self._route_direct_message(message)

        except Exception as e:
            self.logger.error(f"Error routing message: {e}")
            return False

    async def _handle_broadcast_message(self, message: Message) -> bool:
        """处理广播消息"""
        recipient_id = message.recipient.id
        sender_id = message.sender.id
        message_json = MessageParser.to_json(message)

        # 环境内广播
        env_id = BroadcastHelper.extract_env_id_from_broadcast(recipient_id)
        if env_id:
            self.logger.info(f"Broadcasting to environment {env_id}")
            sent_count = await self.session_manager.broadcast_to_env(
                env_id, message_json, exclude={sender_id}
            )
            self.logger.debug(f"Broadcast sent to {sent_count} clients in env {env_id}")
            return sent_count > 0

        # 全局广播
        elif recipient_id in ["all", "broadcast"]:
            self.logger.info("Broadcasting to all clients")
            sent_count = await self.session_manager.broadcast_to_all(
                message_json, exclude={sender_id}
            )
            self.logger.debug(f"Global broadcast sent to {sent_count} clients")
            return sent_count > 0

        return False

    async def _handle_hub_message(self, message: Message) -> bool:
        """处理发送给 Hub 的消息"""
        # 这些消息通过 stream 类型在 message 载荷中发送
        payload = message.payload

        if isinstance(payload, dict) and payload.get("type") == "stream":
            stream_type = payload.get("stream_type", "")
            data = payload.get("data", {})

            # 版本协商
            if stream_type == "version_negotiate":
                return await self._handle_version_negotiate(message, data)

            # 管理员命令
            elif stream_type == "admin_command":
                return await self._handle_admin_command(message)

            # 获取环境列表
            elif stream_type == "get_environments":
                return await self._handle_get_environments(message)

            # 获取服务器统计
            elif stream_type == "get_server_stats":
                return await self._handle_get_server_stats(message)

        # 心跳消息
        elif message.type == "heartbeat":
            return await self._handle_heartbeat(message)

        self.logger.warning(f"Unhandled hub message: {message.type}")
        return False

    async def _route_direct_message(self, message: Message) -> bool:
        """直接路由消息到目标客户端"""
        recipient_id = message.recipient.id
        message_json = MessageParser.to_json(message)

        # 检查目标客户端是否存在
        if not self.session_manager.is_connected(recipient_id):
            self.logger.warning(f"Target client {recipient_id} not connected")
            await self._send_delivery_error(
                message.sender, recipient_id, "target_not_found"
            )
            return False

        # 发送消息
        success = await self.session_manager.send_to_client(recipient_id, message_json)

        if not success:
            await self._send_delivery_error(
                message.sender, recipient_id, "delivery_failed"
            )

        return success

    async def _handle_version_negotiate(self, message: Message, data: Dict) -> bool:
        """处理版本协商"""
        sender = message.sender
        supported_versions = data.get("supported_versions", [])
        preferred_version = data.get("preferred_version", "1.0")

        # 简单的版本协商逻辑
        server_version = "1.0"
        selected_version = (
            server_version
            if server_version in supported_versions
            else preferred_version
        )

        response = Message(
            type="message",
            sender=ClientInfo(id="server", type=ClientType.HUB),
            recipient=sender,
            payload={
                "type": "stream",
                "stream_type": "version_negotiate_response",
                "data": {
                    "selected_version": selected_version,
                    "server_version": server_version,
                },
            },
        )

        return await self.session_manager.send_to_client(
            sender.id, MessageParser.to_json(response)
        )

    async def _handle_connect_message(self, message: Message) -> bool:
        """处理连接消息"""
        sender = message.sender
        payload = message.payload

        if isinstance(payload, dict):
            action = payload.get("action", "")
            data = payload.get("data", {})

            # Agent 注册
            if action == "register" and sender.type == ClientType.AGENT:
                return await self._handle_agent_registration(message, data)

            # 认证请求
            elif action == "authenticate" and sender.type == ClientType.HUMAN:
                return await self._handle_authentication(message, data)

        return False

    async def _handle_agent_registration(self, message: Message, data: Dict) -> bool:
        """处理 Agent 注册"""
        sender = message.sender
        env_id = data.get("env_id")

        if not env_id:
            await self._send_error_response(
                sender, "missing_env_id", "Environment ID required"
            )
            return False

        # 检查环境是否存在
        if not self.session_manager.is_connected(env_id):
            await self._send_error_response(
                sender, "env_not_found", f"Environment {env_id} not found"
            )
            return False

        # 将 Agent 添加到环境
        self.session_manager.add_client_to_env(sender.id, env_id)

        # 转发注册请求给环境
        env_message = Message(
            type=message.type,
            sender=sender,
            recipient=ClientInfo(id=env_id, type=ClientType.ENVIRONMENT),
            payload=message.payload,
        )

        return await self._route_direct_message(env_message)

    async def _handle_authentication(self, message: Message, data: Dict) -> bool:
        """处理用户认证"""
        sender = message.sender
        username = data.get("username", "")
        token = data.get("token", "")

        # 简单的认证逻辑（实际应该更复杂）
        is_authenticated = bool(username and token)

        if is_authenticated:
            self.session_manager.set_authenticated(sender.id, True)
            self.session_manager.set_session_metadata(sender.id, "username", username)
            self.session_manager.set_session_metadata(
                sender.id, "role", data.get("role", "observer")
            )

        # 发送认证响应
        response = Message(
            type="connect",
            sender=ClientInfo(id="server", type=ClientType.HUB),
            recipient=sender,
            payload={
                "action": "authenticate_ack",
                "data": {
                    "status": "success" if is_authenticated else "failed",
                    "username": username,
                    "role": data.get("role", "observer"),
                },
            },
        )

        return await self.session_manager.send_to_client(
            sender.id, MessageParser.to_json(response)
        )

    async def _handle_disconnect_message(self, message: Message) -> bool:
        """处理断开连接消息"""
        sender = message.sender

        # 清理会话
        env_id = self.session_manager.get_client_env(sender.id)
        if env_id:
            self.session_manager.remove_client_from_env(sender.id, env_id)

        # 断开连接
        await self.session_manager.disconnect_client(sender.id)
        return True

    async def _handle_admin_command(self, message: Message) -> bool:
        """处理管理员命令"""
        sender = message.sender

        # 检查管理员权限
        role = self.session_manager.get_session_metadata(sender.id, "role")
        if role != "admin":
            await self._send_error_response(
                sender, "permission_denied", "Admin role required"
            )
            return False

        payload = message.payload
        if isinstance(payload, dict):
            command = payload.get("parameters", {}).get("command", "")
            params = payload.get("parameters", {}).get("params", {})

            if command == "spawn_item":
                return await self._handle_spawn_item_command(message, params)
            elif command == "kick_user":
                return await self._handle_kick_user_command(message, params)
            elif command == "broadcast_announcement":
                return await self._handle_broadcast_announcement(message, params)
            elif command == "get_server_stats":
                return await self._handle_get_server_stats(message)

        return False

    async def _handle_spawn_item_command(self, message: Message, params: Dict) -> bool:
        """处理生成物品命令"""
        env_id = params.get("env_id")
        if not env_id or not self.session_manager.is_connected(env_id):
            await self._send_error_response(
                message.sender, "env_not_found", "Environment not found"
            )
            return False

        # 转发给环境
        env_message = Message(
            type="message",
            sender=message.sender,
            recipient=ClientInfo(id=env_id, type=ClientType.ENVIRONMENT),
            payload={
                "type": "action",
                "id": message.payload.get("id", ""),
                "action": "spawn_item",
                "parameters": params,
            },
        )

        return await self._route_direct_message(env_message)

    async def _handle_kick_user_command(self, message: Message, params: Dict) -> bool:
        """处理踢出用户命令"""
        user_id = params.get("user_id")
        if not user_id:
            return False

        if self.session_manager.is_connected(user_id):
            await self.session_manager.disconnect_client(user_id)

        # 发送成功响应
        return await self._send_command_response(
            message.sender,
            message.payload.get("id", ""),
            {"status": "success", "message": f"User {user_id} kicked"},
        )

    async def _handle_broadcast_announcement(
        self, message: Message, params: Dict
    ) -> bool:
        """处理广播公告"""
        announcement = params.get("message", "")
        env_id = params.get("env_id")

        broadcast_message = Message(
            type="message",
            sender=ClientInfo(id="server", type=ClientType.HUB),
            recipient=(
                BroadcastHelper.create_env_broadcast_target(env_id)
                if env_id
                else BroadcastHelper.create_broadcast_target()
            ),
            payload={
                "type": "event",
                "id": f"announcement_{message.payload.get('id', '')}",
                "event": "announcement",
                "data": {"message": announcement},
            },
        )

        success = await self._handle_broadcast_message(broadcast_message)

        # 发送命令响应
        return await self._send_command_response(
            message.sender,
            message.payload.get("id", ""),
            {"status": "success", "broadcast_sent": success},
        )

    async def _handle_get_environments(self, message: Message) -> bool:
        """处理获取环境列表请求"""
        environments = self.session_manager.get_environments()

        response = Message(
            type="message",
            sender=ClientInfo(id="server", type=ClientType.HUB),
            recipient=message.sender,
            payload={
                "type": "outcome",
                "id": message.payload.get("id", ""),
                "outcome": {
                    "environments": [
                        {
                            "id": env_id,
                            "client_count": len(
                                self.session_manager.get_env_clients(env_id)
                            ),
                        }
                        for env_id in environments
                    ]
                },
                "outcome_type": "dict",
            },
        )

        return await self.session_manager.send_to_client(
            message.sender.id, MessageParser.to_json(response)
        )

    async def _handle_get_server_stats(self, message: Message) -> bool:
        """处理获取服务器统计请求"""
        stats = {
            "active_connections": self.session_manager.get_session_count(),
            "active_agents": len(self.session_manager.get_agents()),
            "active_environments": len(self.session_manager.get_environments()),
            "active_humans": len(self.session_manager.get_humans()),
            "active_env_count": self.session_manager.get_env_count(),
        }

        response = Message(
            type="message",
            sender=ClientInfo(id="server", type=ClientType.HUB),
            recipient=message.sender,
            payload={
                "type": "outcome",
                "id": message.payload.get("id", ""),
                "outcome": stats,
                "outcome_type": "dict",
            },
        )

        return await self.session_manager.send_to_client(
            message.sender.id, MessageParser.to_json(response)
        )

    async def _handle_heartbeat(self, message: Message) -> bool:
        """处理心跳消息"""
        sender = message.sender
        self.session_manager.update_heartbeat(sender.id)

        # 发送心跳响应
        pong_message = Message(
            type="heartbeat",
            sender=ClientInfo(id="server", type=ClientType.HUB),
            recipient=sender,
            payload={"pong": True},
        )

        return await self.session_manager.send_to_client(
            sender.id, MessageParser.to_json(pong_message)
        )

    async def _send_error_response(
        self, client: ClientInfo, error_type: str, message: str
    ) -> bool:
        """发送错误响应"""
        error_message = Message(
            type="error",
            sender=ClientInfo(id="server", type=ClientType.HUB),
            recipient=client,
            payload={
                "error_code": "ROUTER001",
                "error_type": error_type,
                "message": message,
                "details": {},
            },
        )

        return await self.session_manager.send_to_client(
            client.id, MessageParser.to_json(error_message)
        )

    async def _send_delivery_error(
        self, sender: ClientInfo, target_id: str, error_type: str
    ) -> bool:
        """发送投递错误通知"""
        return await self._send_error_response(
            sender, error_type, f"Failed to deliver message to {target_id}"
        )

    async def _send_command_response(
        self, client: ClientInfo, command_id: str, result: Dict
    ) -> bool:
        """发送命令执行结果"""
        response = Message(
            type="message",
            sender=ClientInfo(id="server", type=ClientType.HUB),
            recipient=client,
            payload={
                "type": "outcome",
                "id": command_id,
                "outcome": result,
                "outcome_type": "dict",
            },
        )

        return await self.session_manager.send_to_client(
            client.id, MessageParser.to_json(response)
        )
