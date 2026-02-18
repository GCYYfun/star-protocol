import asyncio
from rich import print
from star_protocol.client import EnvironmentClient


class DemoEnvironment(EnvironmentClient):

    async def on_action(self, sender: str, content: dict):
        print("收到动作:", content)
        await self.send_outcome(sender, {"status": "success", "message": "Action received"})


async def main():
    """主函数"""
    print("="*70)
    print("Star Protocol - Demo Environment 示例")
    print("="*70)
    
    # 创建 Environment
    env = DemoEnvironment(client_id="demo_env")
    
    # 连接到 Hub
    print("连接到 Hub...")
    await env.connect("ws://localhost:8000")
    print("✅ 已连接")
    
    # 启动 Environment（开始接收消息）
    print("启动 Environment...")
    await env.start()
    print("✅ 已启动")
    
    # 保持运行
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("正在停止...")
        await env.stop()
        print("✅ Environment 已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("============")
        print("程序被用户中断")
        print("============")
