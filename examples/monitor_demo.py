"""
Monitor 功能完整演示

展示如何使用 Monitor 功能监控 Agent 和 Environment 的交互。

运行方式：
1. 启动 Hub: uv run python -m star_protocol.cli
2. 运行此示例: uv run python examples/monitor_demo.py
"""

import asyncio
import logging
from star_protocol.client import AgentClient, EnvironmentClient
from star_protocol.client.monitor import MonitorClient
from star_protocol.client.mixins.monitorable import MonitorLevel

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class GameAgent(AgentClient):
    """游戏 Agent - 执行游戏动作"""
    
    async def on_outcome(self, sender: str, content: dict):
        """处理 Environment 返回的结果"""
        print(f"\n[Agent] 收到结果: {content}")


class GameEnvironment(EnvironmentClient):
    """游戏 Environment - 处理游戏逻辑"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player_positions = {}
    
    async def on_action(self, sender: str, content: dict):
        """处理 Agent 的动作"""
        action_type = content.get("type")
        print(f"\n[Environment] 处理动作: {action_type} from {sender}")
        
        if action_type == "move":
            # 更新玩家位置
            x, y = content.get("x", 0), content.get("y", 0)
            self.player_positions[sender] = (x, y)
            
            # 返回结果
            await self.send_outcome(
                recipient=sender,
                content={
                    "success": True,
                    "position": [x, y],
                    "message": f"移动到 ({x}, {y})"
                }
            )
            
            # 广播事件给所有玩家
            await self.broadcast_event(
                event_type="player_moved",
                content={
                    "player": sender,
                    "position": [x, y]
                }
            )


class GameMonitor(MonitorClient):
    """游戏 Monitor - 监控游戏状态"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_count = 0
    
    async def on_monitor_data(self, source_client_id: str, data_type: str, data: dict):
        """处理监控数据"""
        self.event_count += 1
        print(f"\n[Monitor] 事件 #{self.event_count}")
        print(f"  来源: {source_client_id}")
        print(f"  类型: {data_type}")
        print(f"  数据: {data}")


async def main():
    """主函数"""

    hub_server_url = "ws://localhost:8000"

    print("\n" + "="*70)
    print("Star Protocol - Monitor 功能演示")
    print("="*70 + "\n")
    
    # 1. 创建客户端
    print("步骤 1: 创建客户端")
    print("-" * 70)
    
    agent = GameAgent("agent_01", monitorable=True)
    env = GameEnvironment("game_world")
    monitor = GameMonitor("monitor_01")
    
    print("✅ 创建了 Agent、Environment 和 Monitor\n")
    
    # 2. 连接到 Hub
    print("步骤 2: 连接到 Hub")
    print("-" * 70)
    
    await agent.connect(hub_server_url)
    await env.connect(hub_server_url)
    await monitor.connect(hub_server_url)
    
    print("✅ 所有客户端已连接\n")
    await asyncio.sleep(0.5)
    
    # 3. 启动客户端
    print("步骤 3: 启动客户端")
    print("-" * 70)
    
    await agent.start()
    await env.start()
    await monitor.start()
    
    print("✅ 所有客户端已启动\n")
    await asyncio.sleep(0.5)
    
    # 4. Agent 启用监控
    print("步骤 4: Agent 启用监控")
    print("-" * 70)
    
    await agent.enable_monitoring(level=MonitorLevel.DEBUG)
    
    print("✅ Agent 已启用监控（级别：DEBUG）\n")
    await asyncio.sleep(0.5)
    
    # 5. Monitor 订阅 Agent
    print("步骤 5: Monitor 订阅 Agent")
    print("-" * 70)
    
    await monitor.subscribe_to_client("agent_01")
    
    print("✅ Monitor 已订阅 agent_01\n")
    await asyncio.sleep(0.5)
    
    # 6. Agent 加入环境
    print("步骤 6: Agent 加入环境")
    print("-" * 70)
    
    await agent.join_environment("game_world")
    
    print("✅ Agent 已加入环境\n")
    await asyncio.sleep(1)
    
    # 7. 执行游戏动作
    print("步骤 7: 执行游戏动作")
    print("-" * 70)
    
    # 动作 1: 移动
    print("\n[agent_01] 发送移动动作...")
    await agent.send_action(
        recipient="game_world",
        action_name="move",
        params={"x": 10, "y": 20}
    )
    await asyncio.sleep(1)
    
    # 动作 2: 再次移动
    print("\n[agent_01] 发送第二次移动动作...")
    await agent.send_action(
        recipient="game_world",
        action_name="move",
        params={"x": 15, "y": 25}
    )
    await asyncio.sleep(1)
    
    # 8. 总结
    print("\n" + "="*70)
    print("演示完成！")
    print("="*70)
    print(f"\n📊 统计信息:")
    print(f"  - Monitor 接收到 {monitor.event_count} 个监控事件")
    print(f"  - Agent 当前位置: {env.player_positions.get('player_01', 'unknown')}")
    print("\n💡 提示: 按 Ctrl+C 退出\n")
    
    # 保持运行
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n正在清理...")
        await monitor.unsubscribe_from_client("agent_01")
        await agent.disable_monitoring()
        await agent.stop()
        await env.stop()
        await monitor.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  程序被用户中断")
