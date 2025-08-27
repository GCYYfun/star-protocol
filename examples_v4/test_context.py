#!/usr/bin/env python3
"""
测试 Context 模块功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from star_protocol_v4.client.context import ClientContext, ContextStatus
from star_protocol.client.agent import AgentClient
from star_protocol.protocol import OutcomeMessage


async def test_context_basic():
    """测试基本上下文功能"""
    print("🧪 测试基本上下文功能...")

    context = ClientContext("test_client")
    await context.start()

    try:
        # 创建请求上下文
        context_item = context.create_request_context(
            request_type="action",
            request_data={"action": "move", "params": {"direction": "north"}},
            timeout=5.0,
        )

        print(f"✅ 创建上下文: {context_item.request_id}")
        assert context_item.status == ContextStatus.PENDING

        # 模拟响应
        outcome = OutcomeMessage(
            action_id=context_item.request_id,
            status="success",
            outcome={"position": [1, 2], "success": True},
        )

        # 完成请求
        success = context.complete_request(context_item.request_id, outcome)
        assert success
        assert context_item.status == ContextStatus.COMPLETED
        print(f"✅ 完成上下文: {context_item.request_id}")

        # 测试等待响应
        result = await context.wait_for_response(context_item.request_id, timeout=1.0)
        assert result == outcome
        print("✅ 等待响应成功")

        # 测试统计信息
        stats = context.get_stats()
        print(f"📊 统计信息: {stats}")
        assert stats["total_requests"] == 1
        assert stats["completed_requests"] == 1

    finally:
        await context.stop()

    print("🎉 基本上下文功能测试通过！")


async def test_context_timeout():
    """测试超时功能"""
    print("\n🧪 测试超时功能...")

    context = ClientContext("test_client", default_timeout=1.0)
    await context.start()

    try:
        # 创建请求上下文
        context_item = context.create_request_context(
            request_type="action",
            request_data={"action": "wait", "params": {}},
            timeout=0.5,  # 短超时时间
        )

        print(f"✅ 创建上下文: {context_item.request_id}")

        # 尝试等待响应（应该超时）
        try:
            await context.wait_for_response(context_item.request_id, timeout=0.5)
            assert False, "应该超时"
        except asyncio.TimeoutError:
            print("✅ 超时处理正确")
            assert context_item.status == ContextStatus.TIMEOUT

        # 测试统计信息
        stats = context.get_stats()
        print(f"📊 统计信息: {stats}")
        assert stats["timeout_requests"] == 1

    finally:
        await context.stop()

    print("🎉 超时功能测试通过！")


async def test_context_callback():
    """测试回调功能"""
    print("\n🧪 测试回调功能...")

    context = ClientContext("test_client")
    await context.start()

    callback_triggered = False
    callback_result = None

    async def test_callback(result):
        nonlocal callback_triggered, callback_result
        callback_triggered = True
        callback_result = result
        print(f"📞 回调被触发: {result}")

    try:
        # 创建带回调的上下文
        context_item = context.create_request_context(
            request_type="action",
            request_data={"action": "test", "params": {}},
            callback=test_callback,
        )

        print(f"✅ 创建带回调的上下文: {context_item.request_id}")

        # 模拟响应
        outcome = OutcomeMessage(
            action_id=context_item.request_id, status="success", outcome={"test": True}
        )

        # 完成请求
        context.complete_request(context_item.request_id, outcome)

        # 等待回调执行
        await asyncio.sleep(0.1)

        assert callback_triggered
        assert callback_result == outcome
        print("✅ 回调功能正常")

    finally:
        await context.stop()

    print("🎉 回调功能测试通过！")


async def test_agent_context_integration():
    """测试 Agent 与 Context 的集成"""
    print("\n🧪 测试 Agent 与 Context 的集成...")

    # 创建 Agent 客户端（不连接到真实的 Hub）
    agent = AgentClient(
        agent_id="test_agent",
        env_id="test_env",
        hub_url="ws://localhost:8999",  # 假的地址
    )

    # 启动上下文管理器
    await agent.context.start()

    try:
        # 测试上下文统计
        stats = agent.get_context_stats()
        print(f"📊 Agent 上下文统计: {stats}")
        assert stats["total_requests"] == 0

        # 创建一些测试上下文
        context_item1 = agent.context.create_request_context(
            request_type="action",
            request_data={"action": "move", "params": {"direction": "north"}},
        )

        context_item2 = agent.context.create_request_context(
            request_type="action",
            request_data={"action": "attack", "params": {"target": "enemy"}},
        )

        print(f"✅ 创建了 2 个上下文")

        # 测试按类型获取上下文
        action_contexts = agent.context.get_contexts_by_type("action")
        assert len(action_contexts) == 2
        print(f"✅ 按类型查询: {len(action_contexts)} 个 action 上下文")

        # 测试待处理上下文
        pending_contexts = agent.context.get_pending_contexts()
        assert len(pending_contexts) == 2
        print(f"✅ 待处理上下文: {len(pending_contexts)} 个")

        # 完成一个上下文
        outcome = OutcomeMessage(
            action_id=context_item1.request_id,
            status="success",
            outcome={"position": [1, 1]},
        )
        agent.context.complete_request(context_item1.request_id, outcome)

        # 重新检查待处理上下文
        pending_contexts = agent.context.get_pending_contexts()
        assert len(pending_contexts) == 1
        print(f"✅ 完成后待处理上下文: {len(pending_contexts)} 个")

        # 最终统计
        stats = agent.get_context_stats()
        print(f"📊 最终统计: {stats}")
        assert stats["total_requests"] == 2
        assert stats["completed_requests"] == 1
        assert stats["pending_requests"] == 1

    finally:
        await agent.context.stop()

    print("🎉 Agent 与 Context 集成测试通过！")


async def main():
    """主测试函数"""
    print("🚀 开始测试 Context 模块...")

    try:
        await test_context_basic()
        await test_context_timeout()
        await test_context_callback()
        await test_agent_context_integration()

        print("\n🎉 所有测试通过！")
        print("✨ Context 模块功能正常")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    asyncio.run(main())
