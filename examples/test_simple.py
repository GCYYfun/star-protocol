"""改进后的端到端测试 - 使用简化 API"""

import asyncio
import logging
from star_protocol import AgentClient, EnvironmentClient, HumanClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)


class QAAgent(AgentClient):
    """问答 Agent"""
    
    async def on_action(self, sender: str, content: dict):
        """处理问题"""
        question = content.get("question")
        print(f"  🤖 Agent 收到问题: {question}")
        
        # 简单的回答逻辑
        answer = f"这是对 '{question}' 的回答"
        
        # 返回结果
        await self.send_outcome(
            recipient=sender,
            content={"answer": answer}
        )
        print(f"  🤖 Agent 已回答")


class QAEnvironment(EnvironmentClient):
    """问答环境"""
    
    async def on_message(self, envelope):
        """Environment 接收所有消息的抄送"""
        payload = envelope.payload
        print(f"  🌍 Environment 观察: {envelope.sender} -> {envelope.recipient}, type={payload.type}")


class User(HumanClient):
    """用户客户端"""
    
    async def on_outcome(self, sender: str, content: dict):
        """处理回答"""
        answer = content.get("answer")
        print(f"  👤 User 收到回答: {answer}")
    
    async def ask_question(self, question: str):
        """提问"""
        print(f"  👤 User 提问: {question}")
        await self.send_action(
            recipient="qa_agent",
            action_name="ask",
            params={"question": question}
        )


async def main():
    """主函数 - 使用简化 API"""
    print("=" * 70)
    print("Star Protocol 简化 API 测试")
    print("=" * 70)
    print()
    print("⚠️  请先在另一个终端启动 Hub Server:")
    print("   uv run python -m star_protocol.cli")
    print()
    input("按 Enter 继续...")
    print()
    
    # 方式 1: 使用 async with 上下文管理器（推荐）
    print("方式 1: 使用 async with 上下文管理器")
    print("-" * 70)
    
    async with QAEnvironment(client_id="qa_room") as env:
        await env.connect("ws://127.0.0.1:8000")
        await env.start()  # 自动启动消息循环
        print("✅ Environment 已启动")
        
        async with QAAgent(client_id="qa_agent") as agent:
            await agent.connect("ws://127.0.0.1:8000")
            await agent.start()
            await agent.join_environment("qa_room")
            print("✅ Agent 已启动并加入环境")
            
            async with User(client_id="user_01") as user:
                await user.connect("ws://127.0.0.1:8000")
                await user.start()
                await user.join_environment("qa_room")
                print("✅ User 已启动并加入环境")
                print()
                
                # 等待消息循环启动
                await asyncio.sleep(0.3)
                
                # 问答交互
                print("开始问答:")
                print("-" * 70)
                await user.ask_question("什么是 Star Protocol?")
                await asyncio.sleep(0.5)
                print()
                
                await user.ask_question("如何使用这个 SDK?")
                await asyncio.sleep(0.5)
                print()
                
                # 自动清理（__aexit__）
    
    print("-" * 70)
    print("✅ 所有客户端已自动清理")
    print()
    
    # 方式 2: 手动管理（更灵活）
    # print("方式 2: 手动管理 start/stop")
    # print("-" * 70)
    
    # env = QAEnvironment(client_id="qa_room_2")
    # await env.connect("ws://127.0.0.1:8000")
    # await env.start()
    # print("✅ Environment 已启动")
    
    # agent = QAAgent(client_id="qa_agent_2")
    # await agent.connect("ws://127.0.0.1:8000")
    # await agent.start()
    # await agent.join_environment("qa_room_2")
    # print("✅ Agent 已启动并加入环境")
    
    # await asyncio.sleep(0.3)
    
    # # 手动清理
    # await agent.stop()
    # await env.stop()
    # print("✅ 手动清理完成")
    # print()
    
    print("=" * 70)
    print("✅ 测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 已退出")
