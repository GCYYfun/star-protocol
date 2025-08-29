#!/usr/bin/env python3
"""测试修正后的 Protocol 模块消息格式"""

import sys
import os
import json

# 添加当前目录路径以便导入模块
current_dir = os.path.dirname(__file__)
sys.path.insert(0, current_dir)

from star_protocol_v3.star_protocol_v4.protocol import (
    Envelope,
    Message,
    EnvelopeType,
    SerializationException,
    ValidationException,
    ActionMessage,
    OutcomeMessage,
    EventMessage,
    StreamMessage,
)


def test_action_message():
    """测试 action 消息格式"""
    print("=== 测试 Action 消息 ===")

    # 创建 action 消息
    action_msg = ActionMessage(
        action="move",
        parameters={"direction": "north", "distance": 2.5},
    )

    print(f"Message Type: {action_msg.message_type}")
    print(f"Action: {action_msg.action}")
    print(f"ID: {action_msg.action_id}")
    print(f"Parameters: {action_msg.parameters}")

    # 序列化测试
    action_dict = action_msg.to_dict()
    print(f"序列化: {action_dict}")

    # 反序列化测试
    restored_msg = ActionMessage.from_dict(action_dict)
    print(f"反序列化: {restored_msg.message_type}, {restored_msg.action}")

    print("✅ Action 消息测试通过\n")


def test_outcome_message():
    """测试 outcome 消息格式"""
    print("=== 测试 Outcome 消息 ===")

    # 创建 outcome 消息
    outcome_msg = OutcomeMessage(
        action_id="action_12345",
        status="success",
        outcome={
            "message": "移动成功",
        },
    )

    print(f"Message Type: {outcome_msg.message_type}")
    print(f"ID: {outcome_msg.action_id}")
    print(f"Outcome: {outcome_msg.outcome}")

    # 序列化测试
    outcome_dict = outcome_msg.to_dict()
    print(f"序列化: {outcome_dict}")

    print("✅ Outcome 消息测试通过\n")


def test_event_message():
    """测试 event 消息格式"""
    print("=== 测试 Event 消息 ===")

    # 创建 event 消息
    event_msg = EventMessage(
        event="agent_moved",
        event_id="event_12345",
        data={
            "agent_id": "agent_001",
            "new_position": {"x": 5, "y": 10},
            "timestamp": "2025-08-19T10:30:00Z",
        },
    )

    print(f"Message Type: {event_msg.message_type}")
    print(f"Event: {event_msg.event}")
    print(f"Data: {event_msg.data}")

    print("✅ Event 消息测试通过\n")


def test_stream_message():
    """测试 stream 消息格式"""
    print("=== 测试 Stream 消息 ===")

    # 创建 stream 消息
    stream_msg = StreamMessage(
        stream="sensor_data",
        sequence=12345,
        chunk={
            "temperature": 25.5,
            "humidity": 60.2,
            "timestamp": "2025-08-19T10:30:00Z",
        },
    )

    print(f"Message Type: {stream_msg.message_type}")
    print(f"Stream: {stream_msg.stream}")
    print(f"Sequence: {stream_msg.sequence}")
    print(f"Chunk: {stream_msg.chunk}")

    print("✅ Stream 消息测试通过\n")


def test_envelope_with_action():
    """测试完整的信封+动作消息格式"""
    print("=== 测试 Envelope + Action 消息 ===")

    # 创建 action 消息
    action_msg = ActionMessage(
        action="move",
        action_id="action_12345",
        parameters={"direction": "north", "distance": 2.5},
    )

    # 创建信封
    envelope = Envelope(
        envelope_type=EnvelopeType.MESSAGE,
        sender="agent_001",
        recipient="demo_world",
        message=action_msg,
    )

    print(f"Envelope Type: {envelope.envelope_type.value}")
    print(f"Sender: {envelope.sender}")
    print(f"Recipient: {envelope.recipient}")
    print(f"Message Type: {envelope.message.message_type}")

    # 序列化为字典
    envelope_dict = envelope.to_dict()
    print(f"字典格式: {json.dumps(envelope_dict, indent=2)}")

    # 验证协议规范的字段
    assert envelope_dict["type"] == "message"  # 外层使用 type 字段
    assert "message" in envelope_dict  # 使用 message 字段，不是 payload
    assert envelope_dict["message"]["message_type"] == "action"  # 内层使用 message_type

    # JSON 序列化
    json_str = envelope.to_json()
    print(f"JSON 长度: {len(json_str)}")

    # JSON 反序列化
    restored_envelope = Envelope.from_json(json_str)
    print(f"反序列化成功: {restored_envelope.message.action}")

    print("✅ Envelope + Action 消息测试通过\n")


def test_protocol_compliance():
    """测试协议规范兼容性"""
    print("=== 测试协议规范兼容性 ===")

    # 模拟协议规范中的示例消息
    protocol_example = {
        "type": "message",
        "sender": "agent_001",
        "recipient": "demo_world",
        "message": {
            "message_type": "action",
            "action": "move",
            "action_id": "action_12345",
            "parameters": {"direction": "north", "distance": 2.5},
        },
        "envelope_id": "envelope_001",
        "timestamp": 1692449400.0,
    }

    # 测试能否正确解析协议规范格式
    envelope = Envelope.from_dict(protocol_example)
    print(f"解析成功: {envelope.message.action}")

    # 测试生成的格式是否符合协议规范
    generated_dict = envelope.to_dict()

    # 验证关键字段
    assert generated_dict["type"] == "message"
    assert "message" in generated_dict
    assert generated_dict["message"]["message_type"] == "action"
    assert generated_dict["message"]["action"] == "move"

    print("✅ 协议规范兼容性测试通过\n")


def main():
    """运行所有测试"""
    print("🚀 开始测试 Star Protocol V3 - 动态消息格式\n")

    try:
        test_action_message()
        test_outcome_message()
        test_event_message()
        test_stream_message()
        test_envelope_with_action()
        test_protocol_compliance()

        print("🎉 所有测试通过！消息格式符合协议规范！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
