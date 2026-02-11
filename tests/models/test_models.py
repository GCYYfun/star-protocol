"""测试 Envelope 和 Payload 模型"""

import pytest
from star_protocol.models import (
    Envelope,
    SystemPayload,
    MessagePayload,
    BroadcastPayload,
)


def test_system_payload_creation():
    """测试系统消息载荷创建"""
    payload = SystemPayload(
        type="ctrl",
        content={"op": "join", "env_id": "room_1"}
    )
    assert payload.type == "ctrl"
    assert payload.content["op"] == "join"


def test_message_payload_creation():
    """测试业务消息载荷创建"""
    payload = MessagePayload(
        type="action",
        content={"name": "move", "x": 10, "y": 5}
    )
    assert payload.type == "action"
    assert payload.content["name"] == "move"


def test_broadcast_payload_creation():
    """测试广播消息载荷创建"""
    payload = BroadcastPayload(
        type="event",
        content={"name": "night_fall", "vision_modifier": 0.5}
    )
    assert payload.type == "event"
    assert payload.content["name"] == "night_fall"


def test_envelope_with_system_payload():
    """测试系统消息信封"""
    envelope = Envelope(
        type="system",
        sender="agent_01",
        recipient="hub",
        payload=SystemPayload(
            type="ctrl",
            content={"op": "join", "env_id": "room_1"}
        )
    )
    
    assert envelope.type == "system"
    assert envelope.sender == "agent_01"
    assert envelope.recipient == "hub"
    assert envelope.payload.type == "ctrl"
    assert envelope.id  # UUID 自动生成
    assert envelope.timestamp > 0  # 时间戳自动生成


def test_envelope_with_message_payload():
    """测试业务消息信封"""
    envelope = Envelope(
        type="message",
        sender="agent_01",
        recipient="env_main",
        payload=MessagePayload(
            type="action",
            content={"name": "move", "x": 10, "y": 5}
        )
    )
    
    assert envelope.type == "message"
    assert envelope.payload.type == "action"


def test_envelope_with_broadcast_payload():
    """测试广播消息信封"""
    envelope = Envelope(
        type="broadcast",
        sender="env_main",
        recipient="@all",
        payload=BroadcastPayload(
            type="event",
            content={"name": "time_tick"}
        )
    )
    
    assert envelope.type == "broadcast"
    assert envelope.recipient == "@all"


def test_envelope_json_serialization():
    """测试 JSON 序列化"""
    envelope = Envelope(
        type="message",
        sender="agent_01",
        recipient="env_main",
        payload=MessagePayload(
            type="action",
            content={"name": "move", "x": 10, "y": 5}
        )
    )
    
    # 序列化
    json_str = envelope.model_dump_json()
    assert "agent_01" in json_str
    assert "action" in json_str
    
    # 反序列化
    envelope_2 = Envelope.model_validate_json(json_str)
    assert envelope_2.sender == envelope.sender
    assert envelope_2.payload.type == envelope.payload.type


def test_envelope_dict_conversion():
    """测试字典转换"""
    envelope = Envelope(
        type="system",
        sender="hub",
        recipient="agent_01",
        payload=SystemPayload(
            type="notify",
            content={"message": "Connected"}
        )
    )
    
    # 转为字典
    data = envelope.model_dump()
    assert data["type"] == "system"
    assert data["payload"]["type"] == "notify"
    
    # 从字典创建
    envelope_2 = Envelope.model_validate(data)
    assert envelope_2.sender == "hub"


def test_payload_type_validation():
    """测试 Payload 类型验证"""
    # 正确的类型
    SystemPayload(type="error", content={})
    SystemPayload(type="ctrl", content={})
    SystemPayload(type="notify", content={})
    
    MessagePayload(type="action", content={})
    MessagePayload(type="outcome", content={})
    MessagePayload(type="stream", content={})
    MessagePayload(type="event", content={})
    
    BroadcastPayload(type="event", content={})
    BroadcastPayload(type="stream", content={})
    
    # 错误的类型会在运行时被 Pydantic 捕获
    with pytest.raises(Exception):
        SystemPayload(type="invalid", content={})


def test_envelope_discriminator():
    """测试 discriminator 多态"""
    # system 类型必须配 SystemPayload
    envelope_dict = {
        "type": "system",
        "sender": "hub",
        "recipient": "agent_01",
        "payload": {
            "type": "notify",
            "content": {"message": "test"}
        }
    }
    
    envelope = Envelope.model_validate(envelope_dict)
    assert isinstance(envelope.payload, SystemPayload)
    
    # message 类型必须配 MessagePayload
    envelope_dict["type"] = "message"
    envelope_dict["payload"]["type"] = "action"
    
    envelope = Envelope.model_validate(envelope_dict)
    assert isinstance(envelope.payload, MessagePayload)
