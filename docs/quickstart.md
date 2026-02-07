# Star Protocol - 快速开始指南

本指南将帮助您在 5 分钟内开始使用 Star Protocol。

## 前置要求

- Python 3.10+
- `uv` 或 `pip` 包管理器

## 安装

```bash
# 使用 uv（推荐）
uv add star-protocol

# 或使用 pip
pip install star-protocol
```

## 第一步：启动 Hub

Hub 是所有客户端连接的中心节点。

```bash
# 使用 CLI 启动
uv run python -m star_protocol.cli

# 或指定端口
uv run python -m star_protocol.cli --port 8765
```

您应该看到类似的输出：

```
🚀 Starting Star Protocol Hub on 0.0.0.0:8765
📡 WebSocket endpoint: ws://0.0.0.0:8765/ws/{role}/{client_id}
🏥 Health check: http://0.0.0.0:8765/health
```

## 第二步：创建 Environment

创建文件 `my_environment.py`：

```python
import asyncio
from star_protocol import EnvironmentClient

class MyEnvironment(EnvironmentClient):
    async def on_action(self, sender: str, content: dict):
        """处理 Agent 的动作"""
        print(f"收到动作: {content}")
        
        # 返回结果
        await self.send_outcome(
            recipient=sender,
            content={"success": True, "message": "动作已处理"}
        )

async def main():
    env = MyEnvironment(client_id="my_env")
    
    # 连接并启动
    await env.connect("ws://localhost:8765")
    await env.start()
    
    print("Environment 已启动，等待 Agent...")
    await env.run()

if __name__ == "__main__":
    asyncio.run(main())
```

在新终端运行：

```bash
uv run python my_environment.py
```

## 第三步：创建 Agent

创建文件 `my_agent.py`：

```python
import asyncio
from star_protocol import AgentClient

class MyAgent(AgentClient):
    async def on_outcome(self, sender: str, content: dict):
        """处理 Environment 的结果"""
        print(f"收到结果: {content}")

async def main():
    agent = MyAgent(client_id="agent_01")
    
    # 连接并启动
    await agent.connect("ws://localhost:8765")
    await agent.start()
    
    # 加入环境
    await agent.join_environment("my_env")
    
    # 发送动作
    await agent.send_action(
        recipient="my_env",
        action_name="test",
        params={"message": "Hello!"}
    )
    
    # 等待结果
    await asyncio.sleep(2)
    
    # 清理
    await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

在新终端运行：

```bash
uv run python my_agent.py
```

## 第四步：添加 Monitor（可选）

Monitor 可以实时监控 Agent 和 Environment 的交互。

创建文件 `my_monitor.py`：

```python
import asyncio
from star_protocol.client import AgentClient, MonitorClient
from star_protocol.client.mixins.monitorable import MonitorLevel

async def main():
    # 1. 创建可监控的 Agent
    agent = AgentClient("agent_01", monitorable=True)
    await agent.connect("ws://localhost:8765")
    await agent.start()
    await agent.enable_monitoring(level=MonitorLevel.DEBUG)
    
    # 2. 创建 Monitor
    monitor = MonitorClient("monitor_01")
    await monitor.connect("ws://localhost:8765")
    await monitor.start()
    
    # 3. 订阅 Agent
    await monitor.subscribe_to_client("agent_01")
    
    print("Monitor 已启动，正在监控 agent_01...")
    
    # 4. Agent 执行动作（会被监控）
    await agent.join_environment("my_env")
    await agent.send_action("my_env", "test", {"data": "test"})
    
    await asyncio.sleep(5)
    
    # 清理
    await monitor.unsubscribe_from_client("agent_01")
    await agent.disable_monitoring()
    await monitor.stop()
    await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## 使用 async with 简化代码

推荐使用 `async with` 自动管理连接：

```python
async def main():
    async with AgentClient("agent_01") as agent:
        await agent.connect("ws://localhost:8765")
        await agent.join_environment("my_env")
        await agent.send_action("my_env", "test", {})
        await agent.run()
```

## 常见问题

### Q: Hub 启动失败？

**A:** 检查端口是否被占用：

```bash
# macOS/Linux
lsof -i :8765

# Windows
netstat -ano | findstr :8765
```

### Q: 客户端连接失败？

**A:** 确保：
1. Hub 已启动
2. 连接 URL 正确（`ws://localhost:8765`）
3. 防火墙未阻止连接

### Q: Environment 未收到消息？

**A:** 确保：
1. Agent 已调用 `join_environment()`
2. Environment 已调用 `start()`
3. Environment ID 匹配

## 下一步

- 查看 [完整示例](../examples/) 了解更多用法
- 阅读 [API 参考](api_reference.md) 了解所有 API
- 阅读 [使用指南](user_guide.md) 深入学习
- 查看 [协议规范](../SPEC.md) 了解协议细节

## 获取帮助

- [GitHub Issues](https://github.com/your-org/star-protocol-python/issues)
- [协议规范](../SPEC.md)
- [示例代码](../examples/)
