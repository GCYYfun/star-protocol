"""消息路由器"""

import logging
import time
from fastapi import WebSocket, WebSocketDisconnect

from star_protocol.server.connection import SessionManager, Session
from star_protocol.models import Envelope, SystemPayload, MonitorPayload, EnvelopeType, MonitorType


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
                {"message": "Connected to Star Protocol Hub"}
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
                        {"message": f"Environment {client_id} has been closed"}
                    )
                
                logger.info(f"Environment {client_id} closing, {len(members)} members notified")
            
            await self.connection_manager.remove_session(client_id)
    
    async def route_message(self, envelope: Envelope) -> None:
        """
        路由消息到目标
        
        Args:
            envelope: 消息信封
        """
        if envelope.type == "system":
            await self.handle_system_message(envelope)
        elif envelope.type == "message":
            await self.handle_unicast_message(envelope)
        elif envelope.type == "broadcast":
            await self.handle_broadcast_message(envelope)
        elif envelope.type == "monitor":
            await self.handle_monitor_message(envelope)
    
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
                        {"message": f"Joined environment {env_id}"}
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
                        {"message": f"Left environment {env_id}"}
                    )
                    logger.info(f"{envelope.sender} left {env_id}")
    
    async def handle_unicast_message(self, envelope: Envelope) -> None:
        """
        处理点对点消息
        
        Args:
            envelope: 消息信封
        """
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
        
        # 检查发送者是否在环境中
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
        recipient_env = self.connection_manager.get_client_environment(envelope.recipient)
        if recipient_env != sender_env:
            await self.send_error(
                envelope.sender,
                403,
                f"Recipient '{envelope.recipient}' is not in the same environment",
                envelope.id
            )
            return
        
        # 转发消息给接收者
        try:
            await target_session.websocket.send_text(envelope.model_dump_json())
            logger.debug(f"Routed message: {envelope.sender} -> {envelope.recipient}")
        except Exception as e:
            logger.error(f"Failed to send message to {envelope.recipient}: {e}")
            await self.send_error(
                envelope.sender,
                500,
                f"Failed to deliver message to {envelope.recipient}",
                envelope.id
            )
            return
        
        # 抄送给 Environment（如果 Environment 不是发送者或接收者）
        if sender_env != envelope.sender and sender_env != envelope.recipient:
            env_session = self.connection_manager.get_session(sender_env)
            if env_session:
                try:
                    await env_session.websocket.send_text(envelope.model_dump_json())
                    logger.debug(f"CC to environment: {sender_env}")
                except Exception as e:
                    logger.warning(f"Failed to CC message to environment {sender_env}: {e}")
    
    async def handle_broadcast_message(self, envelope: Envelope) -> None:
        """
        处理广播消息
        
        Args:
            envelope: 消息信封
        """
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
        members = self.connection_manager.get_environment_members(env_id)
        broadcast_count = 0
        
        for member_id in members:
            if member_id != envelope.sender:
                session = self.connection_manager.get_session(member_id)
                if session:
                    try:
                        await session.websocket.send_text(envelope.model_dump_json())
                        broadcast_count += 1
                    except Exception as e:
                        logger.error(f"Failed to broadcast to {member_id}: {e}")
        
        logger.debug(f"Broadcast from {envelope.sender} to {broadcast_count} clients")
    
    async def send_system_message(
        self,
        client_id: str,
        msg_type: str,
        content: dict
    ) -> None:
        """
        发送系统消息
        
        Args:
            client_id: 目标客户端 ID
            msg_type: 消息类型
            content: 消息内容
        """
        session = self.connection_manager.get_session(client_id)
        if not session:
            return
        
        envelope = Envelope(
            type="system",
            sender="hub",
            recipient=client_id,
            payload=SystemPayload(type=msg_type, content=content)
        )
        
        try:
            await session.websocket.send_text(envelope.model_dump_json())
        except Exception as e:
            logger.error(f"Failed to send system message to {client_id}: {e}")
    
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
                            content={"event": "monitoring_disabled"}
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
                                    "target_client_id": target
                                }
                            )
                        )
            
            # 发送响应
            if response:
                session = self.connection_manager.get_session(envelope.sender)
                if session:
                    await session.websocket.send_text(response.model_dump_json())
        
        elif payload.type == MonitorType.DATA:
            # 转发监控数据
            await self.connection_manager.forward_monitor_data(
                client_id=envelope.sender,
                data_type=payload.content.get("data_type"),
                payload=payload.content.get("data")
            )
    
    def get_uptime(self) -> float:
        """获取运行时间（秒）"""
        return time.time() - self.start_time
