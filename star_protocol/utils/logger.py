"""Star Protocol 日志系统

本模块提供统一的日志接口，支持标准日志和富文本日志（可选）。
支持文件日志、控制台日志，以及为不同模块提供专用的日志器。
"""

import logging
import sys
from typing import Optional
from .config import get_config
from rich.logging import RichHandler


def setup_logger(
    name: str = "star_protocol",
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    enable_rich: Optional[bool] = None,
) -> logging.Logger:
    """设置日志器

    创建并配置一个日志器实例。支持控制台输出和文件输出。

    Args:
        name: 日志器名称
        level: 日志级别，默认从配置读取
        log_file: 日志文件路径，默认从配置读取
        enable_rich: 是否启用 rich 日志，默认从配置读取

    Returns:
        配置好的日志器
    """
    config = get_config()

    # 使用参数或配置中的值
    level = level or config.log_level
    log_file = log_file or config.log_file
    enable_rich = enable_rich if enable_rich is not None else config.enable_rich_logging

    # 创建日志器
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 清除现有处理器
    logger.handlers.clear()

    # 创建格式器
    if enable_rich:
        try:

            # Rich 处理器
            rich_handler = RichHandler(
                rich_tracebacks=True, show_time=True, show_level=True, show_path=True
            )
            rich_handler.setLevel(getattr(logging, level.upper()))
            logger.addHandler(rich_handler)

            # 当使用 Rich 时，不添加标准控制台处理器

        except ImportError:
            # Rich 不可用，降级到标准日志
            enable_rich = False

    if not enable_rich:
        # 标准控制台处理器（仅当 Rich 不可用时）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))

        formatter = logging.Formatter(config.log_format)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件处理器（如果指定了日志文件）
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))

        formatter = logging.Formatter(config.log_format)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "star_protocol") -> logging.Logger:
    """获取日志器

    获取指定名称的日志器。子日志器通过继承父日志器的配置。
    只有根日志器（"star_protocol"）需要配置 handler。

    Args:
        name: 日志器名称

    Returns:
        日志器实例
    """
    logger = logging.getLogger(name)

    # 只为根日志器配置 handler，子日志器继承父日志器配置
    if name == "star_protocol":
        if not logger.handlers:
            return setup_logger(name)
    else:
        # 确保根日志器已经配置
        root_logger = logging.getLogger("star_protocol")
        if not root_logger.handlers:
            setup_logger("star_protocol")

        # 子日志器不需要 handler，会继承父日志器的配置
        # 设置适当的日志级别
        if not logger.level:
            config = get_config()
            logger.setLevel(getattr(logging, config.log_level.upper()))

    return logger


# === 预定义的专用日志器 ===


def get_protocol_logger() -> logging.Logger:
    """获取协议模块日志器

    Returns:
        协议模块专用日志器
    """
    return get_logger("star_protocol.protocol")


def get_client_logger() -> logging.Logger:
    """获取客户端模块日志器

    Returns:
        客户端模块专用日志器
    """
    return get_logger("star_protocol.client")


def get_hub_logger() -> logging.Logger:
    """获取 Hub 模块日志器

    Returns:
        Hub 模块专用日志器
    """
    return get_logger("star_protocol.hub")


def get_monitor_logger() -> logging.Logger:
    """获取监控模块日志器

    Returns:
        监控模块专用日志器
    """
    return get_logger("star_protocol.monitor")


def get_utils_logger() -> logging.Logger:
    """获取工具模块日志器

    Returns:
        工具模块专用日志器
    """
    return get_logger("star_protocol.utils")


# === 便捷函数 ===


def configure_logging(
    level: str = "INFO", enable_rich: bool = False, log_file: Optional[str] = None
) -> None:
    """配置全局日志

    一次性配置所有模块的日志设置。

    Args:
        level: 日志级别
        enable_rich: 是否启用 rich 日志
        log_file: 日志文件路径
    """
    # 更新配置
    from .config import update_config

    update_config(log_level=level, enable_rich_logging=enable_rich, log_file=log_file)

    # 重新配置根日志器
    setup_logger("star_protocol", level, log_file, enable_rich)


def disable_logging() -> None:
    """禁用所有日志输出

    将日志级别设置为 CRITICAL 以上，实际上禁用所有日志。
    """
    logging.getLogger("star_protocol").setLevel(logging.CRITICAL + 1)
