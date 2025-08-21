# Star Protocol Examples

这个目录包含Star Protocol的完整演示示例，展示了Hub、Environment和Agent之间的交互。


## 基本结构

Star Protocol 采用 Hub-Client 架构：

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Agent Client  │    │   Hub Server    │    │Environment Client│
│                 │◄──►│                 │◄──►│                 │
│  basic_agent.py │    │ hub_server.py   │    │simple_environment│
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              ▲
                              │
                       ┌─────────────────┐
                       │   Human Client  │
                       │                 │
                       └─────────────────┘
```

## 演示组件

### 1. Hub Server (`hub_server_demo.py`)
- **功能**: 中央协调服务器，管理所有客户端连接
- **特性**: 
  - 支持Agent和Environment连接
  - 消息路由和广播
  - 连接状态监控
  - 实时统计输出

### 2. Environment (`environment_demo.py`)
- **功能**: 2D虚拟世界环境
- **特性**:
  - 10x10网格世界
  - 随机生成物品(金币、宝石、药水)
  - Agent动作处理(移动、观察、拾取)
  - 世界状态广播
  - 碰撞检测和边界管理

### 3. Agent (`agent_demo.py`)
- **功能**: 智能Agent客户端
- **特性**:
  - 自主探索和导航
  - 物品收集策略
  - Agent间对话交互
  - 环境观察和决策
  - 实时状态监控

## 快速开始

### 环境要求
- Python 3.13+
- 安装 `uv` 包管理器

### 安装依赖
```bash
cd star_protocol
uv sync  # 安装项目依赖
```

### 启动演示系统

```bash
# 终端1: 启动Hub服务器
uv run examples/hub_server_demo.py --port 9999

# 终端2: 启动环境
uv run examples/environment_demo.py --env-id demo_world

# 终端3+: 启动Agent (可以启动多个)
uv run examples/agent_demo.py --agent-id bot1 --env-id demo_world
uv run examples/agent_demo.py --agent-id bot2 --env-id demo_world
uv run examples/agent_demo.py --agent-id bot3 --env-id demo_world
```

> **注意**: 客户端连接时会自动发送心跳消息来表示连接，而不是发送"connect"消息。这符合Star Protocol的设计规范。



## 运行效果

### Hub Server 输出
```
🌟 Star Protocol Hub Server
==============================
✅ Hub服务器启动成功，监听端口: 9999
📊 [12:34:56] 连接统计: 环境=1, Agent=2, 总计=3
🔄 [12:34:57] 消息路由: action -> environment (agent1)
📡 [12:34:57] 广播事件: agent_moved (environment -> 2 agents)
```

### Environment 输出
```
🌍 Star Protocol Environment Demo  
================================
✅ 环境连接成功! (demo_world)
🎲 生成了 15 个随机物品
👤 Agent agent1 加入世界，位置: (2, 3)
🚶 Agent agent1 移动: (2, 3) → (3, 3)
💎 Agent agent1 拾取了 gem，得分: 15
```

### Agent 输出
```
🤖 Star Protocol Agent Demo
========================
✅ Agent连接成功!
🎯 开始智能行为...
📊 [bot1] 位置: (3, 3) | 得分: 15 | 物品: 2 | 能量: 95 | 🔄
💬 对话来自 bot2: "Hello from bot2! I'm at (1, 5)"
```

## 演示场景

### 1. 基础探索
- Agent自动在世界中移动
- 观察周围环境
- 发现和收集物品
- 监控自身状态

### 2. 多Agent交互
- 多个Agent同时运行
- 相互发现和对话
- 竞争收集物品
- 共享世界信息

### 3. 环境交互
- 动态世界状态
- 实时事件广播
- 物品生成和消失
- 碰撞和边界处理

## 自定义配置

### Environment配置
```python
# 修改世界大小
WORLD_WIDTH = 20
WORLD_HEIGHT = 20

# 修改物品数量
ITEMS_COUNT = 50

# 修改物品类型和价值
ITEM_TYPES = {
    "coin": {"symbol": "💰", "value": 5},
    "gem": {"symbol": "💎", "value": 15},
    "potion": {"symbol": "🧪", "value": 10},
    "crystal": {"symbol": "💠", "value": 25}
}
```

### Agent配置
```python
# 修改行为参数
OBSERVATION_RANGE = 5  # 观察范围
ACTION_INTERVAL = 1    # 动作间隔(秒)
DIALOGUE_PROBABILITY = 0.3  # 对话概率

# 修改移动策略
EXPLORATION_BIAS = 0.7  # 探索倾向
ITEM_ATTRACTION = 2.0   # 物品吸引力
```

## 协议一致性

所有演示代码严格遵循Star Protocol规范:

- **消息格式**: 外层heartbeat/message/error，内层action/outcome/event/stream
- **客户端实现**: 基于BaseStarClient，使用专用AgentClient/EnvironmentClient
- **错误处理**: 完整的异常捕获和错误消息处理
- **监控集成**: 集成monitor系统，实时统计和状态监控

## 故障排除

### 常见问题
1. **连接失败**: 确保Hub服务器先启动
2. **环境未找到**: 确认环境ID一致
3. **端口冲突**: 修改默认端口9999
4. **依赖缺失**: 运行 `uv sync` 安装依赖

### 调试技巧
```bash
# 使用详细输出启动
uv run examples/hub_server_demo.py --port 9999 --verbose

# 检查依赖安装
uv sync --verbose

# 查看uv环境
uv pip list
```

## 扩展开发

基于这些演示，您可以:

1. **创建新环境**: 继承EnvironmentClient，实现自定义世界逻辑
2. **开发智能Agent**: 基于AgentClient，添加AI决策算法
3. **集成外部系统**: 通过Hub连接数据库、API等
4. **构建监控面板**: 使用monitor系统数据创建Web界面