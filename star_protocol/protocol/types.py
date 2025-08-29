"""Star Protocol 类型定义

本模块定义了 Star Protocol 的基础类型，包括消息类型和客户端类型的枚举。
所有枚举都提供了内置的序列化方法。
"""

from enum import Enum
from typing import Any, Dict


class EnvelopeType(Enum):
    """信封类型枚举

    定义了 Star Protocol 支持的所有信封类型。
    """

    HEARTBEAT = "heartbeat"
    MESSAGE = "message"
    ERROR = "error"


class MessageType(Enum):
    """消息类型枚举

    定义了 Star Protocol 支持的所有消息类型。
    """

    # 环境交互
    ACTION = "action"
    OUTCOME = "outcome"
    EVENT = "event"
    STREAM = "stream"
    REGISTRATION = "registration"


class ClientType(Enum):
    """客户端类型枚举

    定义了 Star Protocol 支持的客户端类型。
    """

    AGENT = "agent"
    ENVIRONMENT = "environment"
    HUMAN = "human"
