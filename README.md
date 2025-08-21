# Star Protocol - Python SDK

Star Protocol 是一个基于 WebSocket 的实时多智能体通信协议，支持 Agent、Environment、Human 和 Hub 之间的全双工实时通信。

## 特性

- 🌟 **多角色支持**: Agent (智能体)、Environment (环境)、Human (人类用户)、Hub (服务中心)
- 🚀 **实时通信**: 基于 WebSocket 的全双工通信
- 📡 **广播机制**: 支持全局和环境内广播
- 🔒 **权限控制**: 基于角色的细粒度权限管理
- 🔄 **异步支持**: 全异步设计，支持高并发
- 🎯 **事件驱动**: 支持装饰器式的事件处理
- 📦 **类型安全**: 完整的类型注解和数据验证
- 🛡️ **错误处理**: 结构化的异常处理机制

## 快速开始

### 安装

```bash
pip install star-protocol
```

### Agent 客户端示例

```python
import asyncio
from star_protocol import AgentClient

async def main():
    # 创建 Agent 客户端
    agent = AgentClient(
        server_url="ws://localhost:8765",
        agent_id="agent_001",
        env_id="forest_world"
    )
    
    # 设置事件处理器
    @agent.on_outcome
    async def handle_outcome(message):
        print(f"收到结果: {message.payload}")
    
    # 连接并注册
    async with agent:
        await agent.register("智能探索者", ["move", "observe", "pickup"])
        
        # 执行动作
        action_id = await agent.move("north", distance=2.0)
        await agent.observe(range_distance=10.0)
        
        # 保持连接
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
```

### Environment 客户端示例

```python
import asyncio
from star_protocol import EnvironmentClient

async def main():
    # 创建环境客户端
    env = EnvironmentClient(
        server_url="ws://localhost:8765",
        env_id="forest_world"
    )
    
    # 处理 Agent 动作
    @env.on_agent_action("move")
    async def handle_move(message):
        agent_id = message.sender.id
        params = message.payload["parameters"]
        
        # 处理移动逻辑
        new_position = {"x": 10, "y": 15}
        
        # 发送结果
        await env.send_outcome(
            agent_id,
            message.payload["id"],
            {
                "status": "success",
                "new_position": new_position,
                "observation": "你移动到了一片空地上"
            }
        )
    
    # 连接并初始化
    async with env:
        await env.initialize_environment(
            world_size={"width": 100, "height": 100},
            terrain="forest"
        )
        
        # 定期广播状态
        while True:
            await env.broadcast_state_update()
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
```

### Hub 服务器示例

```python
import asyncio
from star_protocol import StarHubServer

async def main():
    # 创建 Hub 服务器
    server = StarHubServer(
        host="0.0.0.0",
        port=8765,
        enable_auth=False,
        enable_validation=True
    )
    
    # 启动服务器
    async with server:
        print("Star Protocol Hub 服务器已启动...")
        print(f"监听地址: ws://{server.host}:{server.port}")
        
        # 保持运行
        while server.is_running:
            # 显示统计信息
            stats = server.get_stats()
            print(f"活跃连接: {stats['active_connections']}")
            
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
```

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                        Star Server                          │
│                     (WebSocket Hub)                         │
└─────────────┬───────────────┬───────────────┬───────────────┘
              │               │               │
    ┌─────────▼─────────┐ ┌───▼─────┐ ┌───────▼───────┐
    │      Agent        │ │   Env   │ │     Human     │
    │   (AI Client)     │ │(Virtual │ │  (Web Client) │
    │                   │ │ World)  │ │               │
    └───────────────────┘ └─────────┘ └───────────────┘
```

## 项目结构

```
star_protocol/
├── protocol/           # 协议核心定义
│   ├── types.py        # 消息类型和数据结构
│   ├── messages.py     # 消息构建和解析
│   └── validation.py   # 消息验证和权限检查
├── client/             # 客户端实现
│   ├── base.py         # 基础客户端类
│   ├── agent.py        # Agent 客户端
│   ├── environment.py  # Environment 客户端
│   └── human.py        # Human 客户端
├── hub/                # Hub 服务端实现
│   ├── server.py       # WebSocket 服务器
│   ├── session.py      # 会话管理
│   ├── router.py       # 消息路由
│   └── auth.py         # 认证授权
├── utils/              # 工具函数
│   ├── logger.py       # 日志工具
│   └── config.py       # 配置管理
└── exceptions.py       # 异常定义
```

## 消息格式

### 基本消息结构

```json
{
  "type": "message",
  "sender": {
    "id": "agent_001",
    "type": "agent"
  },
  "recipient": {
    "id": "env_001", 
    "type": "env"
  },
  "timestamp": "2025-01-01T10:30:00Z",
  "payload": {
    "type": "action",
    "id": "unique_message_id",
    "action": "move",
    "parameters": {"direction": "north"}
  }
}
```

### 动作消息

```json
{
  "type": "action",
  "id": "unique_message_id",
  "action": "action_name",
  "parameters": {}
}
```

### 结果消息

```json
{
  "type": "outcome",
  "id": "unique_message_id",
  "outcome": "outcome result",
  "outcome_type": "dict"
}
```

## 配置

### 服务器配置文件 (star_protocol.toml)

```toml
[server]
host = "0.0.0.0"
port = 8765
enable_auth = false
enable_validation = true
max_connections = 1000

[auth]
jwt_secret = "your-secret-key"
token_expiry_hours = 24
enable_api_keys = true

[logging]
level = "INFO"
log_file = "logs/star_protocol.log"
json_format = false
```

### 环境变量

```bash
STAR_HOST=0.0.0.0
STAR_PORT=8765
STAR_ENABLE_AUTH=false
STAR_LOG_LEVEL=INFO
```

## 开发

### 安装开发依赖

```bash
pip install -e ".[dev]"
```

### 运行测试

```bash
pytest
```

### 代码格式化

```bash
black star_protocol/
isort star_protocol/
```

### 类型检查

```bash
mypy star_protocol/
```

## 示例

查看 `examples/` 目录获取更多示例：

- `basic_agent.py` - 基础 Agent 示例
- `simple_environment.py` - 简单环境示例  
- `multi_agent_demo.py` - 多智能体协作示例
- `human_interface.py` - 人类用户接口示例

## 文档

完整文档请访问: [https://star-protocol.readthedocs.io/](https://star-protocol.readthedocs.io/)

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v1.0.0
- 初始版本发布
- 支持 Agent、Environment、Human、Hub 四种角色
- 实现实时通信和广播机制
- 添加权限控制和认证系统
- 提供完整的类型注解和文档