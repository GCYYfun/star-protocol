"""Star Protocol 消息格式定义

本模块定义了 Star Protocol 的核心消息结构，包括客户端信息和标准消息格式。
所有消息都提供了内置的 JSON 序列化和反序列化方法。
"""

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from .types import EnvelopeType, MessageType, ClientType
from .exceptions import SerializationException, ValidationException


@dataclass
class ClientInfo:
    """客户端信息"""

    client_id: str
    client_type: ClientType
    env_id: Optional[str] = None  # 环境ID（可选）
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典

        Returns:
            包含客户端信息的字典
        """
        result = {
            "client_id": self.client_id,
            "client_type": self.client_type.value,
        }
        if self.env_id is not None:
            result["env_id"] = self.env_id
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientInfo":
        """从字典反序列化

        Args:
            data: 包含客户端信息的字典

        Returns:
            ClientInfo 实例

        Raises:
            ValidationError: 当数据格式无效时
        """
        try:
            return cls(
                client_id=data["client_id"],
                client_type=ClientType(data["client_type"]),
                env_id=data.get("env_id"),
                metadata=data.get("metadata"),
            )
        except (KeyError, ValueError) as e:
            raise ValidationException(f"Invalid ClientInfo format: {e}")


# === 内层消息类型定义 ===


@dataclass
class ActionMessage:
    """动作消息"""

    message_type: str = MessageType.ACTION.value
    action: str = ""  # 动作类型 (move, observe, pickup, ping等)
    action_id: str = ""  # 动作唯一标识
    parameters: Dict[str, Any] = None  # 动作参数

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if not self.action_id:
            self.action_id = f"act_{str(uuid.uuid4())}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_type": self.message_type,
            "action": self.action,
            "action_id": self.action_id,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionMessage":
        try:
            return cls(
                action=data["action"],
                action_id=data["action_id"],
                parameters=data.get("parameters", {}),
            )
        except KeyError as e:
            raise ValidationException(f"Invalid ActionMessage format: {e}")


@dataclass
class OutcomeMessage:
    """结果消息"""

    message_type: MessageType = MessageType.OUTCOME
    action_id: str = ""  # 对应的动作ID
    status: str = ""  # 执行状态 (success/failure)
    outcome: Optional[Dict[str, Any]] = None  # 具体结果数据

    def __post_init__(self):
        if self.outcome is None:
            self.outcome = {}

    def to_dict(self) -> Dict[str, Any]:

        return {
            "message_type": self.message_type.value,
            "action_id": self.action_id,
            "status": self.status,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutcomeMessage":
        try:
            return cls(
                action_id=data["action_id"],
                status=data["status"],
                outcome=data.get("outcome", {}),
            )
        except KeyError as e:
            raise ValidationException(f"Invalid OutcomeMessage format: {e}")


@dataclass
class EventMessage:
    """事件消息"""

    message_type: MessageType = MessageType.EVENT
    event: str = ""  # 事件类型 (agent_moved, item_spawned, world_update等)
    event_id: str = ""  # 事件唯一标识
    data: Dict[str, Any] = None  # 事件数据

    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if not self.event_id:
            self.event_id = f"evt_{str(uuid.uuid4())}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_type": self.message_type.value,
            "event_id": self.event_id,
            "event": self.event,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventMessage":
        try:
            return cls(
                event=data["event"],
                event_id=data["event_id"],
                data=data.get("data", {}),
            )
        except KeyError as e:
            raise ValidationException(f"Invalid EventMessage format: {e}")


@dataclass
class StreamMessage:
    """数据流消息"""

    message_type: MessageType = MessageType.STREAM
    stream_id: str = ""  # 数据流ID
    stream: str = ""  # 数据流类型
    sequence: int = 0  # 序列号
    chunk: Dict[str, Any] = None  # 流数据

    def __post_init__(self):
        if self.chunk is None:
            self.chunk = {}
        if not self.stream_id:
            self.stream_id = f"strm_{str(uuid.uuid4())}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_type": self.message_type.value,
            "stream_id": self.stream_id,
            "stream": self.stream,
            "sequence": self.sequence,
            "chunk": self.chunk,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamMessage":
        try:
            return cls(
                stream=data["stream"],
                stream_id=data["stream_id"],
                sequence=data["sequence"],
                chunk=data.get("chunk", {}),
            )
        except KeyError as e:
            raise ValidationException(f"Invalid StreamMessage format: {e}")


@dataclass
class RegistrationMessage:
    """客户端注册消息"""

    message_type: str = MessageType.REGISTRATION.value
    client_info: ClientInfo = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "message_type": self.message_type,
            "client_info": self.client_info.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistrationMessage":
        """从字典反序列化"""
        try:
            return cls(client_info=ClientInfo.from_dict(data["client_info"]))
        except KeyError as e:
            raise ValidationException(f"Invalid RegistrationMessage format: {e}")


@dataclass
class HeartbeatInfo:
    """心跳信息"""

    status: str
    metrics: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        result = {"status": self.status}
        if self.metrics is not None:
            result["metrics"] = self.metrics
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HeartbeatInfo":
        """从字典反序列化"""
        try:
            return cls(
                status=data["status"],
                metrics=data.get("metrics"),
            )
        except KeyError as e:
            raise ValidationException(f"Invalid HeartbeatInfo format: {e}")


# Union 类型定义
Message = Union[
    ActionMessage,
    OutcomeMessage,
    EventMessage,
    StreamMessage,
    RegistrationMessage,
    HeartbeatInfo,
]


@dataclass
class ErrorInfo:
    """错误信息"""

    error_message: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        result = {
            "error_message": self.error_message,
        }
        if self.details is not None:
            result["details"] = self.details
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorInfo":
        """从字典反序列化"""
        try:
            return cls(
                error_message=data["error_message"],
                details=data.get("details"),
            )
        except KeyError as e:
            raise ValidationException(f"Invalid ErrorInfo format: {e}")


def message_from_dict(data: Dict[str, Any]) -> Message:
    """从字典创建消息（工厂函数）"""
    message_type = data.get("message_type")

    if message_type == "action":
        return ActionMessage.from_dict(data)
    elif message_type == "outcome":
        return OutcomeMessage.from_dict(data)
    elif message_type == "event":
        return EventMessage.from_dict(data)
    elif message_type == "stream":
        return StreamMessage.from_dict(data)
    elif message_type == "registration":
        return RegistrationMessage.from_dict(data)
    else:
        raise ValidationException(f"Unknown message_type: {message_type}")


@dataclass
class Envelope:
    """Star Protocol 信封消息格式

    根据协议规范，外层信封包含路由信息，内层message包含业务逻辑。
    """

    envelope_type: EnvelopeType
    sender: str  # 发送者ID
    recipient: str  # 接收者ID
    message: Message  # 内层消息（使用message字段，不是payload）
    envelope_id: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        """初始化后处理"""
        if self.envelope_id is None:
            self.envelope_id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典

        根据协议规范，外层结构应该是：
        {
          "type": "message",
          "sender": "sender_id",
          "recipient": "recipient_id",
          "message": { 内层消息 },
          "envelope_id": "uuid",
          "timestamp": 1234567890
        }
        """
        result = {
            "type": self.envelope_type.value,  # 外层协议使用 type 字段
            "sender": self.sender,
            "recipient": self.recipient,
            "message": self.message.to_dict(),  # 使用 message 字段，不是 payload
            "envelope_id": self.envelope_id,
            "timestamp": self.timestamp,
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Envelope":
        """从字典反序列化"""
        try:
            envelope_type = EnvelopeType(data["type"])

            # 心跳信封可能没有message字段
            if envelope_type == EnvelopeType.HEARTBEAT:
                # 为心跳创建一个默认的HeartbeatInfo
                message = HeartbeatInfo(status="alive")
            else:
                # 其他信封类型需要message字段
                message = message_from_dict(data["message"])

            return cls(
                envelope_type=envelope_type,
                sender=data["sender"],
                recipient=data["recipient"],
                message=message,
                envelope_id=data.get("envelope_id"),
                timestamp=data.get("timestamp"),
            )
        except (KeyError, ValueError) as e:
            raise ValidationException(f"Invalid Envelope format: {e}")

    def to_json(self) -> str:
        """序列化为JSON字符串"""
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False)
        except (TypeError, ValueError) as e:
            raise SerializationException(f"Failed to serialize message: {e}")

    @classmethod
    def from_json(cls, json_str: str) -> "Envelope":
        """从JSON字符串反序列化"""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            raise SerializationException(f"Invalid JSON format: {e}")
        except Exception as e:
            raise SerializationException(f"Failed to deserialize message: {e}")

    def validate(self) -> None:
        """验证消息格式"""
        if not isinstance(self.envelope_type, EnvelopeType):
            raise ValidationException("Invalid envelope_type")
        if not self.sender or not isinstance(self.sender, str):
            raise ValidationException("sender must be a non-empty string")
        if not self.recipient or not isinstance(self.recipient, str):
            raise ValidationException("recipient must be a non-empty string")
        if self.message is None:
            raise ValidationException("message cannot be None")
