"""Envelope 信封模型"""

import time
import uuid
from typing import Literal, Optional, Union
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
                    "content": {"name": "move", "params": {"x": 10, "y": 5}},
                },
            }
        }
    )

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="消息唯一标识 (UUID v4)"
    )

    timestamp: int = Field(
        default_factory=lambda: int(time.time() * 1000),
        description="发送时间戳 (Unix ms)",
    )

    type: Literal["system", "message", "broadcast", "monitor"] = Field(
        default="message", description="消息类型，决定 payload 的结构"
    )

    sender: str = Field(default="", description="发送者 ID")

    recipient: str = Field(
        default="", description="接收者 ID 或特殊目标 ('hub', '@all', '@env')"
    )

    payload: Optional[
        Union[SystemPayload, MessagePayload, BroadcastPayload, MonitorPayload]
    ] = Field(default=None, description="业务载荷，类型取决于 Envelope.type")

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload_type(cls, v, info):
        """验证 payload 类型与 envelope type 匹配，并强制转换为正确模型"""
        t = info.data.get("type")
        if v is None:
            return v

        # 使用 info.data.get("type") 强制进行特定的模型校验和加载
        # 避免 Union 在有重叠 Literal (如 "event", "stream") 时匹配错误
        try:
            if t == "system":
                return (
                    SystemPayload.model_validate(v)
                    if not isinstance(v, SystemPayload)
                    else v
                )
            elif t == "message":
                return (
                    MessagePayload.model_validate(v)
                    if not isinstance(v, MessagePayload)
                    else v
                )
            elif t == "broadcast":
                return (
                    BroadcastPayload.model_validate(v)
                    if not isinstance(v, BroadcastPayload)
                    else v
                )
            elif t == "monitor":
                return (
                    MonitorPayload.model_validate(v)
                    if not isinstance(v, MonitorPayload)
                    else v
                )
        except Exception as e:
            raise ValueError(f"{t} type validation failed: {str(e)}")

        return v
