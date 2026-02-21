"""可监控 Mixin - 通过 Hub 转发版本

新架构优势：
- 复用现有 Hub 连接，无需额外服务器
- 无端口管理，无防火墙问题
- 中心化管理，支持多 Monitor 订阅
- 代码更简洁，更易维护
"""

import time
import logging
from enum import IntEnum
from typing import Optional, Set, Dict, Any

from star_protocol.models import Envelope, EnvelopeType, MonitorPayload, MonitorType


class MonitorLevel(IntEnum):
    """监控级别"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


class MonitorableMixin:
    """
    可监控 Mixin - 通过 Hub 转发版本
    
    为客户端添加监控能力：
    - 通过 Hub 发送监控数据
    - 自动发送状态变化
    - 自动发送消息副本
    - 可配置监控级别
    
    新架构：
    - Client 启用监控（发送控制消息到 Hub）
    - Monitor 订阅 Client（通过 Hub）
    - Client 发送监控数据到 Hub
    - Hub 转发给订阅的 Monitor
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._monitor_enabled = False
        self._monitor_level = MonitorLevel.INFO
        self._monitor_data_types: Optional[Set[str]] = None
        self.logger = getattr(self, 'logger', logging.getLogger(__name__))
    
    async def enable_monitoring(
        self,
        level: MonitorLevel = MonitorLevel.INFO,
        data_types: Optional[Set[str]] = None
    ) -> None:
        """
        启用监控功能
        
        Args:
            level: 监控级别
            data_types: 要监控的数据类型（None = 全部）
        """
        self._monitor_enabled = True
        self._monitor_level = level
        self._monitor_data_types = data_types
        
        # 发送控制消息到 Hub
        await self.send(Envelope(
            type=EnvelopeType.MONITOR,
            sender=self.client_id,
            recipient="hub",
            payload=MonitorPayload(
                type=MonitorType.CTRL,
                content={
                    "op": "enable",
                    "level": level.name
                }
            )
        ))
        
        self.logger.info(f"Monitoring enabled (level: {level.name})")
    
    async def disable_monitoring(self) -> None:
        """禁用监控功能"""
        if not self._monitor_enabled:
            return
        
        # 发送控制消息到 Hub
        await self.send(Envelope(
            type=EnvelopeType.MONITOR,
            sender=self.client_id,
            recipient="hub",
            payload=MonitorPayload(
                type=MonitorType.CTRL,
                content={"op": "disable"}
            )
        ))
        
        self._monitor_enabled = False
        self.logger.info("Monitoring disabled")

    async def send_monitor_data(
        self,
        data_type: str,
        data: Dict[str, Any],
    ) -> None:
        """
        应用层主动推送内部遥测事件到 Monitor。

        与 `_send_monitor_data` 的区别：
        - 这是公开 API，供应用层（如 Agent 内部执行节点）调用
        - `_send_monitor_data` 是协议层内部的自动钩子，由 SDK 调用
        - 两者底层机制相同，均通过 Hub 转发给订阅的 Monitor
        - 发送的是 MONITOR 类型信封，不会被 `_on_message_sent` 二次处理

        Args:
            data_type: 事件类型，建议用命名空间前缀，如 "agent:llm_response"
            data: 事件数据字典

        Example:
            await session.send_monitor_data("agent:llm_response", {"text": reply})
            await session.send_monitor_data("agent:tool_call", {"tool": "move", "args": {...}})
        """
        if not self._monitor_enabled:
            return
        await self._send_monitor_data(data_type, data)

    async def _send_monitor_data(
        self,
        data_type: str,
        data: Dict[str, Any]
    ) -> None:
        """
        发送监控数据到 Hub
        
        Args:
            data_type: 数据类型
            data: 数据内容
        """
        if not self._monitor_enabled:
            return
        
        # 检查数据类型过滤
        if self._monitor_data_types and data_type not in self._monitor_data_types:
            return
        
        # 发送监控数据到 Hub
        await self.send(Envelope(
            type=EnvelopeType.MONITOR,
            sender=self.client_id,
            recipient="hub",
            payload=MonitorPayload(
                type=MonitorType.DATA,
                content={
                    "data_type": data_type,
                    "data": data,
                    "timestamp": int(time.time() * 1000)
                }
            )
        ))
        
        self.logger.debug(f"Sent monitor data: {data_type}")
    
    async def _on_state_change(self, old_state: str, new_state: str, **kwargs) -> None:
        """状态变化时的回调（子类可重写）"""
        await self._send_monitor_data(
            "state_change",
            {
                "old_state": old_state,
                "new_state": new_state,
                **kwargs
            }
        )
    
    async def _on_message_sent(self, envelope: Envelope) -> None:
        """消息发送时的回调（子类可重写）"""
        # 避免监控自己的监控数据（防止无限递归）
        if envelope.type == EnvelopeType.MONITOR:
            return
        
        await self._send_monitor_data(
            "message_sent",
            {
                "envelope_type": envelope.type,
                "recipient": envelope.recipient,
                "payload_type": envelope.payload.type if hasattr(envelope.payload, 'type') else None,
                "content": envelope.payload.content if hasattr(envelope.payload, 'content') else None
            }
        )
    
    async def _on_message_received(self, envelope: Envelope) -> None:
        """消息接收时的回调（子类可重写）"""
        # 避免监控自己的监控数据
        if envelope.type == EnvelopeType.MONITOR:
            return
        
        await self._send_monitor_data(
            "message_received",
            {
                "envelope_type": envelope.type,
                "sender": envelope.sender,
                "payload_type": envelope.payload.type if hasattr(envelope.payload, 'type') else None,
                "content": envelope.payload.content if hasattr(envelope.payload, 'content') else None
            }
        )
    
    async def _on_error(self, error: dict, **kwargs) -> None:
        """错误发生时的回调（子类可重写）"""
        await self._send_monitor_data(
            "error",
            {
                "code": error.get("code", 500),
                "message": error.get("msg", str(error)),
                **kwargs,
            },
        )

    
    async def _handle_monitor(self, envelope: Envelope) -> None:
        """
        处理 Monitor 消息（符合 Star Protocol 规范）
        
        Args:
            envelope: 消息信封
        """
        payload = envelope.payload
        
        # 根据 MonitorType 分发
        if payload.type == MonitorType.NOTIFY:
            # 处理 Hub 的通知消息
            content = payload.content
            event = content.get("event")
            
            if event == "monitoring_enabled":
                level = content.get("level")
                self.logger.info(f"Monitoring enabled confirmed by Hub (level: {level})")
            elif event == "monitoring_disabled":
                self.logger.info("Monitoring disabled confirmed by Hub")
            else:
                self.logger.debug(f"Received monitor notify: {event}")
        
        elif payload.type == MonitorType.DATA:
            # MonitorableMixin 不应该接收 DATA 类型（只有 MonitorClient 接收）
            self.logger.warning(f"Unexpected MonitorType.DATA received by {self.client_id}")
        
        elif payload.type == MonitorType.CTRL:
            # MonitorableMixin 不应该接收 CTRL 类型（只发送不接收）
            self.logger.warning(f"Unexpected MonitorType.CTRL received by {self.client_id}")
