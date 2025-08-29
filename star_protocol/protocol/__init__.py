"""Star Protocol 协议核心模块"""

from .exceptions import (
    ProtocolException,
    ValidationException,
    SerializationException,
    MessageFormatException,
)
from .types import EnvelopeType, MessageType, ClientType
from .messages import (
    # 消息类型
    ActionMessage,
    OutcomeMessage,
    EventMessage,
    StreamMessage,
    RegistrationMessage,
    Message,  # Union 类型
    # 其他类
    Envelope,
    ClientInfo,
    HeartbeatInfo,
    ErrorInfo,
    # 工厂函数
    message_from_dict,
)

__all__ = [
    # 异常类
    "ProtocolException",
    "ValidationException",
    "SerializationException",
    "MessageFormatException",
    # 类型枚举
    "EnvelopeType",
    "MessageType",
    "ClientType",
    # 消息类型
    "ActionMessage",
    "OutcomeMessage",
    "EventMessage",
    "StreamMessage",
    "RegistrationMessage",
    "Message",  # Union 类型
    # 其他类
    "Envelope",
    "ClientInfo",
    "HeartbeatInfo",
    "ErrorInfo",
    # 工厂函数
    "message_from_dict",
]
