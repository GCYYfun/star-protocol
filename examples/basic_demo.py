#!/usr/bin/env python3
"""
Star Protocol V3 基础演示

完整的演示，包括：
- Hub 服务器
- Environment 客户端
- Agent 客户端
- 上下文管理
- 监控系统
"""

import asyncio
import argparse
import signal
import sys
import time
from pathlib import Path
from typing import List, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from star_protocol.hub.server import HubServer
from star_protocol.client.environment import EnvironmentClient
from star_protocol.client.agent import AgentClient
from star_protocol.monitor import create_simple_monitor
from star_protocol.utils import setup_logger, get_logger


class BasicDemo:
    """基础演示类"""

    def __init__(
        self,
        port: int = 8000,
        num_agents: int = 2,
        demo_duration: int = 30,
        enable_monitoring: bool = True,
    ):
        self.port = port
        self.num_agents = num_agents
        self.demo_duration = demo_duration
        self.enable_monitoring = enable_monitoring

        # 设置日志
        setup_logger(level="INFO", enable_rich=True)
        self.logger = get_logger("star_protocol.basic_demo")

        # 组件
        self.hub_server: Optional[HubServer] = None
        self.environment: Optional[EnvironmentClient] = None
        self.agents: List[AgentClient] = []

        # 监控
        self.monitor = None
        if enable_monitoring:
            self.monitor = create_simple_monitor()

        # 状态
        self.running = False
        self.action_count = 0

    async def start(self) -> None:
        """启动演示"""
        self.logger.info("🚀 启动 Star Protocol V3 基础演示")
        self.logger.info(f"   Hub 端口: {self.port}")
        self.logger.info(f"   Agent 数量: {self.num_agents}")
        self.logger.info(f"   演示时长: {self.demo_duration} 秒")

        try:
            # 启动监控
            if self.monitor:
                self.monitor.start()
                self.logger.info("📊 监控系统已启动")

            # 启动 Hub 服务器
            await self._start_hub()

            # 等待一秒让 Hub 完全启动
            await asyncio.sleep(1)

            # 启动环境
            await self._start_environment()

            # 等待一秒让环境注册
            await asyncio.sleep(1)

            # 启动 Agent
            await self._start_agents()

            # 等待一秒让 Agent 注册
            await asyncio.sleep(1)

            # 运行演示
            await self._run_demo()

        except Exception as e:
            self.logger.error(f"❌ 演示失败: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """停止演示"""
        self.logger.info("🛑 正在停止演示...")
        self.running = False

        # 断开 Agent
        for i, agent in enumerate(self.agents):
            try:
                await agent.disconnect()
                self.logger.info(f"✅ Agent {i+1} 已断开")
            except Exception as e:
                self.logger.error(f"断开 Agent {i+1} 失败: {e}")

        # 断开环境
        if self.environment:
            try:
                await self.environment.disconnect()
                self.logger.info("✅ Environment 已断开")
            except Exception as e:
                self.logger.error(f"断开 Environment 失败: {e}")

        # 停止 Hub 服务器
        if self.hub_server:
            try:
                await self.hub_server.stop()
                self.logger.info("✅ Hub 服务器已停止")
            except Exception as e:
                self.logger.error(f"停止 Hub 服务器失败: {e}")

        # 停止监控
        if self.monitor:
            try:
                self.monitor.stop()
                self.logger.info("📊 监控系统已停止")
            except Exception as e:
                self.logger.error(f"停止监控失败: {e}")

        self.logger.info("🎉 演示已完成")

    async def _start_hub(self) -> None:
        """启动 Hub 服务器"""
        self.logger.info("🌐 启动 Hub 服务器...")

        self.hub_server = HubServer(
            host="localhost", port=self.port, max_connections=100
        )

        # 启用监控
        if self.monitor:
            self.hub_server.enable_metrics(self.monitor.get_collector())

        await self.hub_server.start()
        self.logger.info(f"✅ Hub 服务器已启动 (端口: {self.port})")

    async def _start_environment(self) -> None:
        """启动环境"""
        self.logger.info("🌍 启动 Environment...")

        self.environment = EnvironmentClient(
            env_id="demo_world",
            hub_url=f"ws://localhost:{self.port}",
            metadata={"type": "grid_world", "size": "10x10"},
        )

        # 启用监控
        if self.monitor:
            self.environment.enable_metrics(self.monitor.get_collector())

        # 注册事件处理器
        self._register_environment_handlers()

        await self.environment.connect()
        self.logger.info("✅ Environment 已启动")

    async def _start_agents(self) -> None:
        """启动 Agent"""
        self.logger.info(f"🤖 启动 {self.num_agents} 个 Agent...")

        for i in range(self.num_agents):
            agent_id = f"demo_agent_{i+1}"

            agent = AgentClient(
                agent_id=agent_id,
                env_id="demo_world",
                hub_url=f"ws://localhost:{self.port}",
                metadata={"type": "simple_ai", "version": "1.0"},
            )

            # 启用监控
            if self.monitor:
                agent.enable_metrics(self.monitor.get_collector())

            # 注册事件处理器
            self._register_agent_handlers(agent, i + 1)

            await agent.connect()
            self.agents.append(agent)

            self.logger.info(f"✅ Agent {i+1} ({agent_id}) 已启动")

            # 间隔启动，避免同时连接
            await asyncio.sleep(0.5)

    def _register_environment_handlers(self) -> None:
        """注册环境事件处理器"""

        @self.environment.action()
        async def handle_action(message, ctx):
            """处理 Agent 动作"""
            action = message.action
            params = message.parameters
            action_id = message.action_id

            # 从上下文获取发送者信息
            agent_id = ctx.sender if ctx.sender else "unknown"

            # 调试日志
            self.logger.debug(
                f"🎯 处理动作: {action} from {agent_id} (sender={ctx.sender})"
            )

            # 模拟环境处理
            await asyncio.sleep(0.1)  # 模拟处理时间

            # 生成结果
            if action == "move":
                direction = params.get("direction", "north")
                result = {
                    "success": True,
                    "position": [
                        max(
                            0,
                            min(
                                9,
                                params.get("x", 5)
                                + (
                                    1
                                    if direction == "east"
                                    else -1 if direction == "west" else 0
                                ),
                            ),
                        ),
                        max(
                            0,
                            min(
                                9,
                                params.get("y", 5)
                                + (
                                    1
                                    if direction == "south"
                                    else -1 if direction == "north" else 0
                                ),
                            ),
                        ),
                    ],
                    "direction": direction,
                }
            elif action == "look":
                result = {
                    "success": True,
                    "visible_objects": ["tree", "rock", "path"],
                    "description": "You see a peaceful landscape",
                }
            else:
                result = {"success": False, "reason": f"Unknown action: {action}"}

            # 发送结果
            from star_protocol.protocol import OutcomeMessage

            await self.environment.send_outcome(
                action_id=action_id,
                status="success" if result["success"] else "error",
                outcome=result,
                recipient=agent_id,
            )

            # 统计
            self.action_count += 1

            self.logger.debug(f"🎯 处理动作: {action} -> {result}")

        @self.environment.event()
        async def handle_agent_joined(event_msg):
            """处理 Agent 加入事件"""
            if event_msg.event == "agent_joined":
                agent_id = event_msg.data.get("agent_id")
                self.logger.info(f"👋 Agent {agent_id} 已加入环境")

                # 欢迎消息
                from star_protocol.protocol import EventMessage

                welcome_event = EventMessage(
                    event="welcome",
                    data={
                        "message": f"欢迎 {agent_id} 进入演示世界！",
                        "world_info": {
                            "size": [10, 10],
                            "available_actions": ["move", "look"],
                            "starting_position": [5, 5],
                        },
                    },
                )
                await self.environment.send_message(welcome_event, agent_id)

    def _register_agent_handlers(self, agent: AgentClient, agent_num: int) -> None:
        """注册 Agent 事件处理器"""

        @agent.outcome()
        async def handle_outcome(outcome_msg):
            """处理动作结果"""
            self.logger.debug(f"🤖 Agent {agent_num} 收到结果: {outcome_msg.outcome}")

        @agent.event()
        async def handle_event(event_msg):
            """处理事件消息"""
            if event_msg.event == "welcome":
                message = event_msg.data.get("message")
                self.logger.info(f"🤖 Agent {agent_num}: {message}")

    async def _run_demo(self) -> None:
        """运行演示"""
        self.logger.info(f"🎮 开始演示 ({self.demo_duration} 秒)...")
        self.running = True

        start_time = time.time()

        # 启动 Agent 行为任务
        agent_tasks = []
        for i, agent in enumerate(self.agents):
            task = asyncio.create_task(self._agent_behavior(agent, i + 1))
            agent_tasks.append(task)

        # 监控任务
        monitor_task = asyncio.create_task(self._monitor_progress(start_time))

        # 等待演示完成
        try:
            await asyncio.wait_for(
                asyncio.gather(*agent_tasks, monitor_task, return_exceptions=True),
                timeout=self.demo_duration + 5,
            )
        except asyncio.TimeoutError:
            self.logger.warning("演示超时")

        self.running = False
        self.logger.info(f"✅ 演示完成，总共执行了 {self.action_count} 个动作")

    async def _agent_behavior(self, agent: AgentClient, agent_num: int) -> None:
        """Agent 行为逻辑"""
        actions = ["move", "look"]
        directions = ["north", "south", "east", "west"]

        action_count = 0
        while self.running and action_count < 20:  # 每个 Agent 最多执行 20 个动作
            try:
                # 随机选择动作
                import random

                action = random.choice(actions)

                if action == "move":
                    params = {
                        "direction": random.choice(directions),
                        "x": random.randint(0, 9),
                        "y": random.randint(0, 9),
                    }
                else:
                    params = {}

                # 使用上下文功能发送动作并等待结果
                try:
                    outcome = await agent.send_action_and_wait(
                        action=action, parameters=params, timeout=3.0
                    )

                    if outcome and hasattr(outcome, "outcome"):
                        result = outcome.outcome
                        if result.get("success"):
                            self.logger.debug(
                                f"🤖 Agent {agent_num} 动作成功: {action}"
                            )
                        else:
                            self.logger.debug(
                                f"🤖 Agent {agent_num} 动作失败: {result.get('reason')}"
                            )

                except asyncio.TimeoutError:
                    self.logger.warning(f"🤖 Agent {agent_num} 动作超时: {action}")
                except Exception as e:
                    self.logger.error(f"🤖 Agent {agent_num} 动作错误: {e}")

                action_count += 1

                # 随机间隔
                await asyncio.sleep(random.uniform(0.5, 2.0))

            except Exception as e:
                self.logger.error(f"Agent {agent_num} 行为错误: {e}")
                break

    async def _monitor_progress(self, start_time: float) -> None:
        """监控进度"""
        while self.running:
            await asyncio.sleep(5)  # 每 5 秒报告一次

            elapsed = time.time() - start_time
            remaining = max(0, self.demo_duration - elapsed)

            # 获取上下文统计
            active_agents = len([a for a in self.agents if a.connected])

            self.logger.info(
                f"📊 演示状态 - 已执行 {self.action_count} 个动作, "
                f"活跃 Agent: {active_agents}, 剩余时间: {remaining:.1f}秒"
            )

            if remaining <= 0:
                break


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Star Protocol V3 基础演示")
    parser.add_argument(
        "--port", type=int, default=8000, help="Hub 服务器端口 (默认: 8000)"
    )
    parser.add_argument("--agents", type=int, default=2, help="Agent 数量 (默认: 2)")
    parser.add_argument(
        "--duration", type=int, default=30, help="演示时长（秒）(默认: 30)"
    )
    parser.add_argument("--no-monitoring", action="store_true", help="禁用监控功能")

    args = parser.parse_args()

    # 检查端口是否可用
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", args.port))
    except OSError:
        print(f"❌ 端口 {args.port} 已被占用，请选择其他端口")
        return 1

    # 创建并运行演示
    demo = BasicDemo(
        port=args.port,
        num_agents=args.agents,
        demo_duration=args.duration,
        enable_monitoring=not args.no_monitoring,
    )

    # 设置信号处理器
    def signal_handler(signum, frame):
        print("\n🛑 收到中断信号，正在停止演示...")
        asyncio.create_task(demo.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await demo.start()
        return 0
    except KeyboardInterrupt:
        print("\n🛑 用户中断")
        return 0
    except Exception as e:
        print(f"❌ 演示失败: {e}")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
