#!/usr/bin/env python3
"""
Star Protocol Hub 服务器演示

启动一个完整的Hub服务器，支持Agent和Environment连接
"""

import asyncio
import signal
import sys
from star_protocol.hub import StarHubServer
from star_protocol.monitor import get_monitor, set_rich_mode


class HubServerDemo:
    """Hub服务器演示类"""

    def __init__(self, host: str = "localhost", port: int = 9999):
        self.host = host
        self.port = port
        self.server = StarHubServer(
            host=host,
            port=port,
            enable_auth=False,  # 简化演示，不启用认证
            enable_validation=True,
        )
        self.running = False

        # 初始化监控
        self.monitor = get_monitor("hub_server_demo")

    async def start(self):
        """启动服务器"""
        self.monitor.info("🚀 启动 Star Protocol Hub 服务器...")
        self.monitor.info(f"📍 地址: {self.host}:{self.port}")
        self.monitor.info(
            f"🔗 Agent 连接: ws://{self.host}:{self.port}/env/{{env_id}}/agent/{{agent_id}}"
        )
        self.monitor.info(
            f"🌍 Environment 连接: ws://{self.host}:{self.port}/env/{{env_id}}"
        )
        self.monitor.info(
            f"👤 Human 连接: ws://{self.host}:{self.port}/human/{{human_id}}"
        )
        self.monitor.set_status("启动中")

        try:
            await self.server.start()
            self.running = True
            self.monitor.success("✅ Hub 服务器启动成功!")
            self.monitor.info("💡 提示: 按 Ctrl+C 停止服务器")
            self.monitor.set_status("运行中")

            # 启动状态监控
            monitor_task = asyncio.create_task(self.monitor_stats())

            # 等待中断信号
            stop_event = asyncio.Event()

            def signal_handler():
                self.monitor.warning("\n📴 收到停止信号，正在关闭服务器...")
                stop_event.set()

            loop = asyncio.get_running_loop()
            if sys.platform == "win32":
                # Windows不支持add_signal_handler，使用线程方式监听KeyboardInterrupt
                async def windows_signal_wait():
                    try:
                        while not stop_event.is_set():
                            await asyncio.sleep(1)
                    except KeyboardInterrupt:
                        signal_handler()

                monitor_task2 = asyncio.create_task(windows_signal_wait())
            else:
                for sig in [signal.SIGINT, signal.SIGTERM]:
                    try:
                        loop.add_signal_handler(sig, signal_handler)
                    except NotImplementedError:
                        self.monitor.warning(
                            f"⚠️ 当前平台不支持信号处理（{sig}），请使用 Ctrl+C 退出。"
                        )

            await stop_event.wait()

        except Exception as e:
            self.monitor.error(f"❌ 服务器启动失败: {e}")
            sys.exit(1)
        finally:
            if hasattr(self, "monitor_task"):
                monitor_task.cancel()
            await self.stop()

    async def monitor_stats(self):
        """监控服务器统计信息"""
        try:
            while self.running:
                await asyncio.sleep(10)  # 每10秒输出一次统计

                stats = {
                    "活跃连接": self.server.session_manager.get_session_count(),
                    "Agent数量": len(self.server.session_manager.get_agents()),
                    "Environment数量": len(
                        self.server.session_manager.get_environments()
                    ),
                    "Human数量": len(self.server.session_manager.get_humans()),
                    "环境数量": self.server.session_manager.get_env_count(),
                }

                # 更新monitor统计
                self.monitor.update_stats(**stats)

                # 显示统计信息
                stats_str = " | ".join([f"{k}: {v}" for k, v in stats.items()])
                self.monitor.info(f"📊 服务器状态: {stats_str}")

        except asyncio.CancelledError:
            pass

    async def stop(self):
        """停止服务器"""
        if self.running:
            self.monitor.info("⏹️  正在停止 Hub 服务器...")
            self.monitor.set_status("停止中")
            self.running = False
            await self.server.stop()
            self.monitor.success("✅ Hub 服务器已停止")
            self.monitor.set_status("已停止")


async def main():
    """主函数"""
    import argparse

    # 命令行参数
    parser = argparse.ArgumentParser(description="Star Protocol Hub Server Demo")
    parser.add_argument("--host", default="localhost", help="Host address")
    parser.add_argument("--port", type=int, default=9999, help="Port number")

    args = parser.parse_args()

    # 创建并启动服务器
    demo = HubServerDemo(args.host, args.port)
    await demo.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:

        monitor = get_monitor("hub_server_demo")
        monitor.warning("\n👋 再见!")
    except Exception as e:

        monitor = get_monitor("hub_server_demo")
        monitor.error(f"❌ 程序异常退出: {e}")
        sys.exit(1)
