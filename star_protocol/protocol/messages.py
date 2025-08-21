"""
Star Protocol 消息构建和解析

提供消息的创建、解析和转换功能
"""

import json
from typing import Any, Dict, Optional, Union
from .types import (
    Message,
    ClientInfo,
    ActionPayload,
    OutcomePayload,
    EventPayload,
    StreamPayload,
    ConnectionRequest,
    ErrorPayload,
    MessageType,
    ClientType,
    PayloadUnion,
)


class MessageBuilder:
    """消息构建器"""

    @staticmethod
    def create_action_message(
        sender: ClientInfo,
        recipient: ClientInfo,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        action_id: Optional[str] = None,
    ) -> Message:
        """创建动作消息"""
        payload = ActionPayload(
            action=action, parameters=parameters or {}, id=action_id
        )
        if action_id:
            payload.id = action_id

        return Message(
            type=MessageType.MESSAGE.value,
            sender=sender,
            recipient=recipient,
            payload=payload,
        )

    @staticmethod
    def create_outcome_message(
        sender: ClientInfo,
        recipient: ClientInfo,
        action_id: str,
        outcome: Any,
        outcome_type: str = "dict",
    ) -> Message:
        """创建结果消息"""
        payload = OutcomePayload(
            id=action_id, outcome=outcome, outcome_type=outcome_type
        )

        return Message(
            type=MessageType.MESSAGE.value,
            sender=sender,
            recipient=recipient,
            payload=payload,
        )

    @staticmethod
    def create_event_message(
        sender: ClientInfo,
        recipient: ClientInfo,
        event: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """创建事件消息"""
        payload = EventPayload(event=event, data=data or {})

        return Message(
            type=MessageType.MESSAGE.value,
            sender=sender,
            recipient=recipient,
            payload=payload,
        )

    @staticmethod
    def create_stream_message(
        sender: ClientInfo,
        recipient: ClientInfo,
        stream: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """创建流消息"""
        payload = StreamPayload(stream=stream, data=data or {})

        return Message(
            type=MessageType.MESSAGE.value,
            sender=sender,
            recipient=recipient,
            payload=payload,
        )

    @staticmethod
    def create_error_message(
        sender: ClientInfo,
        recipient: ClientInfo,
        error_code: str,
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """创建错误消息"""
        payload = ErrorPayload(
            error_code=error_code,
            error_type=error_type,
            message=message,
            details=details or {},
        )

        return Message(
            type=MessageType.ERROR.value,
            sender=sender,
            recipient=recipient,
            payload=payload,
        )

    @staticmethod
    def create_heartbeat_message(sender: ClientInfo, recipient: ClientInfo) -> Message:
        """创建心跳消息"""
        return Message(
            type=MessageType.HEARTBEAT.value,
            sender=sender,
            recipient=recipient,
            payload={},
        )


class MessageParser:
    """消息解析器"""

    @staticmethod
    def parse_json(json_str: str) -> Message:
        """从 JSON 字符串解析消息"""
        try:
            data = json.loads(json_str)
            return MessageParser.parse_dict(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")

    @staticmethod
    def parse_dict(data: Dict[str, Any]) -> Message:
        """从字典解析消息"""
        try:
            return Message.from_dict(data)
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid message format: {e}")

    @staticmethod
    def to_json(message: Message) -> str:
        """将消息转换为 JSON 字符串"""
        return json.dumps(message.to_dict(), ensure_ascii=False, indent=2)

    @staticmethod
    def extract_payload_type(message: Message) -> Optional[str]:
        """提取载荷类型"""
        if isinstance(message.payload, dict):
            return message.payload.get("type")
        elif hasattr(message.payload, "type"):
            return message.payload.type
        return None

    @staticmethod
    def is_action_message(message: Message) -> bool:
        """判断是否为动作消息"""
        return MessageParser.extract_payload_type(message) == "action"

    @staticmethod
    def is_outcome_message(message: Message) -> bool:
        """判断是否为结果消息"""
        return MessageParser.extract_payload_type(message) == "outcome"

    @staticmethod
    def is_event_message(message: Message) -> bool:
        """判断是否为事件消息"""
        return MessageParser.extract_payload_type(message) == "event"

    @staticmethod
    def is_stream_message(message: Message) -> bool:
        """判断是否为流消息"""
        return MessageParser.extract_payload_type(message) == "stream"


class BroadcastHelper:
    """广播消息辅助类"""

    @staticmethod
    def create_broadcast_target() -> ClientInfo:
        """创建广播目标"""
        return ClientInfo(id="all", type=ClientType.HUB)

    @staticmethod
    def create_env_broadcast_target(env_id: str) -> ClientInfo:
        """创建环境内广播目标"""
        return ClientInfo(id=f"env_{env_id}_all", type=ClientType.HUB)

    @staticmethod
    def is_broadcast_message(message: Message) -> bool:
        """判断是否为广播消息"""
        return message.recipient.id in [
            "all",
            "broadcast",
        ] or message.recipient.id.endswith("_all")

    @staticmethod
    def extract_env_id_from_broadcast(recipient_id: str) -> Optional[str]:
        """从广播目标中提取环境 ID"""
        if recipient_id.startswith("env_") and recipient_id.endswith("_all"):
            return recipient_id[4:-4]  # 去掉 "env_" 和 "_all"
        return None
