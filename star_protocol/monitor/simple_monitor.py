"""
Star Protocol 简单监控系统

提供统一的输出管理和状态查看功能
"""

import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, TextIO, Union
from enum import Enum
from dataclasses import dataclass, field
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from rich.layout import Layout
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.tree import Tree

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class OutputLevel(Enum):
    """输出级别"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"


class OutputMode(Enum):
    """输出模式"""

    BASE = "base"  # 普通输出
    RICH = "rich"  # Rich 格式化输出


@dataclass
class LogEntry:
    """日志条目"""

    timestamp: datetime
    level: OutputLevel
    source: str  # 来源 (agent_id, env_id, hub, etc.)
    message: str
    data: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] [{self.level.value}] {self.source}: {self.message}"


class BaseMonitor:
    """基础监控器 - 普通输出模式"""

    def __init__(self, source: str, output_file: Optional[TextIO] = None):
        self.source = source
        self.output_file = output_file or sys.stdout
        self.logs: List[LogEntry] = []
        self.max_logs = 1000
        self.lock = threading.Lock()
        self.status = "Unknown"
        self.stats = {}

    def log(self, level: OutputLevel, message: str, **data):
        """记录日志"""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            source=self.source,
            message=message,
            data=data,
        )

        with self.lock:
            self.logs.append(entry)
            if len(self.logs) > self.max_logs:
                self.logs = self.logs[-self.max_logs :]

        self._output(entry)

    def debug(self, message: str, **data):
        """调试信息"""
        self.log(OutputLevel.DEBUG, message, **data)

    def info(self, message: str, **data):
        """一般信息"""
        self.log(OutputLevel.INFO, message, **data)

    def success(self, message: str, **data):
        """成功信息"""
        self.log(OutputLevel.SUCCESS, message, **data)

    def warning(self, message: str, **data):
        """警告信息"""
        self.log(OutputLevel.WARNING, message, **data)

    def error(self, message: str, **data):
        """错误信息"""
        self.log(OutputLevel.ERROR, message, **data)

    def set_status(self, status: str):
        """设置状态"""
        self.status = status
        self.info(f"Status changed to: {status}")

    def update_stats(self, **stats):
        """更新统计信息"""
        with self.lock:
            self.stats.update(stats)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            return self.stats.copy()

    def get_recent_logs(self, count: int = 50) -> List[LogEntry]:
        """获取最近的日志"""
        with self.lock:
            return self.logs[-count:] if count < len(self.logs) else self.logs.copy()

    def show_status(self):
        """显示当前状态"""
        print(f"\n=== {self.source} Status ===")
        print(f"Status: {self.status}")
        print(f"Stats: {self.stats}")
        print(f"Total logs: {len(self.logs)}")

        # 显示最近几条日志
        recent = self.get_recent_logs(5)
        if recent:
            print("\nRecent logs:")
            for entry in recent:
                print(f"  {entry}")
        print("=" * 30)

    def _output(self, entry: LogEntry):
        """输出日志条目"""
        print(str(entry), file=self.output_file)
        if self.output_file != sys.stdout:
            self.output_file.flush()


class RichMonitor(BaseMonitor):
    """Rich 格式化监控器"""

    def __init__(self, source: str, output_file: Optional[TextIO] = None):
        if not RICH_AVAILABLE:
            raise ImportError(
                "Rich library is not available. Install with: pip install rich"
            )

        super().__init__(source, output_file)
        self.console = Console(file=output_file)
        self.live_display = None
        self.is_live = False

        # 样式定义
        self.level_styles = {
            OutputLevel.DEBUG: "dim",
            OutputLevel.INFO: "blue",
            OutputLevel.SUCCESS: "green",
            OutputLevel.WARNING: "yellow",
            OutputLevel.ERROR: "red bold",
        }

    def _output(self, entry: LogEntry):
        """Rich 格式化输出"""
        if self.is_live:
            return  # 在 live 模式下不直接输出

        time_str = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]
        level_style = self.level_styles.get(entry.level, "")

        # 构建输出文本
        text = Text()
        text.append(f"[{time_str}] ", style="dim")
        text.append(f"[{entry.level.value:7}] ", style=level_style)
        text.append(f"{entry.source}: ", style="cyan")
        text.append(entry.message)

        # 添加额外数据
        if entry.data:
            text.append(f" {entry.data}", style="dim")

        self.console.print(text)

    def show_status(self):
        """Rich 格式化状态显示"""
        # 创建状态面板
        status_table = Table(show_header=False, box=None)
        status_table.add_row("Status:", f"[green]{self.status}[/green]")
        status_table.add_row("Logs:", str(len(self.logs)))

        # 添加统计信息
        for key, value in self.stats.items():
            status_table.add_row(f"{key}:", str(value))

        status_panel = Panel(
            status_table,
            title=f"[bold cyan]{self.source}[/bold cyan]",
            border_style="cyan",
        )

        # 创建日志表格
        log_table = Table(show_header=True, header_style="bold magenta")
        log_table.add_column("Time", style="dim", width=12)
        log_table.add_column("Level", width=8)
        log_table.add_column("Message", min_width=30)

        recent_logs = self.get_recent_logs(10)
        for entry in recent_logs:
            time_str = entry.timestamp.strftime("%H:%M:%S")
            level_style = self.level_styles.get(entry.level, "")

            log_table.add_row(
                time_str,
                f"[{level_style}]{entry.level.value}[/{level_style}]",
                entry.message,
            )

        log_panel = Panel(
            log_table,
            title="[bold yellow]Recent Logs[/bold yellow]",
            border_style="yellow",
        )

        # 输出
        self.console.print(status_panel)
        self.console.print(log_panel)

    def start_live_display(self):
        """启动实时显示"""
        if self.is_live:
            return

        self.is_live = True
        layout = Layout()

        layout.split_column(Layout(name="status", size=8), Layout(name="logs"))

        def generate_layout():
            # 状态区域
            status_table = Table(show_header=False, box=None)
            status_table.add_row("Status:", f"[green]{self.status}[/green]")
            status_table.add_row("Logs:", str(len(self.logs)))

            for key, value in self.stats.items():
                status_table.add_row(f"{key}:", str(value))

            layout["status"].update(
                Panel(
                    status_table,
                    title=f"[bold cyan]{self.source}[/bold cyan]",
                    border_style="cyan",
                )
            )

            # 日志区域
            log_table = Table(show_header=True, header_style="bold magenta")
            log_table.add_column("Time", style="dim", width=12)
            log_table.add_column("Level", width=8)
            log_table.add_column("Message", min_width=40)

            recent_logs = self.get_recent_logs(15)
            for entry in recent_logs:
                time_str = entry.timestamp.strftime("%H:%M:%S")
                level_style = self.level_styles.get(entry.level, "")

                log_table.add_row(
                    time_str,
                    f"[{level_style}]{entry.level.value}[/{level_style}]",
                    (
                        entry.message[:80] + "..."
                        if len(entry.message) > 80
                        else entry.message
                    ),
                )

            layout["logs"].update(
                Panel(
                    log_table,
                    title="[bold yellow]Live Logs[/bold yellow]",
                    border_style="yellow",
                )
            )

            return layout

        self.live_display = Live(generate_layout(), refresh_per_second=2)
        return self.live_display

    def stop_live_display(self):
        """停止实时显示"""
        if self.live_display:
            self.live_display.stop()
            self.live_display = None
        self.is_live = False

    @contextmanager
    def live_context(self):
        """实时显示上下文管理器"""
        live = self.start_live_display()
        try:
            with live:
                yield
        finally:
            self.stop_live_display()


def create_monitor(
    source: str,
    mode: OutputMode = OutputMode.BASE,
    output_file: Optional[TextIO] = None,
) -> BaseMonitor:
    """创建监控器"""
    if mode == OutputMode.RICH:
        if not RICH_AVAILABLE:
            print("Warning: Rich library not available, falling back to base mode")
            return BaseMonitor(source, output_file)
        return RichMonitor(source, output_file)
    else:
        return BaseMonitor(source, output_file)


# 全局监控器管理
class MonitorManager:
    """监控器管理器"""

    def __init__(self):
        self.monitors: Dict[str, BaseMonitor] = {}
        self.default_mode = OutputMode.BASE

    def set_default_mode(self, mode: OutputMode):
        """设置默认输出模式"""
        self.default_mode = mode

    def get_monitor(
        self,
        source: str,
        mode: Optional[OutputMode] = None,
        output_file: Optional[TextIO] = None,
    ) -> BaseMonitor:
        """获取或创建监控器"""
        if source not in self.monitors:
            actual_mode = mode or self.default_mode
            self.monitors[source] = create_monitor(source, actual_mode, output_file)
        return self.monitors[source]

    def remove_monitor(self, source: str):
        """移除监控器"""
        if source in self.monitors:
            monitor = self.monitors[source]
            if hasattr(monitor, "stop_live_display"):
                monitor.stop_live_display()
            del self.monitors[source]

    def get_all_monitors(self) -> Dict[str, BaseMonitor]:
        """获取所有监控器"""
        return self.monitors.copy()

    def show_all_status(self):
        """显示所有监控器状态"""
        if not self.monitors:
            print("No monitors active")
            return

        for source, monitor in self.monitors.items():
            monitor.show_status()
            print()  # 空行分隔

    def cleanup(self):
        """清理所有监控器"""
        for source in list(self.monitors.keys()):
            self.remove_monitor(source)


# 全局管理器实例
monitor_manager = MonitorManager()


# 便捷函数
def get_monitor(source: str, mode: Optional[OutputMode] = None) -> BaseMonitor:
    """获取监控器的便捷函数"""
    return monitor_manager.get_monitor(source, mode)


def set_rich_mode():
    """启用 Rich 模式"""
    monitor_manager.set_default_mode(OutputMode.RICH)


def set_base_mode():
    """启用基础模式"""
    monitor_manager.set_default_mode(OutputMode.BASE)
