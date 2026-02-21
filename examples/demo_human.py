"""
Demo Human Client

作为人类用户连接到 Hub，与 Agent 和 Environment 进行交互。

运行方式：
  1. 启动 Hub:   uv run python -m star_protocol.cli
  2. 启动 Env:   uv run -m examples.demo_env
  3. 启动 Agent: uv run -m examples.demo_agent
  4. 启动 Human: uv run -m examples.demo_human
"""

import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from star_protocol.client import HumanClient

console = Console()


# ─── 帮助文本 ─────────────────────────────────────────────────────────────────

HELP_TEXT = """
[bold cyan]可用命令[/bold cyan]

  [yellow]join \<env_id\>[/yellow]         加入环境（默认: demo_env）
  [yellow]leave[/yellow]                   离开当前环境

  [yellow]send \<target\> \<key=value\>...[/yellow]  向 agent 或 env 发送消息
    示例: [green]send demo_agent type=greet msg=hello[/green]
    示例: [green]send demo_env   type=query  item=gold[/green]

  [yellow]action \<target\> \<action\> \<key=value\>...[/yellow]  以 action 格式发送指令
    示例: [green]action demo_env move x=10 y=20[/green]

  [yellow]help[/yellow]   显示此帮助
  [yellow]quit[/yellow]   退出
"""


# ─── Human Client ──────────────────────────────────────────────────────────────

class DemoHuman(HumanClient):
    """交互式 Human 客户端"""

    async def on_outcome(self, sender: str, content: dict):
        """处理收到的结果"""
        console.print(
            Panel(
                f"[green]{content}[/green]",
                title=f"[bold green]✅ 结果来自 {sender}[/bold green]",
                border_style="green",
            )
        )

    async def on_event(self, sender: str, content: dict):
        """处理点对点事件"""
        console.print(
            Panel(
                f"[cyan]{content}[/cyan]",
                title=f"[bold cyan]📨 事件来自 {sender}[/bold cyan]",
                border_style="cyan",
            )
        )

    async def on_broadcast_event(self, sender: str, content: dict):
        """处理广播事件"""
        console.print(
            Panel(
                f"[magenta]{content}[/magenta]",
                title=f"[bold magenta]📢 广播来自 {sender}[/bold magenta]",
                border_style="magenta",
            )
        )


# ─── 参数解析 ─────────────────────────────────────────────────────────────────

def _parse_kv(tokens: list[str]) -> dict:
    """将 key=value 字符串列表转换为字典，自动尝试类型转换"""
    result = {}
    for token in tokens:
        if "=" in token:
            key, _, raw = token.partition("=")
            raw = raw.strip("\"'")
            for cast in (int, float):
                try:
                    raw = cast(raw)
                    break
                except ValueError:
                    pass
            result[key] = raw
    return result


# ─── 主函数 ───────────────────────────────────────────────────────────────────

async def main():
    hub_url = "ws://localhost:8000"

    console.print(
        Panel(
            "[bold]Star Protocol — Demo Human Client[/bold]\n"
            "连接到 Hub，与 Agent / Environment 交互",
            border_style="bold blue",
        )
    )

    human = DemoHuman(client_id="demo_human")

    # 连接
    console.print(f"连接到 Hub: {hub_url} ...")
    await human.connect(hub_url)
    console.print("[green]✅ 已连接[/green]")

    # 启动消息循环
    await human.start()
    console.print("[green]✅ 已启动[/green]\n")

    console.print(HELP_TEXT)

    try:
        while True:
            raw = await asyncio.to_thread(
                console.input,
                "[bold blue]human > [/bold blue]",
            )
            raw = raw.strip()
            if not raw:
                continue

            parts = raw.split()
            cmd, *args = parts

            # ── quit ──────────────────────────────────────────────────
            if cmd in ("quit", "exit", "q"):
                break

            # ── help ──────────────────────────────────────────────────
            elif cmd == "help":
                console.print(HELP_TEXT)

            # ── join <env_id> ─────────────────────────────────────────
            elif cmd == "join":
                env_id = args[0] if args else "demo_env"
                await human.join_environment(env_id)
                console.print(f"[green]✅ 加入环境: {env_id}[/green]")

            # ── leave ─────────────────────────────────────────────────
            elif cmd == "leave":
                await human.leave_environment()
                console.print("[yellow]已离开环境[/yellow]")

            # ── send <target> key=value ... ───────────────────────────
            elif cmd == "send":
                if len(args) < 1:
                    console.print("[red]用法: send <target> key=value ...[/red]")
                    continue
                target, *kv_tokens = args
                content = _parse_kv(kv_tokens)
                await human.send_message(recipient=target, content=content)
                console.print(f"[dim]→ 消息已发送至 {target}[/dim]")

            # ── action <target> <action_name> key=value ... ───────────
            elif cmd == "action":
                if len(args) < 2:
                    console.print("[red]用法: action <target> <action_name> key=value ...[/red]")
                    continue
                target, action_name, *kv_tokens = args
                params = _parse_kv(kv_tokens) or None
                await human.send_action(
                    recipient=target,
                    action_name=action_name,
                    params=params,
                )
                console.print(f"[dim]→ 动作 [{action_name}] 已发送至 {target}[/dim]")

            else:
                console.print(f"[red]未知命令: {cmd}。输入 help 查看帮助。[/red]")

    except KeyboardInterrupt:
        console.print("\n[yellow]收到中断信号...[/yellow]")

    # 清理
    console.print("\n正在断开...")
    await human.stop()
    console.print("[green]✅ 已断开[/green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("程序被用户中断")
