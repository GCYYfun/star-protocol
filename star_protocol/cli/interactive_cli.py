"""
交互式命令行界面 - 主入口类
"""

import asyncio
import threading
import signal
import sys
from typing import Dict, Any, List, Optional, Callable
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.table import Table

from .commands import (
    CommandRegistry,
    HelpCommand,
    ClearCommand,
    ExitCommand,
    StatusCommand,
)
from .plugins import PluginManager, PluginCommand


class InteractiveCLI:
    """交互式命令行界面"""

    def __init__(
        self,
        app_name: str = "Star Protocol",
        app_context: Optional[Dict[str, Any]] = None,
    ):
        self.app_name = app_name
        self.console = Console()
        self.registry = CommandRegistry()
        self.plugin_manager = PluginManager(self.registry)
        self.app_context = app_context or {}

        # 将自己添加到上下文中，方便命令访问
        self.app_context["_cli"] = self

        # 状态控制
        self.running = False
        self.input_thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # 输入状态管理
        self._input_active = False
        self._prompt_lock = threading.Lock()

        # 回调函数
        self.on_exit_callback: Optional[Callable] = None

        # 初始化基础命令
        self._init_basic_commands()

        # 加载全局装饰器命令
        self._load_global_commands()

        # 注册信号处理
        self._setup_signal_handlers()

    def _init_basic_commands(self):
        """初始化基础命令"""
        self.registry.register(HelpCommand(self.registry))
        self.registry.register(ClearCommand())
        self.registry.register(ExitCommand())
        self.registry.register(StatusCommand())
        self.registry.register(PluginCommand(self.plugin_manager))

    def _load_global_commands(self):
        """加载全局装饰器命令"""
        global_registry = get_global_registry()
        for name, command in global_registry.commands.items():
            self.registry.register(command)

    def _setup_signal_handlers(self):
        """设置信号处理器"""

        def signal_handler(signum, frame):
            self.console.print("\n[yellow]收到中断信号，正在退出...[/yellow]")
            self.stop()

        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, signal_handler)

    def set_exit_callback(self, callback: Callable):
        """设置退出回调函数"""
        self.on_exit_callback = callback

    def add_custom_command(self, command):
        """添加自定义命令"""
        self.registry.register(command)

    def update_context(self, key: str, value: Any):
        """更新应用上下文"""
        self.app_context[key] = value

    def get_context(self, key: str, default=None):
        """获取应用上下文"""
        return self.app_context.get(key, default)

    def get_available_commands_str(self) -> str:
        """获取可用命令的格式化字符串"""
        available_commands = list(self.registry.commands.keys())
        return ", ".join(sorted(available_commands))

    def get_available_commands_list(self) -> list:
        """获取可用命令的列表"""
        return list(self.registry.commands.keys())

    def async_print(self, *args, **kwargs):
        """
        异步安全的打印方法
        用于在交互模式下安全地输出异步消息
        """
        return self.print_with_prompt_restore(*args, **kwargs)

    def print_with_prompt_restore(self, *args, **kwargs):
        """
        打印消息并恢复输入提示符
        用于异步消息输出，避免打断用户输入
        """
        with self._prompt_lock:
            # 如果正在输入状态，先清空当前行
            if self._input_active:
                # 清空当前行并移动到行首
                print("\r\033[K", end="", flush=True)

            # 打印消息
            self.console.print(*args, **kwargs)

            # 如果正在输入状态，重新显示提示符
            if self._input_active:
                print("\033[1;95m📝 CMD >\033[0m ", end="", flush=True)

    async def run_interactive(self):
        """启动交互式模式（异步方式）"""
        self.start()

        try:
            # 保持事件循环运行
            while self.running:
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            self.console.print("\n[yellow]收到中断信号，正在退出...[/yellow]")
        finally:
            self.stop()

    async def execute_command(self, command_line: str):
        """直接执行命令（用于非交互模式）"""
        await self._execute_command(command_line)

    def start(self):
        """启动交互式界面"""
        if self.running:
            return

        self.running = True
        self.loop = asyncio.get_event_loop()

        # 显示欢迎信息
        self._show_welcome()

        # 启动输入线程
        self.input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self.input_thread.start()

    def stop(self):
        """停止交互式界面"""
        if not self.running:
            return

        self.running = False

        # 调用退出回调
        if self.on_exit_callback:
            try:
                self.on_exit_callback()
            except Exception as e:
                self.console.print(f"[red]退出回调执行失败: {e}[/red]")

        self.console.print("[yellow]交互式命令行已停止[/yellow]")

    def _show_welcome(self):
        """显示欢迎信息"""
        welcome_panel = Panel.fit(
            f"[bold blue]{self.app_name}[/bold blue]\n"
            f"[dim]交互式命令行界面[/dim]\n\n"
            f"[green]• 输入 'help' 查看可用命令[/green]\n"
            f"[green]• 输入 'exit' 退出程序[/green]\n"
            f"[green]• 支持Tab补全和历史记录[/green]",
            title="欢迎",
            border_style="blue",
        )
        self.console.print(welcome_panel)

    def _input_loop(self):
        """输入循环（在单独线程中运行）"""
        import time

        # 稍微等待一下，确保欢迎信息完全显示
        time.sleep(0.1)

        while self.running:
            try:
                # 标记进入输入状态
                with self._prompt_lock:
                    self._input_active = True

                # 显示提示符并获取输入
                print("\033[1;95m📝 CMD >\033[0m ", end="", flush=True)
                user_input = input()

                # 标记退出输入状态
                with self._prompt_lock:
                    self._input_active = False

                if not user_input.strip():
                    continue

                # 在事件循环中执行命令
                if self.loop and self.running:
                    future = asyncio.run_coroutine_threadsafe(
                        self._execute_command(user_input.strip()), self.loop
                    )
                    # 等待命令执行完成，避免输出混乱
                    try:
                        future.result(timeout=30)  # 30秒超时
                    except asyncio.TimeoutError:
                        self.console.print("[red]命令执行超时[/red]")

            except EOFError:
                # Ctrl+D
                break
            except KeyboardInterrupt:
                # Ctrl+C在输入时
                with self._prompt_lock:
                    self._input_active = False
                self.console.print("\n[yellow]使用 'exit' 命令退出[/yellow]")
                continue
            except Exception as e:
                with self._prompt_lock:
                    self._input_active = False
                self.console.print(f"[red]输入处理错误: {e}[/red]")

    async def _execute_command(self, command_line: str):
        """执行命令"""
        try:
            # 解析命令行
            parts = command_line.split()
            if not parts:
                return

            command_name = parts[0]
            args = parts[1:]

            # 查找并执行命令
            command = self.registry.get_command(command_name)
            if command:
                await command.execute(args, self.app_context)
            else:
                self.console.print(
                    f"[bold red]❌ ERROR >[/bold red] 未知命令: {command_name}"
                )
                self.console.print(
                    f"[bold yellow]💡 HINT  >[/bold yellow] 输入 'help' 查看可用命令"
                )

        except Exception as e:
            self.console.print(f"[bold red]❌ ERROR >[/bold red] 命令执行错误: {e}")

    def print_status(self):
        """打印状态信息"""
        status_table = Table(title="系统状态")
        status_table.add_column("项目", style="cyan")
        status_table.add_column("值", style="green")

        status_table.add_row("应用名称", self.app_name)
        status_table.add_row("运行状态", "运行中" if self.running else "已停止")
        status_table.add_row("注册命令数", str(len(self.registry.commands)))
        status_table.add_row("加载插件数", str(len(self.plugin_manager.loaded_plugins)))

        # 添加应用上下文信息
        for key, value in self.app_context.items():
            status_table.add_row(f"上下文.{key}", str(value))

        self.console.print(status_table)


# 便捷函数
def create_cli(
    app_name: str = "Star Protocol", app_context: Optional[Dict[str, Any]] = None
) -> InteractiveCLI:
    """创建交互式命令行实例"""
    return InteractiveCLI(app_name, app_context)


# 全局命令注册表（用于装饰器自动注册）
_global_registry = None


def get_global_registry():
    """获取全局命令注册表"""
    global _global_registry
    if _global_registry is None:
        from .commands import CommandRegistry

        _global_registry = CommandRegistry()
    return _global_registry


# 装饰器：将函数转换为命令并自动注册
def command(name: str, description: str = "", aliases: Optional[List[str]] = None):
    """
    将函数转换为命令的装饰器，自动注册到全局注册表

    使用方法:
    @command("hello", "打招呼命令", ["hi", "h"])
    async def hello_cmd(cli):
        print(f"Hello World!")
    """

    def decorator(func):
        from .commands import BaseCommand

        class FunctionCommand(BaseCommand):
            def __init__(self):
                super().__init__(name, description or func.__doc__ or "", aliases or [])
                self.func = func
                # 设置函数的元信息
                self.__name__ = func.__name__
                self.__doc__ = func.__doc__

            async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
                try:
                    # 执行函数 - 传递 CLI 实例
                    cli_instance = context.get("_cli")
                    if asyncio.iscoroutinefunction(self.func):
                        result = await self.func(cli_instance)
                    else:
                        result = self.func(cli_instance)

                    return result
                except Exception as e:
                    self.console.print(
                        f"[bold red]❌ ERROR>[/bold red] 命令 '{name}' 执行失败: {e}"
                    )
                    raise

        # 创建命令实例并自动注册
        command_instance = FunctionCommand()
        global_registry = get_global_registry()
        global_registry.register(command_instance)

        return func

    return decorator


# 高级装饰器：带参数验证的命令
def command_with_args(
    name: str,
    description: str = "",
    aliases: Optional[List[str]] = None,
    expected_args: Optional[int] = None,
    usage: str = "",
):
    """
    带参数验证的命令装饰器

    使用方法:
    @command_with_args("greet", "问候命令", expected_args=1, usage="greet <name>")
    def greet_cmd(cli, args):
        name = args[0]
        return f"Hello, {name}!"
    """

    def decorator(func):
        from .commands import BaseCommand

        class ValidatedCommand(BaseCommand):
            def __init__(self):
                super().__init__(name, description or func.__doc__ or "", aliases or [])
                self.func = func
                self.expected_args = expected_args
                self.usage = usage

            async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
                # 参数验证（仅当 expected_args 不为 None 时）
                if self.expected_args is not None and len(args) != self.expected_args:
                    self.console.print(
                        f"[bold red]❌ ERROR>[/bold red] 命令 '{name}' 需要 {self.expected_args} 个参数，实际提供了 {len(args)} 个"
                    )
                    if self.usage:
                        self.console.print(f"[yellow]用法：{self.usage}[/yellow]")
                    return

                try:
                    # 执行函数 - 传递 CLI 实例和参数
                    cli_instance = context.get("_cli")
                    if asyncio.iscoroutinefunction(self.func):
                        result = await self.func(cli_instance, args)
                    else:
                        result = self.func(cli_instance, args)

                    return result
                except Exception as e:
                    self.console.print(
                        f"[bold red]❌ ERROR>[/bold red] 命令 '{name}' 执行失败: {e}"
                    )
                    raise

        # 创建命令实例并自动注册
        command_instance = ValidatedCommand()
        global_registry = get_global_registry()
        global_registry.register(command_instance)

        return func

    return decorator
