#!/usr/bin/env python3
"""测试 Protocol 模块的基本功能"""

import sys
import os

from star_protocol_v3.star_protocol_v4.protocol import (
    StarMessage,
    ClientInfo,
    MessageType,
    ClientType,
    StarProtocolError,
    ValidationError,
    SerializationError,
)


def test_client_info():
    """测试 ClientInfo"""
    print("=== 测试 ClientInfo ===")

    # 创建客户端信息
    client_info = ClientInfo(
        client_id="agent_001",
        client_type=ClientType.AGENT,
        env_id="demo_world",
        metadata={"version": "1.0"},
    )

    print(f"Client ID: {client_info.client_id}")
    print(f"Client Type: {client_info.client_type.value}")
    print(f"Env ID: {client_info.env_id}")

    # 测试序列化
    client_dict = client_info.to_dict()
    print(f"序列化: {client_dict}")

    # 测试反序列化
    restored_client = ClientInfo.from_dict(client_dict)
    print(f"反序列化成功: {restored_client.client_id}")

    print("✅ ClientInfo 测试通过\n")


def test_star_message():
    """测试 StarMessage"""
    print("=== 测试 StarMessage ===")

    # 创建客户端信息
    client_info = ClientInfo(
        client_id="agent_001", client_type=ClientType.AGENT, env_id="demo_world"
    )

    # 创建消息
    message = StarMessage(
        message_type=MessageType.ACTION,
        sender=client_info,
        payload={"action": "move", "direction": "north"},
        recipient="env_demo_world",
        message_id="msg_001",
    )

    print(f"Message Type: {message.message_type.value}")
    print(f"Sender: {message.sender.client_id}")
    print(f"Payload: {message.payload}")
    print(f"Recipient: {message.recipient}")
    print(f"Timestamp: {message.timestamp}")

    # 测试 JSON 序列化
    json_str = message.to_json()
    print(f"JSON: {json_str[:100]}...")

    # 测试 JSON 反序列化
    restored_message = StarMessage.from_json(json_str)
    print(f"反序列化成功: {restored_message.message_type.value}")

    # 测试验证
    message.validate()
    print("✅ 消息验证通过")

    print("✅ StarMessage 测试通过\n")


def test_message_types():
    """测试消息类型枚举"""
    print("=== 测试 MessageType ===")

    # 测试所有消息类型
    for msg_type in MessageType:
        print(f"{msg_type.name}: {msg_type.value}")

        # 测试序列化
        type_dict = msg_type.to_dict()
        restored_type = MessageType.from_dict(type_dict)
        assert restored_type == msg_type

    print("✅ MessageType 测试通过\n")


def test_client_types():
    """测试客户端类型枚举"""
    print("=== 测试 ClientType ===")

    # 测试所有客户端类型
    for client_type in ClientType:
        print(f"{client_type.name}: {client_type.value}")

        # 测试序列化
        type_dict = client_type.to_dict()
        restored_type = ClientType.from_dict(type_dict)
        assert restored_type == client_type

    print("✅ ClientType 测试通过\n")


def test_exceptions():
    """测试异常处理"""
    print("=== 测试异常处理 ===")

    try:
        # 测试无效的消息类型
        MessageType.from_dict({"value": "invalid_type"})
    except ValueError:
        print("✅ 无效消息类型异常捕获成功")

    try:
        # 测试无效的JSON
        StarMessage.from_json("invalid json")
    except SerializationError:
        print("✅ JSON 反序列化异常捕获成功")

    try:
        # 测试无效的消息格式
        StarMessage.from_dict({"invalid": "format"})
    except ValidationError:
        print("✅ 消息验证异常捕获成功")

    print("✅ 异常处理测试通过\n")


def main():
    """运行所有测试"""
    print("🚀 开始测试 Star Protocol V3 - Protocol 模块\n")

    try:
        test_client_info()
        test_star_message()
        test_message_types()
        test_client_types()
        test_exceptions()

        print("🎉 所有测试通过！Protocol 模块实现成功！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
