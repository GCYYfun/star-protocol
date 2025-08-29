#!/usr/bin/env python3
"""
Environment 客户端示例

这个示例展示如何创建和运行一个环境客户端，包括：
- 连接到 Hub 服务器
- 处理 Agent 的动作请求
- 维护世界状态
- 发送世界事件
- 监控和日志记录
"""

import asyncio
import argparse
import json
import random
import sys
import time
import platform
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from star_protocol.client import EnvironmentClient
from star_protocol.protocol import (
    ActionMessage,
    ClientInfo,
    ClientType,
    EventMessage,
)
from star_protocol.monitor import create_simple_monitor
from star_protocol.utils import setup_logger, get_logger
from star_protocol.cli import create_environment_cli


class SimpleWorld:
    """简单的网格世界模拟"""

    def __init__(self, size: int = 10):
        self.size = size
        self.agents: Dict[str, Tuple[int, int]] = {}  # agent_id -> (x, y)
        self.items: List[Tuple[int, int, str]] = []  # (x, y, item_type)
        self.obstacles: List[Tuple[int, int]] = []  # (x, y)
        self.turn = 0

        # 初始化世界
        self._generate_world()

    def _generate_world(self) -> None:
        """生成初始世界"""
        # 添加一些障碍物
        num_obstacles = random.randint(3, 8)
        for _ in range(num_obstacles):
            x, y = random.randint(0, self.size - 1), random.randint(0, self.size - 1)
            if (x, y) not in self.obstacles:
                self.obstacles.append((x, y))

        # 添加一些物品
        item_types = ["treasure", "potion", "key", "food"]
        num_items = random.randint(5, 12)
        for _ in range(num_items):
            x, y = random.randint(0, self.size - 1), random.randint(0, self.size - 1)
            if (x, y) not in self.obstacles:
                item_type = random.choice(item_types)
                self.items.append((x, y, item_type))

    def add_agent(self, agent_id: str) -> Tuple[int, int]:
        """添加 Agent 到世界"""
        # 找一个空位置
        while True:
            x, y = random.randint(0, self.size - 1), random.randint(0, self.size - 1)
            if self._is_position_free(x, y):
                self.agents[agent_id] = (x, y)
                return (x, y)

    def remove_agent(self, agent_id: str) -> bool:
        """从世界移除 Agent"""
        return self.agents.pop(agent_id, None) is not None

    def move_agent(self, agent_id: str, direction: str) -> Dict[str, Any]:
        """移动 Agent"""
        if agent_id not in self.agents:
            return {"success": False, "reason": "Agent not in world"}

        x, y = self.agents[agent_id]
        new_x, new_y = x, y

        # 计算新位置
        if direction == "north":
            new_y = max(0, y - 1)
        elif direction == "south":
            new_y = min(self.size - 1, y + 1)
        elif direction == "east":
            new_x = min(self.size - 1, x + 1)
        elif direction == "west":
            new_x = max(0, x - 1)
        else:
            return {"success": False, "reason": f"Invalid direction: {direction}"}

        # 检查是否可以移动
        if not self._is_position_free(new_x, new_y, exclude_agent=agent_id):
            return {"success": False, "reason": "Position blocked"}

        # 移动
        self.agents[agent_id] = (new_x, new_y)

        # 检查是否拾取物品
        collected_item = None
        for i, (item_x, item_y, item_type) in enumerate(self.items):
            if item_x == new_x and item_y == new_y:
                collected_item = self.items.pop(i)
                break

        result = {
            "success": True,
            "old_position": (x, y),
            "new_position": (new_x, new_y),
            "direction": direction,
        }

        if collected_item:
            result["collected_item"] = {
                "type": collected_item[2],
                "position": (collected_item[0], collected_item[1]),
            }

        return result

    def get_agent_view(self, agent_id: str, view_range: int = 2) -> Dict[str, Any]:
        """获取 Agent 的视野"""
        if agent_id not in self.agents:
            return {"error": "Agent not in world"}

        x, y = self.agents[agent_id]
        view = {
            "agent_position": (x, y),
            "visible_area": [],
            "nearby_agents": [],
            "nearby_items": [],
            "nearby_obstacles": [],
        }

        # 扫描视野范围
        for dx in range(-view_range, view_range + 1):
            for dy in range(-view_range, view_range + 1):
                check_x, check_y = x + dx, y + dy
                if 0 <= check_x < self.size and 0 <= check_y < self.size:
                    view["visible_area"].append((check_x, check_y))

                    # 检查其他 Agent
                    for other_id, (other_x, other_y) in self.agents.items():
                        if (
                            other_id != agent_id
                            and other_x == check_x
                            and other_y == check_y
                        ):
                            view["nearby_agents"].append(
                                {"agent_id": other_id, "position": (other_x, other_y)}
                            )

                    # 检查物品
                    for item_x, item_y, item_type in self.items:
                        if item_x == check_x and item_y == check_y:
                            view["nearby_items"].append(
                                {"type": item_type, "position": (item_x, item_y)}
                            )

                    # 检查障碍物
                    if (check_x, check_y) in self.obstacles:
                        view["nearby_obstacles"].append((check_x, check_y))

        return view

    def _is_position_free(
        self, x: int, y: int, exclude_agent: Optional[str] = None
    ) -> bool:
        """检查位置是否空闲"""
        # 检查边界
        if not (0 <= x < self.size and 0 <= y < self.size):
            return False

        # 检查障碍物
        if (x, y) in self.obstacles:
            return False

        # 检查其他 Agent
        for agent_id, (agent_x, agent_y) in self.agents.items():
            if agent_id != exclude_agent and agent_x == x and agent_y == y:
                return False

        return True

    def get_world_state(self) -> Dict[str, Any]:
        """获取世界状态"""
        return {
            "turn": self.turn,
            "size": self.size,
            "agents": dict(self.agents),
            "items": [
                {"x": x, "y": y, "type": item_type} for x, y, item_type in self.items
            ],
            "obstacles": [{"x": x, "y": y} for x, y in self.obstacles],
        }

    def advance_turn(self) -> List[Dict[str, Any]]:
        """推进回合，返回世界事件"""
        self.turn += 1
        events = []

        # 随机生成一些世界事件
        if random.random() < 0.1:  # 10% 概率生成新物品
            x, y = random.randint(0, self.size - 1), random.randint(0, self.size - 1)
            if self._is_position_free(x, y):
                item_type = random.choice(["treasure", "potion", "key", "food"])
                self.items.append((x, y, item_type))
                events.append(
                    {
                        "type": "item_spawned",
                        "item": {"type": item_type, "position": (x, y)},
                        "turn": self.turn,
                    }
                )

        if random.random() < 0.05:  # 5% 概率天气变化
            weather = random.choice(["sunny", "rainy", "foggy", "stormy"])
            events.append(
                {"type": "weather_change", "weather": weather, "turn": self.turn}
            )

        return events


class EnvironmentDemo:
    """Environment 演示类"""

    def __init__(
        self,
        env_id: str,
        hub_url: str,
        world_size: int = 10,
        auto_events: bool = True,
        enable_monitoring: bool = True,
        interactive: bool = True,
        log_level: str = "INFO",
    ):
        self.env_id = env_id
        self.hub_url = hub_url
        self.world_size = world_size
        self.auto_events = auto_events
        self.enable_monitoring = enable_monitoring
        self.interactive = interactive

        # 设置日志
        setup_logger(level=log_level, enable_rich=True)
        self.logger = get_logger(f"star_protocol.environment_{env_id}")

        # 创建世界
        self.world = SimpleWorld(world_size)

        # 创建客户端
        self.client: Optional[EnvironmentClient] = None
        self.cli = None

        # 监控
        self.monitor = None
        if enable_monitoring:
            Path("./logs").mkdir(exist_ok=True)
            self.monitor = create_simple_monitor(
                export_interval=60.0,
                file_path=f"./logs/environment_{env_id}.json",
                console_output=True,
            )

        # 状态
        self.running = False
        self.connected_agents: Dict[str, Dict] = {}
        self.action_count = 0
        self.event_count = 0

        # 自动事件任务
        self.auto_event_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """启动环境"""
        try:
            self.logger.info(f"🌍 启动环境演示: {self.env_id}")
            self.logger.info(f"   Hub 地址: {self.hub_url}")
            self.logger.info(f"   世界大小: {self.world_size}x{self.world_size}")
            self.logger.info(f"   自动事件: {'启用' if self.auto_events else '禁用'}")
            self.logger.info(f"   交互模式: {'启用' if self.interactive else '禁用'}")

            # 启动监控
            if self.monitor:
                self.monitor.start()
                self.logger.info("📊 监控系统已启动")

            # 创建客户端
            self.client = EnvironmentClient(env_id=self.env_id, hub_url=self.hub_url)

            # 创建交互式CLI（如果启用）
            if self.interactive:
                self.cli = create_environment_cli(
                    self.client, f"Environment {self.env_id}"
                )

                # 设置CLI退出回调
                def on_cli_exit():
                    self.logger.info("CLI 退出，停止环境...")
                    self.running = False

                self.cli.set_exit_callback(on_cli_exit)

            # 注册事件处理器
            self._register_handlers()

            # 连接到 Hub
            await self.client.connect()
            self.running = True

            # 启动自动事件任务
            if self.auto_events:
                self.auto_event_task = asyncio.create_task(self._auto_event_loop())

            self.logger.info("✅ 环境启动成功")

            if self.interactive:
                # 启动交互式CLI
                self.cli.start()
                self.logger.info("🎮 交互式命令行已启用")

                # 动态获取可用命令
                commands_str = self.cli.get_available_commands_str()
                self.logger.info(f"💡 可用命令: {commands_str}")
            else:
                self.logger.info("💡 环境正在等待 Agent 连接...")

            # 保持运行
            await self._run_loop()

        except Exception as e:
            self.logger.error(f"❌ 启动环境失败: {e}")
            raise

    async def stop(self) -> None:
        """停止环境"""
        if not self.running:
            return

        self.logger.info("🛑 正在停止环境...")
        self.running = False

        # 停止交互式CLI
        if self.cli:
            self.cli.stop()
            self.logger.info("🎮 交互式命令行已停止")

        # 停止自动事件任务
        if self.auto_event_task:
            self.auto_event_task.cancel()
            try:
                await self.auto_event_task
            except asyncio.CancelledError:
                pass

        # 断开客户端
        if self.client:
            await self.client.disconnect()
            self.logger.info("✅ 已断开与 Hub 的连接")

        # 停止监控
        if self.monitor:
            self.monitor.stop()
            self.logger.info("📊 监控系统已停止")

        # 显示摘要
        self._show_summary()

    def _register_handlers(self) -> None:
        """注册事件处理器"""

        @self.client.event("connected")
        async def on_connected(event: EventMessage):
            self.logger.info(f"🔗 已连接到 Hub ,{event}")

            # 记录监控指标
            if self.monitor:
                collector = self.monitor.get_collector()
                client_info = ClientInfo(
                    self.env_id, ClientType.ENVIRONMENT, self.env_id
                )
                await collector.record_client_connected(client_info)

        @self.client.event("disconnected")
        async def on_disconnected():
            self.logger.info("📡 与 Hub 断开连接")
            self.running = False

        @self.client.event("agent_joined")
        async def on_agent_joined(event: EventMessage):
            agent_id = event.data.get("agent_id")
            self.logger.info(f"🤖 {agent_id} Agent 已加入 ")

            # 添加 Agent 到世界
            position = self.world.add_agent(agent_id)
            self.connected_agents[agent_id] = {
                "connected_at": time.time(),
                "position": position,
                "actions": 0,
            }

            # 发送欢迎消息
            welcome_msg = ActionMessage(
                action="welcome",
                parameters={
                    "message": f"欢迎来到世界 {self.env_id}！",
                    "world_size": self.world_size,
                    "start_position": position,
                    "world_state": self.world.get_world_state(),
                },
            )
            await self.client.send_message(welcome_msg, agent_id)

            self.logger.info(f"   位置: {position}")
            self.logger.info(f"   活跃 Agent 数: {len(self.connected_agents)}")

        @self.client.event("agent_disconnected")
        async def on_agent_disconnected(agent_id: str):
            self.logger.info(f"👋 Agent 已断开: {agent_id}")

            # 从世界移除 Agent
            self.world.remove_agent(agent_id)
            agent_info = self.connected_agents.pop(agent_id, {})

            if agent_info:
                duration = time.time() - agent_info.get("connected_at", time.time())
                self.logger.info(f"   连接时长: {duration:.1f} 秒")
                self.logger.info(f"   执行动作: {agent_info.get('actions', 0)}")

        @self.client.event("agent_dialog")
        async def on_agent_dialog(event: EventMessage):
            """监听并抄送 Agent 对话事件"""
            self.logger.info(f"🔍 [DEBUG] 收到 agent_dialog 事件: {event}")

            dialog_data = event.data
            from_agent = dialog_data.get("from_agent", "unknown")
            target_agent = dialog_data.get("target_agent", "unknown")
            message = dialog_data.get("message", "")
            topic = dialog_data.get("topic", "")
            conversation_id = dialog_data.get("conversation_id", "")

            # 抄送Agent对话信息到环境日志
            topic_info = f" (主题: {topic})" if topic else ""
            self.logger.info(
                f"💬 [对话抄送] {from_agent} → {target_agent}{topic_info}: {message}"
            )
            self.logger.debug(f"   对话ID: {conversation_id}")

            # 记录对话统计
            if hasattr(self, "dialog_count"):
                self.dialog_count += 1
            else:
                self.dialog_count = 1

    async def _handle_agent_action(self, agent_id: str, action: ActionMessage) -> None:
        """处理 Agent 动作"""
        self.action_count += 1

        if agent_id in self.connected_agents:
            self.connected_agents[agent_id]["actions"] += 1

        self.logger.debug(f"🎯 处理 {agent_id} 的动作: {action.action}")

        try:
            result = None

            # 处理不同类型的动作
            if action.action == "move":
                direction = action.parameters.get("direction")
                result = self.world.move_agent(agent_id, direction)

                if result.get("success"):
                    self.logger.info(f"   {agent_id} 移动到 {result['new_position']}")
                    if "collected_item" in result:
                        item = result["collected_item"]
                        self.logger.info(f"   🎁 {agent_id} 收集了 {item['type']}")
                else:
                    self.logger.info(
                        f"   ❌ {agent_id} 移动失败: {result.get('reason', 'Unknown')}"
                    )

            elif action.action == "look":
                view_range = action.parameters.get("range", 2)
                result = self.world.get_agent_view(agent_id, view_range)
                self.logger.debug(f"   {agent_id} 查看周围 (范围: {view_range})")

            elif action.action == "get_world_state":
                result = self.world.get_world_state()
                self.logger.debug(f"   {agent_id} 获取世界状态")

            elif action.action == "ping":
                result = {
                    "success": True,
                    "pong": True,
                    "timestamp": time.time(),
                    "server_info": {
                        "env_id": self.env_id,
                        "world_size": self.world_size,
                        "active_agents": len(self.connected_agents),
                    },
                }
                self.logger.debug(f"   {agent_id} ping")

            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action.action}",
                    "available_actions": ["move", "look", "get_world_state", "ping"],
                }
                self.logger.warning(f"   ❓ {agent_id} 未知动作: {action.action}")

            # 发送结果
            if result:
                response = ActionMessage(
                    action="action_result",
                    parameters={
                        "request_action": action.action,
                        "result": result,
                        "timestamp": time.time(),
                    },
                )
                await self.client.send_message(response, agent_id)

            # 记录监控指标
            if self.monitor:
                collector = self.monitor.get_collector()
                await collector.record_custom_metric(
                    "counter",
                    "actions_processed",
                    1.0,
                    {
                        "action": action.action,
                        "agent": agent_id,
                        "success": str(result.get("success", False)),
                    },
                )

        except Exception as e:
            self.logger.error(f"❌ 处理动作失败: {e}")

            # 发送错误响应
            error_response = ActionMessage(
                action="error",
                parameters={
                    "message": f"Action processing failed: {str(e)}",
                    "request_action": action.action,
                },
            )
            await self.client.send_message(
                error_response,
                agent_id,
            )

    async def _auto_event_loop(self) -> None:
        """自动事件循环"""
        self.logger.info("🔄 自动事件循环已启动")

        while self.running:
            try:
                await asyncio.sleep(random.uniform(5.0, 15.0))  # 5-15秒间隔

                if not self.running or not self.connected_agents:
                    continue

                # 推进世界回合
                events = self.world.advance_turn()

                # 广播世界事件
                for event in events:
                    self.event_count += 1
                    event_msg = ActionMessage(action="world_event", parameters=event)

                    # 广播给所有 Agent
                    for agent_id in self.connected_agents:
                        await self.client.send_message(
                            event_msg,
                            agent_id,
                        )

                    self.logger.info(f"📡 广播世界事件: {event['type']}")

                # 记录监控指标
                if self.monitor and events:
                    collector = self.monitor.get_collector()
                    await collector.record_custom_metric(
                        "counter",
                        "world_events_total",
                        len(events),
                        {"turn": str(self.world.turn)},
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"❌ 自动事件循环错误: {e}")

        self.logger.info("🔄 自动事件循环已停止")

    async def _run_loop(self) -> None:
        """主运行循环"""
        while self.running:
            try:
                await asyncio.sleep(1.0)

                # 定期显示状态
                if self.action_count > 0 and self.action_count % 10 == 0:
                    self.logger.info(
                        f"📊 状态更新 - 活跃 Agent: {len(self.connected_agents)}, 处理动作: {self.action_count}, 世界事件: {self.event_count}"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"❌ 运行循环错误: {e}")

    def _show_summary(self) -> None:
        """显示运行摘要"""
        self.logger.info("📋 环境运行摘要:")
        self.logger.info(f"   处理动作总数: {self.action_count}")
        self.logger.info(f"   世界事件总数: {self.event_count}")
        self.logger.info(f"   Agent对话数: {getattr(self, 'dialog_count', 0)}")
        self.logger.info(f"   当前世界回合: {self.world.turn}")
        self.logger.info(f"   世界物品数: {len(self.world.items)}")

        if self.connected_agents:
            self.logger.info(f"   活跃 Agent: {len(self.connected_agents)}")
            for agent_id, info in self.connected_agents.items():
                self.logger.info(f"     {agent_id}: {info['actions']} 动作")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Star Protocol V3 Environment 演示")
    parser.add_argument(
        "--hub-url",
        default="ws://localhost:8000",
        help="Hub 服务器地址 (默认: ws://localhost:8000)",
    )
    parser.add_argument("--env-id", default="world_1", help="环境 ID (默认: world_1)")
    parser.add_argument(
        "--world-size", type=int, default=10, help="世界大小 (默认: 10)"
    )
    parser.add_argument(
        "--no-auto-events", action="store_true", help="禁用自动世界事件"
    )
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

    # 创建并启动环境演示
    demo = EnvironmentDemo(
        env_id=args.env_id,
        hub_url=args.hub_url,
        world_size=args.world_size,
        auto_events=not args.no_auto_events,
        enable_monitoring=not args.no_monitoring,
        interactive=not args.no_interactive,
        log_level=args.log_level,
    )

    try:
        await demo.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ Environment 演示失败: {e}")
        return 1
    finally:
        await demo.stop()

    return 0


if __name__ == "__main__":
    # 在 Windows 上设置事件循环策略以避免一些问题
    if platform.system() == "Windows":
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
        print("\n👋 Environment 演示已停止")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 程序异常退出: {e}")
        sys.exit(1)
