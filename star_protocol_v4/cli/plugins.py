"""
插件管理器 - 支持热插拔命令插件
"""

import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Type, Optional
from rich.console import Console

from .commands import BaseCommand, CommandRegistry


class PluginManager:
    """插件管理器"""

    def __init__(self, registry: CommandRegistry):
        self.registry = registry
        self.console = Console()
        self.loaded_plugins: Dict[str, Any] = {}
        self.plugin_paths: List[str] = []

    def add_plugin_path(self, path: str) -> None:
        """添加插件搜索路径"""
        if path not in self.plugin_paths:
            self.plugin_paths.append(path)
            if path not in sys.path:
                sys.path.insert(0, path)

    def discover_plugins(self, directory: str) -> List[str]:
        """发现插件目录中的插件"""
        plugins = []
        plugin_dir = Path(directory)

        if not plugin_dir.exists():
            return plugins

        for file_path in plugin_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue

            plugin_name = file_path.stem
            plugins.append(plugin_name)

        return plugins

    def load_plugin(self, plugin_name: str, plugin_path: Optional[str] = None) -> bool:
        """加载插件"""
        try:
            # 如果指定了路径，添加到搜索路径
            if plugin_path:
                self.add_plugin_path(plugin_path)

            # 导入插件模块
            if plugin_name in self.loaded_plugins:
                # 重新加载
                importlib.reload(self.loaded_plugins[plugin_name])
            else:
                module = importlib.import_module(plugin_name)
                self.loaded_plugins[plugin_name] = module

            # 查找并注册命令
            self._register_plugin_commands(self.loaded_plugins[plugin_name])

            self.console.print(f"[green]✅ 插件 '{plugin_name}' 加载成功[/green]")
            return True

        except Exception as e:
            self.console.print(f"[red]❌ 加载插件 '{plugin_name}' 失败: {e}[/red]")
            return False

    def unload_plugin(self, plugin_name: str) -> bool:
        """卸载插件"""
        try:
            if plugin_name not in self.loaded_plugins:
                self.console.print(f"[yellow]插件 '{plugin_name}' 未加载[/yellow]")
                return False

            # 卸载插件命令
            self._unregister_plugin_commands(self.loaded_plugins[plugin_name])

            # 从加载列表中移除
            del self.loaded_plugins[plugin_name]

            # 从模块缓存中移除
            if plugin_name in sys.modules:
                del sys.modules[plugin_name]

            self.console.print(f"[green]✅ 插件 '{plugin_name}' 卸载成功[/green]")
            return True

        except Exception as e:
            self.console.print(f"[red]❌ 卸载插件 '{plugin_name}' 失败: {e}[/red]")
            return False

    def reload_plugin(self, plugin_name: str) -> bool:
        """重新加载插件"""
        if plugin_name in self.loaded_plugins:
            self.unload_plugin(plugin_name)
        return self.load_plugin(plugin_name)

    def list_loaded_plugins(self) -> List[str]:
        """列出已加载的插件"""
        return list(self.loaded_plugins.keys())

    def _register_plugin_commands(self, module) -> None:
        """注册插件中的命令"""
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseCommand)
                and obj != BaseCommand
            ):

                # 实例化并注册命令
                try:
                    command = obj()
                    self.registry.register(command)
                    self.console.print(f"[dim]  - 注册命令: {command.name}[/dim]")
                except Exception as e:
                    self.console.print(f"[yellow]  - 跳过命令 {name}: {e}[/yellow]")

    def _unregister_plugin_commands(self, module) -> None:
        """注销插件中的命令"""
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseCommand)
                and obj != BaseCommand
            ):

                # 查找并注销命令
                for command_name, command in list(self.registry.commands.items()):
                    if isinstance(command, obj):
                        self.registry.unregister(command_name)
                        self.console.print(f"[dim]  - 注销命令: {command_name}[/dim]")


class PluginCommand(BaseCommand):
    """插件管理命令"""

    def __init__(self, plugin_manager: PluginManager):
        super().__init__("plugin", "管理插件", ["pl"])
        self.plugin_manager = plugin_manager

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        if not args:
            self._show_help()
            return

        action = args[0].lower()

        if action == "list":
            self._list_plugins()
        elif action == "load" and len(args) > 1:
            plugin_name = args[1]
            plugin_path = args[2] if len(args) > 2 else None
            self.plugin_manager.load_plugin(plugin_name, plugin_path)
        elif action == "unload" and len(args) > 1:
            plugin_name = args[1]
            self.plugin_manager.unload_plugin(plugin_name)
        elif action == "reload" and len(args) > 1:
            plugin_name = args[1]
            self.plugin_manager.reload_plugin(plugin_name)
        elif action == "discover" and len(args) > 1:
            directory = args[1]
            plugins = self.plugin_manager.discover_plugins(directory)
            self.console.print(f"[blue]发现插件: {', '.join(plugins)}[/blue]")
        else:
            self._show_help()

    def _show_help(self):
        help_text = """
[bold blue]插件管理命令:[/bold blue]

[cyan]plugin list[/cyan]                    - 列出已加载的插件
[cyan]plugin load <name> [path][/cyan]      - 加载插件
[cyan]plugin unload <name>[/cyan]           - 卸载插件  
[cyan]plugin reload <name>[/cyan]           - 重新加载插件
[cyan]plugin discover <directory>[/cyan]    - 发现目录中的插件
        """
        self.console.print(help_text)

    def _list_plugins(self):
        plugins = self.plugin_manager.list_loaded_plugins()
        if plugins:
            self.console.print(f"[green]已加载插件: {', '.join(plugins)}[/green]")
        else:
            self.console.print("[yellow]没有已加载的插件[/yellow]")
