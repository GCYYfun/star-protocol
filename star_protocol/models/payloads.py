"""Payload 数据模型"""

from typing import Any, Literal
from pydantic import BaseModel, Field


class SystemPayload(BaseModel):
    """系统消息载荷"""
    type: Literal["error", "ctrl", "notify"]
    content: Any


class MessagePayload(BaseModel):
    """业务消息载荷"""
    type: Literal["action", "outcome", "stream", "event"]
    content: Any


class BroadcastPayload(BaseModel):
    """广播消息载荷"""
    type: Literal["event", "stream"]
    content: Any


class MonitorPayload(BaseModel):
    """监控消息载荷"""
    type: Literal["ctrl", "data", "notify"]
    content: Any
