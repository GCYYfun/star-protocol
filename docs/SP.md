# Star Protocol 规范文档

## 属性概览

| 属性 | 描述 |
| --- | --- |
| **版本** | v1.0 |
| **状态** | Draft |
| **协议层级** | Application Layer (Over WebSocket) |
| **传输格式** | JSON |
| **最后更新** | 2026-02-11 |

---

## 目录

- [属性概览](#属性概览)
- [1. 概述 (Overview)](#1-概述-overview)
  - [1.1 核心设计原则](#11-核心设计原则)
- [2. 架构定义 (Architecture)](#2-架构定义-architecture)
  - [2.1 整体拓扑](#21-整体拓扑)
- [3. 连接与生命周期](#3-连接与生命周期)
  - [3.1 WebSocket 端点](#31-websocket-端点)
  - [3.2 状态流转](#32-状态流转)
- [4. 协议类型定义 (Type Definitions)](#4-协议类型定义-type-definitions)
  - [4.1 Layer 1: Envelope (路由层)](#41-layer-1-envelope-路由层)
    - [4.1.1 EnvelopeType 枚举](#411-envelopetype-枚举)
  - [4.2 Layer 2: Payload (业务层)](#42-layer-2-payload-业务层)
    - [A. System Payload](#a-system-payload)
    - [B. Message Payload](#b-message-payload)
    - [C. Broadcast Payload](#c-broadcast-payload)
    - [D. Monitor Payload](#d-monitor-payload)
- [5. System Envelope (系统信件)](#5-system-envelope-系统信件)
  - [5.1 概述](#51-概述)
  - [5.2 交互类型与数据结构 (SystemType)](#52-交互类型与数据结构-systemtype)
    - [5.2.1 `ctrl` (控制指令)](#521-ctrl-控制指令)
    - [5.2.2 `notify` (通知)](#522-notify-通知)
    - [5.2.3 `error` (错误回调)](#523-error-错误回调)
  - [5.3 完整交互示例：加入环境](#53-完整交互示例加入环境)
- [6. Message Envelope (消息信件)](#6-message-envelope-消息信件)
  - [6.1 概述](#61-概述)
  - [6.2 交互类型与数据结构 (MessageType)](#62-交互类型与数据结构-messagetype)
    - [6.2.1 `action` (动作请求)](#621-action-动作请求)
    - [6.2.2 `outcome` (操作结果反馈)](#622-outcome-操作结果反馈)
    - [6.2.3 `event` (私有/特定事件通知)](#623-event-私有特定事件通知)
    - [6.2.4 `stream` (单播流式数据)](#624-stream-单播流式数据)
  - [6.3 完整交互示例：执行动作与结果反馈](#63-完整交互示例执行动作与结果反馈)
- [7. Broadcast Envelope (广播信件)](#7-broadcast-envelope-广播信件)
  - [7.1 概述](#71-概述)
  - [7.2 交互类型与数据结构 (BroadcastType)](#72-交互类型与数据结构-broadcasttype)
    - [7.2.1 `event` (全局环境事件)](#721-event-全局环境事件)
    - [7.2.2 `stream` (数据公共流)](#722-stream-数据公共流)
  - [7.3 完整交互示例：全局环境变更](#73-完整交互示例全局环境变更)
- [8. Monitor Envelope (监控信件)](#8-monitor-envelope-监控信件)
  - [8.1 概述](#81-概述)
  - [8.2 架构](#82-架构)
  - [8.3 交互类型与数据结构 (MonitorType)](#83-交互类型与数据结构-monitortype)
    - [8.3.1 `ctrl` (控制指令)](#831-ctrl-控制指令)
    - [8.3.2 `data` (透传监控数据)](#832-data-透传监控数据)
    - [8.3.3 `notify` (监控通知)](#833-notify-监控通知)
  - [8.4 完整交互示例](#84-完整交互示例)
- [Changelog](#changelog)


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
or
```
┌─────────────────┐          ┌─────────────────┐          ┌──────────────────┐
│   Agent Client  │          │    Hub Server   │          │Environment Client│
│ (Intelligent)   │  ◄────►  │   (Router)      │  ◄────►  │ (World Logic)    │
└─────────────────┘          └─────────────────┘          └──────────────────┘
                                      ▲                             
                                      │ WebSocket
                                      │
                                      │
                                      │
                                      ▼
                            ┌───────────────────┐         
                            │    Human Client   │
                            │(Observer & Player)│
                            └───────────────────┘

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

```
┌─────────────────────────────────────────────────────────────┐
│                         Envelope                            │
│  负责消息路由、寻址、验证                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                      Payload                        │    │
│  │  负责具体业务逻辑、动作处理、状态同步                     │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 4.1 Layer 1: Envelope (路由层)

Envelope 是所有数据包的通用外壳，其 `type` 字段充当鉴别器 (Discriminator)，决定 `payload` 的结构。

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
  payload: SystemPayload | MessagePayload | BroadcastPayload | MonitorPayload;
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

#### D. Monitor Payload

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
---

## 5. System Envelope (系统信件)

### 5.1 概述

System Envelope（系统控制信件）是不涉及特定业务逻辑的底层控制协议层。它的主要目标是管理客户端的连接状态、分配和进入房间（Environment）、进行错误报告以及系统级的通知。
所有与 **Hub Server** 直接交互的控制指令必须通过此通道发送。


### 5.2 交互类型与数据结构 (SystemType)

**本节概览 (Mini-TOC)**
- [5.2.1 `ctrl`：控制指令](#521-ctrl-控制指令)
- [5.2.2 `notify`：系统通知](#522-notify-系统通知)
- [5.2.3 `error`：错误回调](#523-error-错误回调)

为了保证底层协议解析的稳定性，System Envelope 下辖的 3 种子类型拥有固定的字段结构约定。

#### 5.2.1 `ctrl` (控制指令)

- **发送方**：任意 Client
- **接收方**：Hub Server (`recipient: "hub"`)
- **说明**：向 Hub Server 申请执行的操作控制指令。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface SystemCtrlContent {
  op: "join" | "leave" | string; // 具体操作命令，如加入房间等
  [key: string]: any; // 可基于具体的命令补充附加可选参数，例如 env_id 
}
```

**`SystemCtrlContent` 负载详情举例**：
| `op` | 说明 | 附加参数示例数据 |
|---------|------|---------|
| `join` | 加入指定环境 | `{env_id:string}` |
| `leave` | 离开当前环境 | `{env_id:string}` |

#### 5.2.2 `notify` (通知)

- **发送方**：Hub Server
- **接收方**：特定 Client
- **说明**：Hub 服务器对 Client 指令的确认回执或主动推送的状态广播（例如：`status: "joined"`）。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface SystemNotifyContent {
  event: string;       // 通知事件类型
  msg: string; // 通知的消息
  [key: string]: any; // 可选的附带参数集合，由业务所需自行派生
}
```

**`SystemNotifyContent` 负载详情举例**：
| `event` | 说明 | `msg` 示例数据 | 附加参数示例数据 (`[key:string]`) |
|---------|------|---------|---------|
| `joined` | 成功加入环境的广播 | `"agent_01 joined room_1"` | `{env_id:string, roles:string[]}` |
| `left` | 离开环境的广播 | `"agent_01 left room_1"` | `{env_id:string}` |

#### 5.2.3 `error` (错误回调)

- **发送方**：Hub Server / Environment
- **接收方**：特定 Client
- **说明**：执行任何动作失败（如寻址失败，权限不足）时返回包含错误码的硬性说明。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface SystemErrorContent {
  code: number;          // 标准错误码 (类 HTTP 状态码或自定义码)
  msg: string;           // 人类可读的错误明文描述
  original_msg_id?: string; // 选填：造成该错误的原始信封 ID，便于溯源
  details?: any;         // 选填：更详细的错误原因、堆栈信息等扩展排查参数
}
```

### 5.3 完整交互示例：加入环境

以下是一个典型的“Agent 申请加入 Environment”的过程：

**步骤 1：Agent 发起 Join 控制指令（Client -> Hub）**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1620000000000,
  "type": "system",
  "sender": "agent_01",
  "recipient": "hub",
  "payload": {
    "type": "ctrl",
    "content": {
      "op": "join",
      "env_id": "room_1"
    }
  }
}
```

**步骤 2：Hub 返回审批结果/通知（Hub -> Client）**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440005",
  "timestamp": 1620000000100,
  "type": "system",
  "sender": "hub",
  "recipient": "agent_01",
  "payload": {
    "type": "notify",
    "content": {
      "event": "joined",
      "msg": "agent_01 joined room_1"
    }
  }
}
```

---

## 6. Message Envelope (消息信件)

### 6.1 概述

Message Envelope 是 Star Protocol 的**核心业务信件**，主要处理基于单播（Unicast，点对点）形式的领域逻辑交互。在多智能体场景中，它代表着 Agent 执行特定的决策，或者是 Environment 返还具体的动作结果。
使用此通道的客户端**必须处于同一个 Environment 之中**（In-Env 状态）。


### 6.2 交互类型与数据结构 (MessageType)

**本节概览 (Mini-TOC)**
- [6.2.1 `action`：动作请求](#621-action-动作请求)
- [6.2.2 `outcome`：操作结果反馈](#622-outcome-操作结果反馈)
- [6.2.3 `event`：私有/特定事件通知](#623-event-私有特定事件通知)
- [6.2.4 `stream`：单播流式数据](#624-stream-单播流式数据)

这是开发者**大量派生自身业务逻辑**的主要阵地。尽管业务千变万化，为了维持统一的分发和解析接口，这里约束了 4 种子类型的根节点数据结构，允许你在 params 和 data 等字典字段内任意扩充逻辑。

#### 6.2.1 `action` (动作请求)

- **发送方**：Agent / Human
- **接收方**：Environment (`recipient: "env_main"`)
- **说明**：智能体在世界上试图主动执行的一系列能力与动作触发（如：移动、攻击、合成物品）。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface MessageActionContent {
  name: string;        // 动作的唯一标识符 (例如: "move_to", "use_item")
  params?: {           // 可选的动作所需参数对象，业务全权自定义
    [key: string]: any;
  }; 
}
```

#### 6.2.2 `outcome` (操作结果反馈)

- **发送方**：Environment
- **接收方**：特定 Agent / Human
- **说明**：环境在结算完毕上述 Action 后返回的单一执行确认单据。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface MessageOutcomeContent {
  action_ref: string;  // 原始 Action Envelope 的 ID，必须带上以保证回调对照
  success: boolean;    // 此动作是否成功结算或生效
  data?: {             // 选填：若是成功，里面包含了更新后的自身状态、获取资源的详细字典，全权自定义
    [key: string]: any; 
  };
  error?: string;      // 选填：若是失败(success=false)，可直接给出理由说明
}
```

#### 6.2.3 `event` (私有/特定事件通知)

- **发送方**：Environment
- **接收方**：特定 Agent
- **说明**：环境通过单播方式专门派发给单一角色的动态推送（例如当前角色被某个盗贼偷了钱，这不应该被全局知道）。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface MessageEventContent {
  name: string;        // 识别的具体业务事件名称 (如: "conversation")
  data: {              // 推发的数据载荷，全权自定义扩展
    [key: string]: any; 
  };
}
```

**`MessageEventContent` 负载详情举例**：
| `name` | 说明 | `data` 示例数据 |
|---------|------|---------|
| `conversation` | 被特定角色或系统搭话/系统私聊 | `{input:string, speaker_id:string}` |

#### 6.2.4 `stream` (单播流式数据)

- **发送方/接收方**：任意 Client
- **说明**：处理类似对话系统的 LLM Token 流的碎片化推送。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface MessageStreamContent {
  stream_id: string;   // 本次流的唯一会话标识，拼接碎片的依据
  sequence: number;    // 序号，保证流片段是有序到达的 (比如 0、1、2 递增)
  chunk: any;          // 本次碎片的实际内容 (例如单个字串 token，也可以是对象)
  is_end: boolean;     // 标记本段流式传输是否到此结束
}
```

### 6.3 完整交互示例：执行动作与结果反馈

以下模拟一个 Agent 在环境中执行“移动 (move)”动作，并收到环境确定的交互过程。

**步骤 1：Agent 发起动作（Agent -> Env）**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440100",
  "timestamp": 1620000000100,
  "type": "message",
  "sender": "agent_01",
  "recipient": "env_main",
  "payload": {
    "type": "action",
    "content": {
      "name": "move",
      "params":{
        "x": 10,
        "y": 5
      }
    }
  }
}
```

**步骤 2：Environment 返回结算结果（Env -> Agent）**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440150",
  "timestamp": 1620000000250,
  "type": "message",
  "sender": "env_main",
  "recipient": "agent_01",
  "payload": {
    "type": "outcome",
    "content": {
      "action_ref": "550e8400-e29b-41d4-a716-446655440100",
      "success": true,
      "data": {
        "current_pos": {"x": 10, "y": 5},
        "stamina_cost": 2.5
      }
    }
  }
}
```

**事件消息**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440100",
  "timestamp": 1620000000100,
  "type": "message",
  "sender": "env_main",
  "recipient": "agent_01",
  "payload": {
    "type": "event",
    "content": {
      "name": "conversation",
      "data":{
        "input": "今天天气如何？",
        "speaker_id": "system_npc"
      }
    }
  }
}
```

---

## 7. Broadcast Envelope (广播信件)

### 7.1 概述

Broadcast 通道是用于向一个群体分发状态变化的**公共通道**。当环境（或具备高权限的观察端）发生涉及全体或某个组落盘的数据变量更新时，它不再需要逐个给系统内的 Agent 循环发送信息，而是利用特别的标识 (`@all` 或 `@env`) 将信封发出。Hub Server 接到它后会自动进行展开分发。


### 7.2 交互类型与数据结构 (BroadcastType)

**本节概览 (Mini-TOC)**
- [7.2.1 `event`：全局环境事件](#721-event-全局环境事件)
- [7.2.2 `stream`：数据公共流](#722-stream-数据公共流)

Broadcast 是公共集会场所，主要包含以下 2 种子协议类型，它们的大框架也是定型锁死的：

#### 7.2.1 `event` (全局环境事件)

- **发送方**：Environment
- **接收方**：`@all` 或 `@env`
- **说明**：比如时间流逝、全屏天气巨变或系统级的规则公告。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface BroadcastEventContent {
  name: string;        // 识别的具体广播事件名称 (如: "time_passed", "weather_update")
  data: {              // 推发的全局数据载荷，全权自定义扩展
    [key: string]: any; 
  };
}
```

**`BroadcastEventContent` 负载详情举例**：
| `name` | 说明 | `data` 示例数据 |
|---------|------|---------|
| `time_passed` | 时间推进/温度等周期变化 | `{time_of_day:string, temperature:number}` |
| `weather_update` | 天气突变 | `{condition:string, severity:number}` |

#### 7.2.2 `stream` (数据公共流)

- **发送方**：主要为 Environment 等
- **接收方**：`@all` 或 `@env`
- **说明**：供所有观察者接受的公共直播解说信道，或大屏幕实时渲染画面流。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface BroadcastStreamContent {
  stream_id: string;   // 本次广播流的唯一会话标识
  sequence: number;    // 序号，保证流片段是有序解析的
  chunk: any;          // 本次广播帧的实际内容
  is_end: boolean;     // 标记本段公共广播流是否到此结束
}
```

### 7.3 完整交互示例：全局环境变更

以下展示 Environment 触发了“时间推进”全局事件，向所有处于环境内的角色告知：

**步骤 1：Environment 广播事件（Env -> @all）**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440200",
  "timestamp": 1620000000200,
  "type": "broadcast",
  "sender": "env_main",
  "recipient": "@all",
  "payload": {
    "type": "event",
    "content": {
      "name": "time_passed",
      "data":{
        "time_of_day": "night",
        "temperature": 15,
        "message": "The sun has set, it's getting colder."
      }
    }
  }
}
```
*注：此消息发出后，Hub 将解析 `@all`，并根据当前的拓扑图，将其拷贝至所有连接且在线状态的目标 Agent/Human 所对应的独立 WebSocket 链路中。*

---

## 8. Monitor Envelope (监控信件)

### 8.1 概述

Monitor Envelope 允许特殊的 Monitor 客户端订阅并接收其他 Client 的监控数据，用于调试、分析和可视化。所有监控数据通过 Hub 转发，无需 Client 启动额外服务器。

### 8.2 架构

```
Client (被监控)     Hub (转发)      Monitor (观察)
      │                │                │
      │─ enable ──────►│                │
      │                │◄─ subscribe ───│
      │                │                │
      │─ data ────────►│                │
      │                │─ forward ─────►│
```

### 8.3 交互类型与数据结构 (MonitorType)

**本节概览 (Mini-TOC)**
- [8.3.1 `ctrl`：控制指令](#831-ctrl-控制指令)
- [8.3.2 `data`：透传监控数据](#832-data-透传监控数据)
- [8.3.3 `notify`：监控通知](#833-notify-监控通知)

Monitor 通道作为专用插件性质的存在，其子类型用于控制启停与转发底层报文。

#### 8.3.1 `ctrl` (控制指令)

- **发送方**：Client 或 Monitor 客户端
- **接收方**：Hub Server
- **说明**：向 Hub 发送订阅/取消订阅监控队列的动作。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface MonitorCtrlContent {
  op: "enable" | "disable" | "subscribe" | "unsubscribe";
  [key: string]: any; // 可选，如 `level: "DEBUG"` 或 `target_client_id: "agent_01"` 等参数
}
```
*注：监控级别 `level` 通常包含 `DEBUG`, `INFO`, `WARNING`, `ERROR`*

**`MonitorCtrlContent` 负载详情举例**：
| `op` | 说明 | 附加参数示例数据 |
|---------|------|---------|
| `enable` | 启用全局/特定监控 | `{level:string}` |
| `disable` | 关闭全局/特定监控 | 无附加参数 |
| `subscribe` | 开始订阅特定 Client 数据 | `{target_client_id:string}` |
| `unsubscribe` | 取消订阅特定 Client 数据 | `{target_client_id:string}` |


#### 8.3.2 `data` (透传监控数据)

- **发送方**：Hub Server (转发)
- **接收方**：Monitor 客户端
- **说明**：这里包装的是底下各个具体通讯动作产生时快照下来的原始数据。**注意**：Hub 转发时保持 `sender` 为原始 Client ID，这样 Monitor 可以直接从 `envelope.sender` 识别数据来源。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface MonitorDataContent {
  name: "register" | "state_change" | "message_sent" | "message_received"; 
  data: any;           // 具体的监控负载快照，详情见下表
  timestamp: number;   // 动作发生时的时间戳
}
```

**`MonitorDataContent` 负载详情举例**：
| `name` | 说明 | `data` 示例数据 |
|---------|------|---------|
| `register` | Client 连接并签权信息 | `{client_id:string, role:string, timestamp:number}` |
| `state_change` | Home/In-Env 状态跃迁 | `{old_state:string, new_state:string, env_id:string}` |
| `message_sent` | 发信拦截快照 | `{envelope_type:string, recipient:string, payload_type:string,content:any}` |
| `message_received` | 收信拦截快照 | `{envelope_type:string, sender:string, payload_type:string,content:any}` |

#### 8.3.3 `notify` (监控通知)

- **发送方**：Hub Server
- **接收方**：Client 或 Monitor 客户端
- **说明**：配置订阅成功的确认通知。
- **固定数据结构**：

```typescript
// Envelope.payload.content 的实际内容
interface MonitorNotifyContent {
  event: string;       // 通知事件类型，比如 "subscribed", "enabled"
  msg: string;    // 文字说明
  [key: string]: any; // 可选的附带参数集合，由业务所需自行派生
}
```

**`MonitorNotifyContent` 负载详情举例**：
| `event` | 说明 | `msg` 示例数据 | 附加参数示例数据 (`[key:string]`) |
|---------|------|---------|---------|
| `enabled` | 系统反馈已成功启用监控 | `"Monitoring is now enabled"` | 无附加参数 |
| `subscribed` | 系统反馈已成功订阅某目标 | `"Subscribed to agent_01"` | `{target_client_id:string}` |

### 8.4 完整交互示例

以下展示了启动监控并获取 Agent 动作快照的一套连贯交互。

**步骤 1：Agent 启用监控 (Agent → Hub)**
```json
{
  "id": "uuid_1",
  "timestamp": 1234567890,
  "type": "monitor",
  "sender": "agent_01",
  "recipient": "hub",
  "payload": {
    "type": "ctrl",
    "content": {
      "op": "enable",
      "level": "DEBUG"
    }
  }
}
```

**步骤 2：Hub 通知 Agent 已启用 (Hub → Agent)**
```json
{
  "id": "uuid_2",
  "timestamp": 1234567895,
  "type": "monitor",
  "sender": "hub",
  "recipient": "agent_01",
  "payload": {
    "type": "notify",
    "content": {
      "event": "enabled",
      "msg": "Monitoring is now enabled"
    }
  }
}
```

**步骤 3：独立 Monitor 面板订阅特定 Agent (Monitor → Hub)**
```json
{
  "id": "uuid_3",
  "timestamp": 1234567900,
  "type": "monitor",
  "sender": "monitor_01",
  "recipient": "hub",
  "payload": {
    "type": "ctrl",
    "content": {
      "op": "subscribe",
      "target_client_id": "agent_01"
    }
  }
}
```

**步骤 4：Agent 发生系统状态改变并上报 Monitor Envelope (Agent → Hub)**
```json
{
  "id": "uuid_4",
  "timestamp": 1234568000,
  "type": "monitor",
  "sender": "agent_01",
  "recipient": "hub",
  "payload": {
    "type": "data",
    "content": {
      "name": "state_change",
      "data": {
        "old_state": "HOME",
        "new_state": "IN_ENV",
        "env_id": "room_1"
      },
      "timestamp": 1234568000
    }
  }
}
```

**步骤 5：Hub 向订阅者原样派发（Hub → Monitor），注意发送者未变**
```json
{
  "id": "uuid_5",
  "timestamp": 1234568005,
  "type": "monitor",
  "sender": "agent_01",   // 注意: 发送者保持并透传，直接定位追踪来源
  "recipient": "monitor_01",
  "payload": {
    "type": "data",
    "content": {
      "name": "state_change",
      "data": {
        "old_state": "HOME",
        "new_state": "IN_ENV",
        "env_id": "room_1"
      },
      "timestamp": 1234568000
    }
  }
}
```

---


## Changelog

- **v1.0** (2026-02-11): 初始版本，定义核心协议