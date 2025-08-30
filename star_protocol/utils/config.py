"""Star Protocol 配置管理

本模块提供统一的配置管理接口，支持环境变量、默认值和运行时配置。
配置优先级：环境变量 > 运行时设置 > 默认值
"""

import os
from typing import Any, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class StarConfig:
    """Star Protocol 配置类

    包含所有 Star Protocol 组件的配置选项。
    """

    # Hub 服务器配置
    hub_host: str = "localhost"
    hub_port: int = 8000
    hub_max_connections: int = 1000

    # WebSocket 配置
    ws_ping_interval: float = 30.0
    ws_ping_timeout: float = 10.0
    ws_close_timeout: float = 10.0

    # 日志配置
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: Optional[str] = None
    enable_rich_logging: bool = False

    # 监控配置
    metrics_enabled: bool = False
    metrics_export_interval: float = 60.0
    metrics_file: Optional[str] = None

    # 协议配置
    message_timeout: float = 30.0
    heartbeat_interval: float = 60.0

    # 自定义配置
    custom: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "StarConfig":
        """从环境变量创建配置

        读取环境变量并创建配置实例。环境变量格式：STAR_<配置名>

        Returns:
            从环境变量读取的配置实例
        """
        config = cls()

        # Hub 配置
        config.hub_host = os.getenv("STAR_HUB_HOST", config.hub_host)
        config.hub_port = int(os.getenv("STAR_HUB_PORT", str(config.hub_port)))
        config.hub_max_connections = int(
            os.getenv("STAR_HUB_MAX_CONNECTIONS", str(config.hub_max_connections))
        )

        # WebSocket 配置
        config.ws_ping_interval = float(
            os.getenv("STAR_WS_PING_INTERVAL", str(config.ws_ping_interval))
        )
        config.ws_ping_timeout = float(
            os.getenv("STAR_WS_PING_TIMEOUT", str(config.ws_ping_timeout))
        )
        config.ws_close_timeout = float(
            os.getenv("STAR_WS_CLOSE_TIMEOUT", str(config.ws_close_timeout))
        )

        # 日志配置
        config.log_level = os.getenv("STAR_LOG_LEVEL", config.log_level)
        config.log_format = os.getenv("STAR_LOG_FORMAT", config.log_format)
        config.log_file = os.getenv("STAR_LOG_FILE", config.log_file)
        config.enable_rich_logging = (
            os.getenv("STAR_ENABLE_RICH_LOGGING", "false").lower() == "true"
        )

        # 监控配置
        config.metrics_enabled = (
            os.getenv("STAR_METRICS_ENABLED", "false").lower() == "true"
        )
        config.metrics_export_interval = float(
            os.getenv(
                "STAR_METRICS_EXPORT_INTERVAL", str(config.metrics_export_interval)
            )
        )
        config.metrics_file = os.getenv("STAR_METRICS_FILE", config.metrics_file)

        # 协议配置
        config.message_timeout = float(
            os.getenv("STAR_MESSAGE_TIMEOUT", str(config.message_timeout))
        )
        config.heartbeat_interval = float(
            os.getenv("STAR_HEARTBEAT_INTERVAL", str(config.heartbeat_interval))
        )

        return config

    def update(self, **kwargs) -> None:
        """更新配置项

        Args:
            **kwargs: 要更新的配置项
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.custom[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项

        Args:
            key: 配置项名称
            default: 默认值

        Returns:
            配置项的值
        """
        if hasattr(self, key):
            return getattr(self, key)
        return self.custom.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            配置的字典表示
        """
        result = {
            # Hub 配置
            "hub_host": self.hub_host,
            "hub_port": self.hub_port,
            "hub_max_connections": self.hub_max_connections,
            # WebSocket 配置
            "ws_ping_interval": self.ws_ping_interval,
            "ws_ping_timeout": self.ws_ping_timeout,
            "ws_close_timeout": self.ws_close_timeout,
            # 日志配置
            "log_level": self.log_level,
            "log_format": self.log_format,
            "log_file": self.log_file,
            "enable_rich_logging": self.enable_rich_logging,
            # 监控配置
            "metrics_enabled": self.metrics_enabled,
            "metrics_export_interval": self.metrics_export_interval,
            "metrics_file": self.metrics_file,
            # 协议配置
            "message_timeout": self.message_timeout,
            "heartbeat_interval": self.heartbeat_interval,
        }

        # 添加自定义配置
        result.update(self.custom)
        return result


# # 全局配置实例
# _global_config: Optional[StarConfig] = None


# def get_config() -> StarConfig:
#     """获取全局配置

#     如果配置尚未初始化，则从环境变量创建默认配置。

#     Returns:
#         全局配置实例
#     """
#     global _global_config
#     if _global_config is None:
#         _global_config = StarConfig.from_env()
#     return _global_config


# def set_config(config: StarConfig) -> None:
#     """设置全局配置

#     Args:
#         config: 新的配置实例
#     """
#     global _global_config
#     _global_config = config


# def update_config(**kwargs) -> None:
#     """更新全局配置

#     Args:
#         **kwargs: 要更新的配置项
#     """
#     config = get_config()
#     config.update(**kwargs)


# def reset_config() -> None:
#     """重置全局配置

#     清除当前配置，下次调用 get_config() 时会重新从环境变量读取。
#     """
#     global _global_config
#     _global_config = None
