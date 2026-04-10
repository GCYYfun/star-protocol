"""
Star Protocol - Python SDK for Multi-Agent Communication

A lightweight, strongly-typed communication protocol for Multi-Agent Systems (MAS)
over WebSocket, supporting Agent, Environment, and Human collaboration.
"""

__version__ = "0.2.0"

from star_protocol.models.envelope import Envelope
from star_protocol.models.payloads import (
    SystemPayload,
    MessagePayload,
    BroadcastPayload,
)
from star_protocol.models.enums import (
    EnvelopeType,
    SystemType,
    MessageType,
    BroadcastType,
    ClientState,
)
from star_protocol.client import (
    BaseClient,
    AgentClient,
    EnvironmentClient,
    HumanClient,
    MonitorClient,
    MonitorLevel,
)
from star_protocol.server import (
    MessageRouter,
    SessionManager,
    Session,
    SessionState,
    ClientRole,
)
from star_protocol.exceptions import (
    StarProtocolError,
    ConnectionError,
    PermissionError,
    RecipientNotFoundError,
    InvalidStateError,
    MessageError,
)

__all__ = [
    # Version
    "__version__",
    # Models
    "Envelope",
    "SystemPayload",
    "MessagePayload",
    "BroadcastPayload",
    # Enums
    "EnvelopeType",
    "SystemType",
    "MessageType",
    "BroadcastType",
    "ClientState",
    # Clients
    "BaseClient",
    "AgentClient",
    "EnvironmentClient",
    "HumanClient",
    "MonitorClient",
    "MonitorLevel",
    # Server
    "MessageRouter",
    "SessionManager",
    "Session",
    "SessionState",
    "ClientRole",
    # Exceptions
    "StarProtocolError",
    "ConnectionError",
    "PermissionError",
    "RecipientNotFoundError",
    "InvalidStateError",
    "MessageError",
]
