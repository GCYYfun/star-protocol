# Star Protocol - API 参考文档

本文档提供 Star Protocol Python SDK 的完整 API 参考。

## 目录

- [客户端类](#客户端类)
  - [BaseClient](#baseclient)
  - [AgentClient](#agentclient)
  - [EnvironmentClient](#environmentclient)
  - [HumanClient](#humanclient)
  - [MonitorClient](#monitorclient)
- [数据模型](#数据模型)
- [异常类型](#异常类型)
- [Mixin 功能](#mixin-功能)

---

## 客户端类

### BaseClient

所有客户端的基类，提供核心连接和消息功能。

#### 构造函数

```python
BaseClient(
    client_id: str,
    monitorable: bool = False,
    reconnectable: bool = False
)
```

**参数：**
- `client_id` (str): 客户端唯一标识符
- `monitorable` (bool): 是否启用监控功能，默认 False
- `reconnectable` (bool): 是否启用自动重连，默认 False

#### 核心方法

##### connect()

```python
async def connect(self, url: str) -> None
```

连接到 Hub。

**参数：**
- `url` (str): Hub 的 WebSocket URL，格式：`ws://host:port`

**抛出：**
- `StarConnectionError`: 连接失败

**示例：**
```python
await client.connect("ws://localhost:8765")
```

##### disconnect()

```python
async def disconnect() -> None
```

断开与 Hub 的连接。

##### start()

```python
async def start() -> None
```

启动客户端，开始接收和处理消息。

##### stop()

```python
async def stop() -> None
```

停止客户端，停止接收消息。

##### run()

```python
async def run() -> None
```

运行客户端消息循环（阻塞直到断开连接）。

##### send()

```python
async def send(self, envelope: Envelope) -> None
```

发送消息信封。

**参数：**
- `envelope` (Envelope): 消息信封对象

#### 上下文管理器

```python
async with BaseClient("client_01") as client:
    await client.connect("ws://localhost:8765")
    # 自动调用 start() 和 stop()
```

#### 属性

- `client_id` (str): 客户端 ID
- `role` (ClientRole): 客户端角色
- `state` (ClientState): 当前状态
- `current_env` (Optional[str]): 当前所在环境 ID

---

### AgentClient

Agent 客户端，用于执行动作并接收结果。

#### 构造函数

```python
AgentClient(
    client_id: str,
    monitorable: bool = False,
    reconnectable: bool = False
)
```

#### 方法

##### join_environment()

```python
async def join_environment(self, env_id: str) -> None
```

加入指定环境。

**参数：**
- `env_id` (str): 环境 ID

##### leave_environment()

```python
async def leave_environment() -> None
```

离开当前环境。

##### send_action()

```python
async def send_action(
    self,
    recipient: str,
    action_name: str,
    params: dict = None
) -> None
```

发送动作给 Environment。

**参数：**
- `recipient` (str): 接收者 ID（Environment）
- `action_name` (str): 动作名称
- `params` (dict): 动作参数，默认 {}

**示例：**
```python
await agent.send_action(
    recipient="env_01",
    action_name="move",
    params={"x": 10, "y": 20}
)
```

#### 回调方法（需要重写）

##### on_outcome()

```python
async def on_outcome(self, sender: str, content: dict) -> None
```

处理 Environment 返回的结果。

**参数：**
- `sender` (str): 发送者 ID
- `content` (dict): 结果内容

##### on_event()

```python
async def on_event(self, sender: str, content: dict) -> None
```

处理 Environment 广播的事件。

**参数：**
- `sender` (str): 发送者 ID
- `content` (dict): 事件内容

##### on_stream()

```python
async def on_stream(self, sender: str, content: dict) -> None
```

处理 Environment 发送的流式数据。

**参数：**
- `sender` (str): 发送者 ID
- `content` (dict): 流式数据内容

---

### EnvironmentClient

Environment 客户端，用于处理动作并返回结果。

#### 构造函数

```python
EnvironmentClient(
    client_id: str,
    monitorable: bool = False,
    reconnectable: bool = False
)
```

#### 方法

##### send_outcome()

```python
async def send_outcome(
    self,
    recipient: str,
    content: dict
) -> None
```

发送结果给 Agent。

**参数：**
- `recipient` (str): 接收者 ID（Agent）
- `content` (dict): 结果内容

##### broadcast_event()

```python
async def broadcast_event(
    self,
    event_type: str,
    content: dict
) -> None
```

广播事件给环境内所有客户端。

**参数：**
- `event_type` (str): 事件类型
- `content` (dict): 事件内容

##### broadcast_stream()

```python
async def broadcast_stream(
    self,
    stream_type: str,
    content: dict
) -> None
```

广播流式数据。

**参数：**
- `stream_type` (str): 流类型
- `content` (dict): 流数据内容

#### 回调方法（需要重写）

##### on_action()

```python
async def on_action(self, sender: str, content: dict) -> None
```

处理 Agent 发送的动作。

**参数：**
- `sender` (str): 发送者 ID
- `content` (dict): 动作内容，包含 `name` 和 `params`

---

### MonitorClient

Monitor 客户端，用于监控其他客户端的状态和消息。

#### 构造函数

```python
MonitorClient(
    client_id: str,
    reconnectable: bool = False
)
```

#### 方法

##### subscribe_to_client()

```python
async def subscribe_to_client(self, target_client_id: str) -> None
```

订阅指定客户端的监控数据。

**参数：**
- `target_client_id` (str): 目标客户端 ID

##### unsubscribe_from_client()

```python
async def unsubscribe_from_client(self, target_client_id: str) -> None
```

取消订阅指定客户端。

**参数：**
- `target_client_id` (str): 目标客户端 ID

#### 回调方法（需要重写）

##### on_monitor_data()

```python
async def on_monitor_data(
    self,
    source_client_id: str,
    data_type: str,
    data: dict
) -> None
```

处理监控数据。

**参数：**
- `source_client_id` (str): 数据来源客户端 ID
- `data_type` (str): 数据类型（如 "state_change", "message_sent"）
- `data` (dict): 监控数据内容

---

## 数据模型

### Envelope

消息信封，所有消息的外层包装。

```python
class Envelope(BaseModel):
    type: EnvelopeType          # 消息类型
    sender: str                 # 发送者 ID
    recipient: str              # 接收者 ID
    data: Union[...]            # 消息载荷
    id: str                     # 消息 ID（自动生成）
    timestamp: int              # 时间戳（自动生成）
```

### EnvelopeType

消息类型枚举。

```python
class EnvelopeType(str, Enum):
    SYSTEM = "system"           # 系统消息
    MESSAGE = "message"         # 业务消息
    BROADCAST = "broadcast"     # 广播消息
    MONITOR = "monitor"         # 监控消息
```

### MessageType

业务消息类型。

```python
class MessageType(str, Enum):
    ACTION = "action"           # 动作
    OUTCOME = "outcome"         # 结果
```

### BroadcastType

广播消息类型。

```python
class BroadcastType(str, Enum):
    EVENT = "event"             # 事件
    STREAM = "stream"           # 流式数据
```

### MonitorType

监控消息类型。

```python
class MonitorType(str, Enum):
    CTRL = "ctrl"               # 控制消息
    DATA = "data"               # 监控数据
    NOTIFY = "notify"           # 通知消息
```

---

## 异常类型

### StarProtocolError

所有异常的基类。

```python
class StarProtocolError(Exception):
    pass
```

### StarConnectionError

连接相关错误。

```python
class StarConnectionError(StarProtocolError):
    pass
```

### StarMessageError

消息相关错误。

```python
class StarMessageError(StarProtocolError):
    pass
```

### StarStateError

状态相关错误。

```python
class StarStateError(StarProtocolError):
    pass
```

---

## Mixin 功能

### MonitorableMixin

为客户端添加可监控功能。

#### 方法

##### enable_monitoring()

```python
async def enable_monitoring(
    self,
    level: MonitorLevel = MonitorLevel.INFO,
    data_types: List[str] = None
) -> None
```

启用监控。

**参数：**
- `level` (MonitorLevel): 监控级别（DEBUG, INFO, WARNING, ERROR）
- `data_types` (List[str]): 要监控的数据类型列表，None 表示全部

##### disable_monitoring()

```python
async def disable_monitoring() -> None
```

禁用监控。

### ReconnectableMixin

为客户端添加自动重连功能。

**参数（构造函数）：**
- `max_retries` (int): 最大重试次数，默认 5
- `retry_delay` (float): 重试延迟（秒），默认 2.0
- `backoff_factor` (float): 退避因子，默认 2.0

---

## 完整示例

### 创建自定义 Agent

```python
from star_protocol import AgentClient
from star_protocol.client.mixins.monitorable import MonitorLevel

class MyAgent(AgentClient):
    def __init__(self, client_id: str):
        super().__init__(
            client_id=client_id,
            monitorable=True,
            reconnectable=True
        )
    
    async def on_outcome(self, sender: str, content: dict):
        print(f"结果: {content}")
    
    async def on_event(self, sender: str, content: dict):
        print(f"事件: {content}")

async def main():
    agent = MyAgent("my_agent")
    
    async with agent:
        await agent.connect("ws://localhost:8765")
        await agent.enable_monitoring(level=MonitorLevel.DEBUG)
        await agent.join_environment("my_env")
        
        await agent.send_action("my_env", "test", {"data": "test"})
        
        await agent.run()
```

---

## 更多信息

- [快速开始](quickstart.md)
- [使用指南](user_guide.md)
- [协议规范](../SPEC.md)
- [示例代码](../examples/)
