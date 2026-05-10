"""Payload 数据模型"""

from typing import Any, Literal, Dict, Optional, Union
from typing_extensions import TypedDict
from pydantic import BaseModel

from datetime import datetime
import uuid


def gen_id(type, name):
    now = datetime.now()
    time_id = now.strftime("%m%d%H%M%S")
    random_part = uuid.uuid4().hex[:4]
    return f"{type}-{name}-{time_id}-{random_part}"


# ==================== Tool Definition ====================


class ToolDefinition(TypedDict, total=False):
    """工具定义，由环境提供、Agent 缓存并传递给 LLM"""

    name: str  # 工具名，对应 action_name
    description: str  # 供 LLM 理解用途的描述
    parameters: Dict[str, Any]  # JSON Schema，描述 params 结构
    tags: list  # 可选：分组、权限标签


# System Payload Contents
class SystemCtrlContent(TypedDict, total=False):
    op: str
    env_id: Optional[str]


class SystemNotifyContent(TypedDict, total=False):
    """
    系统通知内容。

    event: 事件名称
    msg:   简单文本或结构化数据（str = 可读消息， dict = 事件数据）
    """

    event: str
    msg: Union[str, Dict[str, Any]]


class SystemErrorContent(TypedDict, total=False):
    code: int
    msg: str
    original_msg_id: Optional[str]
    details: Optional[Any]


class SystemPayload(BaseModel):
    """系统消息载荷"""

    type: Literal["error", "ctrl", "notify"]
    content: Union[
        SystemErrorContent, SystemCtrlContent, SystemNotifyContent, Dict[str, Any]
    ]


# Message Payload Contents
class MessageActionContent(TypedDict, total=False):
    id: Optional[str]
    name: str
    params: Optional[Dict[str, Any]]


class MessageOutcomeContent(TypedDict, total=False):
    ref_id: str
    success: bool
    data: Optional[Dict[str, Any]]
    error: Optional[str]


class MessageEventContent(TypedDict, total=False):
    id: Optional[str]
    name: str
    data: Dict[str, Any]


class MessageStreamContent(TypedDict, total=False):
    id: Optional[str]
    sequence: int
    chunk: Any
    is_end: bool


class MessageDiscoverContent(TypedDict, total=False):
    """discover 请求内容（可以带过滤器）"""

    filter_tags: list  # 可选：按标签过滤工具


class MessageSpecificationContent(TypedDict, total=False):
    """specification 响应内容"""

    tools: list  # list[ToolDefinition]


class MessagePayload(BaseModel):
    """业务消息载荷"""

    type: Literal["action", "outcome", "stream", "event", "discover", "specification"]
    content: Union[
        MessageActionContent,
        MessageOutcomeContent,
        MessageStreamContent,
        MessageEventContent,
        MessageDiscoverContent,
        MessageSpecificationContent,
        Dict[str, Any],
    ]


# Broadcast Payload Contents
class BroadcastEventContent(TypedDict, total=False):
    id: Optional[str]
    name: str
    data: Dict[str, Any]


class BroadcastStreamContent(TypedDict, total=False):
    id: Optional[str]
    sequence: int
    chunk: Any
    is_end: bool


class BroadcastPayload(BaseModel):
    """广播消息载荷"""

    type: Literal["event", "stream"]
    content: Union[BroadcastEventContent, BroadcastStreamContent, Dict[str, Any]]


# Monitor Payload Contents
class MonitorCtrlContent(TypedDict, total=False):
    op: Literal["enable", "disable", "subscribe", "unsubscribe"]
    level: str
    target_client_id: str


class MonitorDataContent(TypedDict, total=False):
    name: Literal[
        "register",
        "state_change",
        "message_sent",
        "message_received",
        "join_env",
        "leave_env",
    ]
    data: Any
    timestamp: int


class MonitorNotifyContent(TypedDict, total=False):
    event: str
    msg: str


class MonitorPayload(BaseModel):
    """监控消息载荷"""

    type: Literal["ctrl", "data", "notify"]
    content: Union[
        MonitorCtrlContent, MonitorDataContent, MonitorNotifyContent, Dict[str, Any]
    ]
