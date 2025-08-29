"""
示例插件 - Hub 服务器相关命令
"""

from typing import List, Dict, Any
from rich.table import Table
from rich.panel import Panel

from ..commands import BaseCommand


class HubStatusCommand(BaseCommand):
    """Hub 服务器状态命令"""

    def __init__(self):
        super().__init__("hub-status", "显示 Hub 服务器状态", ["hs"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        hub_server = context.get("hub_server")

        if not hub_server:
            self.console.print("[red]❌ Hub 服务器未启动[/red]")
            return

        # 创建状态表格
        status_table = Table(title="Hub 服务器状态")
        status_table.add_column("项目", style="cyan")
        status_table.add_column("值", style="green")

        status_table.add_row(
            "服务器状态",
            (
                "运行中"
                if hasattr(hub_server, "server") and hub_server.server
                else "未启动"
            ),
        )
        status_table.add_row("监听地址", f"{hub_server.host}:{hub_server.port}")

        # 连接信息
        if hasattr(hub_server, "sessions"):
            status_table.add_row("活跃连接数", str(len(hub_server.sessions)))

            # 统计客户端类型
            agents = sum(
                1 for s in hub_server.sessions.values() if s.client_type == "agent"
            )
            environments = sum(
                1
                for s in hub_server.sessions.values()
                if s.client_type == "environment"
            )
            humans = sum(
                1 for s in hub_server.sessions.values() if s.client_type == "human"
            )

            status_table.add_row("Agent 数量", str(agents))
            status_table.add_row("Environment 数量", str(environments))
            status_table.add_row("Human 数量", str(humans))

        self.console.print(status_table)


class HubClientsCommand(BaseCommand):
    """显示 Hub 连接的客户端列表"""

    def __init__(self):
        super().__init__("hub-clients", "显示连接的客户端列表", ["hc"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        hub_server = context.get("hub_server")

        if not hub_server or not hasattr(hub_server, "sessions"):
            self.console.print("[red]❌ Hub 服务器未启动或无会话信息[/red]")
            return

        if not hub_server.sessions:
            self.console.print("[yellow]📭 当前无客户端连接[/yellow]")
            return

        # 创建客户端表格
        clients_table = Table(title="连接的客户端")
        clients_table.add_column("ID", style="cyan")
        clients_table.add_column("类型", style="green")
        clients_table.add_column("标识符", style="yellow")
        clients_table.add_column("连接时间", style="dim")

        for session_id, session in hub_server.sessions.items():
            clients_table.add_row(
                session_id[:8] + "...",
                session.client_type,
                session.client_id or "未设置",
                str(getattr(session, "connected_at", "N/A")),
            )

        self.console.print(clients_table)


class HubBroadcastCommand(BaseCommand):
    """向所有客户端广播消息"""

    def __init__(self):
        super().__init__("hub-broadcast", "向所有客户端广播消息", ["hb"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        if not args:
            self.console.print("[red]❌ 请提供要广播的消息[/red]")
            self.console.print("[dim]用法: hub-broadcast <消息内容>[/dim]")
            return

        hub_server = context.get("hub_server")
        if not hub_server:
            self.console.print("[red]❌ Hub 服务器未启动[/red]")
            return

        message = " ".join(args)

        # 构造广播消息
        broadcast_msg = {
            "type": "system_message",
            "content": message,
            "from": "cli_admin",
        }

        try:
            # 发送给所有连接的客户端
            if hasattr(hub_server, "sessions"):
                sent_count = 0
                for session in hub_server.sessions.values():
                    try:
                        await session.send_message(broadcast_msg)
                        sent_count += 1
                    except Exception as e:
                        self.console.print(
                            f"[yellow]⚠️ 发送到 {session.client_id} 失败: {e}[/yellow]"
                        )

                self.console.print(
                    f"[green]✅ 消息已广播到 {sent_count} 个客户端[/green]"
                )
            else:
                self.console.print("[yellow]📭 当前无客户端连接[/yellow]")

        except Exception as e:
            self.console.print(f"[red]❌ 广播失败: {e}[/red]")


class HubShutdownCommand(BaseCommand):
    """关闭 Hub 服务器"""

    def __init__(self):
        super().__init__("hub-shutdown", "关闭 Hub 服务器", ["shutdown"])

    async def execute(self, args: List[str], context: Dict[str, Any]) -> Any:
        hub_server = context.get("hub_server")

        if not hub_server:
            self.console.print("[red]❌ Hub 服务器未启动[/red]")
            return

        # 确认关闭
        from rich.prompt import Confirm

        if not Confirm.ask("[yellow]确认关闭 Hub 服务器？[/yellow]"):
            self.console.print("[cyan]操作已取消[/cyan]")
            return

        try:
            # 通知所有客户端服务器即将关闭
            shutdown_msg = {
                "type": "server_shutdown",
                "content": "服务器即将关闭",
                "from": "server",
            }

            if hasattr(hub_server, "sessions"):
                for session in hub_server.sessions.values():
                    try:
                        await session.send_message(shutdown_msg)
                    except:
                        pass

            # 关闭服务器
            if hasattr(hub_server, "stop"):
                await hub_server.stop()
                self.console.print("[green]✅ Hub 服务器已关闭[/green]")
            else:
                self.console.print("[yellow]⚠️ 无法找到关闭方法[/yellow]")

        except Exception as e:
            self.console.print(f"[red]❌ 关闭服务器失败: {e}[/red]")
