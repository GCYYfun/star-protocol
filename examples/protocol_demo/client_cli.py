"""Independent role entrypoints sharing the exact one-command demo contracts."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from star_protocol.models import gen_id

from .contracts import CONFIG_DIR, load_specification
from .display import ProtocolDisplay
from .environment import DemoEnvironment
from .peers import DemoAgent, DemoHuman

HELP = (
    ("工具与结果", (
        ("tools", "查看环境工具和参数 Schema"),
        ("action <name> <JSON params>", "调用工具；进度和结果显示在该 Action 下"),
        ("await <action_id>", "等待并读取该动作的最终 Outcome"),
        ("cancel <action_id>", "用独立 Action 取消本人持续动作"),
        ("query <action_id>", "查询环境保存的本人原结果"),
        ("replay <action_id>", "重发保存的原 Action，复用原 ID 和参数"),
    )),
    ("Event 与能力协商", (
        ("schemas", "查看自身接收 Event 的声明"),
        ("discover <peer>", "与目标重新协商完整能力"),
        ("event <target> <name> <JSON>", "发送已协商 Event 的 data 对象"),
        ("speech <target> <text>", "发送自然语言 text Event"),
        ("state <state> <text>", "通知环境自身活动 idle/working/listening"),
    )),
    ("原文、监控与退出", (
        ("history <logical_id>", "读取本地授权原 Event/Outcome/Action"),
        ("monitor on / off", "开启或关闭自身遥测"),
        ("telemetry <name> <JSON>", "在开启遥测后发送内部监控数据"),
        ("help / quit", "查看帮助或退出"),
    )),
)


class DemoArgumentParser(argparse.ArgumentParser):
    """Rich help and literal error text for the independent demo entrypoints."""

    def print_help(self, file=None):
        console = Console(file=file or sys.stdout)
        console.print(Panel(Text(self.format_help()), title=Text("启动选项"),
                            border_style="cyan"))

    def _print_message(self, message, file=None):
        if message:
            Console(file=file or sys.stderr).print(Text(message), end="")


def show_help(console: Console):
    tree = Tree(Text("交互命令", style="bold cyan"))
    for title, commands in HELP:
        branch = tree.add(Text(title, style="bold"))
        for command, description in commands:
            label = Text(command, style="cyan")
            label.append(f"  {description}")
            branch.add(label)
    examples = tree.add(Text("输入示例", style="bold"))
    for example in (
        'action calculate {"operation":"add","a":10,"b":20}',
        'action wait {"seconds":3}',
        "state working 我正在处理这个任务。",
        "speech demo_human 你好，我们可以继续讨论。",
    ):
        examples.add(Text(example))
    console.print(tree)


async def run_role(role, *, hub_url, state_dir, client_id=None, trace=False):
    identifier = client_id or {"environment": "demo_env", "agent": "demo_agent",
                               "human": "demo_human"}[role]
    console = Console()
    with ProtocolDisplay(trace=trace, console=console, title=f"Star Protocol · {identifier}",
                         live=False) as display:
        if role == "environment":
            client = DemoEnvironment(identifier, state_dir=state_dir, emit=display.emit)
        else:
            client = {"agent": DemoAgent, "human": DemoHuman}[
                role](identifier, state_dir=state_dir, emit=display.emit)
        try:
            if role == "environment":
                await client.connect(hub_url)
                await client.start()
                display.message(f"Environment {identifier} 已启动，配置目录：{CONFIG_DIR}",
                                style="green")
                display.json(load_specification(role), title="本环境的工具与 Event 接收声明")
                display.message("等待 Agent/Human；Ctrl+C 退出。", style="cyan")
                await asyncio.Event().wait()
                return
            await client.connect_join(hub_url)
            display.message(f"{role} {identifier} 已加入 demo_env 并完成双向协商。", style="green")
            display.message(f"配置目录：{CONFIG_DIR}", style="dim")
            show_help(console)
            while True:
                try:
                    raw = (await asyncio.to_thread(console.input, f"{identifier}> ",
                                                   markup=False)).strip()
                except EOFError:
                    break
                if not raw:
                    continue
                command, _, rest = raw.partition(" ")
                try:
                    if command in {"quit", "exit", "q"}:
                        break
                    if command == "help":
                        show_help(console)
                    elif command == "tools":
                        display.json(client.specification_for("demo_env")["tools"],
                                     title="环境工具与参数 Schema")
                    elif command == "schemas":
                        display.json(load_specification(role)["events"],
                                     title="本角色接收 Event 的声明")
                    elif command == "discover":
                        await client.send_discover(rest)
                        await client.ready(rest)
                        display.message(f"与 {rest} 协商完成。", style="green")
                    elif command == "action":
                        name, _, encoded = rest.partition(" ")
                        params = json.loads(encoded or "{}")
                        action_id = gen_id("action")
                        await client.send_action("demo_env", name, params, action_id=action_id)
                        display.message(f"Action 已保存并发送：{action_id}", style="cyan")
                    elif command in {"cancel", "query"}:
                        name = "cancel" if command == "cancel" else "get_operation_result"
                        action_id = gen_id("action")
                        await client.send_action("demo_env", name, {"action_id": rest},
                                                 action_id=action_id)
                        display.message(f"请求的 Action ID：{action_id}", style="cyan")
                    elif command == "await":
                        display.json(await client.settled(rest), title="最终 Outcome 原文")
                    elif command == "replay":
                        original = client.original_action(rest)
                        if original is None:
                            raise ValueError("没有已保存的本人 Action")
                        await client.send_action("demo_env", original["name"], original["params"],
                                                 action_id=original["id"])
                        display.message(f"原 Action 已重发：{rest}", style="cyan")
                    elif command in {"event", "speech", "state"}:
                        if command == "event":
                            target, name, encoded = rest.split(maxsplit=2)
                            data = json.loads(encoded)
                        elif command == "speech":
                            target, text = rest.split(maxsplit=1)
                            name, data = "speech", {"text": text}
                        else:
                            state, text = rest.split(maxsplit=1)
                            target, name, data = "demo_env", "activity.state", {
                                "text": text, "state": state}
                        if client.protocol_for(target) is None:
                            await client.send_discover(target)
                            await client.ready(target)
                        event_id = gen_id("event")
                        await client.send_event(target, name, data, event_id=event_id)
                        display.message(f"Event 已发送：{event_id}", style="cyan")
                    elif command == "monitor":
                        if rest == "on":
                            await client.enable_monitoring()
                            display.message("自身遥测已开启。", style="green")
                        elif rest == "off":
                            await client.disable_monitoring()
                            display.message("自身遥测已关闭。", style="cyan")
                        else:
                            raise ValueError("使用 monitor on 或 monitor off")
                    elif command == "telemetry":
                        if not client._monitor_enabled:
                            raise ValueError("先执行 monitor on")
                        name, encoded = rest.split(maxsplit=1)
                        data = json.loads(encoded)
                        if type(data) is not dict:
                            raise ValueError("遥测 data 必须是 JSON 对象")
                        await client.send_monitor_data(name, data)
                        display.message(f"遥测已发送：{name}", style="cyan")
                    elif command == "history":
                        original = client.original(rest) or client.original_action(rest)
                        display.json(original, title="本地授权原文")
                    else:
                        display.message("未知命令，输入 help 查看帮助。", style="yellow")
                except (ValueError, TimeoutError, TypeError) as error:
                    display.message(f"请求未完成：{error}", style="red")
                except Exception as error:
                    # JSON Schema ValidationError is an Exception, not ValueError.
                    display.message(f"请求未完成：{type(error).__name__}: {error}", style="red")
        finally:
            await client.stop()


def main(role):
    parser = DemoArgumentParser(description=f"新版协议 {role} 独立演示")
    parser.add_argument("--hub", default="ws://127.0.0.1:8765", help="Hub WebSocket URL")
    parser.add_argument("--state-dir", type=Path, default=Path(".demo-state"),
                        help="原文与恢复数据库目录，默认 .demo-state")
    parser.add_argument("--id", dest="client_id", help="角色 ID；第二个 Agent 可用 demo_colleague")
    parser.add_argument("--trace", action="store_true", help="展开传输信封及完整字段树")
    arguments = parser.parse_args()
    try:
        asyncio.run(run_role(role, hub_url=arguments.hub, state_dir=arguments.state_dir,
                             client_id=arguments.client_id, trace=arguments.trace))
    except KeyboardInterrupt:
        Console().print(Text("客户端已停止。", style="cyan"))
    except Exception as error:
        Console().print(Text(f"客户端启动或连接失败：{error}", style="red"))
        raise SystemExit(1) from None
