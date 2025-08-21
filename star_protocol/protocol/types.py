"""
Star Protocol 核心类型定义

定义了协议中使用的所有数据类型和枚举
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Union
import uuid


class ClientType(Enum):
    """客户端类型枚举"""

    AGENT = "agent"
    ENVIRONMENT = "environment"  # 修正为 environment
    HUMAN = "human"
    HUB = "hub"


class MessageType(Enum):
    """消息类型枚举"""

    MESSAGE = "message"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class PayloadType(Enum):
    """消息载荷类型枚举"""

    ACTION = "action"
    OUTCOME = "outcome"
    EVENT = "event"
    STREAM = "stream"


class OutcomeType(Enum):
    """结果数据类型枚举"""

    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    DICT = "dict"
    LIST = "list"


@dataclass
class ClientInfo:
    """客户端信息"""

    id: str
    type: ClientType

    def to_dict(self) -> Dict[str, str]:
        return {"id": self.id, "type": self.type.value}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "ClientInfo":
        return cls(id=data["id"], type=ClientType(data["type"]))


@dataclass
class ActionPayload:
    """动作载荷"""

    type: str = "action"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "action": self.action,
            "parameters": self.parameters,
        }


@dataclass
class OutcomePayload:
    """结果载荷"""

    type: str = "outcome"
    id: str = ""
    outcome: Any = None
    outcome_type: str = "dict"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "outcome": self.outcome,
            "outcome_type": self.outcome_type,
        }


@dataclass
class EventPayload:
    """事件载荷"""

    type: str = "event"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "event": self.event,
            "data": self.data,
        }


@dataclass
class StreamPayload:
    """流载荷"""

    type: str = "stream"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stream: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "stream": self.stream,
            "data": self.data,
        }


PayloadUnion = Union[
    ActionPayload, OutcomePayload, EventPayload, StreamPayload, Dict[str, Any]
]


@dataclass
class Message:
    """Star Protocol 消息"""

    type: str
    sender: ClientInfo
    recipient: ClientInfo
    payload: PayloadUnion
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload_dict = (
            self.payload.to_dict() if hasattr(self.payload, "to_dict") else self.payload
        )
        return {
            "type": self.type,
            "sender": self.sender.to_dict(),
            "recipient": self.recipient.to_dict(),
            "payload": payload_dict,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            type=data["type"],
            sender=ClientInfo.from_dict(data["sender"]),
            recipient=ClientInfo.from_dict(data["recipient"]),
            payload=data["payload"],
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class ConnectionRequest:
    """连接请求"""

    action: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "data": self.data}


@dataclass
class ErrorPayload:
    """错误载荷"""

    error_code: str
    error_type: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "error_type": self.error_type,
            "message": self.message,
            "details": self.details,
        }
