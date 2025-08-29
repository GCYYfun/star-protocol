# Star Protocol V3 示例

这个目录包含了 Star Protocol V3 的完整运行示例，展示如何使用各个组件进行实际的交互。

## 📁 文件结构

```
examples_v3/
├── README.md                # 本文件 - 示例说明
├── agent_demo.py            # Agent 客户端示例
├── environment_demo.py      # Environment 客户端示例  
├── hub_server_demo.py       # Hub 服务器示例
└── launch_demo.py           # 启动器示例（管理多个 agent client）
```

## 🚀 快速开始

### 1. 启动 Hub 服务器

```bash
# 在终端1中启动 Hub 服务器
cd star_protocol_v3/examples_v3
python hub_server_demo.py --port 8000
```

### 2. 启动 Environment

```bash
# 在终端2中启动环境
python environment_demo.py --hub-url ws://localhost:8000 --env-id world_1
```

### 3. 启动 Agent

```bash
# 在终端3中启动代理
python agent_demo.py --hub-url ws://localhost:8000 --agent-id agent_001 --env-id world_1
```

### 4. 使用启动器（推荐）

```bash
# 一键启动所有组件
python launch_demo.py --agents 2 --port 8000
```

## 🎮 交互示例

一旦所有组件启动，你将看到：

1. **Hub** 管理连接和路由消息
2. **Environment** 模拟游戏世界状态
3. **Agent** 发送动作并接收结果
4. **实时监控** 显示连接状态和消息统计

## 📊 监控功能

每个示例都集成了监控功能：

- **连接统计** - 实时显示活跃连接数
- **消息统计** - 统计发送/接收的消息数量
- **性能指标** - 显示消息处理延迟
- **错误监控** - 记录和显示错误信息

## 🔧 配置选项

### Hub 服务器选项

```bash
python hub_server_demo.py --help
```

- `--port` - 服务器端口（默认: 8000）
- `--host` - 绑定地址（默认: localhost）
- `--monitoring` - 启用监控（默认: True）

### Agent 选项

```bash
python agent_demo.py --help
```

- `--hub-url` - Hub 服务器地址
- `--agent-id` - Agent 唯一标识
- `--env-id` - 目标环境标识
- `--actions` - 要执行的动作数量

### Environment 选项

```bash
python environment_demo.py --help
```

- `--hub-url` - Hub 服务器地址
- `--env-id` - 环境唯一标识
- `--world-size` - 世界大小（网格）
- `--auto-events` - 自动生成事件

## 🎯 使用场景

### 开发测试
使用单独的组件进行功能测试和调试

### 集成验证
使用启动器同时运行多个组件，验证完整的交互流程

### 性能基准
使用多个 Agent 测试 Hub 的并发处理能力

### 监控演示
观察实时的系统指标和性能数据

## 🐛 故障排除

### 连接问题
- 确保 Hub 服务器已启动
- 检查端口是否被占用
- 验证网络连接

### 消息路由问题
- 检查 client_id 和 env_id 是否匹配
- 确认客户端已成功连接到 Hub
- 查看 Hub 日志了解路由详情

### 性能问题
- 减少并发 Agent 数量
- 调整消息发送频率
- 检查系统资源使用情况

## 📝 扩展示例

基于这些基础示例，你可以：

1. **自定义 Agent 行为** - 修改 Agent 的决策逻辑
2. **扩展 Environment** - 添加更复杂的世界模拟
3. **集成外部系统** - 连接数据库、AI 模型等
4. **自定义监控** - 添加业务特定的指标

参考各个示例文件中的代码注释了解更多实现细节。