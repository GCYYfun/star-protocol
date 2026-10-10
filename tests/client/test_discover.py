"""
Tool Discovery 协议集成测试

每个测试用例都会在内部启动一个真实的 Hub Server，
通过真实 WebSocket 连接验证 discover / rediscover 的完整流程。
"""

import asyncio
import logging
import pytest
import pytest_asyncio

from star_protocol.models.payloads import ToolDefinition
from star_protocol.client import AgentClient, EnvironmentClient

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Hub Fixture：在随机端口启动真实 Hub Server
# ──────────────────────────────────────────────

@pytest_asyncio.fixture
async def hub_url():
    """启动一个临时 Hub Server，yield URL 后关闭"""
    import socket
    import uvicorn
    from app import create_hub_app

    # 找一个可用端口
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    app = create_hub_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    task = asyncio.create_task(server.serve())
    # 等待 server 就绪
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.1)

    url = f"ws://127.0.0.1:{port}"
    yield url

    server.should_exit = True
    await task


# ──────────────────────────────────────────────
# Mock 实现
# ──────────────────────────────────────────────

DEMO_TOOLS: list[ToolDefinition] = [
    {
        "name": "greet",
        "description": "向环境发送问候",
        "parameters": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        "tags": ["social"],
    },
    {
        "name": "calculate",
        "description": "执行四则运算",
        "parameters": {
            "type": "object",
            "properties": {"operation": {"type": "string"}},
            "required": ["operation"],
        },
        "tags": ["math"],
    },
]


class MockEnv(EnvironmentClient):
    def __init__(self):
        super().__init__(client_id="test_env", auto_reconnect=False)
        self.discover_count = 0

    async def on_discover(self, sender: str) -> list[ToolDefinition]:
        self.discover_count += 1
        logger.debug(f"[Env] on_discover #{self.discover_count} from {sender}")
        return DEMO_TOOLS


class MockAgent(AgentClient):
    def __init__(self):
        super().__init__(client_id="test_agent", auto_reconnect=False)
        self.received_specs: list[list[ToolDefinition]] = []
        self._spec_event = asyncio.Event()

    async def on_tool_specification(self, sender: str, tools: list[ToolDefinition]):
        self.received_specs.append(tools)
        logger.debug(f"[Agent] specification #{len(self.received_specs)}: {len(tools)} tools")
        self._spec_event.set()

    async def wait_for_spec(self, timeout: float = 3.0):
        """等待下一个 specification 到达"""
        self._spec_event.clear()
        await asyncio.wait_for(self._spec_event.wait(), timeout=timeout)

    async def on_outcome(self, sender, content):
        pass


# ──────────────────────────────────────────────
# 测试
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_discover_on_join(hub_url):
    """join_environment 后应自动触发 discover，Agent 收到工具清单"""
    env = MockEnv()
    agent = MockAgent()

    await env.connect(hub_url)
    await env.start()
    await agent.connect(hub_url)
    await agent.start()

    # join 会自动触发 discover
    agent._spec_event.clear()
    await agent.join_environment("test_env")

    await agent.wait_for_spec(timeout=3.0)

    # ① 收到 1 次清单
    assert len(agent.received_specs) == 1
    tools = agent.received_specs[0]

    # ② 工具数量正确
    assert len(tools) == 2, f"期望 2 个工具，实际 {len(tools)}"

    # ③ 工具名正确
    tool_names = {t["name"] for t in tools}
    assert tool_names == {"greet", "calculate"}

    # ④ agent.tools 缓存已更新
    assert len(agent.tools) == 2
    assert agent.tools[0]["name"] == "greet"

    # ⑤ Env 侧被 discover 1 次
    assert env.discover_count == 1

    await agent.leave_environment()
    await agent.stop()
    await env.stop()


@pytest.mark.asyncio
async def test_rediscover(hub_url):
    """rediscover() 后应再次收到工具清单，Env 的 on_discover 被调用第 2 次"""
    env = MockEnv()
    agent = MockAgent()

    await env.connect(hub_url)
    await env.start()
    await agent.connect(hub_url)
    await agent.start()

    # 第 1 次：join 触发 auto-discover
    agent._spec_event.clear()
    await agent.join_environment("test_env")
    await agent.wait_for_spec()
    assert len(agent.received_specs) == 1

    # 第 2 次：主动 rediscover
    agent._spec_event.clear()
    await agent.rediscover()
    await agent.wait_for_spec()

    assert len(agent.received_specs) == 2, "rediscover 后应收到第 2 次清单"
    assert env.discover_count == 2, f"Env 应被 discover 两次，实际 {env.discover_count}"

    # 两次清单内容相同
    assert agent.received_specs[0] == agent.received_specs[1]

    await agent.leave_environment()
    await agent.stop()
    await env.stop()


@pytest.mark.asyncio
async def test_rediscover_without_env_logs_warning(hub_url, caplog):
    """未加入环境时调用 rediscover() 应发出 warning 日志，不崩溃"""
    import logging

    agent = MockAgent()
    await agent.connect(hub_url)
    await agent.start()

    with caplog.at_level(logging.WARNING):
        await agent.rediscover()

    warning_found = any(
        "not in any environment" in r.message for r in caplog.records
    )
    assert warning_found, f"应产生 warning，实际日志: {[r.message for r in caplog.records]}"

    await agent.stop()


@pytest.mark.asyncio
async def test_manifest_payload_structure(hub_url):
    """验证 manifest 中每个工具都有 name / description / parameters / tags 字段"""
    env = MockEnv()
    agent = MockAgent()

    await env.connect(hub_url)
    await env.start()
    await agent.connect(hub_url)
    await agent.start()

    agent._spec_event.clear()
    await agent.join_environment("test_env")
    await agent.wait_for_spec()

    tools = agent.tools
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert isinstance(tool["parameters"], dict)

    await agent.leave_environment()
    await agent.stop()
    await env.stop()


@pytest.mark.asyncio
async def test_full_reverse_snapshot_precedes_immediate_runtime_presence(hub_url):
    """Application callback sends presence in the same receive-loop turn."""
    received = asyncio.Event()
    definition = {"name": "presence.announce", "description": "身份声明", "handler": "runtime",
                  "data_schema": {"type": "object", "properties": {
                      "text": {"type": "string"}, "identity": {"type": "object"}},
                      "required": ["text", "identity"], "additionalProperties": False}}
    async def receive(sender, content):
        assert sender == "test_agent" and content["id"] == "saved-presence"
        received.set()
    class ImmediateAgent(AgentClient):
        async def on_specification(self, sender, content):
            await self.send_event(sender, "presence.announce", {
                "text": "上线", "identity": {"id": self.client_id, "role": "agent"}},
                event_id="saved-presence")
    env = MockEnv()
    env.configure_capabilities(events=[definition], runtime_handlers={"presence.announce": receive})
    agent = ImmediateAgent("test_agent", auto_reconnect=False)
    await env.connect(hub_url)
    await env.start()
    await agent.connect(hub_url)
    await agent.start()
    try:
        await agent.join_environment("test_env")
        await asyncio.wait_for(received.wait(), 3)
        assert env.protocol_for("test_agent") == agent.protocol_for("test_env") == "agent-env-compact/2"
    finally:
        await agent.stop()
        await env.stop()
