# Star Protocol 规范文档

## 属性概览

| 属性 | 描述 |
| --- | --- |
| **版本** | v1.6 |
| **状态** | Draft |
| **协议层级** | Application Layer (Over WebSocket) |
| **传输格式** | JSON |
| **最后更新** | 2026-02-06 |

---

## 1. 概述 (Overview)

**Star Protocol** 是一个专为 **多智能体系统 (Multi-Agent Systems, MAS)** 设计的轻量级、强类型协作通信协议。它采用 **Hub-Spoke** 拓扑结构，支持 Agent（智能体）、Environment（环境）与 Human（人类）之间的实时异构协作。

### 1.1 核心设计原则

* **严格多态 (Strict Polymorphism)**：内层载荷 (Payload) 的结构和类型定义完全取决于外层信封 (Envelope) 的 `type` 字段。这种设计确保了路由层与业务层的解耦。
* **环境即容器 (Environment as Room)**：Client 连接后默认处于私有状态 (Home)。必须显式加入特定的 Environment（类似于聊天室或游戏房间）才能与其他 Client 进行广播或交互。

---

## 2. 架构定义 (Architecture)

### 2.1 整体拓扑

系统采用星型（Hub-Spoke）架构，Hub Server 作为中央路由器，负责转发各端消息。

```
graph TD
    subgraph Clients
        Agent[Agent Client - Intelligent]
        Env[Environment Client - World Logic]
        Human[Human Client - Observer & Player]
    end

    Hub((Hub Server - Router))

    Agent <==>|WebSocket| Hub
    Env <==>|WebSocket| Hub
    Human <==>|WebSocket| Hub

    style Hub fill:#f9f,stroke:#333,stroke-width:2px
```

## 3. 连接与生命周期

### 3.1 WebSocket 端点

连接 URL 格式如下：
`ws://<host>:<port>/<role>/<client_id>`

* **role**: 客户端角色 (e.g., `agent`, `environment`, `human`)
* **client_id**: 客户端唯一标识

### 3.2 状态流转

客户端连接后存在两种主要状态：

1. **Home (初始状态)**
* **权限**: 只能收发 `system` 类型消息。
* **行为**: 进行身份验证、列出房间、申请加入环境。


2. **In-Env (环境内状态)**
* **权限**: 可收发 `message`, `broadcast` 类型消息。
* **行为**: 业务交互、感知环境。



---

## 4. 协议类型定义 (Type Definitions)

Star Protocol 采用双层结构：**Envelope (路由层)** + **Payload (业务层)**。

### 4.1 Layer 1: Envelope (路由层)

Envelope 是所有数据包的通用外壳，其 `type` 字段充当鉴别器 (Discriminator)，决定 `data` 的结构。

```typescript
interface Envelope {
  /** 消息唯一标识 (UUID v4) */
  id: string;

  /** 发送时间戳 (Unix ms) */
  timestamp: number;

  /** 决定 Payload 类型的关键字段 */
  type: EnvelopeType;

  /** 发送者 ID */
  sender: string;

  /** 接收者 ID 或 特殊目标 ("hub", "@all", "@env") */
  recipient: string;

  /** 业务载荷，类型取决于 Envelope.type */
  data: SystemPayload | MessagePayload | BroadcastPayload;
}

```

#### 4.1.1 EnvelopeType 枚举

| 类型值 | 含义 | 通信模式 | 对应 Payload 类型 |
| --- | --- | --- | --- |
| `system` | 系统控制 | Hub 处理或发出 | `SystemPayload` |
| `message` | 业务消息 | 点对点 (Unicast) | `MessagePayload` |
| `broadcast` | 环境广播 | 组播 (Multicast) | `BroadcastPayload` |
| `monitor` | 监控数据 | Hub 转发 | `MonitorPayload` |

---

### 4.2 Layer 2: Payload (业务层)

#### A. System Payload

* **条件**: `Envelope.type == "system"`
* **用途**: 连接管理、房间控制、错误报告。

```typescript
interface SystemPayload {
  type: SystemType;
  content: any;
}

enum SystemType {
  ERROR = "error",      // 错误信息
  CTRL = "ctrl",        // 房间控制 (join, leave)
  NOTIFY = "notify"     // 系统通知 (joined, left)
}

```

#### D. Monitor Payload (v1.6 新增)

* **条件**: `Envelope.type == "monitor"`
* **用途**: 监控数据的传输和控制。

```typescript
interface MonitorPayload {
  type: MonitorType;
  content: any;
}

enum MonitorType {
  CTRL = "ctrl",        // 控制命令 (enable, disable, subscribe, unsubscribe)
  DATA = "data",        // 监控数据 (state_change, message_sent, etc.)
  NOTIFY = "notify"     // 通知 (monitoring_enabled, subscribed, etc.)
}


```

#### B. Message Payload

* **条件**: `Envelope.type == "message"`
* **用途**: Agent 与 Environment 之间的核心业务交互。

```typescript
interface MessagePayload {
  type: MessageType;
  content: any;
}

enum MessageType {
  ACTION = "action",    // Agent 发出的动作
  OUTCOME = "outcome",  // Environment 返回的结果
  STREAM = "stream",    // 点对点数据流 (如 Token 流)
  EVENT = "event"       // 定向事件通知
}

```

#### C. Broadcast Payload

* **条件**: `Envelope.type == "broadcast"`
* **用途**: 环境向多个 Agent 广播状态。

```typescript
interface BroadcastPayload {
  type: BroadcastType;
  content: any;
}

enum BroadcastType {
  EVENT = "event",      // 环境事件 (天气变化, 时间流逝)
  STREAM = "stream"     // 广播数据流 (如解说语音)
}

```

---

## 5. 消息示例 (Examples)

### 5.1 System 通道 (加入房间)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1620000000000,
  "type": "system",
  "sender": "agent_01",
  "recipient": "hub",
  "data": {
    "type": "ctrl",
    "content": {
      "op": "join",
      "env_id": "room_1"
    }
  }
}

```

### 5.2 Message 通道 (执行动作)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440100",
  "timestamp": 1620000000100,
  "type": "message",
  "sender": "agent_01",
  "recipient": "env_main",
  "data": {
    "type": "action",
    "content": {
      "name": "move",
      "x": 10,
      "y": 5
    }
  }
}

```

### 5.3 Broadcast 通道 (环境事件)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440200",
  "timestamp": 1620000000200,
  "type": "broadcast",
  "sender": "env_main",
  "recipient": "@all",
  "data": {
    "type": "event",
    "content": {
      "name": "night_fall",
      "vision_modifier": 0.5
    }
  }
}

```

---

## 6. 错误处理

所有层级的错误统一通过 `system` 通道返回给发送者。

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440400",
  "timestamp": 1620000000400,
  "type": "system",
  "sender": "hub",
  "recipient": "agent_01",
  "data": {
    "type": "error",
    "content": {
      "code": 404,
      "msg": "Recipient 'env_main' not found or offline",
      "original_msg_id": "prev_msg_uuid"
    }
  }
}

```

---

## 7. Monitor 功能 (v1.6 新增)

### 7.1 概述

Monitor 功能允许特殊的 Monitor 客户端订阅并接收其他 Client 的监控数据，用于调试、分析和可视化。所有监控数据通过 Hub 转发，无需 Client 启动额外服务器。

### 7.2 架构

```
Client (被监控)     Hub (转发)      Monitor (观察)
      │                │                │
      │─ enable ──────►│                │
      │                │◄─ subscribe ───│
      │                │                │
      │─ data ────────►│                │
      │                │─ forward ─────►│
```

### 7.3 启用监控

Client 向 Hub 发送启用监控请求：

```json
{
  "id": "uuid",
  "timestamp": 1234567890,
  "type": "monitor",
  "sender": "agent_01",
  "recipient": "hub",
  "data": {
    "type": "ctrl",
    "content": {
      "op": "enable",
      "level": "DEBUG"
    }
  }
}
```

**监控级别**：
- `DEBUG`: 所有活动（包括每条消息）
- `INFO`: 状态变化和重要事件
- `WARNING`: 仅警告
- `ERROR`: 仅错误

### 7.4 Monitor 订阅

Monitor 向 Hub 订阅特定 Client 的监控数据：

```json
{
  "id": "uuid",
  "timestamp": 1234567890,
  "type": "monitor",
  "sender": "monitor_01",
  "recipient": "hub",
  "data": {
    "type": "ctrl",
    "content": {
      "op": "subscribe",
      "target_client_id": "agent_01"
    }
  }
}
```

### 7.5 监控数据发送

Client 发送监控数据到 Hub：

```json
{
  "id": "uuid",
  "timestamp": 1234567890,
  "type": "monitor",
  "sender": "agent_01",
  "recipient": "hub",
  "data": {
    "type": "data",
    "content": {
      "data_type": "state_change",
      "data": {
        "old_state": "HOME",
        "new_state": "IN_ENV",
        "env_id": "room_1"
      },
      "timestamp": 1234567890
    }
  }
}
```

### 7.6 Hub 转发给 Monitor

Hub 转发监控数据给订阅的 Monitor（保持原始 sender）：

```json
{
  "id": "uuid",
  "timestamp": 1234567890,
  "type": "monitor",
  "sender": "agent_01",
  "recipient": "monitor_01",
  "data": {
    "type": "data",
    "content": {
      "data_type": "state_change",
      "data": {
        "old_state": "HOME",
        "new_state": "IN_ENV",
        "env_id": "room_1"
      },
      "timestamp": 1234567890
    }
  }
}
```

**注意**：Hub 转发时保持 `sender` 为原始 Client ID，这样 Monitor 可以直接从 `envelope.sender` 识别数据来源。

### 7.7 监控数据类型

| 数据类型 | 说明 | 示例数据 |
|---------|------|---------|
| `register` | Client 注册信息 | `{client_id, role, timestamp}` |
| `state_change` | 状态变化 | `{old_state, new_state, env_id}` |
| `message_sent` | 消息发送 | `{envelope_type, recipient, payload_type}` |
| `message_received` | 消息接收 | `{envelope_type, sender, payload_type}` |
| `error` | 错误信息 | `{code, message, details}` |

### 7.8 完整交互示例

```
1. Agent 启用监控
   Agent → Hub: {type: "monitor", sender: "agent_01", data: {type: "ctrl", content: {op: "enable"}}}
   Hub → Agent: {type: "monitor", sender: "hub", data: {type: "notify", content: {event: "monitoring_enabled"}}}

2. Monitor 订阅 Agent
   Monitor → Hub: {type: "monitor", sender: "monitor_01", data: {type: "ctrl", content: {op: "subscribe", target: "agent_01"}}}
   Hub → Monitor: {type: "monitor", sender: "hub", data: {type: "notify", content: {event: "subscribed"}}}

3. Agent 加入环境（触发监控数据）
   Agent → Hub: {type: "system", sender: "agent_01", data: {type: "ctrl", content: {op: "join"}}}
   Agent → Hub: {type: "monitor", sender: "agent_01", data: {type: "data", content: {data_type: "state_change", ...}}}
   Hub → Monitor: {type: "monitor", sender: "agent_01", data: {type: "data", content: {data_type: "state_change", ...}}}
                                      ↑ 保持原始 sender

4. Agent 发送消息（触发监控数据）
   Agent → Env: {type: "message", sender: "agent_01", ...}
   Agent → Hub: {type: "monitor", sender: "agent_01", data: {type: "data", content: {data_type: "message_sent", ...}}}
   Hub → Monitor: {type: "monitor", sender: "agent_01", data: {type: "data", content: {data_type: "message_sent", ...}}}
                                      ↑ 保持原始 sender
```

**关键点**：
- Hub 转发 `monitor` 类型的 `data` 消息时，**保持原始 `sender`**
- Monitor 可以直接从 `envelope.sender` 识别数据来源
- Hub 只在发送 `notify` 消息时使用 `sender: "hub"`

---

## 8. 版本历史

- **v1.6** (2026-02-06): 新增 Monitor 功能，通过 Hub 转发监控数据
- **v1.5** (2026-01-31): 初始版本，定义核心协议