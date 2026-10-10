# Star Protocol 完整协议演示

本目录演示 SDK 0.3.0 的 `agent-env-compact/2`：一个 Environment、两个 Agent、一个 Human 和一个 Monitor 通过真实 WebSocket Hub 交互。业务角色 ID 分别为 `demo_env / demo_agent / demo_colleague / demo_human`。主体使用固定的演示策略，不调用 LLM 或付费服务。`handler: "model"` 表示自然语言输入会进入 `on_event`，并不意味着 SDK 自动调用模型。

## 一键运行

在 SDK 仓库根目录执行：

```bash
uv sync
uv run python -m examples.protocol_demo
```

默认启动绑定 `127.0.0.1` 随机端口的临时 Hub，按阶段展示主体正在做的操作及时间，逐项执行真实场景和断言，完成后退出并清理临时状态。成功运行说明这些场景的协议交换及应用行为通过检查；不代表任意业务 Schema 的行为都已实现。

保留状态及报文记录：

```bash
uv run python -m examples.protocol_demo --state-dir .demo-state --trace
```

`--state-dir` 保留 `environment.sqlite3`、按客户端 ID 命名的 `demo_agent.sqlite3 / demo_colleague.sqlite3 / demo_human.sqlite3`、`transcript.jsonl` 和 `summary.json`；终端默认使用 Rich 展示按序号排列的交互时间轴及独立的因果关系树，`--trace` 展开详细报文树。`transcript.jsonl` 仍保存完整原始 JSON 记录，包含 Envelope，可对照配置检查发送者、接收者、Payload 类型和 Content。


## 终端关系树

运行时按 12 个阶段展示：“配置与处理器注册 → 主体加入及双向协商 → 观测与工具校验 → 执行与重放 → 持续动作与取消 → Event 感知及反馈 → 能力更新 → 公聊私聊 → Stream 与 Monitor → 持久 ACK → 重启恢复 → 离场清理”。每步说明主体、操作和时间，完成后保留完整的观测时间轴及协议关系树。时间轴按记录产生顺序排列，关系树按业务 ID 和 refs 聚合，两者各有用途。

TTY 终端实时显示当前活动阶段；非 TTY 或重定向 stdout 时逐阶段流式输出，便于边运行边读。最终关系树分为“主体与接收能力”“Action → Outcome”“Event 因果引用”“投递与恢复”“Stream”“Monitor”“运行结果”。

默认视图直接展开本地注册的工具和 Event 条目、Schema 字段概要及实际 handler；发送和接收时显示方向、调用参数与正文。第一个阶段逐个构造主体并完成真实本地配置，第二个阶段显示加入、声明发送开始、消息到达和 `on_specification` 安装完成。重启时也展示重新登记和原账本恢复。完整 Schema 与原始三层报文仍由 `--trace` 展开。

`--trace` 在同一棵树中展开完整的 `Envelope → Payload → Content`、Schema 和检查的明细，不再逐行打印原始 JSON。完整原始报文仍保存在 `transcript.jsonl`；流程注释另以 `flow.*` 记录并明确标为展示信息，不构造 Envelope，不发送给 Hub。

逻辑消息使用短显示别名：`A01` 是 Action、`O01` 是 Outcome、`E01` 是 Event；`D01` 是传输投递。别名只帮助阅读，不写入协议，也不代替原 ID。详细树和原始 JSONL 保留原 ID，可用于检索本地历史。

Event 的多个 `refs` 全部按原顺序列出；树仅用 `refs[0]` 选择视觉挂靠位置。这是展示方式，不是新增的协议规则。若引用的原事件没有出现在本次记录中，树会明确标注“原事件未在本次展示中出现”，不会猜测来源。Action 的取消和查询显示 `params.action_id` 对应的业务目标，仍与 Event 的 `refs` 区分。

“ACK 已确认”以环境实际收到并核验 ACK 为准，发送确认消息不等于环境已确认。原投递补发保留原 Envelope UUID；关系树将传输恢复与逻辑消息重放分别展示。


## 配置演示时间

命令行默认读取 [config/demo-timing.json](protocol_demo/config/demo-timing.json)。三个时间都以秒为单位：

| 字段 / 参数 | 默认值 | 允许范围 | 含义 |
|---|---:|---|---|
| `stage_delay` / `--stage-delay` | 0.7 | 有限数值，0 到 10，含边界 | 阶段启动时的展示停顿 |
| `step_delay` / `--step-delay` | 0.3 | 有限数值，0 到 10，含边界 | 步骤之间的展示停顿 |
| `wait_seconds` / `--wait-seconds` | 1.2 | 有限数值，0.05 到 3，含边界 | 正常完成的真实 `wait` 示例时长 |

时间 JSON 只允许这三个字段，全部必填；额外字段和重复键均被拒绝。配置先通过完整校验，再应用命令行覆盖，参数覆盖不会修复缺字段或无效的配置。具体约束见 [demo-timing.schema.json](protocol_demo/config/demo-timing.schema.json)。

放慢展示并让持续动作等待两秒：

```bash
uv run python -m examples.protocol_demo --stage-delay 1 --step-delay 0.5 --wait-seconds 2
```

也可以修改 JSON，或加载另一份同结构的配置；单独的命令行时间参数覆盖该配置中的对应值：

```bash
uv run python -m examples.protocol_demo --timing examples/protocol_demo/config/demo-timing.json
```

快速运行，清除阶段和步骤的展示停顿：

```bash
uv run python -m examples.protocol_demo --fast
```

`--fast` 不跳过场景，不省略真实协商或结果确认，也不把持续工具改成立即完成；正常完成的 `wait` 示例仍按 `wait_seconds` 实际运行。如需缩短这段真实等待，可显式指定 `--fast --wait-seconds 0.15`。取消示例另启动一个 3 秒 `wait`，收到 `running` 后立即发出独立的 `cancel`；敏感的超时检查和取消提交之间不插入展示停顿。

这些配置只控制演示节奏和示例工具时长，不模拟网络延迟，不调用模型，也不添加协议字段。所有操作仍等真实 Hub、接收者或工具结果；不会靠展示停顿认定已经加入、执行成功或完成投递。配置中的字符串、布尔值、非有限数和越界数值会被拒绝。

连接已启动的 Hub：

```bash
uv run uvicorn app:create_hub_app --factory --host 127.0.0.1 --port 8765
```

另一个终端：

```bash
uv run python -m examples.protocol_demo --hub ws://127.0.0.1:8765 --state-dir .demo-state
```

手动分开运行各角色时，使用三个入口，按各入口打印的交互提示输入 JSON 命令：

```bash
uv run python -m examples.demo_env --hub ws://127.0.0.1:8765 --state-dir .demo-state
uv run python -m examples.demo_agent --hub ws://127.0.0.1:8765 --state-dir .demo-state
uv run python -m examples.demo_human --hub ws://127.0.0.1:8765 --state-dir .demo-state
```

三个命令分别在独立终端运行；自动演示本身会创建全部角色，无需同时启动这些手动入口。第二个 Agent 可另加 `--id demo_colleague`。演示使用 Rich 树形输出；`uv sync` 会安装仓库 dev 依赖中声明的 Rich。

Agent/Human 终端中的三个 JSON 示例：

```text
action calculate {"operation":"add","a":10,"b":20}
event demo_env activity.state {"text":"我正在处理这个任务。","state":"working"}
event demo_human speech {"text":"你好，我们可以继续讨论。"}
```

`state working 我正在处理这个任务。` 与 `speech demo_human 你好。` 是后两种消息的简写。`tools` 查看环境工具及参数 Schema，`schemas` 查看自身 Event 声明，`history <logical_id>` 读取本地原文；`discover <peer>` 重新协商完整能力。

持续动作返回 Action ID 后立即恢复输入，进度异步显示。先发送等待，再用返回的原 Action ID 取消：

```text
action wait {"seconds":3}
cancel <刚返回的ActionID>
```

`cancel` 创建一个独立 Action，不改写原 `wait` 的 ID。`await <action_id>` 显式等待终态，`query <action_id>` 查询原结果，`replay <action_id>` 重发原 ID 和原参数。

独立监控入口：

```bash
uv run python -m examples.demo_monitor --hub ws://127.0.0.1:8765 --target demo_agent
```

Monitor 等待 Hub 的订阅确认后显示目标发出的 `monitor.data`。一键演示会启用 Agent 监控并发送 `demo.trace`；普通业务 Event 和 Outcome 不会自动变成这条遥测。

## 覆盖矩阵

| 能力 | 演示及检查 |
|---|---|
| 加入与协商 | Hub 确认加入；`discover` 和双向 `specification` 完成后发送业务消息 |
| 能力更新 | 更新接收者声明后，重新交换完整能力快照，再使用新声明的 Event |
| 工具声明 | 环境公布六个工具的参数 Schema，双方依据接收者声明校验参数 |
| 工具参数错误 | 缺必填项、错误枚举、未声明字段及未声明工具无法作为有效调用执行 |
| 主动探索 | Agent 调用 `observe`，获得自然语言 Outcome |
| 环境主动输入 | `observation` 文本 Event；文本广播到环境成员 |
| 模型输入 | 默认 Event `data` 只有 `text`，进入 `on_event` |
| 运行时输入 | Agent → Environment 的 `activity.state`；Environment → Agent/Human 的 `interaction.feedback`，均由真实 handler 处理 |
| Schema 扩展 | 接收者声明 `data_schema`；本地 `$defs` / `$ref` 复用约束；未声明的额外字段和反馈强度越界被拒绝 |
| 运行时登记 | 声明 runtime Event 却没有安装 handler 时配置被拒绝 |
| 持续动作 | `wait` 返回独立的 `accepted`、`running`、最终 `completed` Outcome，均关联原 Action |
| 执行失败 | 除零得到 `failed`，自然语言说明原因 |
| 业务拒绝 | Human 调用 `set_light` 得到 `rejected`，灯光不变 |
| 取消动作 | `cancel` 有自己的 Action 和 `completed` Outcome；被取消的原 `wait` 得到 `cancelled` |
| 本地等待超时 | 超时只表示本地未确认，后续仍可等待原 Action 的终态 |
| 幂等重放 | 原 Action ID 和参数重发，返回已保存的原 Outcome；灯光业务不重复执行 |
| 身份不可变 | 同 ID 修改参数或正文产生冲突 |
| 私聊与因果关系 | Agent ↔ Agent、Agent ↔ Human 独立协商并发送文本，回复用有序 `refs` 关联 Event |
| 查询操作 | `get_operation_result` 查询本人操作并重发原 Outcome；查询动作也返回自身的 Outcome |
| 实例恢复 | Environment 和 Agent 从 SQLite 恢复原 Action 及结果，保持原逻辑 ID |
| 持久接收与 ACK | 完整原始 Envelope 存储成功后确认其投递 UUID；环境核对预期接收者 |
| 漏 ACK 与补发 | 接收方已保存原 Event 但暂未确认；环境与 Agent 重启后按原 Envelope UUID 补发完整原文，ACK 清空 outbox |
| 世界与结果事务 | 示例 SQLite 账本将灯光变更与原 Outcome 在同一事务中提交，再发送结果 |
| Star stream | `sequence: 0 / 1` 的两个片段，末片段 `is_end: true`；流片段不替代 Outcome |
| Star monitor | `monitor.ctrl` 订阅，经 Hub 的 `monitor.notify` 确认后收到 `demo.trace` 的 `monitor.data` |

手动监控时，在 Agent 命令行执行 `monitor on`，然后执行 `telemetry demo.trace {"text":"内部遥测"}`；Monitor 订阅 `demo_agent` 后即可收到这条独立的内部遥测。

## 配置：声明接收能力

配置文件是完整的 `specification.content`，不是发送权限表。`environment.json` 声明“环境能接收什么”；`agent.json` 与 `human.json` 声明“Agent/Human 能接收什么”。实际业务权限仍由接收方的 handler 判断。

| 配置 | tools | events |
|---|---|---|
| [environment.json](protocol_demo/config/environment.json) | `observe`、`set_light`、`calculate`、`wait`、`cancel`、`get_operation_result` | `speech`（model）、`activity.state`（runtime） |
| [agent.json](protocol_demo/config/agent.json) | 空数组 | `observation`、`speech`（model）、`interaction.feedback`（runtime） |
| [human.json](protocol_demo/config/human.json) | 空数组 | `observation`、`speech`（model）、`interaction.feedback`（runtime） |

工具条目使用 `name / description / parameters`，可选 `tags`。`parameters` 是 Action 的 `params` Schema。例如 `set_light` 仅接受必填布尔字段 `on`，`additionalProperties: false` 禁止无声明参数。工具出现在清单中并不保证每种身份都能执行：Human 参数正确时仍可能被环境拒绝。

Event 条目使用 `name / description / handler`，可选 `data_schema`。无扩展 Schema 的普通 Event 只能携带 `data: {"text": "…"}`；扩展 Schema 只校验 `data`，协议统一校验 Content 的 `id / name / refs`。`interaction.feedback` 的 Schema 使用 `#/$defs/text`、`#/$defs/intensity`，要求 `text / channel / intensity`，其中 `channel` 为 `haptic`，`intensity` 范围为 0 到 1。

[contracts.py](protocol_demo/contracts.py) 的 `load_specification(role)` 加载并验证配置。客户端在连接前调用 `configure_capabilities`，为每个 runtime Event 登记异步 handler；仅写入 `"handler": "runtime"` 不会安装行为。handler 接收 `(sender, full_content)`，可同时读取身份、正文和因果引用。配置修改后需要重新加载并重新交换完整声明；修改 JSON 文件本身不会更新已协商的会话。


## 从注册到接收、调用

第一阶段加载各主体的接收配置，并真实调用 `configure_capabilities`。本地配置成功后才出现 `capability.registered`；业务回调实际进入时出现 `handler.dispatch`。它们是演示观测记录，不是发给对方的新协议消息。“进入 handler”表示实际回调被调用，不替代 Outcome 的执行结果。原 Action 重试也会进入 `on_action`，随后由账本重放原结果；该记录不表示再次执行世界修改分支。

| 接收主体 | 接收内容 | 本地实际处理入口 |
|---|---|---|
| Environment | 六个工具的 Action：`observe / set_light / calculate / wait / cancel / get_operation_result` | 统一进入 `DemoEnvironment.on_action`，再按 `content.name` 选择对应业务分支 |
| Environment | `speech`，model Event | `DemoEnvironment.on_event` |
| Environment | `activity.state`，runtime Event | 登记的 `DemoEnvironment._activity_state` |
| Agent / Human | `observation / speech`，model Event | `on_event`，实现来自 `DemoPeerMixin` |
| Agent / Human | `interaction.feedback`，runtime Event | 登记的 `_receive_feedback`，实现来自 `DemoPeerMixin` |
| Agent / Human | 与原 Action 关联的 Outcome | 框架回调 `on_outcome`，实现来自 `DemoPeerMixin`；它不是 Event 声明 |
| 双方 | `specification` | 框架回调 `on_specification`，接收对方完整的能力快照 |

本例 Agent 和 Human 的 `tools` 是空数组；六个工具由 Environment 提供，Agent/Human 根据环境的声明调用。工具 Schema 定义请求参数，示例的分派器是已编写的 `DemoEnvironment.on_action`，不会按工具名自动生成六个独立函数。runtime Event 则需要显式登记名称到本地方法的绑定。

主体加入环境后，Agent ↔ Environment 的一次实际协商包含四步：

1. Agent 向 Environment 发送 `discover`，列出支持的 `agent-env-compact/2`。
2. Environment 返回 `specification`，其中 `tools` 是环境提供的六个工具，`events` 是环境能接收的 `speech / activity.state`。
3. Agent 的 SDK 保存环境快照，并自动向 Environment 发送反向 `specification`：`tools: []`，`events` 为 Agent 能接收的 `observation / speech / interaction.feedback`。Agent 的 `on_specification` 获得环境清单；Environment 的 `on_specification` 获得 Agent 清单。
4. 双方的 `protocol_for(peer)` 都确认协议已协商，才开始业务交互。Hub 的加入确认与应用层能力就绪分别等待。

交换声明只建立解析契约；收到远端 Schema 不会安装本地函数。接收者先拥有真实 handler，再公布自己的接收能力；恢复实例时同样先重新配置本地方法，再恢复原记录、重新交换声明。

时间轴中的“发送开始”发生在发送校验和必要落盘之后、网络 I/O 之前；“到达”表示 Envelope 已解析进入接收路由，此时还未承诺接收端 Schema 或业务校验成功；“处理器调用”和“保存”各记录真实发生的时间。`on_specification` 表示远端声明已安装，SDK 可能已在该回调之前自动发出反向声明。发送完成可晚于对端到达，因此不拿发送完成时间推断发送起点。所有序号、相对时间和观测状态只存在于本地日志，不增加协议字段。

Action 的调用链是：本地保存请求 → 开始发送 → Env 到达 → inbox 保存 → 工具处理器调用 → Outcome/outbox 保存 → 开始返回 → Agent 到达 → Outcome 回调 → 完整 Envelope 保存 → 发出 ACK → Env 收到并确认 ACK。发送端 Schema 拒绝明确标记为“未发送”；业务 `rejected / failed` 则是实际收到请求后的 Outcome。

随后能在默认 Rich 时间轴和因果树中看到这些真实调用链：

| 消息方向与内容 | 实际接收、处理与回执 |
|---|---|
| Agent → Environment，Action `set_light`，`params: {"on": true}` | 校验环境工具 Schema → `DemoEnvironment.on_action` 的 `set_light` 分支 → 保存世界修改和 `completed` Outcome → 发回原 Action 的 `refs` → Agent `on_outcome` 保存自然语言结果 |
| Environment → Agent，Event `observation`，`data.text` | Agent `on_event` 保存自然语言输入，后续由固定演示策略选择操作 |
| Agent → Environment，Event `activity.state`，`data: {"text":"我在观察房间。","state":"working"}` | 环境校验接收 Schema → `_activity_state` 更新主体活动展示 |
| Environment → Agent，Event `interaction.feedback`，`data: {"text":"提示操作已被环境感知。","channel":"haptic","intensity":0.2}` | Agent 校验接收 Schema → `_receive_feedback` 解析并保存反馈 |

每次声明、接收和实际分派会分别展示。`on_event` 的“model”路由仍然是模型输入入口的演示，不在本例中调用 LLM；工具完成状态来自真实 Outcome，不由说明文字推断。

## 三层报文

下面是与本例配置匹配的完整报文示意。Envelope 的 `id` 是传输投递记录的 UUID，同一投递补发保留原值；Content 的 `id` 是应保存并保持不变的业务逻辑 ID。`timestamp` 为毫秒 Unix 时间。Payload 用 `type` 指定 Content 的解析规则。

调用环境工具：

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "timestamp": 1790985600000,
  "type": "message",
  "sender": "demo_agent",
  "recipient": "demo_env",
  "payload": {
    "type": "action",
    "content": {
      "id": "action-light-001",
      "name": "set_light",
      "params": {"on": true}
    }
  }
}
```

环境返回自然语言结果：

```json
{
  "id": "22222222-2222-4222-8222-222222222222",
  "timestamp": 1790985600001,
  "type": "message",
  "sender": "demo_env",
  "recipient": "demo_agent",
  "payload": {
    "type": "outcome",
    "content": {
      "id": "outcome-light-001",
      "refs": ["action-light-001"],
      "status": "completed",
      "data": {"text": "灯光已打开。"}
    }
  }
}
```

环境发送接收者已声明的运行时输入：

```json
{
  "id": "33333333-3333-4333-8333-333333333333",
  "timestamp": 1790985600002,
  "type": "message",
  "sender": "demo_env",
  "recipient": "demo_agent",
  "payload": {
    "type": "event",
    "content": {
      "id": "event-feedback-001",
      "name": "interaction.feedback",
      "data": {
        "text": "手柄轻微震动，提示环境发生变化。",
        "channel": "haptic",
        "intensity": 0.25
      }
    }
  }
}
```

普通发言只需要 `data.text`。回复可加 `refs: ["event-speech-001"]`，多个 Event 引用按发送方给定顺序保留。Event 的 `refs` 只引用其他 Event；Outcome 的 `refs` 恰好引用原 Action。取消、查询工具的 `params.action_id` 是各自工具声明的业务参数，不是本消息的逻辑身份，也不替代 Outcome 的关联。

同一 Action 可以有多个不同 ID 的中间 Outcome，但至少有一个最终 Outcome；有效终态只有 `completed / rejected / failed / cancelled`。`accepted / running` 不会结束 `await_action`。本地超时产生的 `unknown` 是等待状态，不是线上 Outcome 的枚举值。查询动作的成功也不代替被查询动作的原始终态。

## 文件导航与职责

| 文件 | 作用 |
|---|---|
| [__main__.py](protocol_demo/__main__.py) | 一键命令的薄入口 |
| [runner.py](protocol_demo/runner.py) | 命令参数、临时 Hub、分阶段运行流程、真实结果确认、验证和输出记录 |
| [flow.py](protocol_demo/flow.py) | 演示主体/操作/时间注释与异步展示停顿，只驱动演示，不发送协议消息 |
| [timing.py](protocol_demo/timing.py) | 演示节奏的严格范围校验、配置加载和覆盖 |
| [demo-timing.json](protocol_demo/config/demo-timing.json) | 演示阶段/步骤停顿与真实 wait 时长，不属于协议接收能力 |
| [demo-timing.schema.json](protocol_demo/config/demo-timing.schema.json) | 本地时间配置的字段、类型与范围约束 |
| [display.py](protocol_demo/display.py) | Rich 层级树、显式引用关系、ID 显示别名、详细报文树与运行结果 |
| [contracts.py](protocol_demo/contracts.py) | 读取完整接收者能力快照、验证配置和 Schema |
| [registration.py](protocol_demo/registration.py) | 观测配置成功后的本地能力及实际回调分派，使用真实方法名称，不改变协议报文 |
| [config/](protocol_demo/config/) | 三类接收者声明与独立的演示时间配置 |
| [environment.py](protocol_demo/environment.py) | 工具执行、运行时控制、持续任务和环境持久操作账本 |
| [peers.py](protocol_demo/peers.py) | Agent/Human 协商、模型事件与运行时反馈、原文存储和恢复 |
| [client_cli.py](protocol_demo/client_cli.py) | 各角色的手动运行与 JSON 交互命令 |
| [monitor.py](protocol_demo/monitor.py) | Hub 确认的监控订阅、遥测接收与等待 |
| [demo_monitor.py](demo_monitor.py) | 独立 Monitor 命令入口 |
| [demo_env.py](demo_env.py)、[demo_agent.py](demo_agent.py)、[demo_human.py](demo_human.py) | 三个手动入口 |

一键演示对上述场景和收发时序进行检查，具体项数与结果保存在 `summary.json`；完整回归同时验证各命令入口能直接加载。

SDK 负责严格解析、双向能力协商、Schema 校验、内存中的 ID/归属/终态一致性和 handler 分发。示例代码中的 SQLite 账本负责事务、业务授权、原文保存、结果重放、投递确认和实例恢复。不能把本例 SQLite 灯光事务直接等同于任意外部服务的事务保证。

本例私聊展示基础消息与因果关联，反馈展示一种触觉输入 Schema。Conversation 2.0 的完整群组生命周期、同意机制、分组/合并、发言权，以及具体游戏手柄、媒体输入和环境时钟的契约，需要对应业务应用实现。增加接收声明只是让消息可校验，不会自动创建这些业务机制。
