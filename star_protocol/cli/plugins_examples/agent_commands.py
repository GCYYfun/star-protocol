"""
示例插件 - Agent 客户端相关命令
"""

from typing import List, Dict, Any
from rich.table import Table
from rich.panel import Panel

from ..commands import BaseCommand


class AgentStatusCommand(BaseCommand):
    """Agent 客户端状态命令"""

    def __init__(self):
        super().__init__("agent-status", "显示 Agent 客户端状态", ["as"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        agent = context.get("agent")

        if not agent:
            self.console.print("[red]❌ Agent 客户端未启动[/red]")
            return

        # 创建状态表格
        status_table = Table(title="Agent 客户端状态")
        status_table.add_column("项目", style="cyan")
        status_table.add_column("值", style="green")

        status_table.add_row(
            "连接状态",
            "已连接" if hasattr(agent, "websocket") and agent.websocket else "未连接",
        )
        status_table.add_row("Agent ID", agent.agent_id or "未设置")

        if hasattr(agent, "hub_url"):
            status_table.add_row("Hub 地址", agent.hub_url)

        if hasattr(agent, "environment_id"):
            status_table.add_row("环境 ID", agent.environment_id or "未指定")

        # 显示最近的消息统计
        if hasattr(agent, "message_count"):
            status_table.add_row("消息计数", str(agent.message_count))

        self.console.print(status_table)


class AgentSendCommand(BaseCommand):
    """向环境发送消息"""

    def __init__(self):
        super().__init__("agent-send", "向环境发送消息", ["send"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        if not args:
            self.console.print("[red]❌ 请提供要发送的消息[/red]")
            self.console.print("[dim]用法: agent-send <消息内容>[/dim]")
            return

        agent = context.get("agent")
        if not agent:
            self.console.print("[red]❌ Agent 客户端未启动[/red]")
            return

        if not hasattr(agent, "websocket") or not agent.websocket:
            self.console.print("[red]❌ Agent 未连接到 Hub[/red]")
            return

        message_content = " ".join(args)

        try:
            # 构造消息
            message = {
                "type": "agent_action",
                "content": message_content,
                "from_agent": agent.agent_id,
                "to_environment": agent.environment_id,
            }

            # 发送消息
            await agent.send_message(message)
            self.console.print(f"[green]✅ 消息已发送: {message_content}[/green]")

        except Exception as e:
            self.console.print(f"[red]❌ 发送消息失败: {e}[/red]")


class AgentDisconnectCommand(BaseCommand):
    """断开 Agent 连接"""

    def __init__(self):
        super().__init__("agent-disconnect", "断开 Agent 连接", ["disconnect"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        agent = context.get("agent")

        if not agent:
            self.console.print("[red]❌ Agent 客户端未启动[/red]")
            return

        try:
            if hasattr(agent, "disconnect"):
                await agent.disconnect()
                self.console.print("[green]✅ Agent 已断开连接[/green]")
            else:
                self.console.print("[yellow]⚠️ 无法找到断开连接方法[/yellow]")

        except Exception as e:
            self.console.print(f"[red]❌ 断开连接失败: {e}[/red]")


class AgentReconnectCommand(BaseCommand):
    """重新连接 Agent"""

    def __init__(self):
        super().__init__("agent-reconnect", "重新连接 Agent", ["reconnect"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        agent = context.get("agent")

        if not agent:
            self.console.print("[red]❌ Agent 客户端未启动[/red]")
            return

        try:
            # 先断开
            if hasattr(agent, "disconnect"):
                await agent.disconnect()
                self.console.print("[yellow]正在断开现有连接...[/yellow]")

            # 再连接
            if hasattr(agent, "connect"):
                await agent.connect()
                self.console.print("[green]✅ Agent 重新连接成功[/green]")
            else:
                self.console.print("[yellow]⚠️ 无法找到连接方法[/yellow]")

        except Exception as e:
            self.console.print(f"[red]❌ 重新连接失败: {e}[/red]")
