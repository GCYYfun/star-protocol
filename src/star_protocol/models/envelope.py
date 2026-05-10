"""Envelope 信封模型"""

import time
import uuid
from typing import Any, Dict, Literal, Optional, Union
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
        Union[SystemPayload, MessagePayload, BroadcastPayload, MonitorPayload, Dict[str, Any]]
    ] = Field(default=None, description="业务载荷，类型取决于 Envelope.type")

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload_type(cls, v, info):
        """
        验证 payload 类型与 envelope type 匹配，并强制转换为正确模型。

        容错策略：已知类型严格校验；未知 payload.type 或校验失败时 fallback
        到原始 dict 透传，确保 Hub 路由层不会因未知协议扩展而崩溃。
        """
        if not info.data:
            return v

        t = info.data.get("type")
        if v is None:
            return v

        def get_dict(v):
            if isinstance(v, (SystemPayload, MessagePayload, BroadcastPayload, MonitorPayload)):
                return v.model_dump()
            return v

        def try_validate(model_cls, v):
            """尝试用指定模型校验，失败时 fallback 到原始 dict（允许协议扩展透传）"""
            if isinstance(v, model_cls):
                return v
            try:
                return model_cls.model_validate(get_dict(v))
            except Exception:
                # payload.type 超出当前模型定义（如协议扩展的新类型）
                # fallback：作为 dict 透传，由目标客户端负责解析
                return get_dict(v) if not isinstance(v, dict) else v

        if t == "system":
            return try_validate(SystemPayload, v)
        elif t == "message":
            return try_validate(MessagePayload, v)
        elif t == "broadcast":
            return try_validate(BroadcastPayload, v)
        elif t == "monitor":
            return try_validate(MonitorPayload, v)

        return v
