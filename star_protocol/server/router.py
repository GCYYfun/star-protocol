"""Star Protocol 消息路由器"""

import logging
import time
from fastapi import WebSocket, WebSocketDisconnect

from star_protocol.server.connection import SessionManager, ClientRole, Session
from star_protocol.models import Envelope, SystemPayload, MonitorPayload, MonitorType, EnvelopeType

logger = logging.getLogger(__name__)


class MessageRouter:
    """
    消息路由核心
    
    职责：
    1. 处理 WebSocket 连接生命周期
    2. 路由消息到目标客户端
    3. 处理系统控制消息（join/leave）
    4. 错误处理和通知
    """
    
    def __init__(
        self,
        max_connections: int = 1000,
        heartbeat_interval: float = 30.0
    ):
        self.connection_manager = SessionManager(max_connections)
        self.heartbeat_interval = heartbeat_interval
        self.start_time = time.time()
    
    async def start(self) -> None:
        """启动路由器"""
        logger.info("Message router started")
    
    async def stop(self) -> None:
        """停止路由器"""
        logger.info("Stopping message router...")
        
        # 清理所有会话
        for client_id in list(self.connection_manager._sessions.keys()):
            await self.connection_manager.remove_session(client_id)
        
        logger.info("Message router stopped")
    
    async def handle_connection(
        self,
        websocket: WebSocket,
        role: str,
        client_id: str
    ) -> None:
        """
        处理 WebSocket 连接
        
        Args:
            websocket: WebSocket 连接
            role: 客户端角色
            client_id: 客户端 ID
        """
        # 创建会话
        session = await self.connection_manager.create_session(
            websocket, client_id, role
        )
        
        if not session:
            return
        
        logger.info(f"Client connected: {client_id} ({role})")
        
        # 如果是 Environment，记录环境创建
        if session.role.value == "environment":
            logger.info(f"Environment created: {client_id}")
        
        try:
            # 发送欢迎消息
            await self.send_system_message(
                client_id,
                "notify",
                {"event": "connected", "msg": "Connected to Star Protocol Hub"}
            )
            
            # 消息循环
            while True:
                # 接收消息
                data = await websocket.receive_text()
                envelope = Envelope.model_validate_json(data)
                
                logger.debug(f"Received from {client_id}: {envelope.type}")
                
                # 路由消息
                await self.route_message(envelope)
                
        except WebSocketDisconnect:
            logger.info(f"Client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"Error handling {client_id}: {e}")
        finally:
            # 清理会话
            # 如果是 Environment，先获取成员列表，然后通知所有成员
            if session.role.value == "environment":
                members = self.connection_manager.get_environment_members(client_id)
                
                # 通知所有成员环境即将关闭
                for member_id in members:
                    await self.send_system_message(
                        member_id,
                        "notify",
                        {"event": "environment_closed", "msg": f"Environment {client_id} has been closed"}
                    )
                
                logger.info(f"Environment {client_id} closing, {len(members)} members notified")
            
            await self.connection_manager.remove_session(client_id)
    
    async def route_message(self, envelope: Envelope) -> None:
        """
        路由消息到目标
        
        路由规则：
        1. Hub Monitor 接收所有非 monitor 协议的消息（系统监控）
        2. Monitor 只接收 monitor 协议的消息（业务监控）
        3. 其他消息正常路由
        
        Args:
            envelope: 消息信封
        """
        # 1. 广播给 Hub Monitor（系统监控）- 不包括 monitor 协议消息
        if envelope.type != "monitor":
            await self.handle_hub_monitors_message(envelope)
        
        # 2. 路由到目标
        if envelope.type == "system":
            await self.handle_system_message(envelope)
        elif envelope.type == "message":
            await self.handle_unicast_message(envelope)
        elif envelope.type == "broadcast":
            await self.handle_broadcast_message(envelope)
        elif envelope.type == "monitor":
            await self.handle_monitor_message(envelope)

    async def handle_hub_monitors_message(self, envelope: Envelope) -> None:
        """
        广播消息给所有 Hub Monitor 客户端（系统监控）
        
        Hub Monitor 接收所有非 monitor 协议的消息，用于系统监控和调试
        
        Args:
            envelope: 消息信封
        """

        
        hub_monitors = self.connection_manager.get_sessions_by_role(ClientRole.HUB_MONITOR)
        
        for monitor_session in hub_monitors:
            try:
                await monitor_session.websocket.send_text(envelope.model_dump_json())
            except Exception as e:
                logger.warning(f"Failed to send to hub_monitor {monitor_session.client_id}: {e}")

    # Handle   

    async def handle_system_message(self, envelope: Envelope) -> None:
        """
        处理系统消息
        
        Args:
            envelope: 消息信封
        """
        payload = envelope.payload
        
        if payload.type == "ctrl":
            op = payload.content.get("op")
            
            if op == "join":
                env_id = payload.content.get("env_id")
                
                # 检查环境是否存在
                if not self.connection_manager.environment_exists(env_id):
                    await self.send_error(
                        envelope.sender,
                        404,
                        f"Environment '{env_id}' does not exist",
                        envelope.id
                    )
                    logger.warning(
                        f"{envelope.sender} tried to join non-existent environment {env_id}"
                    )
                    return
                
                # 加入环境
                success = self.connection_manager.join_environment(
                    envelope.sender, env_id
                )
                
                if success:
                    # 发送确认
                    await self.send_system_message(
                        envelope.sender,
                        "notify",
                        {"event": "joined", "msg": f"Joined environment {env_id}", "env_id": env_id}
                    )
                    logger.info(f"{envelope.sender} joined {env_id}")
                else:
                    await self.send_error(
                        envelope.sender,
                        500,
                        f"Failed to join environment {env_id}",
                        envelope.id
                    )
            
            elif op == "leave":
                env_id = self.connection_manager.get_client_environment(envelope.sender)
                
                if not env_id:
                    await self.send_error(
                        envelope.sender,
                        400,
                        "Not in any environment",
                        envelope.id
                    )
                    return
                
                # 离开环境
                success = self.connection_manager.leave_environment(envelope.sender)
                
                if success:
                    # 发送确认
                    await self.send_system_message(
                        envelope.sender,
                        "notify",
                        {"event": "left", "msg": f"Left environment {env_id}", "env_id": env_id}
                    )
                    logger.info(f"{envelope.sender} left {env_id}")
    
    async def handle_unicast_message(self, envelope: Envelope) -> None:
        """
        处理点对点消息
        
        Args:
            envelope: 消息信封
        """
        # 协议防护：message 类型不应该发送给 hub
        if envelope.recipient == "hub":
            await self.send_error(
                envelope.sender,
                400,
                "Invalid recipient: 'message' type should not be sent to hub. Use 'system' type instead.",
                envelope.id
            )
            return
        
        sender_session = self.connection_manager.get_session(envelope.sender)
        target_session = self.connection_manager.get_session(envelope.recipient)
        
        # 检查接收者是否存在
        if not target_session:
            await self.send_error(
                envelope.sender,
                404,
                f"Recipient '{envelope.recipient}' not found",
                envelope.id
            )
            return
        
        # 检查发送者是否在环境中（Environment 角色除外）
        sender_session = self.connection_manager.get_session(envelope.sender)
        
        # Environment 角色特殊处理：它本身就是环境，不需要"在环境中"
        if sender_session.role == ClientRole.ENVIRONMENT:
            # Environment 发送消息给其成员
            # 检查接收者是否在这个环境中
            recipient_env = self.connection_manager.get_client_environment(envelope.recipient)
            if recipient_env != envelope.sender:
                await self.send_error(
                    envelope.sender,
                    403,
                    f"Recipient '{envelope.recipient}' is not in your environment",
                    envelope.id
                )
                return
        else:
            # Agent/Human 发送消息
            sender_env = self.connection_manager.get_client_environment(envelope.sender)
            if not sender_env:
                await self.send_error(
                    envelope.sender,
                    403,
                    "Must be in an environment to send messages",
                    envelope.id
                )
                return
            
            # 检查接收者是否在同一环境
            # 特殊情况：如果接收者是 Environment 角色，检查其 client_id 是否等于发送者的环境
            if target_session.role == ClientRole.ENVIRONMENT:
                # Agent/Human -> Environment: 检查 environment 的 client_id 是否等于发送者的环境
                if target_session.client_id != sender_env:
                    await self.send_error(
                        envelope.sender,
                        403,
                        f"Recipient environment '{envelope.recipient}' is not your current environment (you are in '{sender_env}')",
                        envelope.id
                    )
                    return
            else:
                # Agent/Human -> Agent/Human: 检查是否在同一环境
                recipient_env = self.connection_manager.get_client_environment(envelope.recipient)
                if recipient_env != sender_env:
                    await self.send_error(
                        envelope.sender,
                        403,
                        f"Recipient '{envelope.recipient}' is not in the same environment",
                        envelope.id
                    )
                    return
        
        # 转发消息给接收者（来自客户端，不重复监控）
        await self.send_message(envelope, from_client=True)
        
        # 抄送给 Environment（仅 Agent/Human 之间的消息需要抄送）
        # Environment 发送的消息不需要抄送
        if sender_session.role != ClientRole.ENVIRONMENT:
            sender_env = self.connection_manager.get_client_environment(envelope.sender)
            if sender_env and sender_env != envelope.sender and sender_env != envelope.recipient:
                env_envelope = Envelope(
                    id=envelope.id,
                    timestamp=envelope.timestamp,
                    type=envelope.type,
                    sender=envelope.sender,
                    recipient=sender_env,
                    payload=envelope.payload
                )
                await self.send_message(env_envelope, from_client=True)  # 转发，不重复监控
    
    async def handle_broadcast_message(self, envelope: Envelope) -> None:
        """
        处理广播消息
        
        Args:
            envelope: 消息信封
        """
        # 协议防护：broadcast 类型不应该发送给 hub
        if envelope.recipient == "hub":
            await self.send_error(
                envelope.sender,
                400,
                "Invalid recipient: 'broadcast' type should not be sent to hub.",
                envelope.id
            )
            return
        
        # 获取发送者所在环境
        env_id = self.connection_manager.get_client_environment(envelope.sender)
        
        if not env_id:
            await self.send_error(
                envelope.sender,
                403,
                "Not in any environment",
                envelope.id
            )
            return
        
        # 广播给环境内所有成员（除了发送者）
        # 使用 @env 作为 recipient，send_message 会处理广播逻辑
        broadcast_envelope = Envelope(
            id=envelope.id,
            timestamp=envelope.timestamp,
            type=envelope.type,
            sender=envelope.sender,
            recipient="@env",
            payload=envelope.payload
        )
        await self.send_message(broadcast_envelope, from_client=True)  # 来自客户端
        
        logger.debug(f"Broadcast from {envelope.sender} to environment {env_id}")
    
    async def handle_monitor_message(self, envelope: Envelope) -> None:
        """
        处理 Monitor 消息
        
        Args:
            envelope: 消息信封
        """
        
        payload = envelope.payload
        
        if payload.type == MonitorType.CTRL:
            # 处理控制命令
            op = payload.content.get("op")
            response = None
            
            if op == "enable":
                # Client 启用监控
                level = payload.content.get("level", "INFO")
                success = self.connection_manager.enable_monitoring(envelope.sender, level)
                
                if success:
                    response = Envelope(
                        type=EnvelopeType.MONITOR,
                        sender="hub",
                        recipient=envelope.sender,
                        payload=MonitorPayload(
                            type=MonitorType.NOTIFY,
                            content={
                                "event": "monitoring_enabled",
                                "msg": "Monitoring is now enabled",
                                "level": level
                            }
                        )
                    )
            
            elif op == "disable":
                # Client 禁用监控
                success = self.connection_manager.disable_monitoring(envelope.sender)
                
                if success:
                    response = Envelope(
                        type=EnvelopeType.MONITOR,
                        sender="hub",
                        recipient=envelope.sender,
                        payload=MonitorPayload(
                            type=MonitorType.NOTIFY,
                            content={"event": "monitoring_disabled", "msg": "Monitoring is now disabled"}
                        )
                    )
            
            elif op == "subscribe":
                # Monitor 订阅 Client
                target = payload.content.get("target_client_id")
                if target:
                    success = self.connection_manager.subscribe_monitor(envelope.sender, target)
                    
                    if success:
                        response = Envelope(
                            type=EnvelopeType.MONITOR,
                            sender="hub",
                            recipient=envelope.sender,
                            payload=MonitorPayload(
                                type=MonitorType.NOTIFY,
                                content={
                                    "event": "subscribed",
                                    "msg": f"Subscribed to {target}",
                                    "target_client_id": target
                                }
                            )
                        )
            
            elif op == "unsubscribe":
                # Monitor 取消订阅
                target = payload.content.get("target_client_id")
                if target:
                    success = self.connection_manager.unsubscribe_monitor(envelope.sender, target)
                    
                    if success:
                        response = Envelope(
                            type=EnvelopeType.MONITOR,
                            sender="hub",
                            recipient=envelope.sender,
                            payload=MonitorPayload(
                                type=MonitorType.NOTIFY,
                                content={
                                    "event": "unsubscribed",
                                    "msg": f"Unsubscribed from {target}",
                                    "target_client_id": target
                                }
                            )
                        )
            
            # 发送响应（使用统一接口）
            if response:
                await self.send_message(response, from_client=False)  # Hub 发送，需要监控
        
        elif payload.type == MonitorType.DATA:
            # 转发监控数据
            await self.connection_manager.forward_monitor_data(
                client_id=envelope.sender,
                name=payload.content.get("name"),
                data=payload.content.get("data")
            )
    
    # Send

    async def send_system_message(
        self,
        client_id: str,
        msg_type: str,
        content: dict
    ) -> None:
        """
        Hub 发送系统消息
        
        通过 send_message 发送，确保 hub_monitor 可见
        
        Args:
            client_id: 目标客户端 ID
            msg_type: 消息类型 (error, ctrl, notify)
            content: 消息内容
        """
        envelope = Envelope(
            type="system",
            sender="hub",
            recipient=client_id,
            payload=SystemPayload(type=msg_type, content=content)
        )
        
        # 使用统一接口发送，hub_monitor 可以监控到
        await self.send_message(envelope, from_client=False)  # Hub 主动发送
    
    
    # Unified Message Sending Interface
    
    async def send_message(self, envelope: Envelope, from_client: bool = False) -> None:
        """
        统一的消息发送接口
        
        所有消息（包括 hub 发送的）都通过此方法，确保：
        1. Hub_monitor 可以监控到所有消息
        2. 消息格式统一
        3. 错误处理统一
        
        Args:
            envelope: 要发送的消息信封
            from_client: 是否来自客户端转发（True=已在route_message中监控，False=Hub主动发送需要监控）
        """
        # 1. 广播给 hub_monitor（只监控 Hub 主动发送的消息，避免重复）
        if not from_client and envelope.type != "monitor":
            await self.handle_hub_monitors_message(envelope)
        
        # 2. 发送给目标
        if envelope.recipient == "hub":
            # Hub 接收消息，不需要发送
            logger.debug(f"Message to hub: {envelope.type} from {envelope.sender}")
            return
        elif envelope.recipient.startswith("@"):
            # 广播消息
            await self._send_broadcast(envelope)
        else:
            # 单播消息
            await self._send_unicast(envelope)
    
    async def _send_unicast(self, envelope: Envelope) -> None:
        """
        发送单播消息给特定客户端
        
        Args:
            envelope: 消息信封
        """
        session = self.connection_manager.get_session(envelope.recipient)
        if not session:
            logger.warning(f"Recipient {envelope.recipient} not found")
            return
        
        try:
            await session.websocket.send_text(envelope.model_dump_json())
            logger.debug(f"Sent {envelope.type} to {envelope.recipient}")
        except Exception as e:
            logger.error(f"Failed to send to {envelope.recipient}: {e}")
    
    async def _send_broadcast(self, envelope: Envelope) -> None:
        """
        发送广播消息
        
        Args:
            envelope: 消息信封
        """
        sessions = []
        
        if envelope.recipient == "@all":
            # 广播给所有客户端
            sessions = list(self.connection_manager._sessions.values())
        elif envelope.recipient == "@env":
            # 广播给环境内所有成员
            sender_env = self.connection_manager.get_client_environment(envelope.sender)
            if not sender_env:
                logger.warning(f"Sender {envelope.sender} not in any environment")
                return
            member_ids = self.connection_manager.get_environment_members(sender_env)
            sessions = [self.connection_manager.get_session(mid) for mid in member_ids]
            sessions = [s for s in sessions if s]
        else:
            logger.warning(f"Unknown broadcast target: {envelope.recipient}")
            return
        
        # 发送给所有目标（排除发送者自己）
        for session in sessions:
            if session.client_id == envelope.sender:
                continue  # 跳过发送者自己
            
            try:
                await session.websocket.send_text(envelope.model_dump_json())
            except Exception as e:
                logger.warning(f"Failed to broadcast to {session.client_id}: {e}")
    
    async def send_error(
        self,
        client_id: str,
        code: int,
        message: str,
        original_msg_id: str
    ) -> None:
        """
        发送错误消息
        
        Args:
            client_id: 目标客户端 ID
            code: 错误代码
            message: 错误消息
            original_msg_id: 原始消息 ID
        """
        await self.send_system_message(
            client_id,
            "error",
            {
                "code": code,
                "msg": message,
                "original_msg_id": original_msg_id
            }
        )
    
    # Utils

    def get_uptime(self) -> float:
        """获取运行时间（秒）"""
        return time.time() - self.start_time
