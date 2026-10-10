# Star Protocol 快速开始

本指南使用当前仓库的 Python SDK **0.3.0** 与 `agent-env-compact/2`。先运行完整 demo，再用两个最小客户端理解注册、协商、Event 和 Action→Outcome。字段规则见 [SP.md](SP.md)，方法签名见 [API 参考](api_reference.md)。

## 1. 安装与完整演示

需要 Python **3.13+** 和 `uv`。在当前仓库根目录执行；这些步骤使用本 checkout，不假设公共包仓库已经发布新版。

```bash
uv sync
uv run python -m examples.protocol_demo
```

Demo 自动启动真实本地 Hub，展示工具/Event 注册、双向声明、调用与接收处理器、六种 Outcome、因果 refs、持续动作、持久投递及恢复。Rich 分别显示观测时间轴和因果树。

保留完整报文和 SQLite 状态：

```bash
uv run python -m examples.protocol_demo --state-dir .demo-state --trace
```

模拟停顿由 `--stage-delay`、`--step-delay` 控制；`--wait-seconds` 是真实 wait 工具的等待时间。配置、独立角色 CLI 和全部能力范围见 [示例指南](../examples/README.md)。

## 2. 启动独立 Hub

以下最小例子需要三个终端，均在仓库根目录运行。在第一个终端执行：

```bash
uv run uvicorn app:create_hub_app --factory --host 127.0.0.1 --port 8765
```

实际端点为 `/ws/<role>/<client_id>`。SDK 的 `connect("ws://127.0.0.1:8765")` 自动添加该路径。当前仓库没有 `star_protocol.cli` 启动模块。

## 3. 创建 Environment

将下面代码保存到仓库根目录的 `my_environment.py`。Env 提供 `echo` 工具，并接收默认文本 `speech` Event。工具参数 Schema 严格限制为一个非空 text；真实执行入口是 `on_action()`。

```python
import asyncio

from star_protocol import EnvironmentClient
from star_protocol.models import gen_id


class EchoEnvironment(EnvironmentClient):
    def __init__(self):
        super().__init__("quickstart_env", auto_reconnect=False)
        self.configure_capabilities(
            tools=[{
                "name": "echo",
                "description": "返回调用者提供的文字，不修改世界。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "minLength": 1, "maxLength": 32000}
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            }],
            events=[{
                "name": "speech",
                "description": "接收自然语言发言。",
                "handler": "model",
            }],
        )

    async def on_action(self, sender, content):
        previous = self.action_outcomes(content["id"])
        if previous:
            for original in previous:
                await self.send_outcome(sender, original)
            return
        await self.send_outcome(sender, {
            "id": gen_id("outcome"),
            "refs": [content["id"]],
            "status": "completed",
            "data": {"text": content["params"]["text"]},
        })

    async def on_event(self, sender, content):
        print("Env 收到 Event:", content["data"]["text"], flush=True)
        await self.send_event(
            sender, "speech", {"text": "我收到了你的说明。"},
            event_id=gen_id("event"), refs=[content["id"]],
        )


async def main():
    async with EchoEnvironment() as env:
        await env.connect("ws://127.0.0.1:8765")
        await env.start()
        print("Env 已连接，等待成员加入。", flush=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
```

在第二个终端运行：

```bash
uv run python my_environment.py
```

Environment 连接时自动建立同名环境，不需要 `join`。本例用 SDK 的进程内原结果缓存处理重试；它没有持久日志。世界修改、执行幂等及重启恢复应采用 [完整 demo](../examples/protocol_demo/environment.py) 中的应用账本机制。

## 4. 创建 Agent

将下面代码保存为 `my_agent.py`。Agent 自身不提供工具，声明能接收 `speech`；加入确认后自动 discover，收到 Env 的完整 specification 时 SDK 已自动回送 Agent 的声明。

```python
import asyncio

from star_protocol import AgentClient, COMPACT_PROTOCOL, TERMINAL_STATUSES
from star_protocol.models import gen_id

ENV_ID = "quickstart_env"


class EchoAgent(AgentClient):
    def __init__(self):
        super().__init__("quickstart_agent", auto_reconnect=False)
        self.ready = asyncio.Event()
        self.reply_processed = asyncio.Event()
        self.outcome_processed = asyncio.Event()
        self.request_id = gen_id("action")
        self.speech_id = gen_id("event")
        self.configure_capabilities(tools=[], events=[{
            "name": "speech",
            "description": "接收自然语言回复。",
            "handler": "model",
        }])

    async def on_specification(self, sender, content):
        await super().on_specification(sender, content)
        if sender == ENV_ID:
            self.ready.set()

    async def on_event(self, sender, content):
        print("Agent 收到 Event:", content["data"]["text"], flush=True)
        if sender == ENV_ID and self.speech_id in content.get("refs", []):
            self.reply_processed.set()

    async def on_outcome(self, sender, content):
        print("Agent 收到 Outcome:", content["status"], content["data"]["text"], flush=True)
        if (sender == ENV_ID and content["refs"] == [self.request_id]
                and content["status"] in TERMINAL_STATUSES):
            self.outcome_processed.set()


async def main():
    async with EchoAgent() as agent:
        await agent.connect("ws://127.0.0.1:8765")
        await agent.start()
        await agent.join_with_retry(ENV_ID, timeout=5, retry_interval=0.5)
        await asyncio.wait_for(agent.ready.wait(), timeout=5)
        assert agent.protocol_for(ENV_ID) == COMPACT_PROTOCOL

        await agent.send_event(
            ENV_ID, "speech", {"text": "请回应我的 echo 请求。"},
            event_id=agent.speech_id,
        )
        result = await agent.request_action(
            ENV_ID, "echo", {"text": "你好，Star Protocol。"},
            action_id=agent.request_id, timeout=5,
        )
        assert result["refs"] == [agent.request_id]
        await asyncio.wait_for(agent.reply_processed.wait(), timeout=5)
        await asyncio.wait_for(agent.outcome_processed.wait(), timeout=5)


if __name__ == "__main__":
    asyncio.run(main())
```

在第三个终端运行：

```bash
uv run python my_agent.py
```

Env 会收到自然语言 Event；Agent 会收到带 refs 的回复，以及 `status="completed"`、`data={text}` 的独立 Outcome。本例两个 ID 都在发送前生成；refs 关联逻辑消息 ID，不是 Envelope UUID。Env 依次处理反向声明和同一连接中的后续业务消息，处理器已在连接前注册。

`request_action()` 相当于 `send_action()` 加 `await_action()`，只等待终态。等待者可能先于应用 `on_outcome()` 完成，因此示例另等回调处理信号，再退出连接。这些信号不是持久化或 ACK。

## 5. 接入时的约定

- `async with client` 进入时只返回客户端，退出时调用 `stop()`；仍需显式 `connect()` 和 `start()`。`start()` 已启动后台接收循环，随后不要再次 `run()`。
- Action 的 `action_id`、Event 的 `event_id` 是必填关键字参数。无参 Action 的 wire `params` 仍为 `{}`；所有正文 text 必须非空且最多 32000 字符。
- Outcome 必须有自身 `id`、恰好一个 Action `refs`、六种状态之一及仅包含 text 的 data；不使用旧版 `success/ref_id/error`。
- 普通 Event 默认只有 data.text；附加控制字段需要接收方声明 `data_schema`。`handler="runtime"` 还必须通过 `runtime_handlers` 安装真实异步回调；配置文件不会生成处理器。
- 持久接收后才显式发送投递 ACK。最小例子没有持久 ACK；需要恢复、inbox/outbox 或可靠原文检索时使用完整 demo 的实现。

## 6. 排查与扩展

| 现象 | 检查 |
|---|---|
| 无法连接 | Hub 是否启动；传入基础 URL；端口是否正确 |
| 加入失败 | Environment 是否已连接，env_id 是否与其 client_id 相同；等待 Hub 确认 |
| 未协商或未知工具错误 | 等目标 specification；用 `specification_for(peer)` 核对 tools 和参数 Schema |
| Event 额外字段被拒绝 | 查看接收方的 Event data_schema；无 Schema 只能 text |
| `ActionTimeoutError` | 仅本地未确认终态；保留原 ID 和进度，通过业务查询/恢复决定后续动作，不推断远端失败 |
| 改写同 ID 内容或第二个终态 | 检查 `ProtocolConflictError`；重试保留原消息内容和原结果 ID |

需要私聊时，同环境内每对主体分别协商。Human 的 `send_event()` 参数名是 `event_data`，`send_action()` 返回 None；不要套用 Agent 的返回值假设。

最小 Agent 完成后会自动退出。需要持续交互、Human 或 Monitor 时，使用 [完整 demo 和独立 CLI](../examples/README.md)；Monitor 使用 `--target` 选择实际在线的主体，完整 demo 自动等待 Hub 的订阅确认。监控构造、订阅及历史查询接口见 [API 参考](api_reference.md)。
