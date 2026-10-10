"""Standalone Monitor: subscribe through Hub and display received telemetry trees."""

import asyncio

from rich.console import Console
from rich.text import Text

from examples.protocol_demo.client_cli import DemoArgumentParser
from examples.protocol_demo.display import ProtocolDisplay
from examples.protocol_demo.monitor import DemoMonitor


async def run(hub: str, target: str, *, trace=False):
    console = Console()
    with ProtocolDisplay(trace=trace, console=console, title="Star Protocol · Monitor",
                         live=False) as display:
        def emit(record: dict):
            display.emit({"component": "monitor", "event": f"monitor.{record['name']}",
                          "source": record["source"], "name": record["name"],
                          "data": record["data"]})

        monitor = DemoMonitor(emit=emit)
        try:
            await monitor.connect(hub)
            await monitor.start()
            await monitor.subscribe_to_client(target)
            await monitor.ready(target)
            display.message(f"Hub 已确认订阅 {target}，等待监控数据；按 Ctrl+C 退出。", style="green")
            await asyncio.Event().wait()
        finally:
            await monitor.stop()


def main():
    parser = DemoArgumentParser(description=__doc__)
    parser.add_argument("--hub", default="ws://127.0.0.1:8765", help="Hub WebSocket URL")
    parser.add_argument("--target", default="demo_agent", help="要订阅的 Client ID")
    parser.add_argument("--trace", action="store_true", help="展开完整监控字段树")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.hub, args.target, trace=args.trace))
    except KeyboardInterrupt:
        Console().print(Text("Monitor 已停止。", style="cyan"))
    except Exception as error:
        Console().print(Text(f"Monitor 启动或连接失败：{error}", style="red"))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
