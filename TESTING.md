# Star Protocol Python SDK - 测试指南

## 快速测试

### 1. 验证核心功能

```bash
uv run python verify.py
```

应该看到所有测试通过 ✅

### 2. 端到端测试

**步骤 1**: 在一个终端启动 Hub Server

```bash
uv run python -m star_protocol.cli
```

应该看到：
```
🚀 Starting Star Protocol Hub on 0.0.0.0:8765
📡 WebSocket endpoint: ws://0.0.0.0:8765/ws/{role}/{client_id}
🏥 Health check: http://0.0.0.0:8765/health
INFO:     Uvicorn running on http://0.0.0.0:8765 (Press CTRL+C to quit)
```

**步骤 2**: 在另一个终端运行测试

```bash
uv run python examples/test_e2e.py
```

应该看到类似输出：
```
============================================================
Star Protocol 端到端测试
============================================================

✅ Agent 已连接并加入环境
✅ User 已连接并加入环境

------------------------------------------------------------
👤 User 提问: 什么是 Star Protocol?
🤖 Agent 收到问题: 什么是 Star Protocol?
🤖 Agent 已回答
👤 User 收到回答: 这是对 '什么是 Star Protocol?' 的回答
------------------------------------------------------------
👤 User 提问: 如何使用这个 SDK?
🤖 Agent 收到问题: 如何使用这个 SDK?
🤖 Agent 已回答
👤 User 收到回答: 这是对 '如何使用这个 SDK?' 的回答
------------------------------------------------------------
👤 User 提问: 支持哪些客户端类型?
🤖 Agent 收到问题: 支持哪些客户端类型?
🤖 Agent 已回答
👤 User 收到回答: 这是对 '支持哪些客户端类型?' 的回答
------------------------------------------------------------

✅ 测试完成！
```

### 3. 检查 Hub Server 状态

在 Hub Server 运行时，可以访问：

- **健康检查**: http://localhost:8765/health
- **统计信息**: http://localhost:8765/stats
- **环境列表**: http://localhost:8765/environments

```bash
# 使用 curl 测试
curl http://localhost:8765/health
curl http://localhost:8765/stats
curl http://localhost:8765/environments
```

## 单元测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/models/test_models.py -v

# 查看覆盖率
uv run pytest --cov=star_protocol --cov-report=html
```

## 常见问题

### 连接失败

**问题**: `ConnectionError: Failed to connect`

**解决**:
1. 确认 Hub Server 正在运行
2. 检查端口 8765 是否被占用
3. 确认 URL 格式正确：`ws://localhost:8765`

### 消息未收到

**问题**: Agent 或 User 没有收到消息

**解决**:
1. 确认已加入环境（状态为 IN_ENV）
2. 检查 recipient 是否正确
3. 查看 Hub Server 日志

### 示例运行错误

**问题**: `examples/simple_qa.py` 运行出错

**解决**:
- 使用简化版本：`uv run python examples/test_e2e.py`
- 手动启动 Hub Server，避免多进程问题

## 开发调试

### 启用调试日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 查看消息流

在 Hub Server 启动时添加 `--log-level debug`:

```bash
uv run python -m star_protocol.cli --log-level debug
```

## 性能测试

```bash
# TODO: 添加性能测试脚本
# uv run python tests/performance/test_throughput.py
```
