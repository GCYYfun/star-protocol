#!/usr/bin/env python3
"""
Star Protocol Environment 演示

创建一个简单的2D世界环境，支持Agent移动、观察和交互
"""

import asyncio
import logging
import random
import signal
import sys
import platform
from typing import Dict, List, Any, Optional
from star_protocol.client import EnvironmentClient
from star_protocol.protocol import Message
from star_protocol.utils.logger import setup_logging
from star_protocol.monitor.simple_monitor import get_monitor, set_rich_mode


class SimpleWorld:
    """简单的2D世界环境"""

    def __init__(self, width: int = 10, height: int = 10):
        self.width = width
        self.height = height
        self.agents: Dict[str, Dict[str, Any]] = {}  # agent_id -> agent_state
        self.items: Dict[str, Dict[str, Any]] = {}  # item_id -> item_state
        self.world_time = 0

        # 初始化一些物品
        self._initialize_world()

    def _initialize_world(self):
        """初始化世界内容"""
        # 随机放置一些物品
        items = ["apple", "sword", "shield", "potion", "key"]
        for i, item_type in enumerate(items):
            item_id = f"item_{i}"
            self.items[item_id] = {
                "id": item_id,
                "type": item_type,
                "position": {
                    "x": random.randint(0, self.width - 1),
                    "y": random.randint(0, self.height - 1),
                },
                "properties": {"value": random.randint(10, 100)},
            }

    def add_agent(self, agent_id: str) -> Dict[str, Any]:
        """添加Agent到世界"""
        if agent_id not in self.agents:
            self.agents[agent_id] = {
                "id": agent_id,
                "position": {
                    "x": random.randint(0, self.width - 1),
                    "y": random.randint(0, self.height - 1),
                },
                "health": 100,
                "energy": 100,
                "inventory": [],
                "score": 0,
            }
        return self.agents[agent_id]

    def remove_agent(self, agent_id: str):
        """从世界中移除Agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]

    def process_action(
        self, agent_id: str, action: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理Agent动作"""
        if agent_id not in self.agents:
            return {"status": "error", "message": "Agent not found"}

        agent = self.agents[agent_id]

        if action == "move":
            return self._process_move(agent, parameters)
        elif action == "observe":
            return self._process_observe(agent, parameters)
        elif action == "pickup":
            return self._process_pickup(agent, parameters)
        elif action == "ping":
            return {
                "status": "success",
                "message": "pong",
                "timestamp": self.world_time,
            }
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}

    def _process_move(
        self, agent: Dict[str, Any], parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理移动动作"""
        direction = parameters.get("direction", "north")
        distance = parameters.get("distance", 1)

        old_pos = agent["position"].copy()
        new_pos = old_pos.copy()

        # 计算新位置
        if direction == "north":
            new_pos["y"] = max(0, new_pos["y"] - distance)
        elif direction == "south":
            new_pos["y"] = min(self.height - 1, new_pos["y"] + distance)
        elif direction == "east":
            new_pos["x"] = min(self.width - 1, new_pos["x"] + distance)
        elif direction == "west":
            new_pos["x"] = max(0, new_pos["x"] - distance)

        # 更新位置
        agent["position"] = new_pos
        agent["energy"] -= 1  # 移动消耗能量

        return {
            "status": "success",
            "message": f"Moved {direction}",
            "data": {
                "old_position": old_pos,
                "new_position": new_pos,
                "energy_cost": 1,
                "remaining_energy": agent["energy"],
            },
        }

    def _process_observe(
        self, agent: Dict[str, Any], parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理观察动作"""
        range_limit = parameters.get("range", 2)
        agent_pos = agent["position"]

        # 查找范围内的物品
        nearby_items = []
        for item_id, item in self.items.items():
            item_pos = item["position"]
            distance = abs(item_pos["x"] - agent_pos["x"]) + abs(
                item_pos["y"] - agent_pos["y"]
            )
            if distance <= range_limit:
                nearby_items.append(
                    {
                        "id": item_id,
                        "type": item["type"],
                        "position": item_pos,
                        "distance": distance,
                    }
                )

        # 查找范围内的其他Agent
        nearby_agents = []
        for other_id, other_agent in self.agents.items():
            if other_id != agent["id"]:
                other_pos = other_agent["position"]
                distance = abs(other_pos["x"] - agent_pos["x"]) + abs(
                    other_pos["y"] - agent_pos["y"]
                )
                if distance <= range_limit:
                    nearby_agents.append(
                        {"id": other_id, "position": other_pos, "distance": distance}
                    )

        return {
            "status": "success",
            "message": "Observation complete",
            "data": {
                "current_position": agent_pos,
                "nearby_items": nearby_items,
                "nearby_agents": nearby_agents,
                "world_size": {"width": self.width, "height": self.height},
            },
        }

    def _process_pickup(
        self, agent: Dict[str, Any], parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理拾取动作"""
        item_id = parameters.get("item_id")
        if not item_id:
            return {"status": "error", "message": "Missing item_id parameter"}

        if item_id not in self.items:
            return {"status": "error", "message": "Item not found"}

        item = self.items[item_id]
        agent_pos = agent["position"]
        item_pos = item["position"]

        # 检查距离
        distance = abs(item_pos["x"] - agent_pos["x"]) + abs(
            item_pos["y"] - agent_pos["y"]
        )
        if distance > 1:
            return {"status": "error", "message": "Item too far away"}

        # 拾取物品
        agent["inventory"].append(item.copy())
        agent["score"] += item["properties"].get("value", 10)
        del self.items[item_id]

        return {
            "status": "success",
            "message": f"Picked up {item['type']}",
            "data": {
                "item": item,
                "new_score": agent["score"],
                "inventory_size": len(agent["inventory"]),
            },
        }

    def get_world_state(self) -> Dict[str, Any]:
        """获取世界状态"""
        return {
            "time": self.world_time,
            "size": {"width": self.width, "height": self.height},
            "agents_count": len(self.agents),
            "items_count": len(self.items),
            "agents": list(self.agents.values()),
            "items": list(self.items.values()),
        }


class EnvironmentDemo:
    """Environment演示类"""

    def __init__(self, env_id: str = "demo_world", port: int = 9999):
        self.env_id = env_id
        self.port = port
        self.client = EnvironmentClient(
            env_id=env_id, port=port, validate_messages=True
        )
        self.world = SimpleWorld()
        self.running = False

        # 设置monitor
        set_rich_mode()
        self.monitor = get_monitor(f"environment_{env_id}")

        # 设置消息处理器
        self.setup_handlers()

    def setup_handlers(self):
        """设置消息处理器"""

        # 设置外层协议处理器
        @self.client.on_message()
        async def handle_message(message: Message):
            """处理message协议 - 分发到内层处理器"""
            try:
                payload = message.payload

                # 获取内层消息类型
                message_type = None
                if isinstance(payload, dict):
                    message_type = payload.get("type")
                elif hasattr(payload, "type"):
                    message_type = payload.type

                if message_type == "action":
                    await self.handle_action(message)
                elif message_type == "event":
                    await self.handle_event(message)
                elif message_type == "outcome":
                    # Environment通常不处理outcome消息，但可以记录
                    self.monitor.debug(f"Received outcome message: {payload}")
                elif message_type == "stream":
                    # 处理流消息
                    self.monitor.debug(f"Received stream message: {payload}")
                else:
                    self.monitor.warning(f"Unknown inner message type: {message_type}")

            except Exception as e:
                self.monitor.error(f"Error handling message: {e}")

        @self.client.on_error()
        async def handle_error(message: Message):
            """处理error协议"""
            self.monitor.error(f"Received error: {message.payload}")

        @self.client.on_heartbeat()
        async def handle_heartbeat(message: Message):
            """处理heartbeat协议"""
            self.monitor.debug("Received heartbeat")

    async def handle_action(self, message: Message):
        """处理Agent动作"""
        payload = message.payload
        agent_id = message.sender.id
        action = payload.get("action")
        action_id = payload.get("id")
        parameters = payload.get("parameters", {})

        self.monitor.info(f"Processing action '{action}' from agent {agent_id}")

        # 确保Agent在世界中
        if agent_id not in self.world.agents:
            agent_state = self.world.add_agent(agent_id)
            await self.client.send_agent_joined(agent_id, agent_state)

        # 处理动作
        result = self.world.process_action(agent_id, action, parameters)

        # 发送结果
        await self.client.send_outcome(
            agent_id=agent_id, action_id=action_id, outcome=result, outcome_type="dict"
        )

        # 如果是移动，广播位置变化事件
        if action == "move" and result["status"] == "success":
            await self.client.send_event(
                "agent_moved",
                {
                    "agent_id": agent_id,
                    "old_position": result["data"]["old_position"],
                    "new_position": result["data"]["new_position"],
                },
            )

        # 如果是拾取，广播物品被拾取事件
        if action == "pickup" and result["status"] == "success":
            await self.client.send_event(
                "item_picked_up", {"agent_id": agent_id, "item": result["data"]["item"]}
            )

    async def handle_event(self, message: Message):
        """处理事件消息"""
        payload = message.payload
        event_type = payload.get("event")

        if event_type == "dialogue":
            # 转发对话消息
            from_agent = payload["data"].get("from_agent")
            self.monitor.info(
                f"Dialogue from {from_agent}: {payload['data'].get('message')}"
            )

    async def start(self):
        """启动Environment"""
        self.monitor.info(f"🌍 启动环境: {self.env_id}")
        self.monitor.info(f"📍 连接地址: ws://localhost:{self.port}/env/{self.env_id}")
        self.monitor.set_status("连接中")

        # 连接到Hub
        success = await self.client.connect()
        if not success:
            self.monitor.error("❌ 连接失败!")
            return

        self.monitor.success("✅ 环境连接成功!")
        self.monitor.info(f"🗺️  世界大小: {self.world.width}x{self.world.height}")
        self.monitor.info(f"📦 初始物品数量: {len(self.world.items)}")
        self.monitor.info("💡 等待Agent连接...")
        self.monitor.set_status("运行中")

        self.running = True

        # 启动世界更新循环
        world_update_task = asyncio.create_task(self.world_update_loop())

        try:
            # 等待中断信号 - 跨平台处理
            stop_event = asyncio.Event()

            def signal_handler():
                self.monitor.warning("\n📴 收到停止信号...")
                stop_event.set()

            # 跨平台信号处理
            loop = asyncio.get_event_loop()
            if platform.system() == "Windows":
                # Windows 系统只支持 SIGINT (Ctrl+C)
                try:
                    loop.add_signal_handler(signal.SIGINT, signal_handler)
                except NotImplementedError:
                    # 如果不支持信号处理，依赖 KeyboardInterrupt
                    self.monitor.debug("Windows: 使用 KeyboardInterrupt 处理停止信号")
            else:
                # Unix-like 系统 (Linux, macOS, etc.)
                loop.add_signal_handler(signal.SIGINT, signal_handler)
                loop.add_signal_handler(signal.SIGTERM, signal_handler)

            await stop_event.wait()

        finally:
            self.running = False

            # 清理信号处理器
            try:
                if platform.system() != "Windows":
                    loop.remove_signal_handler(signal.SIGINT)
                    loop.remove_signal_handler(signal.SIGTERM)
            except Exception:
                pass

            world_update_task.cancel()
            await self.client.disconnect()
            self.monitor.success("✅ 环境已停止")
            self.monitor.set_status("已停止")

    async def world_update_loop(self):
        """世界更新循环"""
        try:
            while self.running:
                await asyncio.sleep(30)  # 每30秒发送一次世界状态

                if self.world.agents:  # 只有当有Agent时才发送
                    world_state = self.world.get_world_state()
                    await self.client.send_event("world_update", world_state)

                    self.monitor.info(
                        f"World update: {len(self.world.agents)} agents, "
                        f"{len(self.world.items)} items"
                    )

                self.world.world_time += 1

        except asyncio.CancelledError:
            pass


async def main():
    """主函数"""
    import argparse

    # 命令行参数
    parser = argparse.ArgumentParser(description="Star Protocol Environment Demo")
    parser.add_argument("--env-id", default="demo_world", help="Environment ID")
    parser.add_argument("--port", type=int, default=9999, help="Hub server port")

    args = parser.parse_args()

    # 设置日志
    setup_logging("INFO")

    monitor = get_monitor("environment_demo")
    monitor.success("=" * 50)
    monitor.success("🌍 Star Protocol Environment Demo")
    monitor.success("=" * 50)

    # 创建并启动环境
    demo = EnvironmentDemo(args.env_id, args.port)
    await demo.start()


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
        asyncio.run(main())
    except KeyboardInterrupt:
        monitor = get_monitor("environment_demo")
        monitor.info("\n👋 再见!")
    except Exception as e:
        monitor = get_monitor("environment_demo")
        monitor.error(f"❌ 程序异常退出: {e}")
        sys.exit(1)
