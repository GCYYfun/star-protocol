# Star Protocol Python SDK — API 参考

对应 SDK `0.3.0` 与应用协议 `agent-env-compact/2`。协议字段与职责以 [SP.md](SP.md) 为准；首次运行参见 [quickstart.md](quickstart.md)。下列签名省略 `self`，`async` 方法必须 `await`；签名块是接口说明，不是独立脚本。

## 1. 导入与客户端构造

```python
from star_protocol import (
    AgentClient, EnvironmentClient, HumanClient, MonitorClient,
    Envelope, MessagePayload, BroadcastPayload, SystemPayload,
    COMPACT_PROTOCOL, TERMINAL_STATUSES,
    ActionTimeoutError, ProtocolConflictError, MonitorLevel,
)
from star_protocol.models import (
    MonitorPayload, MonitorType, ToolDefinition, EventDefinition, gen_id,
)
from star_protocol.client import InMemoryStorage
```

```text
BaseClient(client_id: str, role: str, auto_reconnect: bool = False,
           reconnect_interval: float = 5.0, max_reconnect_attempts: int = 10,
           monitorable: bool = False, logger: logging.Logger | None = None)

AgentClient(client_id: str, auto_reconnect: bool = True,
            monitorable: bool = False, logger: logging.Logger | None = None)
EnvironmentClient(client_id: str, auto_reconnect: bool = True,
                  monitorable: bool = False, logger: logging.Logger | None = None)
HumanClient(client_id: str, auto_reconnect: bool = True,
            monitorable: bool = False, logger: logging.Logger | None = None)
MonitorClient(monitor_id: str, storage: InMemoryStorage | None = None, **kwargs)
```

`BaseClient` 是抽象类，子类须实现 `on_message()` 和 `on_broadcast()`。Agent、Environment、Human 自动设置各自角色；它们的构造函数不接受 `role/reconnect_interval/max_reconnect_attempts`。需要调整重连参数时，可设置实例的 `reconnect_interval` 与 `max_reconnect_attempts`。

Monitor 的首参名为 **monitor_id**，其余 `**kwargs` 传给 BaseClient，例如 `auto_reconnect=False`。不要传入重复的 `client_id/role`。`reconnectable/max_retries/retry_delay/backoff_factor` 均不是当前客户端构造参数。

| 属性 | 当前含义 |
|---|---|
| `client_id`、`role` | 连接主体 ID 与角色字符串 |
| `state` | `ClientState.DISCONNECTED / HOME / IN_ENV` |
| `current_env` | 本地环境 ID 或 `None`；成员加入可能先乐观更新，见下一节 |
| `auto_reconnect` | 接收连接错误时是否尝试重连 |
| `reconnect_interval`、`max_reconnect_attempts` | 重连间隔与最大尝试计数 |
| `AgentClient.tools` | 最近收到的工具列表缓存；多对端读取 `specification_for(peer)` |

## 2. 连接与生命周期（所有客户端）

```text
async connect(url: str) -> None
async start() -> None
async stop() -> None
async disconnect() -> None
async run() -> None
async send(envelope: Envelope) -> None
async join_environment(env_id: str) -> None
async leave_environment() -> None
```

- `connect()` 接收基础 URL，如 `ws://127.0.0.1:8765`；自动构建 `/ws/<role>/<client_id>`，建立连接但不启动接收循环。
- `start()` 在后台启动 `run()`。正常使用中只启动一次；重复启动会先停止原循环并断开连接。`run()` 由生命周期管理器驱动，不要在 `start()` 后再手动调用，形成两个接收循环。
- `stop()` 停止接收循环并断开连接；`disconnect()` 只断开连接并重置连接状态。
- `async with client` 的入口只返回客户端，**不会自动 connect/start**；退出会执行 `stop()`。
- Envelope 构造时校验三层结构；`send()` 再校验发送身份及已协商接收契约后发送。网络发送成功不代表远端执行或持久保存。
- Environment 连接即创建自身 `client_id` 对应的环境，不调用 `join_environment()`。
- Agent/Human 的 `join_environment()` 发送 join 后立即更新本地状态，随后默认触发 discover；它不等待 Hub 的 `joined` 确认。`leave_environment()` 同样发送后更新本地状态。

```python
from star_protocol import AgentClient

async def connect_agent(url: str):
    async with AgentClient("agent_api", auto_reconnect=False) as agent:
        agent.configure_capabilities(tools=[], events=[])
        await agent.connect(url)
        await agent.start()
        await agent.join_with_retry("env_main", timeout=10.0)
        # 下一步等待本端与 Env 的声明接收、安装就绪，再发送业务消息。
```

Agent 特有的环境生命周期接口：

```text
async join_with_retry(env_id: str, timeout: float = 30.0,
                      retry_interval: float = 2.0) -> None
async rediscover() -> None
enable_auto_rejoin(timeout: float = 60.0, retry_interval: float = 3.0) -> None
reset_reconnect_attempts() -> None
```

`join_with_retry()` 等待 Hub 确认，超时抛内置 `TimeoutError`；`timeout=0` 表示无限重试。它不等待双向业务声明完成。`rediscover()` 重新发现当前环境；不在环境时只记录日志并返回。`enable_auto_rejoin()` 用于收到 `environment_closed` 通知后重试加入原环境，`timeout=0` 表示无限重试；Human 没有此接口。

传输重连与重新加入环境是两件事。重连清除能力协商缓存；SDK 不保证自动恢复环境成员关系、业务账本、工具任务或投递队列，应用应重新确认成员与契约。

## 3. 本地注册与双向协商（继承自 CompactClientMixin）

```text
configure_capabilities(*, tools=None, events=None, runtime_handlers=None) -> None
async send_discover(recipient: str) -> None
async send_specification(recipient: str, tools=None, *, events=None,
                         protocol: str = COMPACT_PROTOCOL) -> None
protocol_for(peer: str)
specification_for(peer: str)
async on_discover(sender: str)
async on_specification(sender: str, content: dict) -> None
```

`configure_capabilities()` 安装**本端接收能力**，通常在连接前调用。省略参数保留已有目录/处理器；`tools=[]` 或 `events=[]` 显式清空对应目录。Tool 的实际实现由 `on_action()` 分派，声明不会生成函数。runtime Event 必须在 `runtime_handlers` 中提供同名异步函数，调用签名为 `(sender, full_content)`；没有实际处理器会拒绝注册。

| 声明 | 必填字段 | 可选字段 |
|---|---|---|
| `ToolDefinition` | `name`、`description`、`parameters` | `tags` |
| `EventDefinition` | `name`、`description`、`handler`（`model/runtime`） | `data_schema` |

`parameters/data_schema` 为 JSON Schema Draft 2020-12 对象，启用 FormatChecker；本地引用须以 `#` 开头，外部引用不自动加载。Schema 需要精确字段时主动写 `additionalProperties: false`。未声明名称及省略 `data_schema` 的 Event 只允许 `data: {text}`。TypedDict 是类型提示，校验由 Payload、compact 接收契约与 JSON Schema 执行。

以下示例可直接导入执行，演示本地注册及模型校验，不建立连接：

```python
from star_protocol import EnvironmentClient, Envelope, MessagePayload
from star_protocol.models import gen_id, validate_compact_content

TOOLS = [{
    "name": "set_light",
    "description": "设置灯光开关。",
    "parameters": {
        "type": "object", "properties": {"on": {"type": "boolean"}},
        "required": ["on"], "additionalProperties": False,
    },
}]
EVENTS = [{
    "name": "activity.state", "description": "接收主体活动状态。",
    "handler": "runtime",
    "data_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 32000},
            "state": {"enum": ["idle", "working", "listening"]},
        },
        "required": ["text", "state"], "additionalProperties": False,
    },
}]

async def receive_state(sender: str, content: dict):
    print(sender, content["data"]["state"], content["data"]["text"])

env = EnvironmentClient("env_main", auto_reconnect=False)
env.configure_capabilities(
    tools=TOOLS, events=EVENTS,
    runtime_handlers={"activity.state": receive_state},
)
event_content = {
    "id": gen_id("event"), "name": "activity.state",
    "data": {"text": "我正在观察。", "state": "working"},
}
validate_compact_content("event", event_content, EVENTS)
envelope = Envelope(
    type="message", sender="agent_api", recipient="env_main",
    payload=MessagePayload(type="event", content=event_content),
)
assert Envelope.model_validate_json(envelope.model_dump_json()) == envelope
```

`send_discover()` 发出 `{"protocols":["agent-env-compact/2"]}`，使该对端的旧缓存失效。收到 discover 后 SDK 调用 `on_discover()`，发送完整 specification；默认从本端注册目录取工具。兼容自定义回调可返回工具列表、完整 `protocol/tools/events` 快照或 `None`（采用本端注册快照）。

收到 specification 后，SDK 先缓存远端声明、按需自动回送本端声明，最后调用 `on_specification()`。快照是 `{"protocol": COMPACT_PROTOCOL, "tools": [...], "events": [...]}`，不是增量。

- `protocol_for(peer)` 在本端已发送并收到两方向声明后返回协议字符串，否则返回 `None`。它不是对端处理器完成安装的确认。
- `specification_for(peer)` 返回远端完整快照的深拷贝或 `None`。
- `send_specification()` 的临时 tools/events 覆盖用于这次发送及对应接收契约；不等同于调用 `configure_capabilities()` 更新本地注册。能力变更应先更新真实行为和注册，再对相关对端发布完整快照。
- 单播 Action/Outcome/Event 需这对主体协商；与 Env 协商不能替代 Agent↔Agent/Human 的私聊协商。应用等待双方接收、安装就绪后使用新契约。

Agent 默认 `on_specification()` 更新 `tools` 并调用 `on_tool_specification(sender, tools)`。重写时需要保留该兼容回调可先 `await super().on_specification(sender, content)`；完整 Event 声明仍应从 content 或 `specification_for()` 读取。

## 4. 发送业务消息

### AgentClient

```text
async send_action(recipient: str, action_name: str, params: dict | None = None,
                  *, action_id: str) -> str
async send_event(recipient: str, event_name: str, data: dict | None = None,
                 *, event_id: str, refs: list[str] | None = None) -> str
async send_outcome(recipient: str, content: dict) -> None
```

`send_action/send_event` 返回调用时给出的逻辑 ID；ID 为必填 keyword-only 参数，不自动生成。虽然 Agent 的 data 默认是 None，合法 Event 仍必须提供非空 text。

### EnvironmentClient

```text
async send_action(recipient: str, action_name: str, params=None,
                  *, action_id: str) -> str
async send_event(recipient: str, event_name: str, data: dict,
                 *, event_id: str, refs: list[str] | None = None) -> str
async send_outcome(recipient: str, content: dict) -> None
async broadcast_event(event_name: str, content: dict | None = None,
                      *, event_id: str, refs: list[str] | None = None) -> None
async broadcast_to_env(env_id: str, event_name: str, content: dict | None = None,
                       *, event_id: str, refs: list[str] | None = None) -> None
member_role(client_id: str)
```

`broadcast_event()` 的参数 **content 指 Event.data**，传 `{"text":"..."}`，不要再包一层 id/name/data。它使用 `recipient="@env"` 投给当前环境成员，排除发送者。`broadcast_to_env()` 只允许 `env_id == self.client_id`；并非跨环境广播。广播 Event 只允许基础 text，Hub 仍检查实际接收成员的双向契约与接收 Schema。结构化控制应逐个单播。

`member_role()` 返回从 Hub 成员通知记录的 `agent/human` 或 `None`，业务授权应使用真实 sender/角色。重写 `on_system_notify()` 时调用父类，才能保留成员角色维护。

### HumanClient

```text
async send_action(recipient: str, action_name: str, params: dict | None = None,
                  *, action_id: str) -> None
async send_event(recipient: str, event_name: str, event_data: dict,
                 *, event_id: str, refs: list[str] | None = None) -> None
```

Human 的事件正文参数名是 **event_data**，两种发送方法都返回 None；需要关联调用时保留自己传入的 ID。Human 工具调用是否允许由接收业务授权决定，不由角色统一禁止。

### Content 字段

| Payload.type | 必填 Content | 可选 Content | 关键约束 |
|---|---|---|---|
| `action` | `id/name/params` | 无 | params 是对象，按目标 Tool.parameters 校验；无参传 `{}` |
| `outcome` | `id/refs/status/data` | 无 | refs 恰好一个 Action ID；data 只能 `{text}` |
| `event` | `id/name/data` | `refs` | 必有 text；扩展 data 字段需接收方已声明的 Schema |
| `discover` | `protocols` | 无 | 1..8 个不重复的版本字符串 |
| `specification` | `protocol/tools/events` | 无 | 两个目录最多各 256 项，各自名称唯一 |

逻辑 id 为 1..256 字符，name 为 1..128 字符，text 为 1..32000 字符。Event.refs 若提供为 1..32 个有序 Event ID，不重复、不自引用；不传 refs 表示无显式关联，空数组不合法。data 顶层禁止 `id/event_id/event_type`，通用因果关系使用 content.refs。

Outcome.status 只有 `accepted/running/completed/rejected/failed/cancelled`；后四项在 `TERMINAL_STATUSES` 中。每条中间或最终 Outcome 都有独立 ID，同一 Action 只能有一个不可变终态；结果或失败原因写入 text。`success/ref_id` 不是当前字段。

下面函数供已完成注册、加入及双方就绪的 Agent 调用；env 应实现前节的 set_light 工具，并保证 Action 持久化和执行去重。示例只展示 SDK 调用，不提供存储事务：

```python
from star_protocol import ActionTimeoutError
from star_protocol.models import gen_id

async def use_light(agent, env_id: str):
    action_id = gen_id("action")
    # 应用先保存原 Action 的 id/name/params/目标，再首次发送。
    await agent.send_action(env_id, "set_light", {"on": True}, action_id=action_id)
    try:
        result = await agent.await_action(action_id, timeout=5.0)
    except ActionTimeoutError:
        print(action_id, agent.action_status(action_id), "仍未确认最终结果")
        return
    print(result["status"], result["data"]["text"])
    await agent.send_event(
        env_id, "speech", {"text": "我已收到灯光操作结果。"},
        event_id=gen_id("event"),
    )
```

需要确定执行及结果闭环时用 Action；Event 不自动产生 Outcome。交易 exchange_id、取消/查询 action_id 等可作为工具 Schema 中的业务参数，不替代当前消息的 content.id。

## 5. Action 跟踪与恢复（所有业务客户端）

```text
async request_action(recipient: str, action_name: str, params=None,
                     *, action_id: str, timeout: float | None = None) -> dict
async await_action(action_id: str, *, timeout: float | None = None) -> dict
action_status(action_id: str)
action_outcomes(action_id: str)
restore_action(recipient: str, content: dict) -> None
restore_received_action(sender: str, content: dict) -> None
async send_delivery_ack(recipient: str, envelope_id: str) -> None
async on_delivery_ack(sender: str, envelope_id: str) -> None
```

- `request_action()` 是 send_action + await_action 的便捷组合，返回完整最终 Outcome Content。
- `await_action()` 等待终态；未知本地 ID 抛 ValueError。超时为 `ActionTimeoutError`，`action_id` 指向原调用，异常 `status="unknown"` 表示本地未确认，不是 wire Outcome 的合法状态；不取消远端动作、不重发、不回退已有进度。
- `action_status()` 返回本地状态；未登记或尚无结果时为 unknown。`action_outcomes()` 返回已知 Outcome 列表的深拷贝；未知 ID 返回空列表。
- 终态后迟到的进度保留在历史中，不回退状态；running 后迟到的 accepted 也不回退。相同 Outcome ID/内容重放合法，第二个不同终态会冲突。
- `restore_action()` 从应用日志恢复调用方的原 Action/目标绑定；`restore_received_action()` 恢复执行方收到的原 Action/发送者绑定。都只更新内存，不读取数据库、不执行/发送，也不恢复 Outcome 列表。
- `send_delivery_ack()` 接收物理 **Envelope UUID**；仅在完整校验、持久保存该原 Envelope 后调用。SDK 不自动 ACK；Env 的 `on_delivery_ack()` 应核对 outbox 的预期接收者，再幂等删除原投递。

SDK/Hub 使用 `system.notify` 的 `event="ACK"`，与 SP.md 一致；`msg` 精确为 `{"envelope_id": "原 Envelope UUID"}`。SDK 辅助方法发出该格式，Hub 检查成员归属后路由给所属 Environment。

SDK 在调用 `on_outcome()` **之前**已登记 Outcome 并可能唤醒 await_action。因此等待返回不等于应用回调完成、结果落盘或 ACK 已送出。接收回调只获得 sender/content；需要完整 Envelope 的持久 inbox，应在应用接收封装中保存原 Envelope，参见 [demo peers.py](../examples/protocol_demo/peers.py)。

重复 Action 仍会进入执行方 `on_action()`；应用必须查询持久账本，重放原结果而非再次变更世界。重新协商、持久幂等、取消、历史查询和投递补发是应用职责，详见 [SP.md](SP.md)。

## 6. 回调与分派

SDK 先按 Payload.type 校验，再按接收契约分派；content 是完整 Python dict。runtime Event 直接进入注册函数，不再进入模型 Event 回调。

```text
# 公共连接 / 系统回调
async on_connected() -> None
async on_disconnected() -> None
async on_joined_environment(env_id: str) -> None
async on_system_notify(event: str, content: dict) -> None
async on_error(error: dict) -> None

# Agent / Human：单播与广播分别分派
async on_outcome(sender: str, content: dict) -> None
async on_event(sender: str, content: dict) -> None
async on_stream(sender: str, content: dict) -> None
async on_broadcast_event(sender: str, content: dict) -> None
async on_broadcast_stream(sender: str, content: dict) -> None

# Agent / Environment
async on_action(sender: str, content: dict) -> None

# Agent 特有
async on_tool_specification(sender: str, tools: list[ToolDefinition]) -> None
async on_environment_closed(env_id: str) -> None

# Environment 特有
async on_client_joined(client_id: str) -> None
async on_client_left(client_id: str, reason: str = "leave") -> None
```

| 默认客户端 | 默认业务分派 |
|---|---|
| Agent | Action、Outcome、Event、Stream；广播 Event/Stream |
| Human | Outcome、Event、Stream；广播 Event/Stream；没有默认 on_action 分派 |
| Environment | Action、Event；没有默认 Outcome/Stream/广播业务分派 |

Environment 默认 `on_action()` 返回 rejected：“No action handler is installed.”；相同动作会重放原拒绝结果。实际工具需实现 on_action。Environment 也有 send_action 和内存 await_action，但若要在应用回调中处理返回 Outcome，需扩展 `on_message()`；仅有发送函数不证明默认接收分派齐全。

model Event 的 text 如何进入模型上下文由应用决定；协议不会自动调用 LLM。广播模型事件走 on_broadcast_event，不走 on_event。模型/Outcome/runtime 回调成功后 SDK 标记已处理，相同内容重放通常不再次调用成功处理器；回调失败可重试，重启后的去重仍需持久日志。

重写 Agent 的 `on_joined_environment()`、`on_system_notify()` 或 `on_error()` 时，如需保留默认 discover、加入确认/环境关闭与重试行为，应调用父类；Human 的 on_joined_environment 也默认 discover。`on_error()` 接收 Hub/消息循环的 `{code,msg,...}` 错误，并非 Action 的 failed Outcome。

## 7. 模型与原生 Stream

Envelope 的 Python 构造字段：

| 字段 | 类型 / 默认 |
|---|---|
| `id` | UUID 字符串，默认生成 UUIDv4 |
| `timestamp` | 非负 int，默认 Unix 毫秒 |
| `type` | system/message/broadcast/monitor，默认 message |
| `sender`、`recipient` | 必填字符串，1..256 字符 |
| `payload` | 必填对象，按 Envelope.type 选择相应 Payload |

Wire 解析要求六个字段完整。`Envelope.model_validate_json(raw)` 校验完整 JSON；`model_dump()` 返回字典，`model_dump_json()` 序列化。外层字段不能额外增加；拒绝重复 JSON 键、NaN/Infinity 和非 JSON Content，规范化紧凑编码后限 512 KiB。Envelope.id 是物理投递身份，与逻辑 Content.id 不同。

| Payload 模型 | type 值 |
|---|---|
| `SystemPayload` | error/ctrl/notify |
| `MessagePayload` | action/outcome/stream/event/discover/specification |
| `BroadcastPayload` | event/stream |
| `MonitorPayload` | ctrl/data/notify |

Payload 只含 type/content，content 必须是对象。`EnvelopeType/SystemType/MessageType/BroadcastType/ClientState` 可从顶层导入；`MonitorType` 从 `star_protocol.models` 导入。对应枚举值与本表相同，ClientState 为 disconnected/home/in_env。

```text
gen_id(type: str, name: str = "") -> str
validate_compact_content(kind: str, content, event_definitions=None) -> None
```

`gen_id()` 返回带 type 前缀和 UUID 的逻辑 ID；当前 name 参数不改变结果。应用首次发送前保存 ID。`validate_compact_content()` 校验 Content 与传入的 Event 定义；它不建立协商，不校验 Tool.parameters、Action 所有权或执行幂等。

当前没有 broadcast_stream 快捷接口。原生 Stream 用 send + MessagePayload/BroadcastPayload 构造；content 常用 id/sequence/chunk/is_end，仍是可扩展对象，不提供 compact 式精确字段与自动重排/聚合：

```python
from star_protocol import Envelope, MessagePayload

async def send_chunk(client, recipient: str):
    await client.send(Envelope(
        type="message", sender=client.client_id, recipient=recipient,
        payload=MessagePayload(type="stream", content={
            "id": "stream-api-001", "sequence": 0,
            "chunk": "房间情况正在说明。", "is_end": False,
        }),
    ))
```

Stream 单播仍要求同环境路由，但不要求 compact 协商；它不替代最终 Outcome。System/Monitor 同样有独立原生 Content 约定，不套用 Event.data.text。

## 8. Monitor 与监控 Mixin

```text
async subscribe_to_client(client_id: str) -> None
async unsubscribe_from_client(client_id: str) -> None
async on_monitor_data(client_id: str, data_type: str, data: dict) -> None
async get_client_messages(client_id: str, data_type: str | None = None,
                          limit: int = 100) -> list[dict]
async get_client_stats(client_id: str) -> dict
async get_all_monitored_clients() -> list[str]
get_subscribed_clients() -> set
```

这些是 MonitorClient 方法。公开参数叫 **client_id**；其 wire 订阅 Content 中的键才是 target_client_id。`get_subscribed_clients()` 是本地请求集合副本，不代表 Hub 已确认；订阅/退订请求也不等待 subscribed/unsubscribed 通知。

默认 InMemoryStorage 每个 client/data_type 保存最多 1000 条记录，查询异步执行，重启后丢失。替代 storage 应实现同样的 save/get_messages/get_stats/get_all_clients 异步方法。

所有客户端继承 MonitorableMixin 与 ReconnectableMixin，不需要再次多继承：

```text
async enable_monitoring(level: MonitorLevel = MonitorLevel.INFO,
                        data_types: set[str] | None = None) -> None
async disable_monitoring() -> None
async send_monitor_data(data_type: str, data: dict) -> None
reset_reconnect_attempts() -> None
```

`MonitorLevel` 为 DEBUG=10、INFO=20、WARNING=30、ERROR=40。`data_types=None` 表示不过滤，非空集合按名称过滤。创建业务客户端时传 monitorable=True 会启用 SDK 的消息/状态自动遥测钩子；连接后仍要 enable_monitoring 开启发送。send_monitor_data 未启用时直接返回，启用后向 Hub 发送独立 monitor.data。

Monitor 查询中的数据先保存再调用 on_monitor_data。Hub 按订阅关系产生的路由观测与 SDK 主动遥测来自不同观察点，不能合并为一次网络收发；监控级别也不提供消息排序或持久保证。Hub Monitor 是 Hub 的独立观察连接角色，没有 HubMonitorClient 类。

## 9. 异常与 Hub 入口

```python
from star_protocol import (
    StarProtocolError, ConnectionError as StarConnectionError,
    InvalidStateError, MessageError, PermissionError as StarPermissionError,
    RecipientNotFoundError, ActionTimeoutError, ProtocolConflictError,
)
```

| 异常 | 基类 / 场景 |
|---|---|
| `StarProtocolError` | SDK 自定义传输/状态异常基础类 |
| `ConnectionError` | StarProtocolError；连接、发送或接收失败，示例可起本地别名 StarConnectionError |
| `InvalidStateError` | StarProtocolError；非法 join/leave 状态 |
| `MessageError/PermissionError/RecipientNotFoundError` | StarProtocolError；模块导出的领域异常，Hub 错误仍通常经 system.error 回调 |
| `ProtocolConflictError` | ValueError；逻辑 ID 不可变性、Action 所有权或终态冲突 |
| `ActionTimeoutError` | TimeoutError；本地尚未确认 Action 终态 |
| `ValueError/pydantic.ValidationError` | 字段、JSON、协议或模型校验失败 |
| `jsonschema.ValidationError` | 工具参数或 Event data 不符合接收 Schema |

顶层没有 StarConnectionError/StarMessageError/StarStateError 导出；这些不能作为实际类名导入。ProtocolConflictError 与 ActionTimeoutError 也不是 StarProtocolError 的子类。

Hub 可通过 `star_protocol.MessageRouter` 集成 Starlette/FastAPI WebSocket：

```text
MessageRouter(max_connections: int = 1000, heartbeat_interval: float = 30.0)
async start() -> None
async stop() -> None
async handle_connection(websocket: starlette.websockets.WebSocket,
                        role: str, client_id: str) -> None
async route_message(envelope: Envelope) -> None
get_uptime() -> float
```

router.start 不创建监听服务器；ASGI 应用提供 `/ws/{role}/{client_id}` 路由并调用 handle_connection。当前 heartbeat_interval 是配置属性，start 没有建立心跳后台任务。SessionManager/Session/SessionState/ClientRole 为服务端连接模型，具体实现见 [server/connection.py](../src/star_protocol/server/connection.py)；连接身份绑定不替代部署账号鉴权。

实现依据：[客户端](../src/star_protocol/client/)、[compact 校验与结果管理](../src/star_protocol/client/compact.py)、[消息模型](../src/star_protocol/models/payloads.py)、[完整运行示例](../examples/README.md)。
