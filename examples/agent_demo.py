#!/usr/bin/env python3
"""
Agent 客户端示例

这个示例展示如何创建和运行一个智能体客户端，包括：
- 连接到 Hub 服务器
- 与环境交互
- 执行智能决策
- 处理环境事件
- 监控和日志记录
"""

import asyncio
import argparse
import json
import random
import sys
import time
import traceback
import platform
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from menglong import Model, TaskAgent
from menglong.ml_model.schema.ml_request import (
    UserMessage as user,
    AssistantMessage as assistant,
)

from menglong.agents.component.tool_manager import tool, ToolInfo

from star_protocol.protocol.messages import OutcomeMessage

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from star_protocol.cli.interactive_cli import command_with_args
from star_protocol.client import AgentClient
from star_protocol.protocol import (
    ActionMessage,
    ClientInfo,
    ClientType,
    EventMessage,
)
from star_protocol.monitor import create_simple_monitor
from star_protocol.utils import get_logger
from star_protocol.cli import create_agent_cli
from star_protocol.protocol import EventMessage


# ========== 全局命令定义（在类外部）==========
@command_with_args(
    name="chat",
    description="与 LLM Agent 聊天",
    expected_args=None,  # 允许可变参数
    usage="chat <prompt>",
)
async def agent_chat_command(cli, args):
    """聊天命令实现"""
    try:
        # 从CLI上下文获取当前的agent实例
        agent_demo = cli.get_context("agent_demo")
        if not agent_demo:
            cli.console.print("❌ 无法找到 Agent 实例")
            return

        if not agent_demo.llm_agent:
            cli.console.print("❌ 当前 Agent 不是 LLM 类型，无法聊天")
            return

        if len(args) < 1:
            cli.console.print("❌ 请提供要聊天的内容")
            cli.console.print("用法: agent_chat <prompt>")
            return

        prompt = " ".join(args)  # 合并所有参数为一个提示
        cli.console.print(f"💭 您的问题: {prompt}")

        # 调用同步的 chat 方法
        response = await agent_demo.llm_agent.chat(prompt)
        cli.console.print(f"🤖 AI 回复: {response}")

    except Exception as e:
        traceback.print_exc()
        cli.console.print(f"❌ 聊天失败: {e}")


@command_with_args(
    name="move",
    description="移动智能体",
    expected_args=None,  # 允许可变参数
    usage="move <direction>",
)
async def agent_move_command(cli, args):
    """移动命令实现"""
    try:
        # 从CLI上下文获取当前的agent实例
        agent_demo: AgentDemo = cli.get_context("agent_demo")
        if not agent_demo:
            cli.console.print("❌ 无法找到 Agent 实例")
            return

        if not agent_demo.llm_agent:
            cli.console.print("❌ 当前 Agent 不是 LLM 类型，无法聊天")
            return

        if len(args) < 1:
            cli.console.print("❌ 请提供要聊天的内容")
            cli.console.print("用法: agent_chat <prompt>")
            return

        direction = " ".join(args)  # 合并所有参数为一个提示
        cli.console.print(f"🚶 移动方向: {direction}")

        param = {"direction": direction}

        # 调用同步的 chat 方法
        response = await agent_demo.perform_action("move", param)
        cli.console.print(f"🤖 AI 回复: {response}")

    except Exception as e:
        traceback.print_exc()
        cli.console.print(f"❌ 聊天失败: {e}")


@command_with_args(
    name="dialog",
    description="与指定对象发起主题对话",
    expected_args=None,  # 允许可变参数
    usage="dialog <who> <topic>",
)
async def agent_dialog_command(cli, args):
    """主题对话命令实现"""
    try:
        # 从CLI上下文获取当前的agent实例
        agent_demo = cli.get_context("agent_demo")
        if not agent_demo:
            cli.console.print("❌ 无法找到 Agent 实例")
            return

        if not agent_demo.llm_agent:
            cli.console.print("❌ 当前 Agent 不是 LLM 类型，无法发起对话")
            return

        if len(args) < 2:
            cli.console.print("❌ 请提供对话对象和主题")
            cli.console.print("用法: dialog <who> <topic>")
            cli.console.print("示例: dialog agent_123 天气")
            cli.console.print("示例: dialog npc_guard 任务")
            return

        who = args[0]
        topic = " ".join(args[1:])  # 合并所有参数为一个主题
        cli.console.print(f"🎯 发起主题对话 - 对象: {who}, 主题: {topic}")

        # 调用 dialog 方法发起主题对话
        response = await agent_demo.dialog(who, topic)
        cli.console.print(f"📤 {response}")

    except Exception as e:
        traceback.print_exc()
        cli.console.print(f"❌ 发起对话失败: {e}")


@command_with_args(
    name="task",
    description="规划执行任务",
    expected_args=None,  # 允许可变参数
    usage="task <task_desc>",
)
async def agent_task_command(cli, args):
    """任务命令实现"""
    try:
        # 从CLI上下文获取当前的agent实例
        agent_demo = cli.get_context("agent_demo")
        if not agent_demo:
            cli.console.print("❌ 无法找到 Agent 实例")
            return

        if not agent_demo.llm_agent:
            cli.console.print("❌ 当前 Agent 不是 LLM 类型，无法发起对话")
            return

        if len(args) < 1:
            cli.console.print("❌ 请提供任务描述")
            cli.console.print("用法: task <task_desc>")
            return

        task_desc = (
            " ".join(args) + ",输出[DONE] 停止对话."
        )  # 合并所有参数为一个任务描述
        cli.console.print(f"🎯 规划执行任务: {task_desc}")

        try:
            # 调用 task 方法规划执行任务
            response = await agent_demo.task(task_desc)
            cli.console.print(f"📤 {response}")
            return
        except Exception as inner_e:
            print(f"💥 任务命令执行异常: {type(inner_e).__name__}: {inner_e}")
            traceback.print_exc()
            cli.console.print(f"❌ 任务执行失败: {inner_e}")
            return

    except Exception as e:
        traceback.print_exc()
        cli.console.print(f"❌ 发起对话失败: {e}")


@command_with_args(
    name="agent_status",
    description="查看 Agent 当前状态",
    expected_args=0,
    usage="agent_status",
)
async def agent_status_command(cli, args):
    """状态查看命令实现"""
    try:
        # 从CLI上下文获取当前的agent实例
        agent_demo = cli.get_context("agent_demo")
        if not agent_demo:
            cli.console.print("❌ 无法找到 Agent 实例")
            return

        status = agent_demo.ai.get_status()

        cli.console.print("📊 Agent 状态:")
        cli.console.print(f"   位置: {status['position']}")
        cli.console.print(f"   背包物品: {status['inventory_count']}")
        cli.console.print(f"   执行动作: {status['actions_taken']}")
        cli.console.print(f"   成功移动: {status['successful_moves']}")
        cli.console.print(f"   失败移动: {status['failed_moves']}")
        cli.console.print(f"   成功率: {status['success_rate']:.1%}")
        cli.console.print(f"   当前目标: {status['current_goal']}")
        cli.console.print(f"   探索策略: {status['exploration_strategy']}")
        cli.console.print(f"   风险容忍度: {status['risk_tolerance']:.1f}")
        cli.console.print(f"   世界知识: {status['world_knowledge_size']} 个位置")

        if hasattr(agent_demo, "chat_partners") and agent_demo.chat_partners:
            cli.console.print(f"   聊天伙伴: {', '.join(agent_demo.chat_partners)}")

        # 如果是 LLM Agent，显示更多信息
        if agent_demo.llm_agent:
            summary = agent_demo.llm_agent.get_conversation_summary()
            cli.console.print(f"   LLM 可用: {summary['llm_available']}")
            cli.console.print(f"   对话消息: {summary['total_messages']} 条")

    except Exception as e:
        traceback.print_exc()
        cli.console.print(f"❌ 获取状态失败: {e}")


# ========== 全局命令定义（在类外部）==========


# ========== Agent ==========


class LLMAgent:
    """基于大语言模型的智能 Agent"""

    def __init__(self, agent_id: str, personality: str = "friendly"):
        self.agent_id = agent_id
        self.personality = personality
        self.conversation_history: List[Dict[str, str]] = []
        self.other_agents: List[str] = []

        self.agent = TaskAgent()

        self.context = []

        # 先初始化 logger
        self.logger = get_logger(f"llm_agent_{agent_id}")

    async def chat(self, message: str) -> str:
        """与 Agent 进行对话"""
        self.context.append(user(content=message))

        # 构建对话上下文
        messages = self.context

        # 调用 LLM 生成回复
        response = await self.agent.chat(messages)

        self.context.append(assistant(content=response))
        return response

    # async def task(self, task_desc: str) -> str:
    #     """规划并执行任务"""
    #     # 调用 LLM 生成任务规划
    #     res = await self.agent.task(task=task_desc, tools=[available_actions])

    def get_conversation_summary(self) -> Dict[str, Any]:
        """获取对话摘要"""
        return {
            "llm_available": True,
            "total_messages": len(self.context),
            "other_agents": self.other_agents,
        }


class SimpleAI:
    """简单的 AI 决策系统"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.position: Optional[Tuple[int, int]] = None
        self.world_size: Optional[int] = None
        self.inventory: List[Dict[str, Any]] = []
        self.world_knowledge: Dict[str, Any] = {}
        self.goals: List[str] = ["explore", "collect_items", "avoid_obstacles"]
        self.current_goal = "explore"
        self.exploration_targets: List[Tuple[int, int]] = []
        self.visited_positions: List[Tuple[int, int]] = []

        # 行为策略
        self.exploration_strategy = (
            "random_walk"  # "random_walk", "systematic", "target_based"
        )
        self.risk_tolerance = 0.7  # 0.0 = 极度谨慎, 1.0 = 极度冒险
        self.cooperation_level = 0.5  # 与其他 Agent 的合作程度

        # 统计信息
        self.actions_taken = 0
        self.items_collected = 0
        self.successful_moves = 0
        self.failed_moves = 0

    def update_position(self, new_position: Tuple[int, int]) -> None:
        """更新位置"""
        if self.position:
            self.visited_positions.append(self.position)
        self.position = new_position

    def add_to_inventory(self, item: Dict[str, Any]) -> None:
        """添加物品到背包"""
        self.inventory.append(item)
        self.items_collected += 1

    def update_world_knowledge(self, view_data: Dict[str, Any]) -> None:
        """更新世界知识"""
        if "visible_area" in view_data:
            for pos in view_data["visible_area"]:
                if pos not in self.world_knowledge:
                    self.world_knowledge[str(pos)] = {"visited": False, "safe": True}

        # 更新障碍物信息
        if "nearby_obstacles" in view_data:
            for obstacle_pos in view_data["nearby_obstacles"]:
                self.world_knowledge[str(obstacle_pos)] = {
                    "obstacle": True,
                    "safe": False,
                }

        # 更新物品信息
        if "nearby_items" in view_data:
            for item in view_data["nearby_items"]:
                pos_key = str(item["position"])
                if pos_key not in self.world_knowledge:
                    self.world_knowledge[pos_key] = {}
                self.world_knowledge[pos_key]["has_item"] = item["type"]

    def decide_next_action(self) -> Dict[str, Any]:
        """决定下一个动作"""
        self.actions_taken += 1

        # 如果没有位置信息，先查看周围
        if self.position is None:
            return {"action": "look", "parameters": {"range": 3}}

        # 根据当前目标决定动作
        if self.current_goal == "explore":
            return self._decide_exploration_action()
        elif self.current_goal == "collect_items":
            return self._decide_collection_action()
        elif self.current_goal == "avoid_obstacles":
            return self._decide_avoidance_action()
        else:
            return self._decide_random_action()

    def _decide_exploration_action(self) -> Dict[str, Any]:
        """决定探索动作"""
        if self.exploration_strategy == "random_walk":
            # 随机游走，但避免重复访问
            directions = ["north", "south", "east", "west"]

            # 优先选择未访问的方向
            preferred_directions = []
            for direction in directions:
                next_pos = self._get_next_position(direction)
                if next_pos not in self.visited_positions:
                    preferred_directions.append(direction)

            if preferred_directions:
                direction = random.choice(preferred_directions)
            else:
                direction = random.choice(directions)

            return {"action": "move", "parameters": {"direction": direction}}

        elif self.exploration_strategy == "systematic":
            # 系统性探索（简化版本）
            if not self.exploration_targets:
                self._generate_exploration_targets()

            if self.exploration_targets:
                target = self.exploration_targets[0]
                direction = self._get_direction_to_target(target)
                return {"action": "move", "parameters": {"direction": direction}}

        # 默认随机移动
        return {
            "action": "move",
            "parameters": {
                "direction": random.choice(["north", "south", "east", "west"])
            },
        }

    def _decide_collection_action(self) -> Dict[str, Any]:
        """决定收集动作"""
        # 查看周围是否有物品
        return {"action": "look", "parameters": {"range": 2}}

    def _decide_avoidance_action(self) -> Dict[str, Any]:
        """决定避险动作"""
        # 简单的避险策略：远离已知的危险区域
        safe_directions = []
        for direction in ["north", "south", "east", "west"]:
            next_pos = self._get_next_position(direction)
            pos_key = str(next_pos)
            if pos_key not in self.world_knowledge or self.world_knowledge[pos_key].get(
                "safe", True
            ):
                safe_directions.append(direction)

        if safe_directions:
            return {
                "action": "move",
                "parameters": {"direction": random.choice(safe_directions)},
            }
        else:
            # 没有安全方向，查看周围情况
            return {"action": "look", "parameters": {"range": 3}}

    def _decide_random_action(self) -> Dict[str, Any]:
        """随机动作"""
        actions = [
            {
                "action": "move",
                "parameters": {
                    "direction": random.choice(["north", "south", "east", "west"])
                },
            },
            {"action": "look", "parameters": {"range": random.randint(1, 3)}},
            {"action": "get_world_state", "parameters": {}},
            {"action": "ping", "parameters": {}},
        ]
        return random.choice(actions)

    def _get_next_position(self, direction: str) -> Tuple[int, int]:
        """计算指定方向的下一个位置"""
        if not self.position or not self.world_size:
            return (0, 0)

        x, y = self.position
        if direction == "north":
            return (x, max(0, y - 1))
        elif direction == "south":
            return (x, min(self.world_size - 1, y + 1))
        elif direction == "east":
            return (min(self.world_size - 1, x + 1), y)
        elif direction == "west":
            return (max(0, x - 1), y)
        else:
            return self.position

    def _get_direction_to_target(self, target: Tuple[int, int]) -> str:
        """计算到达目标的方向"""
        if not self.position:
            return "north"

        x, y = self.position
        target_x, target_y = target

        # 简单的方向选择
        if target_x > x:
            return "east"
        elif target_x < x:
            return "west"
        elif target_y > y:
            return "south"
        elif target_y < y:
            return "north"
        else:
            return random.choice(["north", "south", "east", "west"])

    def _generate_exploration_targets(self) -> None:
        """生成探索目标"""
        if not self.world_size:
            return

        # 生成一些探索点
        targets = []
        for _ in range(5):
            x = random.randint(0, self.world_size - 1)
            y = random.randint(0, self.world_size - 1)
            targets.append((x, y))

        self.exploration_targets = targets

    def process_action_result(self, result: Dict[str, Any]) -> None:
        """处理动作结果"""
        if result.get("success"):
            if "new_position" in result:
                self.update_position(result["new_position"])
                self.successful_moves += 1

            if "collected_item" in result:
                self.add_to_inventory(result["collected_item"])
        else:
            if "reason" in result:
                self.failed_moves += 1

    def adapt_strategy(self, performance_data: Dict[str, Any]) -> None:
        """根据性能调整策略"""
        success_rate = self.successful_moves / max(
            1, self.successful_moves + self.failed_moves
        )

        # 如果成功率低，变得更谨慎
        if success_rate < 0.5:
            self.risk_tolerance = max(0.1, self.risk_tolerance - 0.1)
            self.exploration_strategy = "systematic"
        elif success_rate > 0.8:
            # 如果成功率高，可以更冒险
            self.risk_tolerance = min(1.0, self.risk_tolerance + 0.1)

    def get_status(self) -> Dict[str, Any]:
        """获取 AI 状态"""
        return {
            "position": self.position,
            "inventory_count": len(self.inventory),
            "actions_taken": self.actions_taken,
            "items_collected": self.items_collected,
            "successful_moves": self.successful_moves,
            "failed_moves": self.failed_moves,
            "success_rate": self.successful_moves
            / max(1, self.successful_moves + self.failed_moves),
            "current_goal": self.current_goal,
            "exploration_strategy": self.exploration_strategy,
            "risk_tolerance": self.risk_tolerance,
            "world_knowledge_size": len(self.world_knowledge),
        }


class AgentDemo:
    """Agent 演示类"""

    def __init__(
        self,
        agent_id: str,
        env_id: str,
        hub_url: str,
        max_actions: int = 0,
        action_interval: float = 2.0,
        enable_monitoring: bool = True,
        interactive: bool = True,
        log_level: str = "INFO",
        agent_type: str = "llm",  # "simple" 或 "llm"
        personality: str = "friendly",  # LLM agent 的性格
        enable_chat: bool = True,  # 是否启用聊天功能
    ):
        self.agent_id = agent_id
        self.env_id = env_id
        self.hub_url = hub_url
        self.max_actions = max_actions
        self.action_interval = action_interval
        self.enable_monitoring = enable_monitoring
        self.interactive = interactive
        self.agent_type = agent_type
        self.personality = personality
        self.enable_chat = enable_chat

        # 设置日志
        self.logger = get_logger(f"agent_{agent_id}")

        # 创建 AI
        if agent_type == "llm":
            self.llm_agent = LLMAgent(agent_id, personality)
            self.ai = SimpleAI(agent_id)  # 仍然需要简单 AI 处理环境交互
            self.logger.info(f"🤖 创建 LLM Agent，性格: {personality}")
        else:
            self.ai = SimpleAI(agent_id)
            self.llm_agent = None

        # 创建客户端
        self.client: Optional[AgentClient] = None
        self.cli = None

        # 聊天相关
        self.chat_partners: List[str] = []
        self.last_chat_time = 0
        self.chat_interval = 10.0  # 聊天间隔

        # 对话管理
        self.conversations: Dict[str, Dict[str, Any]] = (
            {}
        )  # 对话会话管理 {conversation_id: {...}}
        self.active_conversations: Dict[str, str] = (
            {}
        )  # 与某人的活跃对话 {target: conversation_id}
        self.message_queue: asyncio.Queue = asyncio.Queue()  # 接收到的消息队列

        # 监控
        self.monitor = None
        if enable_monitoring:
            Path("./logs").mkdir(exist_ok=True)
            self.monitor = create_simple_monitor(
                export_interval=60.0,
                file_path=f"./logs/agent_{agent_id}.json",
                console_output=True,
            )

        # 状态
        self.running = False
        self.connected_to_env = False
        self.last_action_time = 0
        self.action_task: Optional[asyncio.Task] = None
        self.chat_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """启动 Agent"""
        try:
            self.logger.info(f"🤖 启动 Agent 演示: {self.agent_id}")
            self.logger.info(f"   Agent 类型: {self.agent_type}")
            if self.agent_type == "llm":
                self.logger.info(f"   性格: {self.personality}")
                self.logger.info(
                    f"   聊天功能: {'启用' if self.enable_chat else '禁用'}"
                )
            self.logger.info(f"   Hub 地址: {self.hub_url}")
            self.logger.info(f"   目标环境: {self.env_id}")
            self.logger.info(f"   动作间隔: {self.action_interval} 秒")
            self.logger.info(f"   交互模式: {'启用' if self.interactive else '禁用'}")
            if self.max_actions > 0:
                self.logger.info(f"   最大动作数: {self.max_actions}")

            # 启动监控
            if self.monitor:
                self.monitor.start()
                self.logger.info("📊 监控系统已启动")

            # 创建客户端
            self.client = AgentClient(
                agent_id=self.agent_id, env_id=self.env_id, hub_url=self.hub_url
            )

            # 创建交互式CLI（如果启用）
            if self.interactive:
                self.cli = create_agent_cli(self.client, f"Agent {self.agent_id}")

                # 设置CLI退出回调
                def on_cli_exit():
                    self.logger.info("CLI 退出，停止 Agent...")
                    self.running = False

                self._create_custom_commands()
                self.cli.set_exit_callback(on_cli_exit)

            # 注册事件处理器
            self._register_handlers()

            # 连接到 Hub
            await self.client.connect()
            self.running = True

            self.logger.info("✅ Agent 启动成功")

            if self.interactive:
                # 启动交互式CLI
                self.cli.start()
                self.logger.info("🎮 交互式命令行已启用")

                # 动态获取可用命令
                commands_str = self.cli.get_available_commands_str()
                self.logger.info(f"💡 可用命令: {commands_str}")
            else:
                self.logger.info("💡 正在连接到环境...")

            # 启动对话管理任务（如果启用）
            if self.enable_chat and self.llm_agent:
                self.chat_task = asyncio.create_task(self._chat_loop())
                self.logger.info("💬 对话管理系统已启动")

            # 保持运行
            await self._run_loop()

        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"❌ 启动 Agent 失败: {e}")
            raise

    async def stop(self) -> None:
        """停止 Agent"""
        if not self.running:
            return

        self.logger.info("🛑 正在停止 Agent...")
        self.running = False

        # 停止交互式CLI
        if self.cli:
            self.cli.stop()
            self.logger.info("🎮 交互式命令行已停止")

        # 停止对话管理任务
        if self.chat_task:
            self.chat_task.cancel()
            try:
                await self.chat_task
            except asyncio.CancelledError:
                pass
            self.logger.info("💬 对话管理系统已停止")

        # 停止动作任务
        if self.action_task:
            self.action_task.cancel()
            try:
                await self.action_task
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

    def _create_custom_commands(self):
        """创建自定义 CLI 命令"""

        # 将自己添加到CLI上下文中，供全局命令使用
        if hasattr(self, "cli") and self.cli:
            self.cli.update_context("agent_demo", self)

        # 注意：全局装饰器命令已经自动注册
        # agent_chat_command 和 agent_status_command 已经通过装饰器注册

    def _register_handlers(self) -> None:
        """注册事件处理器"""

        @self.client.event("connected")
        async def on_connected(event: EventMessage):
            self.logger.info(f"🔗 已连接到 Hub , {event.data}")

            # 记录监控指标
            if self.monitor:
                collector = self.monitor.get_collector()
                client_info = ClientInfo(self.agent_id, ClientType.AGENT, self.env_id)
                await collector.record_client_connected(client_info)

        @self.client.event("disconnected")
        async def on_disconnected(event: EventMessage):
            self.logger.info("📡 与 Hub 断开连接")
            self.running = False

        @self.client.event("agent_dialog")
        async def on_agent_dialog(event: EventMessage):
            """处理接收到的对话事件"""
            try:
                dialog_data = event.data
                # 只处理发给自己且不是自己发送的消息
                if (
                    dialog_data.get("target_agent") == self.agent_id
                    and dialog_data.get("from_agent") != self.agent_id
                ):
                    # 将消息放入队列，由chat_loop处理
                    await self.message_queue.put(dialog_data)
                    self.logger.debug(
                        f"📥 收到来自 {dialog_data.get('from_agent')} 的对话消息，已加入处理队列"
                    )
            except Exception as e:
                traceback.print_exc()
                self.logger.error(f"❌ 处理对话事件失败: {e}")

        @self.client.event("chat")
        async def on_chat(event: EventMessage):
            """处理传统聊天消息（兼容性）"""
            try:
                chat_data = event.data
                # 只处理发给自己且不是自己发送的消息
                if (
                    chat_data.get("target_agent") == self.agent_id
                    and chat_data.get("from_agent") != self.agent_id
                ):
                    # 转换为对话格式
                    dialog_data = {
                        "from_agent": chat_data.get("from_agent"),
                        "target_agent": self.agent_id,
                        "message": chat_data.get("message"),
                        "timestamp": time.time(),
                        "type": "chat",  # 标记为传统聊天
                    }
                    await self.message_queue.put(dialog_data)
                    self.logger.debug(
                        f"📥 收到来自 {chat_data.get('from_agent')} 的传统聊天消息，已转换为对话格式"
                    )
            except Exception as e:
                traceback.print_exc()
                self.logger.error(f"❌ 处理聊天事件失败: {e}")

        @self.client.outcome("move")
        async def on_action_outcome(message: OutcomeMessage):
            self.logger.info(f"🔔 动作结果: {message.outcome} - 结果: {message.data}")
            context_item = self.client.context.get_request_context(message.action_id)
            if context_item:
                context_item.future.set_result(message.data)
            await asyncio.sleep(0)  # Yield control to the event loop

    async def _run_loop(self) -> None:
        """主运行循环"""
        while self.running:
            try:
                await asyncio.sleep(5.0)

                # 定期显示 AI 状态
                if self.connected_to_env:
                    status = self.ai.get_status()
                    self.logger.debug(
                        f"🧠 AI 状态: 目标={status['current_goal']}, 策略={status['exploration_strategy']}, 风险容忍度={status['risk_tolerance']:.1f}"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                traceback.print_exc()
                self.logger.error(f"❌ 运行循环错误: {e}")

    def _show_summary(self) -> None:
        """显示运行摘要"""
        status = self.ai.get_status()

        self.logger.info("📋 Agent 运行摘要:")
        self.logger.info(f"   Agent 类型: {self.agent_type}")
        self.logger.info(f"   总动作数: {status['actions_taken']}")
        self.logger.info(f"   成功移动: {status['successful_moves']}")
        self.logger.info(f"   失败移动: {status['failed_moves']}")
        self.logger.info(f"   成功率: {status['success_rate']:.1%}")
        self.logger.info(f"   收集物品: {status['items_collected']}")
        self.logger.info(f"   最终位置: {status['position']}")
        self.logger.info(f"   世界知识: {status['world_knowledge_size']} 个位置")

        # 显示聊天摘要
        if self.llm_agent:
            chat_summary = self.llm_agent.get_conversation_summary()
            self.logger.info(f"   聊天伙伴: {len(self.chat_partners)} 个")
            self.logger.info(f"   LLM 对话消息: {chat_summary['total_messages']} 条")
            self.logger.info(f"   活跃对话数: {len(self.active_conversations)}")
            self.logger.info(f"   总对话会话: {len(self.conversations)}")
            if self.chat_partners:
                self.logger.info(f"   聊天对象: {', '.join(self.chat_partners)}")

    #  ---- Agent Action ----
    async def chat(self, message):
        await self.llm_agent.chat(message)

    async def task(self, task_desc):
        try:
            print(f"🎯 开始执行任务: {task_desc}")
            # 直接传递绑定的实例方法
            tools = [self.perform_action, self.available_actions]
            print(f"🔧 可用工具: {[tool.__name__ for tool in tools]}")

            # 添加详细的调试信息
            try:
                result = await self.llm_agent.agent.task(task_desc, tools=tools)
                print(f"✅ 任务执行完成: {result}")
                return result
            except Exception as inner_e:
                print(f"💥 LLM任务执行内部错误: {type(inner_e).__name__}: {inner_e}")
                traceback.print_exc()
                raise

        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"❌ 任务执行失败: {e}")
            raise

    async def dialog(self, who: str, topic: str) -> str:
        """发起主题对话

        Args:
            who: 对话接收方（向谁对话）
            topic: 对话主题（根据主题生成开场白）

        Returns:
            str: 发起状态信息
        """
        try:
            self.logger.info(f"🎯 发起主题对话 - 对象: {who}, 主题: {topic}")

            # 检查是否已有活跃对话
            conversation_id = self.active_conversations.get(who)
            if not conversation_id:
                # 创建新的对话会话
                conversation_id = f"conv_{self.agent_id}_{who}_{int(time.time())}"
                self.active_conversations[who] = conversation_id
                self.conversations[conversation_id] = {
                    "participants": [self.agent_id, who],
                    "topic": topic,  # 记录对话主题
                    "messages": [],
                    "created_at": time.time(),
                    "last_activity": time.time(),
                    "status": "active",
                }
                self.logger.info(
                    f"🆕 创建新对话会话: {conversation_id} (主题: {topic})"
                )
            else:
                # 更新现有对话的主题
                self.conversations[conversation_id]["topic"] = topic
                self.logger.info(f"🔄 更新对话主题: {topic}")

            # 使用 LLM 根据主题生成开场白
            opening_message = await self._generate_opening_message(who, topic)

            # 记录消息到对话历史
            self.conversations[conversation_id]["messages"].append(
                {
                    "from": self.agent_id,
                    "to": who,
                    "content": opening_message,
                    "timestamp": time.time(),
                    "type": "outgoing",
                    "message_type": "opening",  # 标记为开场白
                }
            )
            self.conversations[conversation_id]["last_activity"] = time.time()

            # 发送对话事件消息
            await self._send_dialog_event(who, opening_message, conversation_id, topic)

            # 如果对方不在聊天伙伴列表中，添加到列表
            if who not in self.chat_partners:
                self.chat_partners.append(who)

            self.logger.info(f"💬 发送开场白给 {who}: {opening_message}")
            return f"已向 {who} 发起主题对话 '{topic}'，开场白: {opening_message}"

        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"❌ 发起主题对话失败: {e}")
            return f"发起主题对话失败: {e}"

    @tool
    async def perform_action(self, action: str, params: Any):
        """执行动作"""
        try:
            print(f"🚀 执行动作: {action}, 参数: {params}")
            print(f"🔍 self.client 类型: {type(self.client)}")
            print(f"🔍 client 连接状态: {getattr(self.client, 'connected', '未知')}")

            response = None

            action_id = await self.client.send_action(action, params)
            print(f"执行动作的立刻结果 - success: {action_id}")
            response = await self.client.get_outcome(action_id)
            print(f"response: {response}")
            return response
        except Exception as e:
            print(f"💥 perform_action 执行失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            self.logger.error(f"❌ 执行动作失败: {e}")
            return f"执行动作失败: {e}"

    @tool
    async def available_actions(self) -> list[Dict[str, Any]]:
        """获取当前可用的动作"""
        try:
            print(f"🔍 获取可用动作列表...")
            result = await self.perform_action("get_action_list", {})
            print(
                f"✅ 获取到 {len(result) if isinstance(result, list) else '未知数量'} 个可用动作"
            )
            return result
        except Exception as e:
            print(f"💥 available_actions 执行失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            self.logger.error(f"❌ 获取可用动作失败: {e}")
            return []

    async def _generate_opening_message(self, target: str, topic: str) -> str:
        """根据主题生成开场白"""
        try:
            # 构建开场白生成提示
            context = f"我是 {self.agent_id}，性格是 {self.personality}"
            if hasattr(self, "ai") and self.ai.position:
                context += f"，当前在位置 {self.ai.position}"

            prompt = f"""
{context}

我想与 {target} 就 "{topic}" 这个主题开始一段对话。
请为我生成一个自然、友好且符合我性格特点的开场白。

要求：
1. 开场白要与主题 "{topic}" 相关
2. 语气要符合 {self.personality} 的性格
3. 长度适中，不要太长也不要太短
4. 自然引导对方参与讨论

请直接生成开场白，不要包含其他解释：
"""

            # 使用 LLM 生成开场白
            opening_message = await self.llm_agent.chat(prompt)

            # 清理生成的内容，移除可能的引号或多余文本
            opening_message = opening_message.strip().strip('"').strip("'")

            return opening_message

        except Exception as e:
            self.logger.error(f"❌ 生成开场白失败: {e}")
            # 如果生成失败，使用简单的后备开场白
            return f"你好 {target}，我想和你聊聊关于 {topic} 的话题。"

    async def _send_dialog_event(
        self, target: str, message: str, conversation_id: str, topic: str = None
    ) -> None:
        """发送对话事件消息"""
        try:
            if not self.client:
                self.logger.warning("❌ 客户端未连接，无法发送对话事件")
                return

            # 构建对话事件数据
            dialog_event = {
                "type": "dialog",
                "conversation_id": conversation_id,
                "from_agent": self.agent_id,
                "target_agent": target,
                "message": message,
                "topic": topic,  # 添加主题信息
                "timestamp": time.time(),
            }

            # 创建事件消息
            event_message = EventMessage(event="agent_dialog", data=dialog_event)

            # 发送给目标Agent
            await self.client.send_message(event_message, target)
            topic_info = f" (主题: {topic})" if topic else ""
            self.logger.info(f"📤 已发送对话事件给 {target}{topic_info}")

            # 同时广播一份给环境进行抄送监控
            await self.client.send_message(event_message, "broadcast")
            self.logger.info(f"📡 已广播对话事件供环境抄送")

        except Exception as e:
            self.logger.error(f"❌ 发送对话事件失败: {e}")

    async def _send_chat_message(self, message: str, target_agent: str = None) -> None:
        """发送聊天消息（保留原有功能，用于兼容）"""
        try:
            if not self.client:
                return

            # 构建聊天动作
            chat_action = {
                "action": "chat",
                "parameters": {
                    "message": message,
                    "target_agent": target_agent,
                    "from_agent": self.agent_id,
                },
            }

            # 发送动作
            await self.client.send_action(
                action=chat_action["action"], parameters=chat_action["parameters"]
            )

        except Exception as e:
            self.logger.error(f"❌ 发送聊天消息失败: {e}")

    async def _chat_loop(self) -> None:
        """对话感知与管理循环

        持续监听新的对话消息，管理对话状态，
        在对话未结束前能够在同一对话线程下回复对方
        """
        self.logger.info("💬 对话管理循环已启动")

        while self.running and self.llm_agent:
            try:
                # 处理消息队列中的新消息
                try:
                    # 等待新消息，超时后继续其他逻辑
                    message_data = await asyncio.wait_for(
                        self.message_queue.get(), timeout=5.0
                    )
                    await self._process_incoming_message(message_data)
                except asyncio.TimeoutError:
                    # 超时是正常的，继续其他逻辑
                    pass

                # 检查并清理过期的对话
                await self._cleanup_expired_conversations()

                # 处理活跃对话中的智能回复
                await self._handle_active_conversations()

                # # 偶尔主动发起新的对话（降低频率）
                # if random.random() < 0.1 and self.chat_partners:  # 10% 概率发起新对话
                #     await self._initiate_random_conversation()

                # 等待一段时间再继续
                await asyncio.sleep(2.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"❌ 对话管理循环错误: {e}")
                await asyncio.sleep(1.0)

        self.logger.info("💬 对话管理循环已停止")

    async def _process_incoming_message(self, message_data: Dict[str, Any]) -> None:
        """处理接收到的消息"""
        try:
            sender = message_data.get("from_agent")
            content = message_data.get("message")
            conversation_id = message_data.get("conversation_id")
            topic = message_data.get("topic")  # 获取主题信息

            if not all([sender, content]):
                self.logger.warning("❌ 收到不完整的消息数据")
                return

            topic_info = f" (主题: {topic})" if topic else ""
            self.logger.info(f"📨 收到来自 {sender} 的消息{topic_info}: {content}")

            # 如果没有conversation_id，为此对话创建新的会话
            if not conversation_id:
                conversation_id = self.active_conversations.get(sender)
                if not conversation_id:
                    conversation_id = (
                        f"conv_{sender}_{self.agent_id}_{int(time.time())}"
                    )
                    self.active_conversations[sender] = conversation_id
                    self.conversations[conversation_id] = {
                        "participants": [sender, self.agent_id],
                        "topic": topic,  # 记录对话主题
                        "messages": [],
                        "created_at": time.time(),
                        "last_activity": time.time(),
                        "status": "active",
                    }
                    self.logger.info(f"🆕 接收方创建新对话会话: {conversation_id}")
            else:
                # 使用发送方提供的conversation_id
                if conversation_id not in self.conversations:
                    # 如果是新的conversation_id，创建对话记录
                    self.active_conversations[sender] = conversation_id
                    self.conversations[conversation_id] = {
                        "participants": [sender, self.agent_id],
                        "topic": topic,  # 记录对话主题
                        "messages": [],
                        "created_at": time.time(),
                        "last_activity": time.time(),
                        "status": "active",
                    }
                    self.logger.info(f"🔗 使用发送方的对话会话: {conversation_id}")
                else:
                    # 如果对话已存在但有新主题，更新主题
                    if topic:
                        self.conversations[conversation_id]["topic"] = topic
                        self.logger.info(f"🔄 更新对话主题: {topic}")

            # 记录消息到对话历史
            if conversation_id in self.conversations:
                self.conversations[conversation_id]["messages"].append(
                    {
                        "from": sender,
                        "to": self.agent_id,
                        "content": content,
                        "timestamp": time.time(),
                        "type": "incoming",
                    }
                )
                self.conversations[conversation_id]["last_activity"] = time.time()

            # 如果发送者不在聊天伙伴列表中，添加到列表
            if sender not in self.chat_partners:
                self.chat_partners.append(sender)

            # 生成智能回复（传递主题信息）
            if self.llm_agent and conversation_id in self.conversations:
                await self._generate_smart_reply(sender, content, conversation_id)

        except Exception as e:
            self.logger.error(f"❌ 处理接收消息失败: {e}")

    async def _generate_smart_reply(
        self, sender: str, message: str, conversation_id: str
    ) -> None:
        """生成智能回复"""
        try:
            # 构建对话上下文
            conversation = self.conversations[conversation_id]
            recent_messages = conversation["messages"][-5:]  # 最近5条消息作为上下文
            topic = conversation.get("topic", "")  # 获取对话主题

            # 构建基于主题的回复提示
            context_prompt = f"我是{self.agent_id}，性格是{self.personality}，正在与{sender}就'{topic}'这个主题进行对话。\n\n"
            context_prompt += "对话历史:\n"
            for msg in recent_messages[:-1]:  # 除了最新的消息
                context_prompt += f"{msg['from']}: {msg['content']}\n"

            context_prompt += f"\n{sender}刚刚说: {message}\n\n"
            context_prompt += f"请生成一个{self.personality}的回复，要求：\n"
            context_prompt += f"1. 与主题'{topic}'相关\n"
            context_prompt += f"2. 符合{self.personality}的性格特点\n"
            context_prompt += "3. 自然地延续对话\n"
            context_prompt += "4. 适当地提问或分享观点\n\n"
            context_prompt += "请直接生成回复内容："

            # 使用LLM生成回复
            reply = await self.llm_agent.chat(context_prompt)

            # 清理生成的内容
            reply = reply.strip().strip('"').strip("'")

            # 记录回复到对话历史
            conversation["messages"].append(
                {
                    "from": self.agent_id,
                    "to": sender,
                    "content": reply,
                    "timestamp": time.time(),
                    "type": "outgoing",
                    "message_type": "reply",  # 标记为回复
                }
            )
            conversation["last_activity"] = time.time()

            topic_info = f" (主题: {topic})" if topic else ""
            self.logger.info(f"🤖 智能回复给 {sender}{topic_info}: {reply}")

            # 发送回复事件，包含主题信息
            await self._send_dialog_event(sender, reply, conversation_id, topic)

        except Exception as e:
            self.logger.error(f"❌ 生成智能回复失败: {e}")

    async def _cleanup_expired_conversations(self) -> None:
        """清理过期的对话"""
        try:
            current_time = time.time()
            expired_conversations = []

            for conv_id, conversation in self.conversations.items():
                # 30分钟无活动则标记为过期
                if current_time - conversation["last_activity"] > 1800:
                    expired_conversations.append(conv_id)

            for conv_id in expired_conversations:
                conversation = self.conversations[conv_id]
                # 从活跃对话中移除
                for participant in conversation["participants"]:
                    if participant in self.active_conversations:
                        if self.active_conversations[participant] == conv_id:
                            del self.active_conversations[participant]

                # 标记为已过期
                conversation["status"] = "expired"
                self.logger.debug(f"🕐 对话 {conv_id} 已过期")

        except Exception as e:
            self.logger.error(f"❌ 清理过期对话失败: {e}")

    async def _handle_active_conversations(self) -> None:
        """处理活跃对话中的智能交互"""
        try:
            # 检查是否有需要主动响应的对话
            for target, conv_id in self.active_conversations.items():
                if conv_id not in self.conversations:
                    continue

                conversation = self.conversations[conv_id]
                if conversation["status"] != "active":
                    continue

                # 检查是否需要继续对话（而不是重复回复）
                messages = conversation["messages"]
                if messages:
                    last_message = messages[-1]
                    current_time = time.time()

                    # 如果最后一条消息是对方发的，且是回复类型，考虑继续对话
                    if (
                        last_message["from"] != self.agent_id
                        and last_message.get("message_type") == "reply"
                        and current_time - last_message["timestamp"]
                        > 10  # 10秒后考虑继续
                        and random.random() < 0.4  # 40% 概率继续对话
                    ):
                        # 基于话题生成继续对话的内容
                        topic = conversation.get("topic", "")
                        context = f"在关于'{topic}'的对话中，{target}刚刚回复了，我想继续这个话题的讨论"

                        continue_message = await self.llm_agent.chat(
                            f"我是{self.agent_id}，性格是{self.personality}。{context}。"
                            f"请生成一个自然的后续问题或观点来继续关于'{topic}'的讨论，"
                            f"要符合{self.personality}的性格特点："
                        )

                        continue_message = (
                            continue_message.strip().strip('"').strip("'")
                        )

                        # 发送继续对话的消息（不是新dialog，而是在现有对话中继续）
                        await self._send_dialog_event(
                            target, continue_message, conv_id, topic
                        )

                        # 记录到对话历史
                        conversation["messages"].append(
                            {
                                "from": self.agent_id,
                                "to": target,
                                "content": continue_message,
                                "timestamp": time.time(),
                                "type": "outgoing",
                                "message_type": "continue",  # 标记为继续对话
                            }
                        )
                        conversation["last_activity"] = time.time()

                        self.logger.info(
                            f"� 继续与 {target} 的对话 (主题: {topic}): {continue_message}"
                        )

        except Exception as e:
            self.logger.error(f"❌ 处理活跃对话失败: {e}")

    async def _initiate_random_conversation(self) -> None:
        """主动发起随机对话"""
        try:
            if not self.chat_partners:
                return

            target_agent = random.choice(self.chat_partners)
            context = (
                f"我在位置 {self.ai.position}，已执行 {self.ai.actions_taken} 个动作"
            )

            prompt = f"请生成一个{self.personality}的主动问候消息，当前状态: {context}"
            message = await self.llm_agent.chat(prompt)

            await self.dialog(target_agent, message)
            self.logger.info(f"💬 主动对话 {target_agent}: {message}")

        except Exception as e:
            self.logger.error(f"❌ 主动发起对话失败: {e}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Star Protocol V4 Agent 演示")
    parser.add_argument(
        "--hub-url",
        default="ws://localhost:8000",
        help="Hub 服务器地址 (默认: ws://localhost:8000)",
    )
    parser.add_argument(
        "--agent-id",
        default=f"agent_{random.randint(1000, 9999)}",
        help="Agent ID (默认: 随机生成)",
    )
    parser.add_argument(
        "--env-id", default="world_1", help="目标环境 ID (默认: world_1)"
    )
    parser.add_argument(
        "--max-actions", type=int, default=0, help="最大动作数 (0=无限制, 默认: 0)"
    )
    parser.add_argument(
        "--action-interval", type=float, default=2.0, help="动作间隔秒数 (默认: 2.0)"
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

    # LLM Agent 相关参数
    parser.add_argument(
        "--agent-type",
        default="llm",
        choices=["simple", "llm"],
        help="Agent 类型 (默认: simple)",
    )
    parser.add_argument(
        "--personality",
        default="friendly",
        choices=["friendly", "curious", "analytical", "creative"],
        help="LLM Agent 性格 (默认: friendly)",
    )
    parser.add_argument(
        "--enable-chat",
        action="store_true",
        help="启用聊天功能 (仅对 LLM Agent 有效)",
    )

    args = parser.parse_args()

    # 对于 LLM Agent，默认启用聊天功能
    enable_chat = args.enable_chat
    if args.agent_type == "llm" and not args.enable_chat:
        enable_chat = True  # LLM Agent 默认启用聊天

    # 创建并启动 Agent 演示
    demo = AgentDemo(
        agent_id=args.agent_id,
        env_id=args.env_id,
        hub_url=args.hub_url,
        max_actions=args.max_actions,
        action_interval=args.action_interval,
        enable_monitoring=not args.no_monitoring,
        interactive=not args.no_interactive,
        log_level=args.log_level,
        agent_type=args.agent_type,
        personality=args.personality,
        enable_chat=enable_chat,
    )

    try:
        await demo.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        traceback.print_exc()
        print(f"❌ Agent 演示失败: {e}")
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
        print("\n👋 Agent 演示已停止")
        sys.exit(0)
    except Exception as e:
        traceback.print_exc()
        print(f"❌ 程序异常退出: {e}")
        sys.exit(1)
