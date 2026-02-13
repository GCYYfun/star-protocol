"""
基础 Agent 示例

展示如何创建和使用 Agent 客户端。

运行方式：
1. 启动 Hub: uv run python -m star_protocol.cli
2. 启动 Environment: uv run python examples/basic_environment.py
3. 运行此示例: uv run python examples/basic_agent.py
"""

import asyncio
import logging
from star_protocol.client import AgentClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class MyAgent(AgentClient):
    """自定义 Agent 类"""
    
    async def on_outcome(self, sender: str, content: dict):
        """处理 Environment 返回的结果"""
        print(f"\n✅ 收到结果: {content}")
    
    async def on_event(self, sender: str, content: dict):
        """处理 Environment 广播的事件"""
        event_type = content.get("type")
        print(f"\n📢 收到事件: {event_type}")
        print(f"   内容: {content.get('data', {})}")


async def main():
    """主函数"""
    print("\n" + "="*70)
    print("Star Protocol - 基础 Agent 示例")
    print("="*70 + "\n")
    
    # 创建 Agent
    agent = MyAgent(client_id="agent_01")
    
    # 连接到 Hub
    print("连接到 Hub...")
    await agent.connect("ws://localhost:8000")
    print("✅ 已连接\n")
    
    # 启动 Agent（开始接收消息）
    print("启动 Agent...")
    await agent.start()
    print("✅ 已启动\n")
    
    # 加入环境
    print("加入环境 'my_env'...")
    await agent.join_environment("my_env")
    print("✅ 已加入环境\n")
    
    await asyncio.sleep(1)
    
    # 发送动作
    print("发送动作...")
    await agent.send_action(
        recipient="my_env",
        action_name="greet",
        params={"message": "Hello, World!"}
    )
    
    await asyncio.sleep(1)
    
    # 再发送一个动作
    await agent.send_action(
        recipient="my_env",
        action_name="calculate",
        params={"operation": "add", "a": 10, "b": 20}
    )
    
    await asyncio.sleep(2)
    
    # 离开环境
    print("\n离开环境...")
    await agent.leave_environment()
    print("✅ 已离开环境\n")
    
    # 停止并断开
    await agent.stop()
    print("✅ Agent 已停止\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  程序被用户中断")
