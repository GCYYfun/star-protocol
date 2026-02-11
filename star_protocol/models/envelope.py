"""Envelope 信封模型"""

import time
import uuid
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict

from .payloads import SystemPayload, MessagePayload, BroadcastPayload, MonitorPayload


class Envelope(BaseModel):
    """
    协议信封 - 所有消息的外层包装
    
    type 字段决定 payload 的类型：
    - type="system" -> payload 必须是 SystemPayload
    - type="message" -> payload 必须是 MessagePayload  
    - type="broadcast" -> payload 必须是 BroadcastPayload
    - type="monitor" -> payload 必须是 MonitorPayload
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": 1620000000000,
                "type": "message",
                "sender": "agent_01",
                "recipient": "env_main",
                "payload": {
                    "type": "action",
                    "content": {
                        "name": "move",
                        "x": 10,
                        "y": 5
                    }
                }
            }
        }
    )
    
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="消息唯一标识 (UUID v4)"
    )
    
    timestamp: int = Field(
        default_factory=lambda: int(time.time() * 1000),
        description="发送时间戳 (Unix ms)"
    )
    
    type: Literal["system", "message", "broadcast", "monitor"] = Field(
        description="消息类型，决定 payload 的结构"
    )
    
    sender: str = Field(
        description="发送者 ID"
    )
    
    recipient: str = Field(
        description="接收者 ID 或特殊目标 ('hub', '@all', '@env')"
    )
    
    payload: Union[SystemPayload, MessagePayload, BroadcastPayload, MonitorPayload] = Field(
        description="业务载荷，类型取决于 Envelope.type"
    )
    
    @field_validator('payload', mode='before')
    @classmethod
    def validate_payload_type(cls, v, info):
        """验证 payload 类型与 envelope type 匹配"""
        if info.data.get('type') == 'system' and not isinstance(v, (dict, SystemPayload)):
            raise ValueError("system type requires SystemPayload")
        elif info.data.get('type') == 'message' and not isinstance(v, (dict, MessagePayload)):
            raise ValueError("message type requires MessagePayload")
        elif info.data.get('type') == 'broadcast' and not isinstance(v, (dict, BroadcastPayload)):
            raise ValueError("broadcast type requires BroadcastPayload")
        elif info.data.get('type') == 'monitor' and not isinstance(v, (dict, MonitorPayload)):
            raise ValueError("monitor type requires MonitorPayload")
        return v

