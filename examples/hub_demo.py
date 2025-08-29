#!/usr/bin/env python3
"""
Hub 服务器示例

这个示例展示如何启动和运行 Hub 服务器，包括：
- WebSocket 服务器启动
- 客户端连接管理
- 消息路由处理
- 实时监控显示
- 优雅关闭处理
"""

import asyncio
import argparse
import signal
import sys
import os
import platform
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from star_protocol.hub import HubServer
from star_protocol.monitor import create_simple_monitor
from star_protocol.utils import setup_logger, get_logger
from star_protocol.protocol import ClientType
from star_protocol.cli import create_hub_cli


class HubServerDemo:
    """Hub 服务器演示类"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        enable_monitoring: bool = True,
        interactive: bool = True,
        log_level: str = "INFO",
    ):
        self.host = host
        self.port = port
        self.enable_monitoring = enable_monitoring
        self.interactive = interactive
        self.log_level = log_level

        # 设置日志
        setup_logger(level=log_level, enable_rich=True)
        self.logger = get_logger("star_protocol.hub_server_demo")

        # 创建监控器
        self.monitor = None
        if enable_monitoring:
            # 确保日志目录存在
            Path("./logs").mkdir(exist_ok=True)

            self.monitor = create_simple_monitor(
                export_interval=30.0,  # 30秒导出一次
                file_path=f"./logs/hub_server_{port}.json",
                console_output=True,
            )

        # Hub 服务器
        self.hub_server: Optional[HubServer] = None
        self.cli = None
        self.running = False

        # 统计信息
        self.start_time = None
        self.total_connections = 0
        self.total_messages = 0

    async def start(self) -> None:
        """启动 Hub 服务器"""
        try:
            self.logger.info("🚀 启动 Hub 服务器演示")
            self.logger.info(f"   服务器地址: {self.host}:{self.port}")
            self.logger.info(
                f"   监控功能: {'启用' if self.enable_monitoring else '禁用'}"
            )
            self.logger.info(f"   交互模式: {'启用' if self.interactive else '禁用'}")

            # 启动监控
            if self.monitor:
                self.monitor.start()
                self.logger.info("📊 监控系统已启动")

            # 创建并启动 Hub 服务器
            self.hub_server = HubServer(host=self.host, port=self.port)

            # 创建交互式CLI（如果启用）
            if self.interactive:
                self.cli = create_hub_cli(
                    self.hub_server, f"Hub Server ({self.host}:{self.port})"
                )

                # 设置CLI退出回调
                def on_cli_exit():
                    self.logger.info("CLI 退出，停止服务器...")
                    self.running = False

                self.cli.set_exit_callback(on_cli_exit)

            # 如果启用监控，将监控器集成到 Hub
            if self.monitor:
                # 注意：这里需要 HubServer 支持监控集成
                # 目前我们手动设置回调来记录指标
                collector = self.monitor.get_collector()
                await self._setup_monitoring_callbacks(collector)

            # 设置信号处理
            self._setup_signal_handlers()

            self.running = True
            import time

            self.start_time = time.time()

            # 启动服务器
            await self.hub_server.start()

            self.logger.info("✅ Hub 服务器启动成功")
            self.logger.info(f"🌐 WebSocket 服务器运行在 ws://{self.host}:{self.port}")

            if self.interactive:
                # 启动交互式CLI
                self.cli.start()
                self.logger.info("🎮 交互式命令行已启用")

                # 动态获取可用命令
                commands_str = self.cli.get_available_commands_str()
                self.logger.info(f"💡 可用命令: {commands_str}")
            else:
                self.logger.info("💡 按 Ctrl+C 停止服务器")

            # 保持服务器运行 - 使用跨平台的方式
            if platform.system() == "Windows":
                # Windows 系统使用 asyncio 的方式处理信号
                await self._keep_running_windows()
            else:
                # Unix-like 系统可以使用 asyncio 信号处理
                await self._keep_running_unix()

        except Exception as e:
            self.logger.error(f"❌ 启动 Hub 服务器失败: {e}")
            raise
        finally:
            # 确保停止服务器
            await self.stop()

    async def stop(self) -> None:
        """停止 Hub 服务器"""
        if not self.running:
            return

        self.logger.info("🛑 正在停止 Hub 服务器...")
        self.running = False

        # 停止交互式CLI
        if self.cli:
            self.cli.stop()
            self.logger.info("🎮 交互式命令行已停止")

        # 停止 Hub 服务器
        if self.hub_server:
            await self.hub_server.stop()
            self.logger.info("✅ Hub 服务器已停止")

        # 停止监控
        if self.monitor:
            self.monitor.stop()
            self.logger.info("📊 监控系统已停止")

        # 显示运行摘要
        await self._show_summary()

    async def _keep_running(self) -> None:
        """保持服务器运行"""
        try:
            while self.running:
                await asyncio.sleep(1.0)
                # 检查服务器状态
                if self.hub_server and not self.hub_server.running:
                    self.logger.warning("Hub 服务器意外停止")
                    break
        except asyncio.CancelledError:
            self.logger.info("服务器运行循环被取消")
        except Exception as e:
            self.logger.error(f"服务器运行循环出错: {e}")
        finally:
            self.logger.info("退出服务器运行循环")

    async def _keep_running_windows(self) -> None:
        """Windows 系统的服务器运行循环"""
        try:
            while self.running:
                await asyncio.sleep(1.0)
                # 检查服务器状态
                if self.hub_server and not self.hub_server.running:
                    self.logger.warning("Hub 服务器意外停止")
                    break
        except asyncio.CancelledError:
            self.logger.info("服务器运行循环被取消")
        except Exception as e:
            self.logger.error(f"服务器运行循环出错: {e}")
        finally:
            self.logger.info("退出服务器运行循环")

    async def _keep_running_unix(self) -> None:
        """Unix-like 系统的服务器运行循环 - 使用 asyncio 信号处理"""
        loop = asyncio.get_running_loop()

        # 创建一个 Event 用于等待停止信号
        stop_event = asyncio.Event()

        def signal_handler():
            self.logger.info("📡 收到停止信号，准备停止服务器...")
            self.running = False
            stop_event.set()

        # 在 Unix-like 系统上使用 asyncio 的信号处理
        try:
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)

            # 等待停止信号或服务器异常停止
            while self.running:
                try:
                    # 等待 1 秒或停止信号
                    await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                    break  # 收到停止信号
                except asyncio.TimeoutError:
                    # 超时是正常的，继续循环检查
                    pass
                except asyncio.CancelledError:
                    # 被取消，退出循环
                    break

                # 检查服务器状态
                if self.hub_server and not self.hub_server.running:
                    self.logger.warning("Hub 服务器意外停止")
                    break

        except asyncio.CancelledError:
            # 正常的取消操作
            pass
        except Exception as e:
            self.logger.error(f"Unix 运行循环出错: {e}")
        finally:
            # 清理信号处理器
            try:
                loop.remove_signal_handler(signal.SIGINT)
                loop.remove_signal_handler(signal.SIGTERM)
            except Exception:
                pass
            self.logger.info("退出服务器运行循环")

    async def _setup_monitoring_callbacks(self, collector):
        """设置监控回调"""
        # 注意：这是一个简化版本
        # 实际实现中，HubServer 应该直接支持监控集成

        original_on_connect = getattr(self.hub_server, "_on_client_connect", None)
        original_on_disconnect = getattr(self.hub_server, "_on_client_disconnect", None)
        original_on_message = getattr(self.hub_server, "_on_message_route", None)

        async def monitored_on_connect(client_info):
            self.total_connections += 1
            await collector.record_client_connected(client_info)
            if original_on_connect:
                await original_on_connect(client_info)

        async def monitored_on_disconnect(client_id):
            await collector.record_client_disconnected(client_id)
            if original_on_disconnect:
                await original_on_disconnect(client_id)

        async def monitored_on_message(envelope):
            self.total_messages += 1
            await collector.record_envelope_routed(envelope)
            if original_on_message:
                await original_on_message(envelope)

        # 设置回调（简化版本，实际需要 HubServer 支持）
        # self.hub_server._on_client_connect = monitored_on_connect
        # self.hub_server._on_client_disconnect = monitored_on_disconnect
        # self.hub_server._on_message_route = monitored_on_message

    def _setup_signal_handlers(self) -> None:
        """设置信号处理器 - 跨平台兼容"""

        def signal_handler(signum, frame):
            self.logger.info(f"📡 收到信号 {signum}，准备停止服务器...")
            # 设置停止标志，让主循环优雅退出
            self.running = False

        # 跨平台信号处理
        if platform.system() == "Windows":
            # Windows 系统只支持 SIGINT (Ctrl+C)
            signal.signal(signal.SIGINT, signal_handler)
            self.logger.debug("已设置 Windows 信号处理器 (SIGINT)")
        else:
            # Unix-like 系统 (Linux, macOS, etc.)
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            self.logger.debug("已设置 Unix 信号处理器 (SIGINT, SIGTERM)")

        # 对于所有平台，我们还可以添加一个简单的键盘中断处理
        # 这样即使信号处理失败，程序也能通过 KeyboardInterrupt 退出

    async def _show_summary(self) -> None:
        """显示运行摘要"""
        if not self.start_time:
            return

        import time

        runtime = time.time() - self.start_time

        self.logger.info("📋 Hub 服务器运行摘要:")
        self.logger.info(f"   运行时间: {runtime:.1f} 秒")
        self.logger.info(f"   总连接数: {self.total_connections}")
        self.logger.info(f"   总消息数: {self.total_messages}")

        if self.total_messages > 0 and runtime > 0:
            msgs_per_sec = self.total_messages / runtime
            self.logger.info(f"   消息频率: {msgs_per_sec:.1f} 消息/秒")

        # 获取监控摘要
        if self.monitor:
            try:
                current_metrics = await self.monitor.get_current_metrics()
                active_connections = sum(
                    1
                    for conn in current_metrics.get("connections", [])
                    if conn.get("disconnected_at") is None
                )
                self.logger.info(f"   活跃连接: {active_connections}")
                self.logger.info(
                    f"   监控记录: {len(current_metrics.get('connections', []))} 连接, {len(current_metrics.get('envelopes', []))} 信封"
                )
            except Exception as e:
                self.logger.warning(f"获取监控摘要失败: {e}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Star Protocol V3 Hub 服务器演示")
    parser.add_argument(
        "--host", default="localhost", help="绑定地址 (默认: localhost)"
    )
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认: 8000)")
    parser.add_argument("--no-monitoring", action="store_true", help="禁用监控功能")
    parser.add_argument(
        "--no-interactive", action="store_true", help="禁用交互式命令行"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认: INFO)",
    )

    args = parser.parse_args()

    # 检查端口是否被占用
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 允许地址重用
            s.bind((args.host, args.port))
    except OSError as e:
        print(f"❌ 端口 {args.port} 已被占用，请选择其他端口: {e}")
        return 1

    # 创建并启动 Hub 服务器演示
    demo = HubServerDemo(
        host=args.host,
        port=args.port,
        enable_monitoring=not args.no_monitoring,
        interactive=not args.no_interactive,
        log_level=args.log_level,
    )

    try:
        await demo.start()
    except KeyboardInterrupt:
        print("\n🛑 收到键盘中断信号 (Ctrl+C)，正在停止服务器...")
        # 在 Windows 上，KeyboardInterrupt 是主要的停止方式
        demo.running = False
    except Exception as e:
        print(f"❌ Hub 服务器演示失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    # 在 Windows 上设置事件循环策略以避免一些问题
    if platform.system() == "Windows":
        # Windows 特定的优化
        try:
            # 使用 ProactorEventLoop 在 Windows 上获得更好的性能
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except AttributeError:
            # 如果没有 WindowsProactorEventLoopPolicy，使用默认策略
            pass

    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Hub 服务器演示已停止")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 程序异常退出: {e}")
        sys.exit(1)
