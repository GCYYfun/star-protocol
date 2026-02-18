# 交互式 Demo Agent 使用指南

## 概述

`demo_agent.py` 已升级为交互式模式，支持实时输入命令并发送动作到环境。在等待响应时，会显示动态的 Rich 组件，展示随机的状态文字（如"思考中"、"解析中"、"反思中"等），让等待过程更加生动有趣。

## 主要改进

### 1. **交互式命令输入**
- 不再是预设的脚本化动作序列
- 支持用户实时输入命令
- 灵活的参数解析（key=value 格式）

### 2. **动态等待指示器**
使用 `rich.status.Status` 组件显示动态等待状态：
- 🤔 思考中
- 📡 发送中
- ⚙️ 处理中
- 🔍 解析中
- 💭 反思中
- 🎯 执行中

每次发送动作时，会随机选择一个状态消息并配合旋转的 spinner 动画。

### 3. **改进的用户体验**
- 彩色的命令提示符
- 清晰的使用说明
- 优雅的退出机制
- 实时反馈显示

## 使用方法

### 启动步骤

1. **启动 Hub 服务器**（在一个终端窗口）:
```bash
cd /Users/own/Workspace/star_protocol_python
uv run -m star_protocol.server
```

2. **启动 Demo Environment**（在另一个终端窗口）:
```bash
cd /Users/own/Workspace/star_protocol_python
uv run -m examples.demo_env
```

3. **启动交互式 Agent**（在第三个终端窗口）:
```bash
cd /Users/own/Workspace/star_protocol_python
uv run -m examples.demo_agent
```

4. **启动 Monitor Client**（在第四个终端窗口）:
```bash
cd /Users/own/Workspace/star_protocol_python
uv run -m examples.demo_monitor
```
