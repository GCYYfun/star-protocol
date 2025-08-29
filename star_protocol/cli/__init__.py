"""
交互式命令行工具 - Rich 驱动的模块化热插拔命令行界面
"""

from .interactive_cli import InteractiveCLI, create_cli, command, command_with_args
from .commands import BaseCommand, CommandRegistry
from .plugins import PluginManager, PluginCommand
from .integration import (
    CLIIntegration,
    create_hub_cli,
    create_agent_cli,
    create_environment_cli,
    run_with_cli,
    with_cli,
)

__all__ = [
    "InteractiveCLI",
    "create_cli",
    "command",
    "BaseCommand",
    "CommandRegistry",
    "PluginManager",
    "PluginCommand",
    "CLIIntegration",
    "create_hub_cli",
    "create_agent_cli",
    "create_environment_cli",
    "run_with_cli",
    "with_cli",
]

from .interactive_cli import InteractiveCLI
from .commands import BaseCommand, CommandRegistry
from .plugins import PluginManager

__all__ = [
    "InteractiveCLI",
    "BaseCommand",
    "CommandRegistry",
    "PluginManager",
]
