"""Star Protocol 日志系统

本模块提供统一的日志接口，支持标准日志和富文本日志（可选）。
支持文件日志、控制台日志，以及为不同模块提供专用的日志器。
"""

import logging
import sys
from typing import Optional

# from .config import get_config, update_config
from rich.logging import RichHandler


def configure_logging(
    name: Optional[str] = "star",
    level: Optional[str] = "info",
    log_file: Optional[str] = None,
    enable_rich: Optional[bool] = True,
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
    # config = get_config()

    # 使用参数或配置中的值
    # level = level or config.log_level
    # log_file = log_file or config.log_file
    # enable_rich = enable_rich if enable_rich is not None else config.enable_rich_logging
    level = level or "INFO"
    log_file = log_file or "app.log"
    enable_rich = enable_rich if enable_rich is not None else True
    # 创建日志器
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())

    # 清除现有处理器
    logger.handlers.clear()

    default_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # 创建格式器
    if enable_rich:
        try:

            # Rich 处理器
            rich_handler = RichHandler(
                rich_tracebacks=True, show_time=True, show_level=True, show_path=True
            )
            rich_handler.setLevel(level.upper())
            logger.addHandler(rich_handler)

            # 当使用 Rich 时，不添加标准控制台处理器

        except ImportError:
            # Rich 不可用，降级到标准日志
            enable_rich = False

    if not enable_rich:
        # 标准控制台处理器（仅当 Rich 不可用时）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level.upper())

        formatter = logging.Formatter(default_format)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件处理器（如果指定了日志文件）
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))

        formatter = logging.Formatter(default_format)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "star") -> logging.Logger:
    """获取日志器

    获取指定名称的日志器。子日志器通过继承父日志器的配置。
    只有根日志器（"star_protocol"）需要配置 handler。

    Args:
        name: 日志器名称

    Returns:
        日志器实例
    """
    logger = configure_logging(name)
    return logger
