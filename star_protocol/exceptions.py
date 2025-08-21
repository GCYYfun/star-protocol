"""
Star Protocol Exceptions

Custom exception classes for error handling
"""


class StarProtocolError(Exception):
    """Base Star Protocol exception"""
    
    def __init__(self, message: str, error_code: str = "STAR000", details: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> dict:
        """Convert to dictionary format"""
        return {
            "error_code": self.error_code,
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details
        }


# Connection errors
class ConnectionError(StarProtocolError):
    """Connection error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "CONN001", details)


class ConnectionTimeoutError(ConnectionError):
    """Connection timeout error"""
    
    def __init__(self, message: str = "Connection timeout", details: dict = None):
        super().__init__(message, details)
        self.error_code = "CONN002"


class ConnectionRefusedError(ConnectionError):
    """Connection refused error"""
    
    def __init__(self, message: str = "Connection refused", details: dict = None):
        super().__init__(message, details)
        self.error_code = "CONN003"


# Authentication errors
class AuthenticationError(StarProtocolError):
    """Authentication error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "AUTH001", details)


class AuthenticationTimeoutError(AuthenticationError):
    """Authentication timeout error"""
    
    def __init__(self, message: str = "Authentication timeout", details: dict = None):
        super().__init__(message, details)
        self.error_code = "AUTH002"


class InvalidCredentialsError(AuthenticationError):
    """Invalid credentials error"""
    
    def __init__(self, message: str = "Invalid credentials", details: dict = None):
        super().__init__(message, details)
        self.error_code = "AUTH003"


class PermissionDeniedError(AuthenticationError):
    """Permission denied error"""
    
    def __init__(self, message: str = "Permission denied", details: dict = None):
        super().__init__(message, details)
        self.error_code = "AUTH004"


class TokenExpiredError(AuthenticationError):
    """Token expired error"""
    
    def __init__(self, message: str = "Token expired", details: dict = None):
        super().__init__(message, details)
        self.error_code = "AUTH005"


# Message errors
class MessageError(StarProtocolError):
    """Message error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "MSG001", details)


class MessageValidationError(MessageError):
    """Message validation error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)
        self.error_code = "MSG002"


class MessageRoutingError(MessageError):
    """Message routing error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)
        self.error_code = "MSG003"


class MessageSizeError(MessageError):
    """Message size error"""
    
    def __init__(self, message: str = "Message too large", details: dict = None):
        super().__init__(message, details)
        self.error_code = "MSG004"


class InvalidMessageFormatError(MessageError):
    """Invalid message format error"""
    
    def __init__(self, message: str = "Invalid message format", details: dict = None):
        super().__init__(message, details)
        self.error_code = "MSG005"


# Client errors
class ClientError(StarProtocolError):
    """Client error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "CLIENT001", details)


class ClientNotFoundError(ClientError):
    """Client not found error"""
    
    def __init__(self, client_id: str, details: dict = None):
        message = f"Client not found: {client_id}"
        super().__init__(message, details)
        self.error_code = "CLIENT002"
        self.client_id = client_id


class ClientAlreadyConnectedError(ClientError):
    """Client already connected error"""
    
    def __init__(self, client_id: str, details: dict = None):
        message = f"Client already connected: {client_id}"
        super().__init__(message, details)
        self.error_code = "CLIENT003"
        self.client_id = client_id


class ClientDisconnectedError(ClientError):
    """Client disconnected error"""
    
    def __init__(self, client_id: str, details: dict = None):
        message = f"Client disconnected: {client_id}"
        super().__init__(message, details)
        self.error_code = "CLIENT004"
        self.client_id = client_id


# Environment errors
class EnvironmentError(StarProtocolError):
    """Environment error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "ENV001", details)


class EnvironmentNotFoundError(EnvironmentError):
    """Environment not found error"""
    
    def __init__(self, env_id: str, details: dict = None):
        message = f"Environment not found: {env_id}"
        super().__init__(message, details)
        self.error_code = "ENV002"
        self.env_id = env_id


class EnvironmentFullError(EnvironmentError):
    """Environment full error"""
    
    def __init__(self, env_id: str, details: dict = None):
        message = f"Environment is full: {env_id}"
        super().__init__(message, details)
        self.error_code = "ENV003"
        self.env_id = env_id


class InvalidActionError(EnvironmentError):
    """Invalid action error"""
    
    def __init__(self, action: str, details: dict = None):
        message = f"Invalid action: {action}"
        super().__init__(message, details)
        self.error_code = "ENV004"
        self.action = action


# Server errors
class ServerError(StarProtocolError):
    """Server error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "SERVER001", details)


class ServerOverloadError(ServerError):
    """Server overload error"""
    
    def __init__(self, message: str = "Server overloaded", details: dict = None):
        super().__init__(message, details)
        self.error_code = "SERVER002"


class ServiceUnavailableError(ServerError):
    """Service unavailable error"""
    
    def __init__(self, service: str, details: dict = None):
        message = f"Service unavailable: {service}"
        super().__init__(message, details)
        self.error_code = "SERVER003"
        self.service = service


# Configuration errors
class ConfigurationError(StarProtocolError):
    """Configuration error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "CONFIG001", details)


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration error"""
    
    def __init__(self, key: str, value: str, details: dict = None):
        message = f"Invalid configuration: {key} = {value}"
        super().__init__(message, details)
        self.error_code = "CONFIG002"
        self.key = key
        self.value = value


class MissingConfigurationError(ConfigurationError):
    """Missing configuration error"""
    
    def __init__(self, key: str, details: dict = None):
        message = f"Missing required configuration: {key}"
        super().__init__(message, details)
        self.error_code = "CONFIG003"
        self.key = key


# Protocol errors  
class ProtocolError(StarProtocolError):
    """Protocol error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "PROTO001", details)


class UnsupportedProtocolVersionError(ProtocolError):
    """Unsupported protocol version error"""
    
    def __init__(self, version: str, details: dict = None):
        message = f"Unsupported protocol version: {version}"
        super().__init__(message, details)
        self.error_code = "PROTO002"
        self.version = version


class ProtocolViolationError(ProtocolError):
    """Protocol violation error"""
    
    def __init__(self, violation: str, details: dict = None):
        message = f"Protocol violation: {violation}"
        super().__init__(message, details)
        self.error_code = "PROTO003"
        self.violation = violation


# Resource errors
class ResourceError(StarProtocolError):
    """Resource error"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "RESOURCE001", details)


class ResourceNotFoundError(ResourceError):
    """Resource not found error"""
    
    def __init__(self, resource_type: str, resource_id: str, details: dict = None):
        message = f"{resource_type} not found: {resource_id}"
        super().__init__(message, details)
        self.error_code = "RESOURCE002"
        self.resource_type = resource_type
        self.resource_id = resource_id


class ResourceConflictError(ResourceError):
    """Resource conflict error"""
    
    def __init__(self, resource_type: str, resource_id: str, details: dict = None):
        message = f"{resource_type} conflict: {resource_id}"
        super().__init__(message, details)
        self.error_code = "RESOURCE003"
        self.resource_type = resource_type
        self.resource_id = resource_id


class ResourceExhaustedError(ResourceError):
    """Resource exhausted error"""
    
    def __init__(self, resource_type: str, details: dict = None):
        message = f"{resource_type} exhausted"
        super().__init__(message, details)
        self.error_code = "RESOURCE004"
        self.resource_type = resource_type


# Utility functions
def create_error_message(error: StarProtocolError) -> dict:
    """Create error message format"""
    return {
        "type": "error",
        "payload": error.to_dict()
    }


# Error code mapping
ERROR_CODE_MAP = {
    "CONN001": ConnectionError,
    "CONN002": ConnectionTimeoutError,
    "CONN003": ConnectionRefusedError,
    "AUTH001": AuthenticationError,
    "AUTH002": AuthenticationTimeoutError,
    "AUTH003": InvalidCredentialsError,
    "AUTH004": PermissionDeniedError,
    "AUTH005": TokenExpiredError,
    "MSG001": MessageError,
    "MSG002": MessageValidationError,
    "MSG003": MessageRoutingError,
    "MSG004": MessageSizeError,
    "MSG005": InvalidMessageFormatError,
    "CLIENT001": ClientError,
    "CLIENT002": ClientNotFoundError,
    "CLIENT003": ClientAlreadyConnectedError,
    "CLIENT004": ClientDisconnectedError,
    "ENV001": EnvironmentError,
    "ENV002": EnvironmentNotFoundError,
    "ENV003": EnvironmentFullError,
    "ENV004": InvalidActionError,
    "SERVER001": ServerError,
    "SERVER002": ServerOverloadError,
    "SERVER003": ServiceUnavailableError,
    "CONFIG001": ConfigurationError,
    "CONFIG002": InvalidConfigurationError,
    "CONFIG003": MissingConfigurationError,
    "PROTO001": ProtocolError,
    "PROTO002": UnsupportedProtocolVersionError,
    "PROTO003": ProtocolViolationError,
    "RESOURCE001": ResourceError,
    "RESOURCE002": ResourceNotFoundError,
    "RESOURCE003": ResourceConflictError,
    "RESOURCE004": ResourceExhaustedError,
}
