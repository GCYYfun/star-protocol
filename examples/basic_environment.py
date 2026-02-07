"""
基础 Environment 示例

展示如何创建和使用 Environment 客户端。

运行方式：
1. 启动 Hub: uv run python -m star_protocol.cli
2. 运行此示例: uv run python examples/basic_environment.py
3. 启动 Agent: uv run python examples/basic_agent.py
"""

import asyncio
import logging
from star_protocol.client import EnvironmentClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class MyEnvironment(EnvironmentClient):
    """自定义 Environment 类"""
    
    async def on_action(self, sender: str, content: dict):
        """处理 Agent 的动作"""
        action_name = content.get("name")
        params = content.get("params", {})
        
        print(f"\n📥 收到动作: {action_name}")
        print(f"   来自: {sender}")
        print(f"   参数: {params}")
        
        # 根据动作类型处理
        if action_name == "greet":
            result = {
                "success": True,
                "message": f"Hello, {sender}! {params.get('message', '')}"
            }
        elif action_name == "calculate":
            op = params.get("operation")
            a = params.get("a", 0)
            b = params.get("b", 0)
            
            if op == "add":
                value = a + b
            elif op == "subtract":
                value = a - b
            elif op == "multiply":
                value = a * b
            elif op == "divide":
                value = a / b if b != 0 else None
            else:
                value = None
            
            result = {
                "success": value is not None,
                "operation": op,
                "result": value
            }
        else:
            result = {
                "success": False,
                "error": f"Unknown action: {action_name}"
            }
        
        # 返回结果
        print(f"📤 返回结果: {result}")
        await self.send_outcome(recipient=sender, content=result)
        
        # 广播事件
        await self.broadcast_event(
            event_type="action_processed",
            content={
                "agent": sender,
                "action": action_name
            }
        )


async def main():
    """主函数"""
    print("\n" + "="*70)
    print("Star Protocol - 基础 Environment 示例")
    print("="*70 + "\n")
    
    # 创建 Environment
    env = MyEnvironment(client_id="my_env")
    
    # 连接到 Hub
    print("连接到 Hub...")
    await env.connect("ws://localhost:8765")
    print("✅ 已连接\n")
    
    # 启动 Environment（开始接收消息）
    print("启动 Environment...")
    await env.start()
    print("✅ 已启动\n")
    
    print("等待 Agent 连接...")
    print("💡 提示: 在另一个终端运行 'uv run python examples/basic_agent.py'\n")
    print("按 Ctrl+C 退出\n")
    
    # 保持运行
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n正在停止...")
        await env.stop()
        print("✅ Environment 已停止\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  程序被用户中断")
