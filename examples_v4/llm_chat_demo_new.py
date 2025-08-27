#!/usr/bin/env python3
"""
LLM Agent 聊天演示

完整的双 LLM Agent 聊天演示，包括：
- Hub 服务器
- Environment 客户端 (支持聊天路由)
- 两个 LLM Agent 客户端
- 聊天消息路由和处理
"""

import asyncio
import argparse
import sys
import time
import random
from pathlib import Path
from typing import List, Optional, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from star_protocol.hub.server import HubServer
from star_protocol.client.environment import EnvironmentClient
from star_protocol.client.agent import AgentClient
from star_protocol.monitor import create_simple_monitor
from star_protocol.utils import setup_logger, get_logger

# 导入 LLM Agent 类
from agent_demo import LLMAgent


class ChatEnvironment:
    """支持聊天的环境客户端"""

    def __init__(self, env_id: str, hub_url: str):
        self.env_id = env_id
        self.hub_url = hub_url
        self.logger = get_logger(f"star_protocol.chat_env.{env_id}")

        # 聊天管理
        self.connected_agents: Dict[str, Dict[str, Any]] = {}

        # 创建自定义环境客户端
        self.client = ChatEnvironmentClient(
            env_id=env_id, hub_url=hub_url, chat_env=self
        )

    async def start(self) -> None:
        """启动聊天环境"""
        self.logger.info(f"🌍 启动聊天环境: {self.env_id}")

        # 连接到 Hub
        await self.client.connect()
        self.logger.info(f"✅ 聊天环境已连接")

    async def stop(self) -> None:
        """停止聊天环境"""
        if self.client:
            await self.client.disconnect()
            self.logger.info(f"✅ 聊天环境已断开")

    async def handle_chat_action(self, action, envelope) -> None:
        """处理聊天动作"""
        try:
            message = action.parameters.get("message", "")
            target_agent = action.parameters.get("target_agent")  # None = 广播
            from_agent = envelope.sender

            if not message:
                await self.client.send_outcome(
                    action_id=action.action_id,
                    status="failure",
                    outcome={"success": False, "reason": "消息不能为空"},
                    recipient=envelope.sender,
                )
                return

            self.logger.info(
                f"💬 {from_agent} -> {target_agent or '所有人'}: {message}"
                + (f" (对 {target_agent})" if target_agent else " (广播)")
            )

            # 路由消息
            if target_agent and target_agent in self.connected_agents:
                # 私聊
                await self._send_chat_to_agent(target_agent, from_agent, message)
            elif not target_agent:
                # 广播给所有其他 Agent
                for agent_id in self.connected_agents:
                    if agent_id != from_agent:
                        await self._send_chat_to_agent(agent_id, from_agent, message)
            else:
                await self.client.send_outcome(
                    action_id=action.action_id,
                    status="failure",
                    outcome={
                        "success": False,
                        "reason": f"找不到目标 Agent: {target_agent}",
                    },
                    recipient=envelope.sender,
                )
                return

            # 发送成功响应
            await self.client.send_outcome(
                action_id=action.action_id,
                status="success",
                outcome={"success": True, "message_delivered": True},
                recipient=envelope.sender,
            )

        except Exception as e:
            self.logger.error(f"❌ 处理聊天动作失败: {e}")
            await self.client.send_outcome(
                action_id=action.action_id,
                status="failure",
                outcome={"success": False, "reason": f"聊天失败: {str(e)}"},
                recipient=envelope.sender,
            )

    async def handle_look_action(self, action, envelope) -> None:
        """处理查看动作"""
        try:
            # 返回当前环境中的其他 Agent
            other_agents = [
                {"id": agent_id, "info": info["info"]}
                for agent_id, info in self.connected_agents.items()
                if agent_id != envelope.sender
            ]

            await self.client.send_outcome(
                action_id=action.action_id,
                status="success",
                outcome={
                    "success": True,
                    "nearby_agents": other_agents,
                    "environment_type": "chat_room",
                },
                recipient=envelope.sender,
            )

        except Exception as e:
            self.logger.error(f"❌ 处理查看动作失败: {e}")
            await self.client.send_outcome(
                action_id=action.action_id,
                status="failure",
                outcome={"success": False, "reason": f"查看失败: {str(e)}"},
                recipient=envelope.sender,
            )

    async def handle_get_agents_action(self, action, envelope) -> None:
        """处理获取 Agent 列表动作"""
        try:
            agent_list = list(self.connected_agents.keys())

            await self.client.send_outcome(
                action_id=action.action_id,
                status="success",
                outcome={
                    "success": True,
                    "agents": agent_list,
                    "total_agents": len(agent_list),
                },
                recipient=envelope.sender,
            )

        except Exception as e:
            self.logger.error(f"❌ 处理获取 Agent 列表失败: {e}")
            await self.client.send_outcome(
                action_id=action.action_id,
                status="failure",
                outcome={"success": False, "reason": f"获取 Agent 列表失败: {str(e)}"},
                recipient=envelope.sender,
            )

    async def _send_chat_to_agent(
        self, target_agent: str, from_agent: str, message: str
    ) -> None:
        """发送聊天消息给指定 Agent"""
        try:
            # 通过 Hub 发送动作给目标 Agent
            chat_result = {
                "action": "chat_message",
                "parameters": {
                    "from_agent": from_agent,
                    "message": message,
                    "timestamp": time.time(),
                },
            }

            await self.client.send_action_to_agent(
                target_agent=target_agent,
                action="chat_message",
                parameters=chat_result["parameters"],
            )

        except Exception as e:
            self.logger.error(f"❌ 发送聊天消息给 {target_agent} 失败: {e}")

    async def _broadcast_chat_message(self, from_agent: str, message: str) -> None:
        """广播聊天消息"""
        for agent_id in self.connected_agents:
            if agent_id != from_agent:
                await self._send_chat_to_agent(agent_id, from_agent, message)

    def register_agent(self, agent_id: str, agent_info: Dict[str, Any]) -> None:
        """注册 Agent"""
        self.connected_agents[agent_id] = {
            "id": agent_id,
            "info": agent_info,
            "joined_at": time.time(),
        }
        self.logger.info(f"👋 Agent {agent_id} 加入聊天环境")


class ChatEnvironmentClient(EnvironmentClient):
    """聊天环境客户端实现"""

    def __init__(self, env_id: str, hub_url: str, chat_env: ChatEnvironment):
        super().__init__(env_id, hub_url)
        self.chat_env = chat_env

    async def on_action(self, message, envelope) -> None:
        """处理 Agent 动作"""
        try:
            if message.action == "chat":
                await self.chat_env.handle_chat_action(message, envelope)
            elif message.action == "look":
                await self.chat_env.handle_look_action(message, envelope)
            elif message.action == "get_agents":
                await self.chat_env.handle_get_agents_action(message, envelope)
            else:
                # 默认响应
                await self.send_outcome(
                    action_id=message.action_id,
                    status="error",
                    outcome={
                        "success": False,
                        "reason": f"不支持的动作: {message.action}",
                    },
                    recipient=envelope.sender,
                )
        except Exception as e:
            self.logger.error(f"❌ 处理动作失败: {e}")
            await self.send_outcome(
                action_id=message.action_id,
                status="error",
                outcome={"success": False, "reason": f"处理失败: {str(e)}"},
                recipient=envelope.sender,
            )


class LLMChatAgent:
    """支持聊天的 LLM Agent"""

    def __init__(
        self, agent_id: str, env_id: str, hub_url: str, personality: str = "friendly"
    ):
        self.agent_id = agent_id
        self.env_id = env_id
        self.hub_url = hub_url
        self.personality = personality

        self.llm_agent = LLMAgent(agent_id, personality)
        self.logger = get_logger(f"star_protocol.llm_chat.{agent_id}")

        # 聊天状态
        self.is_connected = False
        self.other_agents: List[str] = []
        self.chat_active = True
        self.chat_interval = (5.0, 15.0)  # 聊天间隔范围
        self.last_chat_time = 0

        # 创建自定义客户端
        self.client = LLMChatAgentClient(
            agent_id=agent_id, env_id=env_id, hub_url=hub_url, llm_chat_agent=self
        )

    async def start(self) -> None:
        """启动 LLM 聊天 Agent"""
        self.logger.info(
            f"🤖 启动 LLM 聊天 Agent: {self.agent_id} (性格: {self.personality})"
        )

        # 连接到 Hub
        await self.client.connect()
        self.is_connected = True

        self.logger.info(f"✅ LLM Agent {self.agent_id} 已连接")

        # 启动聊天循环
        asyncio.create_task(self._chat_loop())

        # 定期发现其他 Agent
        asyncio.create_task(self._discovery_loop())

    async def stop(self) -> None:
        """停止 LLM 聊天 Agent"""
        self.chat_active = False

        if self.client:
            await self.client.disconnect()
            self.logger.info(f"✅ LLM Agent {self.agent_id} 已断开")

    async def handle_incoming_chat(self, params: Dict[str, Any]) -> None:
        """处理接收到的聊天消息"""
        try:
            from_agent = params.get("from_agent")
            message = params.get("message")

            if not from_agent or not message:
                return

            self.logger.info(f"💬 收到 {from_agent}: {message}")

            # 使用 LLM 生成回复
            reply = await self.llm_agent.process_received_message(from_agent, message)

            # 等待一下再回复（模拟思考时间）
            await asyncio.sleep(random.uniform(1.0, 3.0))

            # 发送回复
            await self._send_chat_message(reply, from_agent)
            self.logger.info(f"💬 回复 {from_agent}: {reply}")

        except Exception as e:
            self.logger.error(f"❌ 处理聊天消息失败: {e}")

    async def _send_chat_message(self, message: str, target_agent: str = None) -> bool:
        """发送聊天消息"""
        try:
            if not self.is_connected or not self.client:
                return False

            # 发送聊天动作
            result = await self.client.send_action_and_wait(
                action="chat",
                parameters={
                    "message": message,
                    "target_agent": target_agent,
                    "from_agent": self.agent_id,
                },
                timeout=5.0,
            )

            return result and result.outcome.get("success", False)

        except Exception as e:
            self.logger.error(f"❌ 发送聊天消息失败: {e}")
            return False

    async def _discovery_loop(self) -> None:
        """发现其他 Agent 的循环"""
        while self.chat_active and self.is_connected:
            try:
                # 查看环境中的其他 Agent
                result = await self.client.send_action_and_wait(
                    action="look", parameters={}, timeout=3.0
                )

                if result and result.outcome.get("success"):
                    nearby_agents = result.outcome.get("nearby_agents", [])
                    new_agents = [
                        agent["id"]
                        for agent in nearby_agents
                        if agent["id"] not in self.other_agents
                    ]

                    for agent_id in new_agents:
                        self.other_agents.append(agent_id)
                        self.logger.info(f"🔍 发现新 Agent: {agent_id}")

                # 等待一段时间再检查
                await asyncio.sleep(10.0)

            except Exception as e:
                self.logger.error(f"❌ Agent 发现失败: {e}")
                await asyncio.sleep(5.0)

    async def _chat_loop(self) -> None:
        """聊天循环"""
        self.logger.info(f"💬 {self.agent_id} 聊天循环已启动")

        # 等待一下让系统稳定
        await asyncio.sleep(3.0)

        while self.chat_active and self.is_connected:
            try:
                current_time = time.time()

                # 随机聊天间隔
                chat_interval = random.uniform(*self.chat_interval)

                if current_time - self.last_chat_time >= chat_interval:
                    # 随机决定是否主动发起聊天
                    if random.random() < 0.6 and self.other_agents:  # 60% 概率
                        target_agent = random.choice(self.other_agents)

                        # 生成聊天内容
                        context = f"我是 {self.agent_id}，想和 {target_agent} 聊天"
                        message = await self.llm_agent.generate_message(
                            context, target_agent
                        )

                        # 发送消息
                        success = await self._send_chat_message(message, target_agent)
                        if success:
                            self.logger.info(f"💬 主动对 {target_agent} 说: {message}")
                            self.last_chat_time = current_time
                        else:
                            self.logger.warning(f"❌ 向 {target_agent} 发送消息失败")

                # 等待一段时间
                await asyncio.sleep(2.0)

            except Exception as e:
                self.logger.error(f"❌ 聊天循环错误: {e}")
                await asyncio.sleep(3.0)

        self.logger.info(f"💬 {self.agent_id} 聊天循环已停止")


class LLMChatAgentClient(AgentClient):
    """LLM 聊天 Agent 客户端实现"""

    def __init__(
        self, agent_id: str, env_id: str, hub_url: str, llm_chat_agent: LLMChatAgent
    ):
        super().__init__(agent_id, env_id, hub_url)
        self.llm_chat_agent = llm_chat_agent

    async def on_action(self, message, envelope) -> None:
        """处理收到的动作消息（例如来自环境的聊天消息）"""
        try:
            if message.action == "chat_message":
                await self.llm_chat_agent.handle_incoming_chat(message.parameters)
        except Exception as e:
            self.logger.error(f"❌ 处理动作失败: {e}")


class LLMChatDemo:
    """LLM 聊天演示类"""

    def __init__(
        self,
        port: int = 8000,
        demo_duration: int = 60,
        agent_personalities: List[str] = None,
    ):
        self.port = port
        self.demo_duration = demo_duration
        self.agent_personalities = agent_personalities or ["friendly", "curious"]

        # 设置日志
        setup_logger(level="INFO", enable_rich=True)
        self.logger = get_logger("star_protocol.llm_chat_demo")

        # 组件
        self.hub_server: Optional[HubServer] = None
        self.environment: Optional[ChatEnvironment] = None
        self.agents: List[LLMChatAgent] = []

        # 监控
        self.monitor = None

        # 状态
        self.running = False

    async def start(self) -> None:
        """启动演示"""
        self.logger.info("🚀 启动 LLM Agent 聊天演示")
        self.logger.info(f"   Hub 端口: {self.port}")
        self.logger.info(f"   演示时长: {self.demo_duration} 秒")
        self.logger.info(f"   Agent 性格: {', '.join(self.agent_personalities)}")

        try:
            # 启动监控
            self.monitor = create_simple_monitor()
            self.monitor.start()
            self.logger.info("📊 监控系统已启动")

            # 启动 Hub 服务器
            await self._start_hub()

            # 启动环境
            await self._start_environment()

            # 启动 Agent
            await self._start_agents()

            # 运行演示
            await self._run_demo()

        except Exception as e:
            self.logger.error(f"❌ 启动演示失败: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """停止演示"""
        if not self.running:
            return

        self.logger.info("🛑 正在停止演示...")
        self.running = False

        # 停止 Agent
        for i, agent in enumerate(self.agents):
            await agent.stop()
            self.logger.info(f"✅ Agent {i+1} 已停止")

        # 停止环境
        if self.environment:
            await self.environment.stop()
            self.logger.info("✅ 环境已停止")

        # 停止 Hub 服务器
        if self.hub_server:
            await self.hub_server.stop()
            self.logger.info("✅ Hub 服务器已停止")

        # 停止监控
        if self.monitor:
            self.monitor.stop()
            self.logger.info("📊 监控系统已停止")

        self.logger.info("🎉 演示已完成")

    async def _start_hub(self) -> None:
        """启动 Hub 服务器"""
        self.logger.info("🌐 启动 Hub 服务器...")

        self.hub_server = HubServer(port=self.port)
        await self.hub_server.start()

        self.logger.info(f"✅ Hub 服务器已启动 (端口: {self.port})")

    async def _start_environment(self) -> None:
        """启动环境"""
        self.logger.info("🌍 启动聊天环境...")

        self.environment = ChatEnvironment(
            env_id="chat_room", hub_url=f"ws://localhost:{self.port}"
        )
        await self.environment.start()

        self.logger.info("✅ 聊天环境已启动")

    async def _start_agents(self) -> None:
        """启动 Agent"""
        self.logger.info(f"🤖 启动 {len(self.agent_personalities)} 个 LLM Agent...")

        for i, personality in enumerate(self.agent_personalities):
            agent_id = f"llm_agent_{i+1}"

            agent = LLMChatAgent(
                agent_id=agent_id,
                env_id="chat_room",
                hub_url=f"ws://localhost:{self.port}",
                personality=personality,
            )

            await agent.start()
            self.agents.append(agent)

            self.logger.info(f"✅ LLM Agent {i+1} ({personality}) 已启动")

            # 错开启动时间
            await asyncio.sleep(2.0)

    async def _run_demo(self) -> None:
        """运行演示"""
        self.running = True

        self.logger.info(f"🎮 开始 LLM 聊天演示 ({self.demo_duration} 秒)...")

        start_time = time.time()

        while self.running and (time.time() - start_time) < self.demo_duration:
            # 每 10 秒显示一次状态
            await asyncio.sleep(10.0)

            elapsed = time.time() - start_time
            remaining = max(0, self.demo_duration - elapsed)

            self.logger.info(
                f"📊 演示进行中 - 已运行 {elapsed:.0f}秒, 剩余 {remaining:.0f}秒"
            )

        self.logger.info("⏰ 演示时间结束")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="LLM Agent 聊天演示")
    parser.add_argument(
        "--port", type=int, default=8020, help="Hub 服务器端口 (默认: 8020)"
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="演示时长 (秒, 默认: 60)"
    )
    parser.add_argument(
        "--personalities",
        nargs="+",
        default=["friendly", "curious"],
        choices=["friendly", "curious", "analytical", "creative"],
        help="Agent 性格列表 (默认: friendly curious)",
    )

    args = parser.parse_args()

    # 创建并启动演示
    demo = LLMChatDemo(
        port=args.port,
        demo_duration=args.duration,
        agent_personalities=args.personalities,
    )

    try:
        await demo.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ 演示失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 演示已停止")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 程序异常退出: {e}")
        sys.exit(1)
