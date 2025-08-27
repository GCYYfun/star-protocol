"""
命令系统基础类和注册表
"""

import asyncio
import inspect
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable, Union
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel


class BaseCommand(ABC):
    """命令基类"""

    def __init__(
        self, name: str, description: str, aliases: Optional[List[str]] = None
    ):
        self.name = name
        self.description = description
        self.aliases = aliases or []
        self.console = Console()

    @abstractmethod
    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        """执行命令

        Args:
            args: 命令参数
            context: 执行上下文（包含当前运行的demo实例等）

        Returns:
            命令执行结果
        """
        pass

    def get_help(self) -> str:
        """获取命令帮助信息"""
        return f"{self.name}: {self.description}"

    def validate_args(self, args: List[str]) -> bool:
        """验证参数"""
        return True


class CommandRegistry:
    """命令注册表"""

    def __init__(self):
        self.commands: Dict[str, BaseCommand] = {}
        self.aliases: Dict[str, str] = {}

    def register(self, command: BaseCommand) -> None:
        """注册命令"""
        self.commands[command.name] = command

        # 注册别名
        for alias in command.aliases:
            self.aliases[alias] = command.name

    def unregister(self, name: str) -> None:
        """注销命令"""
        if name in self.commands:
            command = self.commands[name]
            del self.commands[name]

            # 移除别名
            for alias in command.aliases:
                if alias in self.aliases:
                    del self.aliases[alias]

    def get_command(self, name: str) -> Optional[BaseCommand]:
        """获取命令"""
        # 先检查直接命令名
        if name in self.commands:
            return self.commands[name]

        # 再检查别名
        if name in self.aliases:
            return self.commands[self.aliases[name]]

        return None

    def get(self, name: str) -> Optional[BaseCommand]:
        """获取命令（get_command的别名）"""
        return self.get_command(name)

    def list_commands(self) -> List[BaseCommand]:
        """列出所有命令"""
        return list(self.commands.values())

    def get_command_names(self) -> List[str]:
        """获取所有命令名（包括别名）"""
        names = list(self.commands.keys())
        names.extend(self.aliases.keys())
        return sorted(names)


class HelpCommand(BaseCommand):
    """帮助命令"""

    def __init__(self, registry: CommandRegistry):
        super().__init__("help", "显示帮助信息", ["h", "?"])
        self.registry = registry

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        if args:
            # 显示特定命令的帮助
            command_name = args[0]
            command = self.registry.get_command(command_name)
            if command:
                self.console.print(
                    f"[bold blue]{command.name}[/bold blue]: {command.description}"
                )
                if command.aliases:
                    self.console.print(f"[dim]别名: {', '.join(command.aliases)}[/dim]")
            else:
                self.console.print(f"[red]未找到命令: {command_name}[/red]")
        else:
            # 显示所有命令
            table = Table(title="可用命令")
            table.add_column("命令", style="cyan", no_wrap=True)
            table.add_column("别名", style="dim")
            table.add_column("描述", style="green")

            for command in self.registry.list_commands():
                aliases_str = ", ".join(command.aliases) if command.aliases else ""
                table.add_row(command.name, aliases_str, command.description)

            self.console.print(table)


class ClearCommand(BaseCommand):
    """清屏命令"""

    def __init__(self):
        super().__init__("clear", "清除屏幕", ["cls"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        self.console.clear()


class ExitCommand(BaseCommand):
    """退出命令"""

    def __init__(self):
        super().__init__("exit", "退出程序", ["quit", "q"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        self.console.print("[yellow]正在退出...[/yellow]")
        # 通过上下文中的 CLI 实例设置退出标志
        cli = context.get("_cli")
        if cli:
            cli.stop()
        return "exit"


class StatusCommand(BaseCommand):
    """状态命令"""

    def __init__(self):
        super().__init__("status", "显示当前状态", ["st"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        demo = context.get("demo")
        if not demo:
            self.console.print("[red]没有找到运行中的demo实例[/red]")
            return

        # 创建状态面板
        status_info = []

        # 基本信息
        if hasattr(demo, "running"):
            status_info.append(
                f"运行状态: {'🟢 运行中' if demo.running else '🔴 已停止'}"
            )

        # Hub服务器状态
        if hasattr(demo, "hub_server"):
            hub_running = demo.hub_server and demo.hub_server.running
            status_info.append(
                f"Hub服务器: {'🟢 运行中' if hub_running else '🔴 已停止'}"
            )
            if hasattr(demo, "host") and hasattr(demo, "port"):
                status_info.append(f"服务地址: {demo.host}:{demo.port}")

        # Agent状态
        if hasattr(demo, "client") and hasattr(demo.client, "connected"):
            connected = demo.client.connected
            status_info.append(f"连接状态: {'🟢 已连接' if connected else '🔴 未连接'}")

        # 环境状态
        if hasattr(demo, "world"):
            world = demo.world
            status_info.append(f"世界大小: {world.width}x{world.height}")
            status_info.append(f"活跃Agent: {len(world.agents)}")
            status_info.append(f"物品数量: {len(world.items)}")

        # 监控状态
        if hasattr(demo, "monitor") and demo.monitor:
            status_info.append("📊 监控: 启用")

        status_text = "\n".join(status_info) if status_info else "无状态信息"

        panel = Panel(status_text, title="📊 系统状态", border_style="blue")
        self.console.print(panel)


def create_default_registry() -> CommandRegistry:
    """创建默认命令注册表"""
    registry = CommandRegistry()

    # 注册基础命令
    registry.register(ClearCommand())
    registry.register(ExitCommand())
    registry.register(StatusCommand())

    # 帮助命令需要访问注册表
    registry.register(HelpCommand(registry))

    return registry
