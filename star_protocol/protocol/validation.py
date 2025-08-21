"""
Star Protocol 消息验证

提供消息格式验证和权限检查功能
"""

from typing import Any, Dict, List, Optional, Set
from .types import Message, ClientInfo, ClientType, MessageType
from .messages import MessageParser, BroadcastHelper


class ValidationError(Exception):
    """验证错误"""

    pass


class PermissionError(ValidationError):
    """权限错误"""

    pass


class MessageValidator:
    """消息验证器"""

    REQUIRED_MESSAGE_FIELDS = {"type", "sender", "recipient", "payload"}
    REQUIRED_CLIENT_FIELDS = {"id", "type"}

    @staticmethod
    def validate_message_structure(data: Dict[str, Any]) -> None:
        """验证消息基本结构"""
        # 检查必需字段
        missing_fields = MessageValidator.REQUIRED_MESSAGE_FIELDS - set(data.keys())
        if missing_fields:
            raise ValidationError(f"Missing required fields: {missing_fields}")

        # 验证发送者和接收者结构
        for field in ["sender", "recipient"]:
            if not isinstance(data[field], dict):
                raise ValidationError(f"{field} must be a dictionary")

            missing_client_fields = MessageValidator.REQUIRED_CLIENT_FIELDS - set(
                data[field].keys()
            )
            if missing_client_fields:
                raise ValidationError(
                    f"{field} missing required fields: {missing_client_fields}"
                )

        # 验证客户端类型
        for field in ["sender", "recipient"]:
            client_type = data[field]["type"]
            try:
                ClientType(client_type)
            except ValueError:
                raise ValidationError(f"Invalid client type in {field}: {client_type}")

        # 验证消息类型
        try:
            MessageType(data["type"])
        except ValueError:
            raise ValidationError(f"Invalid message type: {data['type']}")

    @staticmethod
    def validate_payload_structure(message: Message) -> None:
        """验证载荷结构"""
        payload = message.payload

        if isinstance(payload, dict):
            payload_type = payload.get("type")

            if payload_type == "action":
                MessageValidator._validate_action_payload(payload)
            elif payload_type == "outcome":
                MessageValidator._validate_outcome_payload(payload)
            elif payload_type == "event":
                MessageValidator._validate_event_payload(payload)
            elif payload_type == "stream":
                MessageValidator._validate_stream_payload(payload)

    @staticmethod
    def _validate_action_payload(payload: Dict[str, Any]) -> None:
        """验证动作载荷"""
        required_fields = {"type", "id", "action"}
        missing_fields = required_fields - set(payload.keys())
        if missing_fields:
            raise ValidationError(f"Action payload missing fields: {missing_fields}")

        if not isinstance(payload.get("parameters", {}), dict):
            raise ValidationError("Action parameters must be a dictionary")

    @staticmethod
    def _validate_outcome_payload(payload: Dict[str, Any]) -> None:
        """验证结果载荷"""
        required_fields = {"type", "id", "outcome", "outcome_type"}
        missing_fields = required_fields - set(payload.keys())
        if missing_fields:
            raise ValidationError(f"Outcome payload missing fields: {missing_fields}")

    @staticmethod
    def _validate_event_payload(payload: Dict[str, Any]) -> None:
        """验证事件载荷"""
        required_fields = {"type", "id", "event"}
        missing_fields = required_fields - set(payload.keys())
        if missing_fields:
            raise ValidationError(f"Event payload missing fields: {missing_fields}")

        if not isinstance(payload.get("data", {}), dict):
            raise ValidationError("Event data must be a dictionary")

    @staticmethod
    def _validate_stream_payload(payload: Dict[str, Any]) -> None:
        """验证流载荷"""
        required_fields = {"type", "id", "stream"}
        missing_fields = required_fields - set(payload.keys())
        if missing_fields:
            raise ValidationError(f"Stream payload missing fields: {missing_fields}")

        if not isinstance(payload.get("data", {}), dict):
            raise ValidationError("Stream data must be a dictionary")


class PermissionValidator:
    """权限验证器"""

    # 定义各角色允许的动作
    ROLE_PERMISSIONS = {
        ClientType.AGENT: {
            "allowed_actions": {"move", "pickup", "use", "observe", "dialogue", "ping"},
            "can_send_to": {ClientType.ENVIRONMENT, ClientType.AGENT, ClientType.HUB},
            "can_broadcast": False,
        },
        ClientType.ENVIRONMENT: {
            "allowed_actions": {
                "broadcast",
                "response",
                "spawn",
                "update_state",
                "initialize",
            },
            "can_send_to": {ClientType.AGENT, ClientType.HUMAN, ClientType.HUB},
            "can_broadcast": True,
        },
        ClientType.HUMAN: {
            "allowed_actions": {
                "observe",
                "control_character",
                "admin_command",
                "spectate",
            },
            "can_send_to": {ClientType.ENVIRONMENT, ClientType.AGENT, ClientType.HUB},
            "can_broadcast": False,
        },
        ClientType.HUB: {
            "allowed_actions": set(),  # Hub 可以转发任何消息
            "can_send_to": {ClientType.AGENT, ClientType.ENVIRONMENT, ClientType.HUMAN},
            "can_broadcast": True,
        },
    }

    @staticmethod
    def validate_action_permission(sender: ClientInfo, action: str) -> None:
        """验证动作权限"""
        permissions = PermissionValidator.ROLE_PERMISSIONS.get(sender.type)
        if not permissions:
            raise PermissionError(f"Unknown client type: {sender.type}")

        # Hub 有特殊权限，跳过动作检查
        if sender.type == ClientType.HUB:
            return

        allowed_actions = permissions["allowed_actions"]
        if action not in allowed_actions:
            raise PermissionError(
                f"Client type {sender.type.value} not allowed to perform action: {action}"
            )

    @staticmethod
    def validate_send_permission(sender: ClientInfo, recipient: ClientInfo) -> None:
        """验证发送权限"""
        permissions = PermissionValidator.ROLE_PERMISSIONS.get(sender.type)
        if not permissions:
            raise PermissionError(f"Unknown sender client type: {sender.type}")

        can_send_to = permissions["can_send_to"]
        if recipient.type not in can_send_to:
            raise PermissionError(
                f"Client type {sender.type.value} cannot send to {recipient.type.value}"
            )

    @staticmethod
    def validate_broadcast_permission(sender: ClientInfo) -> None:
        """验证广播权限"""
        permissions = PermissionValidator.ROLE_PERMISSIONS.get(sender.type)
        if not permissions:
            raise PermissionError(f"Unknown client type: {sender.type}")

        if not permissions["can_broadcast"]:
            raise PermissionError(
                f"Client type {sender.type.value} cannot broadcast messages"
            )


class MessageValidationService:
    """消息验证服务 - 统一的验证入口"""

    def __init__(self, enable_permission_check: bool = True):
        self.enable_permission_check = enable_permission_check

    def validate_message(self, data: Dict[str, Any]) -> Message:
        """完整的消息验证"""
        # 1. 验证消息结构
        MessageValidator.validate_message_structure(data)

        # 2. 解析消息
        message = MessageParser.parse_dict(data)

        # 3. 验证载荷结构
        MessageValidator.validate_payload_structure(message)

        # 4. 权限检查（如果启用）
        if self.enable_permission_check:
            self._validate_permissions(message)

        return message

    def _validate_permissions(self, message: Message) -> None:
        """验证权限"""
        # 验证发送权限
        PermissionValidator.validate_send_permission(message.sender, message.recipient)

        # 验证广播权限
        if BroadcastHelper.is_broadcast_message(message):
            PermissionValidator.validate_broadcast_permission(message.sender)

        # 验证动作权限
        if MessageParser.is_action_message(message):
            payload = message.payload
            if isinstance(payload, dict):
                action = payload.get("action")
                if action:
                    PermissionValidator.validate_action_permission(
                        message.sender, action
                    )
