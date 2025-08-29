"""Star Protocol 异常定义

本模块定义了 Star Protocol 的异常体系，为协议层面的错误提供明确的分类。
"""


class ProtocolException(Exception):
    """Star Protocol 基础异常

    所有 Star Protocol 相关异常的基类。
    """

    pass


class ValidationException(ProtocolException):
    """消息验证错误

    当消息格式不符合协议规范时抛出。
    """

    pass


class SerializationException(ProtocolException):
    """序列化/反序列化错误

    当消息序列化或反序列化失败时抛出。
    """

    pass


class MessageFormatException(ProtocolException):
    """消息格式错误

    当消息结构不正确时抛出。
    """

    pass
