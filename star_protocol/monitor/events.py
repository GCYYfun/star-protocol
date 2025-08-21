"""
监控事件定义

定义监控系统中的事件类型和事件数据结构
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Union
import uuid


class EventType(Enum):
    """监控事件类型"""

    # 连接事件
    CONNECTION_ESTABLISHED = "connection_established"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_FAILED = "connection_failed"
    CONNECTION_RETRY = "connection_retry"

    # 消息事件
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_FAILED = "message_failed"
    MESSAGE_TIMEOUT = "message_timeout"

    # 性能事件
    PERFORMANCE_METRIC = "performance_metric"
    LATENCY_HIGH = "latency_high"
    THROUGHPUT_LOW = "throughput_low"
    MEMORY_HIGH = "memory_high"

    # 错误事件
    ERROR_OCCURRED = "error_occurred"
    WARNING_ISSUED = "warning_issued"
    EXCEPTION_CAUGHT = "exception_caught"

    # 状态事件
    STATUS_CHANGED = "status_changed"
    HEALTH_CHECK = "health_check"

    # 业务事件
    ACTION_EXECUTED = "action_executed"
    EVENT_BROADCAST = "event_broadcast"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"

    # 系统事件
    MONITOR_STARTED = "monitor_started"
    MONITOR_STOPPED = "monitor_stopped"
    CLEANUP_PERFORMED = "cleanup_performed"


@dataclass
class MonitorEvent:
    """监控事件数据结构"""

    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""  # 事件来源 (client_id, agent_id, etc.)
    source_type: str = ""  # 来源类型 (agent, environment, human, hub)

    # 事件数据
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    # 分类信息
    severity: str = "info"  # debug, info, warning, error, critical
    category: str = ""  # network, performance, business, system

    # 关联信息
    session_id: Optional[str] = None
    environment_id: Optional[str] = None
    user_id: Optional[str] = None

    # 性能指标
    duration_ms: Optional[float] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None

    # 异常信息
    exception: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "source_type": self.source_type,
            "message": self.message,
            "data": self.data,
            "severity": self.severity,
            "category": self.category,
            "session_id": self.session_id,
            "environment_id": self.environment_id,
            "user_id": self.user_id,
            "duration_ms": self.duration_ms,
            "memory_mb": self.memory_mb,
            "cpu_percent": self.cpu_percent,
            "exception": self.exception,
            "stack_trace": self.stack_trace,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MonitorEvent":
        """从字典创建事件"""
        # 转换事件类型
        event_type = EventType(data["event_type"])

        # 转换时间戳
        if isinstance(data["timestamp"], str):
            timestamp = datetime.fromisoformat(data["timestamp"])
        else:
            timestamp = data["timestamp"]

        return cls(
            event_type=event_type,
            timestamp=timestamp,
            event_id=data.get("event_id", str(uuid.uuid4())),
            source=data.get("source", ""),
            source_type=data.get("source_type", ""),
            message=data.get("message", ""),
            data=data.get("data", {}),
            severity=data.get("severity", "info"),
            category=data.get("category", ""),
            session_id=data.get("session_id"),
            environment_id=data.get("environment_id"),
            user_id=data.get("user_id"),
            duration_ms=data.get("duration_ms"),
            memory_mb=data.get("memory_mb"),
            cpu_percent=data.get("cpu_percent"),
            exception=data.get("exception"),
            stack_trace=data.get("stack_trace"),
        )


def create_connection_event(
    event_type: EventType, source: str, source_type: str, message: str = "", **kwargs
) -> MonitorEvent:
    """创建连接事件"""
    return MonitorEvent(
        event_type=event_type,
        source=source,
        source_type=source_type,
        message=message,
        category="network",
        **kwargs
    )


def create_message_event(
    event_type: EventType,
    source: str,
    source_type: str,
    message_type: str = "",
    message_id: str = "",
    recipient: str = "",
    **kwargs
) -> MonitorEvent:
    """创建消息事件"""
    data = {
        "message_type": message_type,
        "message_id": message_id,
        "recipient": recipient,
    }
    data.update(kwargs.get("data", {}))

    return MonitorEvent(
        event_type=event_type,
        source=source,
        source_type=source_type,
        category="network",
        data=data,
        **{k: v for k, v in kwargs.items() if k != "data"}
    )


def create_performance_event(
    source: str,
    source_type: str,
    metric_name: str,
    metric_value: float,
    unit: str = "",
    **kwargs
) -> MonitorEvent:
    """创建性能事件"""
    data = {"metric_name": metric_name, "metric_value": metric_value, "unit": unit}
    data.update(kwargs.get("data", {}))

    return MonitorEvent(
        event_type=EventType.PERFORMANCE_METRIC,
        source=source,
        source_type=source_type,
        category="performance",
        data=data,
        **{k: v for k, v in kwargs.items() if k != "data"}
    )


def create_error_event(
    source: str,
    source_type: str,
    error_message: str,
    exception: Optional[Exception] = None,
    **kwargs
) -> MonitorEvent:
    """创建错误事件"""
    event_data = {"error_message": error_message}

    exception_str = None
    stack_trace = None

    if exception:
        exception_str = str(exception)
        # 获取堆栈跟踪
        import traceback

        stack_trace = traceback.format_exc()

    return MonitorEvent(
        event_type=EventType.ERROR_OCCURRED,
        source=source,
        source_type=source_type,
        message=error_message,
        category="error",
        severity="error",
        data=event_data,
        exception=exception_str,
        stack_trace=stack_trace,
        **kwargs
    )


def create_business_event(
    event_type: EventType,
    source: str,
    source_type: str,
    action: str = "",
    target: str = "",
    **kwargs
) -> MonitorEvent:
    """创建业务事件"""
    data = {"action": action, "target": target}
    data.update(kwargs.get("data", {}))

    return MonitorEvent(
        event_type=event_type,
        source=source,
        source_type=source_type,
        category="business",
        data=data,
        **{k: v for k, v in kwargs.items() if k != "data"}
    )
