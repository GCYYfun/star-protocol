"""
Star Protocol - Python SDK

/ Agent, Environment, Human & Hub Components
"""

__version__ = "1.0.0"
__author__ = "Star Protocol Team"
__description__ = "Real-time multi-agent communication protocol SDK"

# Protocol core
from .protocol import (
    # Enums and data classes
    ClientType,
    MessageType,
    PayloadType,
    OutcomeType,
    ClientInfo,
    Message,
    ActionPayload,
    OutcomePayload,
    EventPayload,
    StreamPayload,
    ConnectionRequest,
    ErrorPayload,
    # Message utilities
    MessageBuilder,
    MessageParser,
    BroadcastHelper,
    # Validation services
    MessageValidationService,
    ValidationError,
    PermissionError,
)

# Clients
from .client import (
    BaseStarClient,
    AgentClient,
    EnvironmentClient,
    HumanClient,
    EventHandler,
    AsyncEventHandler,
)

# Hub server
from .hub import (
    StarHubServer,
    SessionManager,
    MessageRouter,
    AuthenticationService,
    run_server,
)

# Utilities
from .utils import setup_logging, get_config, init_config, StarProtocolConfig, LogLevel

# Exceptions
from .exceptions import (
    StarProtocolError,
    ConnectionError,
    AuthenticationError,
    MessageError,
    ClientError,
    EnvironmentError,
    ServerError,
)

__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__description__",
    # Protocol core
    "ClientType",
    "MessageType",
    "PayloadType",
    "OutcomeType",
    "ClientInfo",
    "Message",
    "ActionPayload",
    "OutcomePayload",
    "EventPayload",
    "StreamPayload",
    "ConnectionRequest",
    "ErrorPayload",
    "MessageBuilder",
    "MessageParser",
    "BroadcastHelper",
    "MessageValidationService",
    "ValidationError",
    "PermissionError",
    # Clients
    "BaseStarClient",
    "AgentClient",
    "EnvironmentClient",
    "HumanClient",
    "EventHandler",
    "AsyncEventHandler",
    # Hub server
    "StarHubServer",
    "SessionManager",
    "MessageRouter",
    "AuthenticationService",
    "run_server",
    # Utils
    "setup_logging",
    "get_config",
    "init_config",
    "StarProtocolConfig",
    "LogLevel",
    # Exceptions
    "StarProtocolError",
    "ConnectionError",
    "AuthenticationError",
    "MessageError",
    "ClientError",
    "EnvironmentError",
    "ServerError",
]


def get_version() -> str:
    """Get the current version of the Star Protocol SDK."""
    return __version__


def create_agent_client(server_url: str, agent_id: str, env_id: str) -> AgentClient:
    """Create a new Agent client instance."""
    return AgentClient(server_url, agent_id, env_id)


def create_environment_client(server_url: str, env_id: str) -> EnvironmentClient:
    """Create a new Environment client instance."""
    return EnvironmentClient(server_url, env_id)


def create_human_client(server_url: str, user_id: str) -> HumanClient:
    """Create a new Human client instance."""
    return HumanClient(server_url, user_id)


def create_hub_server(host: str = "localhost", port: int = 8765) -> StarHubServer:
    """Create a new Hub server instance."""
    return StarHubServer(host, port)


# Aliases
Agent = AgentClient
Environment = EnvironmentClient
Human = HumanClient
Hub = StarHubServer
