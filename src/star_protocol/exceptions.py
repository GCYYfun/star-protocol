"""自定义异常"""


class StarProtocolError(Exception):
    """Star Protocol 基础异常"""

    pass


class ConnectionError(StarProtocolError):
    """连接错误"""

    pass


class PermissionError(StarProtocolError):
    """权限错误"""

    pass


class RecipientNotFoundError(StarProtocolError):
    """接收者不存在"""

    pass


class InvalidStateError(StarProtocolError):
    """无效状态错误"""

    pass


class MessageError(StarProtocolError):
    """消息错误"""

    pass
