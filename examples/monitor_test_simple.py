"""简化的 Monitor 测试 - 只测试基本订阅功能"""

import asyncio
import logging
from star_protocol.client import AgentClient
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
    print("Monitor 基本功能测试")
    print("="*70 + "\n")
    
    # 创建客户端
    print("步骤 1: 创建客户端")
    agent = AgentClient("agent_01", monitorable=True)
    monitor = MonitorClient("monitor_01")
    print("✅ 创建完成\n")
    
    # 连接
    print("步骤 2: 连接到 Hub")
    await agent.connect("ws://localhost:8765")
    await monitor.connect("ws://localhost:8765")
    print("✅ 连接完成\n")
    
    await asyncio.sleep(0.5)
    
    # Agent 启动
    print("步骤 3: Agent 启动")
    await agent.start()
    await asyncio.sleep(0.5)
    print("✅ Agent 已启动\n")
    
    # Agent 启用监控
    print("步骤 4: Agent 启用监控")
    await agent.enable_monitoring(level=MonitorLevel.DEBUG)
    await asyncio.sleep(0.5)
    print("✅ 监控已启用\n")
    
    # Monitor 订阅
    print("步骤 5: Monitor 订阅 Agent")
    await monitor.subscribe_to_client("agent_01")
    await asyncio.sleep(0.5)
    print("✅ 订阅完成\n")
    
    # 清理
    print("步骤 6: 清理")
    await monitor.unsubscribe_from_client("agent_01")
    await agent.disable_monitoring()
    await asyncio.sleep(0.3)
    
    await monitor.disconnect()
    await agent.stop()
    print("✅ 清理完成\n")
    
    print("="*70)
    print("✅ 测试完成！")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  程序被用户中断")
