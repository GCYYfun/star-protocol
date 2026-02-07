"""Monitor 功能示例 - 通过 Hub 转发版本

演示如何使用 Monitor 功能监控其他客户端：
1. Agent 启用监控
2. Monitor 订阅 Agent
3. Agent 执行操作（触发监控数据）
4. Monitor 接收并存储数据
5. 查询监控数据和统计信息
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


async def main():
    """主函数"""
    print("\n" + "="*70)
    print("Monitor 功能示例 - 通过 Hub 转发")
    print("="*70 + "\n")
    
    # 步骤 1: 创建客户端
    print("步骤 1: 创建客户端")
    print("-" * 70)
    
    agent = AgentClient("agent_01", monitorable=True)
    env = EnvironmentClient("env_01")
    monitor = MonitorClient("monitor_01")
    
    print("✅ 创建了 Agent、Environment 和 Monitor 客户端\n")
    
    # 步骤 2: 连接到 Hub
    print("步骤 2: 连接到 Hub")
    print("-" * 70)
    
    await agent.connect("ws://localhost:8765")
    await env.connect("ws://localhost:8765")
    await monitor.connect("ws://localhost:8765")
    
    print("✅ 所有客户端已连接到 Hub\n")
    
    # 启动 Environment
    await env.start()
    
    await asyncio.sleep(0.5)
    
    # 步骤 3: Agent 启动并启用监控
    print("步骤 3: Agent 启动并启用监控")
    print("-" * 70)
    
    await agent.start()
    await agent.enable_monitoring(level=MonitorLevel.DEBUG)
    
    print("✅ Agent 已启用监控（级别：DEBUG）\n")
    
    await asyncio.sleep(0.5)
    
    # 步骤 4: Monitor 订阅 Agent
    print("步骤 4: Monitor 订阅 Agent")
    print("-" * 70)
    
    await monitor.subscribe_to_client("agent_01")
    
    print("✅ Monitor 已订阅 Agent\n")
    
    await asyncio.sleep(0.5)
    
    # 步骤 5: Agent 执行操作（触发监控数据）
    print("步骤 5: Agent 执行操作")
    print("-" * 70)
    
    # 5.1 加入环境
    print("  5.1 Agent 加入环境...")
    await agent.join_environment("env_01")
    await asyncio.sleep(0.3)
    
    # 5.2 发送消息
    print("  5.2 Agent 发送 action...")
    await agent.send_action("env_01", {"type": "move", "x": 10, "y": 20})
    await asyncio.sleep(0.3)
    
    # 5.3 离开环境
    print("  5.3 Agent 离开环境...")
    await agent.leave_environment()
    await asyncio.sleep(0.3)
    
    print("✅ Agent 完成操作\n")
    
    # 步骤 6: 查询监控数据
    print("步骤 6: 查询监控数据")
    print("-" * 70)
    
    # 6.1 获取统计信息
    stats = await monitor.get_client_stats("agent_01")
    print(f"  统计信息: {stats}")
    
    # 6.2 获取消息历史
    messages = await monitor.get_client_messages("agent_01", limit=10)
    print(f"  消息数量: {len(messages)}")
    
    # 6.3 获取订阅列表
    subscribed = monitor.get_subscribed_clients()
    print(f"  已订阅: {subscribed}")
    
    print("\n✅ 查询完成\n")
    
    # 步骤 7: 清理资源
    print("步骤 7: 清理资源")
    print("-" * 70)
    
    await monitor.unsubscribe_from_client("agent_01")
    await agent.disable_monitoring()
    
    await monitor.disconnect()
    await agent.disconnect()
    await env.disconnect()
    
    print("✅ 所有客户端已断开连接\n")
    
    print("="*70)
    print("✅ 示例完成！")
    print("="*70 + "\n")
    
    print("📝 总结:")
    print("  - Agent 通过 Hub 发送监控数据")
    print("  - Monitor 通过 Hub 订阅和接收数据")
    print("  - 无需额外的 WebSocket Server")
    print("  - 中心化管理，支持多 Monitor 订阅")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  程序被用户中断")
