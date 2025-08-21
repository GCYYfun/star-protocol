#!/usr/bin/env python3
"""
Star Protocol Agent 演示

创建一个智能Agent，能够在环境中移动、观察和交互
"""

import asyncio
import logging
import random
import signal
import sys
from typing import Dict, List, Any, Optional
from star_protocol.client import AgentClient
from star_protocol.protocol import Message
from star_protocol.utils.logger import setup_logging
from star_protocol.monitor.simple_monitor import get_monitor, set_rich_mode

from menglong import Model, ChatAgent
from menglong.agents.component.tool_manager import tool


class AgentDemo:
    """
    Agent演示类 - 负责通信层管理

    这个类作为智能Agent和Star Protocol通信层之间的桥梁。
    要替换为其他LLM Agent，只需要：
    1. 创建新的Agent类，实现相同的接口（handle_action_outcome, handle_environment_event等）
    2. 替换 self.agent = IntelligentAgent(...) 为新的Agent实例
    3. 确保新Agent使用相同的回调函数接口
    """

    def __init__(
        self, agent_id: str = None, env_id: str = "demo_world", port: int = 9999
    ):
        self.agent_id = agent_id or f"agent_{random.randint(1000, 9999)}"
        self.env_id = env_id
        self.port = port

        # 创建 agent client
        self.client = AgentClient(
            agent_id=self.agent_id, env_id=env_id, port=port, validate_messages=True
        )

        # 创建智能 agent 实例
        self.agent = LLMAgent(self.agent_id, env_id)
        self.running = False

        # 初始化monitor
        set_rich_mode()
        self.monitor = get_monitor(f"agent_{self.agent_id}")
        self.monitor.set_status("正在初始化")

        # 设置 agent 的回调函数
        self.agent.set_callbacks(
            send_action_callback=self.send_action,
            send_conversation_callback=self.send_conversation,
            log_callback=self.log_message,
        )

        # 设置消息处理器
        self.setup_handlers()

        # 交互模式相关
        self.interactive_mode = False
        self.command_queue = asyncio.Queue()

    async def send_action(self, action: str, parameters: dict) -> str:
        """发送动作（回调函数）"""
        return await self.client.send_action(action, parameters)

    async def send_conversation(
        self,
        target_agent: str,
        data: dict,
    ):
        """发送对话（回调函数）"""
        await self.client.conversation(
            target_agent,
            data,
        )

    def log_message(self, message: str, level: str = "info"):
        """日志输出（回调函数）"""
        if level == "info":
            self.monitor.info(message)
        elif level == "success":
            self.monitor.success(message)
        elif level == "warning":
            self.monitor.warning(message)
        elif level == "error":
            self.monitor.error(message)
        else:
            self.monitor.info(message)

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

                if message_type == "outcome":
                    await self.agent.handle_action_outcome(payload)
                elif message_type == "event":
                    self.monitor.success(f"Received event: {payload}")
                    # await self.agent.handle_environment_event(payload)
                elif message_type == "action":
                    # Agent通常不处理action消息，但可以记录
                    self.monitor.debug(f"Received action message: {payload}")
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

    async def start_interactive_mode(self):
        """启动交互模式"""
        self.interactive_mode = True
        self.monitor.info("🎮 进入交互模式")
        self.monitor.info("📋 可用命令:")
        self.monitor.info(
            "  move <direction> [distance] - 移动 (north/south/east/west)"
        )
        self.monitor.info("  observe [range] - 观察周围环境")
        self.monitor.info("  pickup <item_id> - 拾取物品")
        self.monitor.info("  talk <agent_id> <message> - 与其他Agent对话")
        self.monitor.info("  status - 显示当前状态")
        self.monitor.info("  auto - 切换回自动模式")
        self.monitor.info("  help - 显示帮助")
        self.monitor.info("  quit - 退出")
        self.monitor.info("-" * 50)

        # 启动命令输入任务
        input_task = asyncio.create_task(self.command_input_loop())
        processor_task = asyncio.create_task(self.command_processor_loop())

        return input_task, processor_task

    async def command_input_loop(self):
        """命令输入循环"""
        try:
            while self.interactive_mode and self.running:
                try:
                    # 使用 asyncio 的方式处理输入
                    command = await asyncio.get_event_loop().run_in_executor(
                        None, input, "🎮 [Interactive] > "
                    )
                    await self.command_queue.put(command.strip())
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break
        except Exception as e:
            self.monitor.error(f"Input loop error: {e}")

    async def command_processor_loop(self):
        """命令处理循环"""
        try:
            while self.interactive_mode and self.running:
                try:
                    # 等待命令，超时1秒检查状态
                    command = await asyncio.wait_for(
                        self.command_queue.get(), timeout=1.0
                    )
                    await self.process_command(command)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.monitor.error(f"Command processing error: {e}")
        except Exception as e:
            self.monitor.error(f"Command processor error: {e}")

    async def process_command(self, command: str):
        """处理用户命令"""
        if not command:
            return

        parts = command.split()
        cmd = parts[0].lower()

        try:
            if cmd == "task":
                await self.cmd_task(parts)
            # elif cmd == "ata":
            #     await self.cmd_dialogue(parts)
            elif cmd == "pickup":
                await self.cmd_pickup(parts)
            elif cmd == "talk":
                await self.cmd_talk(parts)
            elif cmd == "status":
                await self.cmd_status()
            elif cmd == "auto":
                await self.cmd_auto()
            elif cmd == "help":
                await self.cmd_help()
            elif cmd == "quit":
                await self.cmd_quit()
            else:
                self.monitor.warning(f"❓ 未知命令: {cmd}. 输入 'help' 查看帮助")
        except Exception as e:
            self.monitor.error(f"命令执行错误: {e}")

    async def cmd_task(self, parts):
        """处理任务命令"""
        if len(parts) < 1:
            self.monitor.warning("用法: task <prompt>")
            return

        prompt = parts[1]

        self.monitor.info(f"💼 执行任务: {prompt}")
        res = await self.agent.task(prompt=prompt)

        print("===")
        print(res)
        print("===")
        # action_id = await self.send_action(
        #     "move", {"direction": direction, "distance": distance}
        # )
        # if action_id:
        #     self.monitor.success(f"✅ 移动命令已发送 (ID: {action_id})")

    # async def cmd_dialogue(self, parts):
    #     """处理对话命令"""
    #     if len(parts) < 3:
    #         self.monitor.warning("用法: ata <who> <topic>")
    #         return
    #     who = parts[1]
    #     topic = " ".join(parts[2:])
    #     self.monitor.info(f"💬 与 {who} 对话: {topic}")
    #     res = await self.agent.ata(topic=topic)
    #     action_id = await self.send_conversation(
    #         "dialogue", {"who": who, "prompt": topic}
    #     )
    #     # if action_id:
    #     #     self.monitor.success(f"✅ 对话命令已发送 (ID: {action_id})")

    async def cmd_pickup(self, parts):
        """处理拾取命令"""
        if len(parts) < 2:
            self.monitor.warning("用法: pickup <item_id>")
            return

        item_id = parts[1]
        self.monitor.info(f"📦 拾取物品: {item_id}")
        action_id = await self.send_action("pickup", {"item_id": item_id})
        if action_id:
            self.monitor.success(f"✅ 拾取命令已发送 (ID: {action_id})")

    async def cmd_talk(self, parts):
        """处理对话命令"""
        if len(parts) < 3:
            self.monitor.warning("用法: talk <agent_id> <topic>")
            return

        agent_id = parts[1]
        topic = " ".join(parts[2:])
        self.monitor.info(f"💬 与 {agent_id} 对话: {topic}")
        res = await self.agent.ata(prompt=topic)
        conversation_data = {
            "topic": topic,
            "message": res,
            "form": self.agent_id,
            "to": agent_id,
        }
        await self.send_conversation(agent_id, conversation_data)
        self.monitor.success("✅ 消息已发送")

    async def cmd_status(self):
        """显示状态"""
        status = self.agent.get_status()
        self.monitor.info("📊 当前状态:")
        self.monitor.info(f"  ID: {status['id']}")
        self.monitor.info(
            f"  位置: ({status['position']['x']}, {status['position']['y']})"
        )
        self.monitor.info(f"  生命值: {status['health']}")
        self.monitor.info(f"  能量: {status['energy']}")
        self.monitor.info(f"  得分: {status['score']}")
        self.monitor.info(f"  物品数量: {status['inventory_count']}")
        self.monitor.info(f"  已知物品: {status['known_items']}")
        self.monitor.info(f"  已知Agent: {status['known_agents']}")
        self.monitor.info(f"  动作队列: {status['action_queue_size']}")
        self.monitor.info(f"  繁忙状态: {'是' if status['is_busy'] else '否'}")

    async def cmd_auto(self):
        """切换回自动模式"""
        self.interactive_mode = False
        self.monitor.info("🤖 切换回自动模式")

    async def cmd_help(self):
        """显示帮助"""
        self.monitor.info("📋 交互模式命令:")
        self.monitor.info("  move <direction> [distance] - 移动到指定方向")
        self.monitor.info("    方向: north, south, east, west")
        self.monitor.info("    距离: 可选，默认为1")
        self.monitor.info("    示例: move north 2")
        self.monitor.info("")
        self.monitor.info("  observe [range] - 观察周围环境")
        self.monitor.info("    范围: 可选，默认为3")
        self.monitor.info("    示例: observe 5")
        self.monitor.info("")
        self.monitor.info("  pickup <item_id> - 拾取指定物品")
        self.monitor.info("    示例: pickup item_123")
        self.monitor.info("")
        self.monitor.info("  talk <agent_id> <message> - 与其他Agent对话")
        self.monitor.info("    示例: talk agent_456 Hello there!")
        self.monitor.info("")
        self.monitor.info("  status - 显示当前Agent状态")
        self.monitor.info("  auto - 切换回自动模式")
        self.monitor.info("  help - 显示此帮助信息")
        self.monitor.info("  quit - 退出程序")

    async def cmd_quit(self):
        """退出程序"""
        self.monitor.info("👋 正在退出...")
        self.running = False
        self.interactive_mode = False

    async def start(self, interactive: bool = False):
        """启动Agent"""
        self.monitor.info(f"🤖 启动Agent: {self.agent_id}")
        self.monitor.info(f"🌍 目标环境: {self.env_id}")
        self.monitor.info(
            f"📍 连接地址: ws://localhost:{self.port}/env/{self.env_id}/agent/{self.agent_id}"
        )

        if interactive:
            self.monitor.info("🎮 交互模式已启用")
        else:
            self.monitor.info("🤖 自动模式已启用")

        self.monitor.info("-" * 50)
        self.monitor.set_status("正在连接")

        # 连接到Hub
        success = await self.client.connect()
        if not success:
            self.monitor.error("❌ 连接失败!")
            return

        self.monitor.success("✅ Agent连接成功!")

        if interactive:
            self.monitor.info("🎮 Agent将在交互模式下运行")
            self.monitor.info("💡 您可以手动控制Agent的行为")
        else:
            self.monitor.info("🎯 开始智能行为...")
            self.monitor.info("💡 Agent将自动探索、拾取物品并与其他Agent交互")

        self.monitor.set_status("已连接 - 运行中")

        self.running = True

        # 启动任务列表
        tasks = []

        # 启动状态监控
        status_task = asyncio.create_task(self.status_monitor())
        tasks.append(status_task)

        # 根据模式启动不同的任务
        if interactive:
            # 交互模式
            input_task, processor_task = await self.start_interactive_mode()
            tasks.extend([input_task, processor_task])
        else:
            # 自动模式 - 启动行为循环
            behavior_task = asyncio.create_task(self.agent.behavior_loop())
            tasks.append(behavior_task)

        try:
            # 等待中断信号
            stop_event = asyncio.Event()

            def signal_handler():
                self.monitor.warning(f"\n📴 Agent {self.agent_id} 收到停止信号...")
                stop_event.set()

            loop = asyncio.get_event_loop()
            for sig in [signal.SIGINT, signal.SIGTERM]:
                loop.add_signal_handler(sig, signal_handler)

            # 在交互模式下，如果用户切换到自动模式，需要重新启动行为循环
            while self.running:
                if interactive and not self.interactive_mode:
                    # 从交互模式切换到自动模式
                    self.monitor.info("🔄 切换到自动模式...")
                    behavior_task = asyncio.create_task(self.agent.behavior_loop())
                    tasks.append(behavior_task)
                    interactive = False

                # 等待停止信号或短暂休眠
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                    break
                except asyncio.TimeoutError:
                    continue

        finally:
            self.running = False
            self.interactive_mode = False

            # 取消所有任务
            for task in tasks:
                if not task.done():
                    task.cancel()

            # 等待任务完成
            await asyncio.gather(*tasks, return_exceptions=True)

            await self.client.disconnect()
            self.monitor.success(f"✅ Agent {self.agent_id} 已停止")
            self.monitor.set_status("已停止")

    async def status_monitor(self):
        """状态监控"""
        try:
            while self.running:
                await asyncio.sleep(15)  # 每15秒输出一次状态

                status = self.agent.get_status()

                # 更新monitor统计
                self.monitor.update_stats(
                    位置=f"({status['position']['x']}, {status['position']['y']})",
                    得分=status["score"],
                    物品=status["inventory_count"],
                    能量=status["energy"],
                )

                # 输出详细状态
                self.monitor.info(
                    f"📊 [{self.agent_id}] "
                    f"位置: {status['position']} | "
                    f"得分: {status['score']} | "
                    f"物品: {status['inventory_count']} | "
                    f"能量: {status['energy']} | "
                    f"{'🔄' if status['is_busy'] else '💤'}"
                )

        except asyncio.CancelledError:
            pass


# 示例：如何替换为其他LLM Agent
class LLMAgent:
    """
    示例LLM Agent - 展示如何替换IntelligentAgent

    这个类展示了如何创建一个可替换的Agent接口
    """

    def __init__(self, agent_id: str, env_id: str):
        self.agent_id = agent_id
        self.env_id = env_id

        # Agent状态
        self.position = {"x": 0, "y": 0}
        self.inventory = []
        self.score = 0

        self.agent = ChatAgent()

        # 回调函数
        self.send_action_callback = None
        self.send_conversation_callback = None
        self.log_callback = None

    async def task(self, prompt):

        res = await self.agent.chat(task=prompt)  # , tools=[available_actions])
        return res

    async def ata(self, prompt):
        # 执行动作
        from menglong.ml_model.schema.ml_request import UserMessage as user

        response = await self.agent.raw_chat([user(content=prompt)])
        return response

    def set_callbacks(
        self, send_action_callback, send_conversation_callback, log_callback
    ):
        """设置回调函数"""
        self.send_action_callback = send_action_callback
        self.send_conversation_callback = send_conversation_callback
        self.log_callback = log_callback

    def log(self, message: str, level: str = "info"):
        """日志输出"""
        if self.log_callback:
            self.log_callback(message, level)

    async def handle_action_outcome(self, payload: dict):
        """处理动作结果 - LLM决策逻辑在这里"""
        self.log("LLM Agent: Processing action outcome...")
        # 这里可以调用LLM API进行决策
        # 例如：decision = await call_llm_api(payload)
        pass

    async def handle_environment_event(self, payload: dict):
        """处理环境事件 - LLM决策逻辑在这里"""
        self.log("LLM Agent: Processing environment event...")
        # 这里可以调用LLM API进行决策
        pass

    async def behavior_loop(self):
        """行为循环 - LLM驱动的行为"""
        try:
            while True:
                await asyncio.sleep(5)  # LLM可能需要更长的思考时间
                # 这里可以定期调用LLM进行策略规划
                self.log("LLM Agent: Thinking...")
        except asyncio.CancelledError:
            pass

    async def execute_next_action(self):
        """执行下一个动作"""
        # LLM决策的动作执行
        if self.send_action_callback:
            action_id = await self.send_action_callback("observe", {"range": 3})

    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return {
            "id": self.agent_id,
            "position": self.position,
            "score": self.score,
            "inventory_count": len(self.inventory),
        }


# 要使用LLMAgent，只需在AgentDemo.__init__中替换：
# self.agent = LLMAgent(self.agent_id, env_id)


async def main():
    """主函数"""
    import argparse

    # 命令行参数
    parser = argparse.ArgumentParser(description="Star Protocol Agent Demo")
    parser.add_argument("--agent-id", help="Agent ID (auto-generated if not provided)")
    parser.add_argument("--env-id", default="demo_world", help="Environment ID")
    parser.add_argument("--port", type=int, default=9999, help="Hub server port")
    parser.add_argument(
        "--interactive",
        default=True,
        action="store_true",
        help="启用交互模式，允许手动控制Agent",
    )

    args = parser.parse_args()

    # 设置日志
    setup_logging("INFO")

    monitor = get_monitor("agent_demo")
    monitor.success("=" * 50)
    monitor.success("🤖 Star Protocol Agent Demo")
    if args.interactive:
        monitor.success("🎮 交互模式")
    else:
        monitor.success("🤖 自动模式")
    monitor.success("=" * 50)

    # 创建并启动Agent
    demo = AgentDemo(args.agent_id, args.env_id, args.port)
    await demo.start(interactive=args.interactive)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:

        monitor = get_monitor("agent_demo")
        monitor.info("\n👋 再见!")
    except Exception as e:

        monitor = get_monitor("agent_demo")
        monitor.error(f"❌ 程序异常退出: {e}")
        sys.exit(1)
