import asyncio
from rich.console import Console
from rich.status import Status
import random
from star_protocol.client import AgentClient
from star_protocol.client.mixins.monitorable import MonitorLevel

console = Console()

class DemoAgent(AgentClient):
    """自定义 Agent 类"""
    
    def __init__(self, client_id: str):
        super().__init__(client_id=client_id, monitorable=True)

    async def on_outcome(self, sender: str, content: dict):
        """处理 Environment 返回的结果"""
        console.print(f"✅ 收到结果: {content}")
    
    async def on_event(self, sender: str, content: dict):
        """处理 Environment 广播的事件"""
        event_type = content.get("type")
        console.print(f"📢 收到事件: {event_type}")
        console.print(f"   内容: {content.get('data', {})}")


async def main():
    """主函数"""
    console.print("="*70)
    console.print("Star Protocol - Demo Agent 交互示例")
    console.print("="*70)
    
    # 创建 Agent
    agent = DemoAgent(client_id="demo_agent")
    
    # 连接到 Hub
    console.print("连接到 Hub...")
    await agent.connect("ws://localhost:8000")
    console.print("✅ 已连接\n")
    
    # 启动 Agent（开始接收消息）
    console.print("启动 Agent...")
    await agent.start()
    console.print("✅ 已启动\n")
    
    # 启用监控
    await agent.enable_monitoring(level=MonitorLevel.DEBUG)
    console.print("✅ 监控已启用 (DEBUG)\n")
    
    # 加入环境
    console.print("加入环境 'demo_env'...")
    await agent.join_environment("demo_env")
    console.print("✅ 已加入环境\n")
    
    await asyncio.sleep(0.5)
    
    # 交互式发送动作
    console.print("\n[bold cyan]📝 交互模式已启动[/bold cyan]")
    console.print("输入命令格式: [yellow]<action_name> [params][/yellow]")
    console.print("示例: [green]greet message=\"Hello\"[/green] 或 [green]calculate operation=add a=10 b=20[/green]")
    console.print("输入 [red]quit[/red] 或 [red]exit[/red] 退出\n")
    
    try:
        while True:
            # 获取用户输入
            user_input = await asyncio.to_thread(
                console.input,
                "[bold blue]>>> [/bold blue]"
            )
            
            user_input = user_input.strip()
            
            # 检查退出命令
            if user_input.lower() in ["quit", "exit", "q"]:
                console.print("\n[yellow]正在退出...[/yellow]")
                break
            
            if not user_input:
                continue
            
            # 解析命令
            parts = user_input.split(maxsplit=1)
            action_name = parts[0]
            params = {}
            
            # 解析参数
            if len(parts) > 1:
                param_str = parts[1]
                # 简单的参数解析 (key=value 格式)
                for param in param_str.split():
                    if "=" in param:
                        key, value = param.split("=", 1)
                        # 尝试转换为数字
                        try:
                            value = int(value)
                        except ValueError:
                            try:
                                value = float(value)
                            except ValueError:
                                # 移除引号
                                value = value.strip('"\'')
                        params[key] = value
            
            # 动态状态文字列表
            status_messages = [
                "🤔 思考中",
                "📡 发送中",
                "⚙️  处理中",
                "🔍 解析中",
                "💭 反思中",
                "🎯 执行中"
            ]
            
            # 随机选择一个状态消息
            status_msg = random.choice(status_messages)
            
            with Status(f"[bold green]{status_msg}...[/bold green]", console=console, spinner="dots"):
                await agent.send_action(
                    recipient="demo_env",
                    action_name=action_name,
                    params=params if params else None
                )
                # 等待一小段时间以便接收响应
                await asyncio.sleep(0.8)
            
            console.print(f"[dim]✓ 动作已发送: {action_name}[/dim]\n")
    
    except KeyboardInterrupt:
        console.print("\n[yellow]收到中断信号...[/yellow]")
    
    # 离开环境
    console.print("\n离开环境...")
    await agent.leave_environment()
    console.print("✅ 已离开环境")
    
    # 停止并断开
    await agent.stop()
    console.print("✅ Agent 已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("程序被用户中断")
