# Star Protocol Python SDK

一个轻量级、强类型的多智能体通信协议 Python SDK，基于 WebSocket 实现 Agent、Environment、Human 和 Monitor 之间的实时协作。

## ✨ 特性

- ✅ **类型安全**: 使用 Pydantic 模型确保消息结构正确性
- ✅ **异步优先**: 基于 `asyncio` 和 `websockets` 的高性能实现
- ✅ **FastAPI 集成**: 生产级 Hub Server，支持 HTTP API 和 WebSocket
- ✅ **五种客户端**: Agent、Environment、Human、Monitor、Hub Monitor 开箱即用
- ✅ **Monitor 功能**: 实时监控 Agent 和 Environment 的交互状态
- ✅ **自动重连**: 内置连接管理和故障恢复
- ✅ **易于扩展**: 支持自定义 Payload 和中间件

## 🚀 快速开始

### 安装

```bash
pip install star-protocol
# 或使用 uv
uv add star-protocol
```

### 启动 Hub Server

```bash
# 使用 CLI
star-hub --host 0.0.0.0 --port 8765

# 或使用 Python
python -m star_protocol.cli
```

### Agent 客户端示例

```python
from star_protocol import AgentClient
import asyncio

class MyAgent(AgentClient):
    async def on_outcome(self, sender: str, content: dict):
        print(f"收到结果: {content}")

async def main():
    agent = MyAgent(client_id="agent_01")
    
    # 使用 async with 自动管理连接
    async with agent:
        await agent.connect("ws://localhost:8765")
        await agent.join_environment("my_env")
        
        # 发送动作
        await agent.send_action(
            recipient="my_env",
            action_name="move",
            params={"x": 10, "y": 5}
        )
        
        await agent.run()

asyncio.run(main())
```

### Environment 客户端示例

```python
from star_protocol import EnvironmentClient

class GameEnvironment(EnvironmentClient):
    async def on_action(self, sender: str, content: dict):
        # 处理动作
        result = {"success": True, "position": [10, 5]}
        await self.send_outcome(recipient=sender, content=result)
        
        # 广播事件
        await self.broadcast_event("player_moved", {"player": sender})

async def main():
    env = GameEnvironment(client_id="my_env")
    
    async with env:
        await env.connect("ws://localhost:8765")
        await env.run()

asyncio.run(main())
```

### Monitor 功能示例

Monitor 可以实时监控 Agent 和 Environment 的交互：

```python
from star_protocol.client import AgentClient, MonitorClient
from star_protocol.client.mixins.monitorable import MonitorLevel

# 1. Agent 启用监控
agent = AgentClient("agent_01", monitorable=True)
await agent.connect("ws://localhost:8765")
await agent.start()
await agent.enable_monitoring(level=MonitorLevel.DEBUG)

# 2. Monitor 订阅 Agent
monitor = MonitorClient("monitor_01")
await monitor.connect("ws://localhost:8765")
await monitor.start()
await monitor.subscribe_to_client("agent_01")

# 3. Monitor 接收数据
class MyMonitor(MonitorClient):
    async def on_monitor_data(self, source_client_id: str, data_type: str, data: dict):
        print(f"监控数据 - 来源: {source_client_id}, 类型: {data_type}")
        print(f"数据: {data}")
```

## 📚 核心概念

### 五种客户端类型

1. **Agent** - 智能体，执行动作并接收结果
2. **Environment** - 环境，处理动作并返回结果，管理环境状态
3. **Human** - 人类用户，可以观察和参与交互
4. **Monitor** - 业务监控，实时监听特定客户端的通讯状态和消息
5. **Hub Monitor** - 系统监控，监听 Hub 上的所有系统与业务消息

### 消息类型

- **Action** - Agent 发送给 Environment 的动作
- **Outcome** - Environment 返回给 Agent 的结果
- **Event** - Environment 广播的事件
- **Stream** - Environment 发送的流式数据
- **Monitor** - 监控相关的控制和数据消息

### 环境管理

- Environment 自动创建和销毁
- Agent 通过 `join_environment()` 加入环境
- 环境内的消息自动路由
- Environment 自动接收环境内所有消息的副本

## 📁 项目结构

```
star_protocol/
├── models/              # 数据模型
│   ├── enums.py        # 枚举类型
│   ├── payloads.py     # 消息载荷
│   └── envelope.py     # 消息信封
├── client/              # 客户端
│   ├── base.py         # 基础客户端
│   ├── agent.py        # Agent 客户端
│   ├── environment.py  # Environment 客户端
│   ├── human.py        # Human 客户端
│   ├── monitor.py      # Monitor 客户端
│   ├── core/           # 核心模块
│   └── mixins/         # Mixin 功能
├── server/              # Hub Server
│   ├── app.py          # FastAPI 应用
│   ├── router.py       # 消息路由
│   ├── connection.py   # 连接管理
│   └── monitor_manager.py  # 监控管理
├── exceptions.py        # 自定义异常
└── cli.py              # 命令行工具
```

## 📖 文档

- [协议规范](docs/SP.md) - 完整的协议交互定义
- [快速入门指南](docs/quickstart.md) - 了解 SDK 基础概念及起步流程
- [API 参考](docs/api_reference.md) - 接口参数与核心类说明

## 💡 示例

查看 `examples/` 目录获取更多示例：

- [`demo_agent.py`](examples/demo_agent.py) - Agent 客户端功能演示
- [`demo_env.py`](examples/demo_env.py) - Environment 客户端功能演示
- [`demo_human.py`](examples/demo_human.py) - Human 客户端功能演示
- [`demo_monitor.py`](examples/demo_monitor.py) - 独立 Monitor 客户端及 Hub Monitor 功能演示
- [`INTERACTIVE_DEMO.md`](examples/INTERACTIVE_DEMO.md) - 多智能体完整交互情景演示指南

### 运行示例

```bash
# 1. 启动 Hub Server
uv run python -m star_protocol.cli

# 2. 在其他终端分别运行客户端示例代码进行联动测试
uv run examples/demo_env.py
uv run examples/demo_agent.py
uv run examples/demo_monitor.py
```

## 🔧 开发

### 环境设置

```bash
# 克隆仓库
git clone https://github.com/your-org/star-protocol
cd star-protocol

# 安装依赖
uv sync

# 运行测试
uv run pytest

# 启动 Hub
uv run python -m star_protocol.cli
```

### 运行测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/models/

# 查看覆盖率
uv run pytest --cov=star_protocol
```

## 🎯 使用场景

### 多智能体系统
- 多个 Agent 在共享环境中协作
- Environment 管理状态和规则
- Monitor 实时监控系统运行

### 游戏开发
- Agent 作为游戏 AI
- Environment 作为游戏世界
- Human 作为玩家
- Monitor 用于调试和分析

### 仿真系统
- Agent 作为仿真实体
- Environment 作为仿真环境
- Monitor 收集仿真数据

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

MIT License

## 🔗 相关链接

- [GitHub 仓库](https://github.com/your-org/star-protocol-python)
- [问题反馈](https://github.com/your-org/star-protocol-python/issues)
- [协议规范](docs/SP.md)
