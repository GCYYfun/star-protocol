import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from star_protocol.client import EnvironmentClient
from star_protocol.models.payloads import ToolDefinition

console = Console()


# ==================== 工具清单定义 ====================
# 集中声明，便于 on_discover 引用
DEMO_TOOLS: list[ToolDefinition] = [
    {
        "name": "greet",
        "description": "向环境发送问候，环境将回复欢迎消息",
        "parameters": {
            "schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "问候语内容"},
            },
            "required": ["message"],
        },
        "tags": ["social"],
    },
    {
        "name": "calculate",
        "description": "执行基础四则运算，返回计算结果",
        "parameters": {
            "schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "sub", "mul", "div"],
                    "description": "运算类型",
                },
                "a": {"type": "number", "description": "第一个操作数"},
                "b": {"type": "number", "description": "第二个操作数"},
            },
            "required": ["operation", "a", "b"],
        },
        "tags": ["math"],
    },
]


class DemoEnvironment(EnvironmentClient):
    async def on_discover(self, sender: str) -> list[ToolDefinition]:
        """响应工具发现请求，返回本环境支持的工具清单"""
        console.print(
            f"\n[bold magenta]🔍 收到 Discover 请求[/bold magenta] 来自 [cyan]{sender}[/cyan]"
        )
        console.print(
            f"[dim]   → 返回 {len(DEMO_TOOLS)} 个工具: "
            + ", ".join(t["name"] for t in DEMO_TOOLS)
            + "[/dim]\n"
        )
        return DEMO_TOOLS

    async def on_action(self, sender: str, content: dict):
        """覆盖接收 action 的回调并提供自定义的处理与美化打印"""
        action_name = content.get("name", "unknown")
        action_id = content.get("id", "none")
        params = content.get("params", {})

        # ========== [Rich Output] 接收展示 ==========
        table = Table(show_header=False, box=None)
        table.add_column("Key", style="cyan", justify="right")
        table.add_column("Value", style="magenta")

        table.add_row("Sender:", sender)
        table.add_row("Action ID:", str(action_id))
        table.add_row("Params:", str(params) if params else "{ }")

        panel = Panel(
            table,
            title=f"[bold green]📥 收到动作: {action_name}[/bold green]",
            border_style="green",
            expand=False,
        )
        console.print(panel)

        # ========== [Action Logic] 分发模拟反馈 ==========
        reply_data = {}

        if action_name == "greet":
            # 针对问候指令
            msg = params.get("message", "你好！")
            reply_data = {
                "reply": f"Environment 收到你的问候并回复：{msg}，欢迎连接",
                "success": True,
            }

        elif action_name == "calculate":
            # 针对计算指令 (测试附带多参情况)
            op = params.get("operation", "add")
            try:
                a = float(params.get("a", 0))
                b = float(params.get("b", 0))
                if op == "add":
                    res = a + b
                elif op == "sub":
                    res = a - b
                elif op == "mul":
                    res = a * b
                elif op == "div":
                    res = a / b if b != 0 else "division_by_zero"
                else:
                    res = "unknown_operation"
                reply_data = {"result": res, "success": True}
            except ValueError:
                reply_data = {
                    "error": "Invalid numbers provided in params.",
                    "success": False,
                }

        else:
            # 默认通用下发结构兜底
            reply_data = {
                "status": "success",
                "message": f"Action '{action_name}' 已经收到并处理完毕.",
                "echo_params": params,
            }

        # ========== [Rich Output] 回执响应 ==========
        outcome_content = {
            "ref_id": action_id,
            "success": True,
            "data": reply_data,
        }

        console.print(
            f"[dim]📤 向 {sender} 发送处理结果 (Action: {action_name})...[/dim]\n"
        )

        # 将构造好的执行结果返回给发送者
        await self.send_outcome(sender, outcome_content)

    async def on_client_joined(self, client_id: str):
        """有 Agent 加入环境"""
        console.print(
            f"[bold green]🟢 Agent 加入[/bold green]: [cyan]{client_id}[/cyan]"
        )

    async def on_client_left(self, client_id: str, reason: str = "leave"):
        """有 Agent 离开环境"""
        icon = "🔴" if reason == "disconnected" else "🟡"
        label = "断线" if reason == "disconnected" else "主动离开"
        console.print(
            f"[bold yellow]{icon} Agent {label}[/bold yellow]: [cyan]{client_id}[/cyan]"
        )


async def main():
    """主程序入口"""
    console.print(
        Panel(
            "[bold blue]Star Protocol - Demo Environment 示例[/bold blue]",
            border_style="blue",
            expand=False,
        )
    )

    # 实例化自定义环境客户端
    env = DemoEnvironment(client_id="demo_env")

    # 连接到 Hub
    with console.status("[bold yellow]连接到 Hub 服务器...[/bold yellow]"):
        await env.connect("ws://localhost:8000")
    console.print(
        "[bold green]✅ 已连接到 Hub 服务器 (ws://localhost:8000)[/bold green]"
    )

    # 启动 Environment 进行监听
    with console.status(
        "[bold yellow]启动 Environment，开始监听网络事件...[/bold yellow]"
    ):
        await env.start()
    console.print(
        "[bold green]✅ Environment 已启动并开始监听消息... 随时准备处理 Agent 发来的动作[/bold green]\n"
    )

    # 阻塞主协程保持存续
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        console.print("\n[bold red]正在执行退出协议...[/bold red]")
        await env.stop()
        console.print("[bold green]✅ Environment 已安全停止[/bold green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print(
            "\n[bold red]============\n程序已被用户强制中断\n============[/bold red]"
        )
