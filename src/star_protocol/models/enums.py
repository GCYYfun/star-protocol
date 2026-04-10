"""枚举类型定义"""

from enum import Enum


class EnvelopeType(str, Enum):
    """信封类型枚举"""

    SYSTEM = "system"
    MESSAGE = "message"
    BROADCAST = "broadcast"
    MONITOR = "monitor"


class SystemType(str, Enum):
    """系统消息类型"""

    ERROR = "error"
    CTRL = "ctrl"
    NOTIFY = "notify"


class MessageType(str, Enum):
    """业务消息类型"""

    ACTION = "action"
    OUTCOME = "outcome"
    STREAM = "stream"
    EVENT = "event"


class BroadcastType(str, Enum):
    """广播消息类型"""

    EVENT = "event"
    STREAM = "stream"


class MonitorType(str, Enum):
    """监控消息类型"""

    CTRL = "ctrl"  # 控制命令
    DATA = "data"  # 监控数据
    NOTIFY = "notify"  # 通知


class ClientState(str, Enum):
    """客户端状态"""

    DISCONNECTED = "disconnected"
    HOME = "home"
    IN_ENV = "in_env"
