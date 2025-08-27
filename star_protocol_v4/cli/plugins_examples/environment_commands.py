"""
示例插件 - Environment 客户端相关命令
"""

from typing import List, Dict, Any
from rich.table import Table
from rich.panel import Panel

from ..commands import BaseCommand


class EnvironmentStatusCommand(BaseCommand):
    """Environment 客户端状态命令"""

    def __init__(self):
        super().__init__("status", "显示 Environment 客户端状态", ["es"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        environment = context.get("environment")

        if not environment:
            self.console.print("[red]❌ Environment 客户端未启动[/red]")
            return

        # 创建状态表格
        status_table = Table(title="Environment 客户端状态")
        status_table.add_column("项目", style="cyan")
        status_table.add_column("值", style="green")

        status_table.add_row(
            "连接状态",
            (
                "已连接"
                if hasattr(environment, "websocket") and environment.websocket
                else "未连接"
            ),
        )
        status_table.add_row("Environment ID", environment.environment_id or "未设置")

        if hasattr(environment, "hub_url"):
            status_table.add_row("Hub 地址", environment.hub_url)

        # 显示环境状态
        if hasattr(environment, "state"):
            status_table.add_row("环境状态", str(environment.state))

        # 显示最近的消息统计
        if hasattr(environment, "message_count"):
            status_table.add_row("消息计数", str(environment.message_count))

        # 显示连接的 Agent
        if hasattr(environment, "connected_agents"):
            agents_list = (
                ", ".join(environment.connected_agents)
                if environment.connected_agents
                else "无"
            )
            status_table.add_row("连接的 Agents", agents_list)

        self.console.print(status_table)


class EnvironmentResponseCommand(BaseCommand):
    """向 Agent 发送响应"""

    def __init__(self):
        super().__init__("response", "向 Agent 发送环境响应", ["response"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        if len(args) < 2:
            self.console.print("[red]❌ 请提供 Agent ID 和响应内容[/red]")
            self.console.print("[dim]用法: response <agent_id> <响应内容>[/dim]")
            return

        environment = context.get("environment")
        if not environment:
            self.console.print("[red]❌ Environment 客户端未启动[/red]")
            return

        if not hasattr(environment, "websocket") or not environment.websocket:
            self.console.print("[red]❌ Environment 未连接到 Hub[/red]")
            return

        agent_id = args[0]
        response_content = " ".join(args[1:])

        try:
            # 构造响应消息
            message = {
                "type": "environment_response",
                "content": response_content,
                "from_environment": environment.environment_id,
                "to_agent": agent_id,
                "state": getattr(environment, "state", "unknown"),
            }

            # 发送消息
            await environment.send_message(message)
            self.console.print(
                f"[green]✅ 响应已发送给 {agent_id}: {response_content}[/green]"
            )

        except Exception as e:
            self.console.print(f"[red]❌ 发送响应失败: {e}[/red]")


class EnvironmentStateCommand(BaseCommand):
    """更新环境状态"""

    def __init__(self):
        super().__init__("env-state", "更新环境状态", ["state"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        if not args:
            environment = context.get("environment")
            if environment and hasattr(environment, "state"):
                self.console.print(f"[cyan]当前环境状态: {environment.state}[/cyan]")
            else:
                self.console.print("[yellow]无法获取环境状态[/yellow]")
            return

        environment = context.get("environment")
        if not environment:
            self.console.print("[red]❌ Environment 客户端未启动[/red]")
            return

        new_state = " ".join(args)

        try:
            # 更新状态
            if hasattr(environment, "state"):
                old_state = environment.state
                environment.state = new_state
                self.console.print(
                    f"[green]✅ 环境状态已更新: {old_state} → {new_state}[/green]"
                )

                # 如果连接到 Hub，通知状态变化
                if hasattr(environment, "websocket") and environment.websocket:
                    state_message = {
                        "type": "environment_state_change",
                        "from_environment": environment.environment_id,
                        "old_state": old_state,
                        "new_state": new_state,
                    }
                    await environment.send_message(state_message)
                    self.console.print("[dim]状态变化已通知 Hub[/dim]")
            else:
                self.console.print("[yellow]⚠️ 环境对象不支持状态设置[/yellow]")

        except Exception as e:
            self.console.print(f"[red]❌ 更新状态失败: {e}[/red]")


class EnvironmentDisconnectCommand(BaseCommand):
    """断开 Environment 连接"""

    def __init__(self):
        super().__init__("env-disconnect", "断开 Environment 连接", ["env-dc"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        environment = context.get("environment")

        if not environment:
            self.console.print("[red]❌ Environment 客户端未启动[/red]")
            return

        try:
            if hasattr(environment, "disconnect"):
                await environment.disconnect()
                self.console.print("[green]✅ Environment 已断开连接[/green]")
            else:
                self.console.print("[yellow]⚠️ 无法找到断开连接方法[/yellow]")

        except Exception as e:
            self.console.print(f"[red]❌ 断开连接失败: {e}[/red]")


class EnvironmentReconnectCommand(BaseCommand):
    """重新连接 Environment"""

    def __init__(self):
        super().__init__("env-reconnect", "重新连接 Environment", ["env-rc"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        environment = context.get("environment")

        if not environment:
            self.console.print("[red]❌ Environment 客户端未启动[/red]")
            return

        try:
            # 先断开
            if hasattr(environment, "disconnect"):
                await environment.disconnect()
                self.console.print("[yellow]正在断开现有连接...[/yellow]")

            # 再连接
            if hasattr(environment, "connect"):
                await environment.connect()
                self.console.print("[green]✅ Environment 重新连接成功[/green]")
            else:
                self.console.print("[yellow]⚠️ 无法找到连接方法[/yellow]")

        except Exception as e:
            self.console.print(f"[red]❌ 重新连接失败: {e}[/red]")
