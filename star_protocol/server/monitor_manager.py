"""Monitor 管理器 - Hub 端"""

import time
import logging
from typing import Dict, Set, Optional
from collections import defaultdict

from star_protocol.models import Envelope, EnvelopeType, MonitorPayload, MonitorType
from star_protocol.server.connection import SessionManager


class MonitorManager:
    """
    Hub 端的监控管理器
    
    职责：
    - 管理哪些 Client 启用了监控
    - 管理 Monitor 的订阅关系
    - 处理监控控制消息
    - 转发监控数据给订阅的 Monitor
    """
    
    def __init__(self):
        # 哪些 Client 启用了监控：{client_id: level}
        self.monitored_clients: Dict[str, str] = {}
        
        # 哪些 Monitor 订阅了哪些 Client：{client_id: {monitor_id1, monitor_id2, ...}}
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)
        
        self.logger = logging.getLogger(__name__)
    
    async def handle_monitor_ctrl(
        self,
        sender: str,
        content: dict,
        session_manager: SessionManager
    ) -> Optional[Envelope]:
        """
        处理 Monitor 控制消息
        
        Args:
            sender: 发送者 ID
            content: 控制消息内容
            connection_manager: Connection 管理器
        
        Returns:
            响应消息（如果有）
        """
        op = content.get("op")
        
        if op == "enable":
            # Client 启用监控
            level = content.get("level", "INFO")
            self.monitored_clients[sender] = level
            
            self.logger.info(f"Client {sender} enabled monitoring (level: {level})")
            
            return Envelope(
                type=EnvelopeType.MONITOR,
                sender="hub",
                recipient=sender,
                data=MonitorPayload(
                    type=MonitorType.NOTIFY,
                    content={
                        "event": "monitoring_enabled",
                        "level": level
                    }
                )
            )
        
        elif op == "disable":
            # Client 禁用监控
            self.monitored_clients.pop(sender, None)
            
            self.logger.info(f"Client {sender} disabled monitoring")
            
            return Envelope(
                type=EnvelopeType.MONITOR,
                sender="hub",
                recipient=sender,
                data=MonitorPayload(
                    type=MonitorType.NOTIFY,
                    content={"event": "monitoring_disabled"}
                )
            )
        
        elif op == "subscribe":
            # Monitor 订阅 Client
            target = content.get("target_client_id")
            if not target:
                self.logger.warning(f"Monitor {sender} subscribe missing target_client_id")
                return None
            
            self.subscriptions[target].add(sender)
            
            self.logger.info(f"Monitor {sender} subscribed to {target}")
            
            return Envelope(
                type=EnvelopeType.MONITOR,
                sender="hub",
                recipient=sender,
                data=MonitorPayload(
                    type=MonitorType.NOTIFY,
                    content={
                        "event": "subscribed",
                        "target_client_id": target
                    }
                )
            )
        
        elif op == "unsubscribe":
            # Monitor 取消订阅
            target = content.get("target_client_id")
            if not target:
                self.logger.warning(f"Monitor {sender} unsubscribe missing target_client_id")
                return None
            
            self.subscriptions[target].discard(sender)
            
            self.logger.info(f"Monitor {sender} unsubscribed from {target}")
            
            return Envelope(
                type=EnvelopeType.MONITOR,
                sender="hub",
                recipient=sender,
                data=MonitorPayload(
                    type=MonitorType.NOTIFY,
                    content={
                        "event": "unsubscribed",
                        "target_client_id": target
                    }
                )
            )
        
        else:
            self.logger.warning(f"Unknown monitor control op: {op}")
            return None
    
    async def forward_monitor_data(
        self,
        client_id: str,
        data_type: str,
        data: dict,
        session_manager: SessionManager
    ) -> None:
        """
        转发监控数据给订阅的 Monitor
        
        Args:
            client_id: 被监控的 Client ID
            data_type: 监控数据类型
            data: 监控数据内容
            connection_manager: Connection 管理器
        """
        # 检查是否有 Monitor 订阅此 Client
        if client_id not in self.subscriptions:
            return
        
        # 构建转发消息（保持原始 sender）
        envelope = Envelope(
            type=EnvelopeType.MONITOR,
            sender=client_id,  # 保持原始 Client ID
            recipient="",      # 稍后填充
            data=MonitorPayload(
                type=MonitorType.DATA,
                content={
                    "data_type": data_type,
                    "data": data,
                    "timestamp": int(time.time() * 1000)
                }
            )
        )
        
        # 转发给所有订阅的 Monitor
        for monitor_id in self.subscriptions[client_id]:
            envelope.recipient = monitor_id
            session = session_manager.get_session(monitor_id)
            if session:
                await session.websocket.send_text(envelope.model_dump_json())
                self.logger.debug(f"Forwarded {data_type} from {client_id} to {monitor_id}")
            else:
                self.logger.warning(f"Monitor {monitor_id} session not found")
    
    def is_monitored(self, client_id: str) -> bool:
        """检查 Client 是否启用了监控"""
        return client_id in self.monitored_clients
    
    def get_subscribers(self, client_id: str) -> Set[str]:
        """获取订阅某个 Client 的所有 Monitor"""
        return self.subscriptions.get(client_id, set())
    
    def cleanup_client(self, client_id: str) -> None:
        """清理 Client 的监控数据（Client 断开时调用）"""
        # 移除监控状态
        self.monitored_clients.pop(client_id, None)
        
        # 移除订阅关系
        self.subscriptions.pop(client_id, None)
        
        self.logger.info(f"Cleaned up monitoring data for {client_id}")
    
    def cleanup_monitor(self, monitor_id: str) -> None:
        """清理 Monitor 的订阅数据（Monitor 断开时调用）"""
        # 从所有订阅中移除此 Monitor
        for client_id in list(self.subscriptions.keys()):
            self.subscriptions[client_id].discard(monitor_id)
            if not self.subscriptions[client_id]:
                del self.subscriptions[client_id]
        
        self.logger.info(f"Cleaned up subscriptions for monitor {monitor_id}")
