"""Monitor 客户端 - 通过 Hub 订阅版本"""

import time
import logging
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque

from star_protocol.client.base import BaseClient
from star_protocol.models import Envelope, EnvelopeType, MonitorPayload, MonitorType


class InMemoryStorage:
    """内存存储后端"""
    
    def __init__(self, max_messages_per_client: int = 1000):
        self.max_messages = max_messages_per_client
        self._data: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.max_messages))
        )
        self._stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
    
    async def save(self, client_id: str, data_type: str, data: Dict[str, Any]) -> None:
        """保存数据"""
        self._data[client_id][data_type].append({
            "timestamp": time.time(),
            "data": data
        })
        self._stats[client_id][f"{data_type}_count"] += 1
    
    async def get_messages(
        self,
        client_id: str,
        data_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """获取消息历史"""
        if data_type:
            messages = list(self._data[client_id][data_type])
        else:
            # 合并所有类型的消息
            messages = []
            for dtype, msgs in self._data[client_id].items():
                for msg in msgs:
                    messages.append({**msg, "type": dtype})
            messages.sort(key=lambda x: x["timestamp"])
        
        return messages[-limit:]
    
    async def get_stats(self, client_id: str) -> Dict:
        """获取统计信息"""
        return dict(self._stats[client_id])
    
    async def get_all_clients(self) -> List[str]:
        """获取所有被监控的客户端"""
        return list(self._data.keys())


class MonitorClient(BaseClient):
    """
    Monitor 客户端 - 通过 Hub 订阅版本
    
    用于监控和可视化其他客户端的行为：
    - 通过 Hub 订阅 Client 的监控数据
    - 接收 Hub 转发的监控数据
    - 存储和查询监控数据
    - 提供统计和分析接口
    
    新架构：
    - Monitor 连接到 Hub
    - Monitor 订阅 Client（通过 Hub）
    - Hub 转发 Client 的监控数据给 Monitor
    - Monitor 存储和分析数据
    """
    
    def __init__(
        self,
        monitor_id: str,
        storage: Optional[InMemoryStorage] = None,
        **kwargs
    ):
        """
        初始化 Monitor 客户端
        
        Args:
            monitor_id: Monitor ID
            storage: 存储后端（默认使用内存存储）
            **kwargs: 传递给 BaseClient 的其他参数
        """
        # 先调用父类初始化
        super().__init__(
            client_id=monitor_id,
            role="monitor",
            **kwargs
        )
        
        # 初始化 Monitor 特有属性
        self.storage = storage or InMemoryStorage()
        self._subscribed_clients: set = set()
        
        # 注册 Monitor 消息处理器
        self._messaging.register_handler("monitor", self._handle_monitor_message)
    
    async def subscribe_to_client(self, client_id: str) -> None:
        """
        订阅 Client 的监控数据
        
        Args:
            client_id: 要订阅的 Client ID
        """
        if client_id in self._subscribed_clients:
            self.logger.warning(f"Already subscribed to {client_id}")
            return
        
        # 发送订阅请求到 Hub
        await self.send(Envelope(
            type=EnvelopeType.MONITOR,
            sender=self.client_id,
            recipient="hub",
            data=MonitorPayload(
                type=MonitorType.CTRL,
                content={
                    "op": "subscribe",
                    "target_client_id": client_id
                }
            )
        ))
        
        self._subscribed_clients.add(client_id)
        self.logger.info(f"Subscribed to {client_id}")
    
    async def unsubscribe_from_client(self, client_id: str) -> None:
        """
        取消订阅 Client
        
        Args:
            client_id: 要取消订阅的 Client ID
        """
        if client_id not in self._subscribed_clients:
            self.logger.warning(f"Not subscribed to {client_id}")
            return
        
        # 发送取消订阅请求到 Hub
        await self.send(Envelope(
            type=EnvelopeType.MONITOR,
            sender=self.client_id,
            recipient="hub",
            data=MonitorPayload(
                type=MonitorType.CTRL,
                content={
                    "op": "unsubscribe",
                    "target_client_id": client_id
                }
            )
        ))
        
        self._subscribed_clients.discard(client_id)
        self.logger.info(f"Unsubscribed from {client_id}")
    
    async def _handle_monitor_message(self, envelope: Envelope) -> None:
        """
        处理 Monitor 消息
        
        Args:
            envelope: 消息信封
        """
        payload = envelope.payload
        
        if payload.type == MonitorType.NOTIFY:
            # 处理通知
            await self._handle_monitor_notify(payload.content)
        
        elif payload.type == MonitorType.DATA:
            # 处理监控数据
            client_id = envelope.sender  # 从 sender 获取 client_id
            data_type = payload.content.get("data_type")
            data = payload.content.get("data")
            
            # 存储数据
            await self.storage.save(client_id, data_type, data)
            
            # 触发回调
            await self.on_monitor_data(client_id, data_type, data)
    
    async def _handle_monitor_notify(self, content: Dict[str, Any]) -> None:
        """处理 Monitor 通知"""
        event = content.get("event")
        
        if event == "subscribed":
            target = content.get("target_client_id")
            self.logger.info(f"Subscription confirmed for {target}")
        
        elif event == "unsubscribed":
            target = content.get("target_client_id")
            self.logger.info(f"Unsubscription confirmed for {target}")
        
        else:
            self.logger.debug(f"Monitor notify: {event}")
    
    async def on_monitor_data(
        self,
        client_id: str,
        data_type: str,
        data: Dict[str, Any]
    ) -> None:
        """
        监控数据回调（子类可重写）
        
        Args:
            client_id: 被监控的 Client ID
            data_type: 数据类型
            data: 数据内容
        """
        self.logger.debug(f"Received {data_type} from {client_id}: {data}")
    
    # 查询接口
    
    async def get_client_messages(
        self,
        client_id: str,
        data_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        获取 Client 的消息历史
        
        Args:
            client_id: Client ID
            data_type: 数据类型（None = 全部）
            limit: 返回数量限制
        
        Returns:
            消息列表
        """
        return await self.storage.get_messages(client_id, data_type, limit)
    
    async def get_client_stats(self, client_id: str) -> Dict:
        """
        获取 Client 的统计信息
        
        Args:
            client_id: Client ID
        
        Returns:
            统计信息字典
        """
        return await self.storage.get_stats(client_id)
    
    async def get_all_monitored_clients(self) -> List[str]:
        """
        获取所有被监控的客户端
        
        Returns:
            Client ID 列表
        """
        return await self.storage.get_all_clients()
    
    def get_subscribed_clients(self) -> set:
        """
        获取当前订阅的客户端
        
        Returns:
            订阅的 Client ID 集合
        """
        return self._subscribed_clients.copy()
    
    # 实现抽象方法（Monitor 不处理业务消息）
    
    async def on_message(self, envelope: Envelope) -> None:
        """处理业务消息（Monitor 不处理）"""
        pass
    
    async def on_broadcast(self, envelope: Envelope) -> None:
        """处理广播消息（Monitor 不处理）"""
        pass
