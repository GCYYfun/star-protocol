"""
Monitor Client 示例

此示例展示如何创建一个独立的 Monitor Client，用于监控其他 Client（如 Agent）的活动。
"""

import asyncio
import logging
from rich.console import Console
from rich.table import Table
from rich.live import Live
from star_protocol.client.monitor import MonitorClient

# 配置日志
logging.basicConfig(level=logging.INFO)
console = Console()

class DemoMonitor(MonitorClient):
    """自定义 Monitor Client"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []
    
    async def on_monitor_data(self, source_client_id: str, data_type: str, data: dict):
        """处理监控数据"""
        event = {
            "source": source_client_id,
            "type": data_type,
            "data": data,
            "timestamp": asyncio.get_event_loop().time()
        }
        self.events.append(event)
        
        # 打印事件
        self._print_event(event)

    def _print_event(self, event):
        """打印事件详情"""
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")
        
        header = Table.grid(expand=True)
        header.add_column()
        header.add_column(justify="right")
        header.add_row(
            f"[bold cyan]SOURCE:[/bold cyan] {event['source']}",
            f"[dim]{event['timestamp']:.2f}[/dim]"
        )
        
        grid.add_row(header)
        grid.add_row(f"[bold yellow]TYPE:[/bold yellow]   {event['type']}")
        grid.add_row(f"[bold green]DATA:[/bold green]   {event['data']}")
        
        console.print(
            Panel(
                grid,
                title="[bold magenta]Monitor Event[/bold magenta]",
                border_style="cyan"
            )
        )

async def main():
    hub_url = "ws://localhost:8000"
    target_client_id = "auto"  # 要监控的 ID
    
    console.print(f"[bold]启动 Monitor Client...[/bold]")
    console.print(f"目标 Hub: {hub_url}")
    console.print(f"监控目标: {target_client_id}")
    
    # 创建 Monitor
    monitor = DemoMonitor(monitor_id="monitor_client_01")
    
    try:
        # 连接
        await monitor.connect(hub_url)
        console.print("[green]✅ 已连接到 Hub[/green]")
        
        # 启动
        await monitor.start()
        console.print("[green]✅ Monitor 已启动[/green]")
        
        # 订阅
        await monitor.subscribe_to_client(target_client_id)
        console.print(f"[green]✅ 已订阅 Client: {target_client_id}[/green]")
        
        console.print("\n[yellow]正在等待监控数据 (按 Ctrl+C 退出)...[/yellow]\n")
        
        # 保持运行
        await asyncio.Event().wait()
            
    except Exception as e:
        console.print(f"[red]发生错误: {e}[/red]")
    finally:
        # 清理
        await monitor.stop()
        console.print("[yellow]Monitor 已停止[/yellow]")

if __name__ == "__main__":
    from rich.panel import Panel 
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold]程序已退出[/bold]")
