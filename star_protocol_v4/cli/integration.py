"""
CLI 集成工具 - 将交互式命令行集成到现有应用中
"""

import asyncio
from typing import Optional, Dict, Any, Callable
from pathlib import Path

from .interactive_cli import InteractiveCLI


class CLIIntegration:
    """CLI 集成助手"""

    @staticmethod
    def integrate_with_hub_server(cli: InteractiveCLI, hub_server) -> None:
        """集成 Hub 服务器"""
        # 更新上下文
        cli.update_context("hub_server", hub_server)

        # 加载 Hub 相关插件
        plugins_dir = Path(__file__).parent / "plugins_examples"
        cli.plugin_manager.add_plugin_path(str(plugins_dir))
        cli.plugin_manager.load_plugin("hub_commands")

    @staticmethod
    def integrate_with_agent(cli: InteractiveCLI, agent) -> None:
        """集成 Agent 客户端"""
        # 更新上下文
        cli.update_context("agent", agent)

        # 加载 Agent 相关插件（暂时禁用以避免导入错误）
        # plugins_dir = Path(__file__).parent / "plugins_examples"
        # cli.plugin_manager.add_plugin_path(str(plugins_dir))
        # cli.plugin_manager.load_plugin("agent_commands")

    @staticmethod
    def integrate_with_environment(cli: InteractiveCLI, environment) -> None:
        """集成 Environment 客户端"""
        # 更新上下文
        cli.update_context("environment", environment)

        # 加载 Environment 相关插件
        plugins_dir = Path(__file__).parent / "plugins_examples"
        cli.plugin_manager.add_plugin_path(str(plugins_dir))
        cli.plugin_manager.load_plugin("environment_commands")


def create_hub_cli(hub_server, app_name: str = "Hub Server") -> InteractiveCLI:
    """为 Hub 服务器创建交互式 CLI"""
    cli = InteractiveCLI(app_name)
    CLIIntegration.integrate_with_hub_server(cli, hub_server)
    return cli


def create_agent_cli(agent, app_name: str = "Agent Client") -> InteractiveCLI:
    """为 Agent 客户端创建交互式 CLI"""
    cli = InteractiveCLI(app_name)
    CLIIntegration.integrate_with_agent(cli, agent)
    return cli


def create_environment_cli(
    environment, app_name: str = "Environment Client"
) -> InteractiveCLI:
    """为 Environment 客户端创建交互式 CLI"""
    cli = InteractiveCLI(app_name)
    CLIIntegration.integrate_with_environment(cli, environment)
    return cli


async def run_with_cli(
    main_coroutine: Callable,
    cli: InteractiveCLI,
    setup_callback: Optional[Callable] = None,
):
    """运行主协程并启动 CLI"""
    try:
        # 启动 CLI
        cli.start()

        # 如果有设置回调，执行它
        if setup_callback:
            setup_callback(cli)

        # 运行主协程
        await main_coroutine()

    except KeyboardInterrupt:
        cli.console.print("\n[yellow]收到中断信号，正在退出...[/yellow]")
    finally:
        cli.stop()


# 便捷装饰器
def with_cli(cli_type: str = "generic", app_name: Optional[str] = None):
    """装饰器：为函数添加 CLI 支持"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 确定应用名称
            name = app_name or func.__name__.replace("_", " ").title()

            # 创建 CLI
            if cli_type == "hub":
                # 假设第一个参数是 hub_server
                cli = create_hub_cli(args[0] if args else None, name)
            elif cli_type == "agent":
                # 假设第一个参数是 agent
                cli = create_agent_cli(args[0] if args else None, name)
            elif cli_type == "environment":
                # 假设第一个参数是 environment
                cli = create_environment_cli(args[0] if args else None, name)
            else:
                cli = InteractiveCLI(name)

            # 运行函数与 CLI
            await run_with_cli(lambda: func(*args, **kwargs), cli)

        return wrapper

    return decorator
