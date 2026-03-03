"""Payload 数据模型"""

from typing import Any, Literal, Dict, Optional, Union
from typing_extensions import TypedDict
from pydantic import BaseModel, ConfigDict


# System Payload Contents
class SystemCtrlContent(TypedDict, total=False):
    op: str
    env_id: Optional[str]

class SystemNotifyContent(TypedDict, total=False):
    event: str
    msg: str

class SystemErrorContent(TypedDict, total=False):
    code: int
    msg: str
    original_msg_id: Optional[str]
    details: Optional[Any]

class SystemPayload(BaseModel):
    """系统消息载荷"""
    type: Literal["error", "ctrl", "notify"]
    content: Union[SystemErrorContent, SystemCtrlContent, SystemNotifyContent, Dict[str, Any]]


# Message Payload Contents
class MessageActionContent(TypedDict, total=False):
    name: str
    params: Optional[Dict[str, Any]]

class MessageOutcomeContent(TypedDict, total=False):
    action_ref: str
    success: bool
    data: Optional[Dict[str, Any]]
    error: Optional[str]

class MessageEventContent(TypedDict, total=False):
    name: str
    data: Dict[str, Any]

class MessageStreamContent(TypedDict, total=False):
    stream_id: str
    sequence: int
    chunk: Any
    is_end: bool

class MessagePayload(BaseModel):
    """业务消息载荷"""
    type: Literal["action", "outcome", "stream", "event"]
    content: Union[MessageActionContent, MessageOutcomeContent, MessageStreamContent, MessageEventContent, Dict[str, Any]]


# Broadcast Payload Contents
class BroadcastEventContent(TypedDict, total=False):
    name: str
    data: Dict[str, Any]

class BroadcastStreamContent(TypedDict, total=False):
    stream_id: str
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
    name: Literal["register", "state_change", "message_sent", "message_received"]
    data: Any
    timestamp: int

class MonitorNotifyContent(TypedDict, total=False):
    event: str
    msg: str

class MonitorPayload(BaseModel):
    """监控消息载荷"""
    type: Literal["ctrl", "data", "notify"]
    content: Union[MonitorCtrlContent, MonitorDataContent, MonitorNotifyContent, Dict[str, Any]]
