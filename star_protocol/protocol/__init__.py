"""
Star Protocol Protocol Module

Protocol definitions and message handling utilities
"""

from .types import (
    ClientType,
    MessageType,
    PayloadType,
    OutcomeType,
    ClientInfo,
    ActionPayload,
    OutcomePayload,
    EventPayload,
    StreamPayload,
    Message,
    ConnectionRequest,
    ErrorPayload,
    PayloadUnion,
)

from .messages import (
    MessageBuilder,
    MessageParser,
    BroadcastHelper,
)

from .validation import (
    ValidationError,
    PermissionError,
    MessageValidator,
    PermissionValidator,
    MessageValidationService,
)

__all__ = [
    # Types
    "ClientType",
    "MessageType",
    "PayloadType",
    "OutcomeType",
    "ClientInfo",
    "ActionPayload",
    "OutcomePayload",
    "EventPayload",
    "StreamPayload",
    "Message",
    "ConnectionRequest",
    "ErrorPayload",
    "PayloadUnion",
    # Message utilities
    "MessageBuilder",
    "MessageParser",
    "BroadcastHelper",
    # Validation
    "ValidationError",
    "PermissionError",
    "MessageValidator",
    "PermissionValidator",
    "MessageValidationService",
]
