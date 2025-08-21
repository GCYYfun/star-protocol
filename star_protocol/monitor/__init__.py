"""
Star Protocol 监控系统

提供简单统一的输出管理和状态查看功能
"""

from .simple_monitor import (
    BaseMonitor,
    RichMonitor,
    OutputLevel,
    OutputMode,
    LogEntry,
    create_monitor,
    MonitorManager,
    monitor_manager,
    get_monitor,
    set_rich_mode,
    set_base_mode,
)

__all__ = [
    "BaseMonitor",
    "RichMonitor",
    "OutputLevel",
    "OutputMode",
    "LogEntry",
    "create_monitor",
    "MonitorManager",
    "monitor_manager",
    "get_monitor",
    "set_rich_mode",
    "set_base_mode",
]
