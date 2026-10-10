"""One command, real WebSocket Hub, deterministic protocol capability checks."""

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import socket
import tempfile

from jsonschema import ValidationError
import uvicorn

from app import create_hub_app
from star_protocol import ActionTimeoutError, AgentClient, ProtocolConflictError
from star_protocol.models import COMPACT_PROTOCOL, Envelope, MessagePayload, gen_id

from .contracts import validate_configs
from .chronology import chronology_checks
from .environment import DemoEnvironment
from .display import ProtocolDisplay
from .flow import DemoFlow
from .timing import DemoTiming, load_timing
from .peers import DemoAgent, DemoHuman


class Transcript:
    def __init__(self, state_dir, *, trace=False, quiet=False):
        self.path = Path(state_dir) / "transcript.jsonl"
        self.trace = trace
        self.quiet = quiet
        self.records = []
        self.checks = []
        self.stage_id = None
        self.elapsed = None
        self._stream = self.path.open("w", encoding="utf-8")
        self.display = None if quiet else ProtocolDisplay(trace=trace, title="Star Protocol 完整演示", live=True)
        if self.display:
            self.display.start()

    def emit(self, record):
        record = json.loads(json.dumps(record, ensure_ascii=False, allow_nan=False))
        if self.stage_id is not None:
            record.setdefault("stage_id", self.stage_id)
        if self.elapsed:
            record.setdefault("elapsed", round(self.elapsed(), 3))
        record["seq"] = len(self.records) + 1
        self.records.append(record)
        self._stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._stream.flush()
        if self.display:
            self.display.emit(record)

    def check(self, name, condition=True, **details):
        if not condition:
            raise AssertionError(f"Demo check failed: {name}")
        self.checks.append(name)
        self.emit({"component": "demo", "event": "check", "name": name, **details})

    async def rejected(self, name, operation, expected=(ValueError, ValidationError)):
        before = len(self.records)
        try:
            await operation()
        except expected as error:
            assert not any(row["event"] == "wire.send.start" for row in self.records[before:]), (
                "A local rejection must happen before any network send"
            )
            self.check(name, reason=str(error), exception=type(error).__name__, not_sent=True)
        else:
            raise AssertionError(f"Expected rejection: {name}")

    def close(self):
        self._stream.close()
        if self.display:
            self.display.finish()


@asynccontextmanager
async def local_hub():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_hub_app(), log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async def started():
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Hub exited before becoming ready")
                await asyncio.sleep(0.01)
        await asyncio.wait_for(started(), 5)
        yield f"ws://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 5)
        finally:
            listener.close()


async def run_scenario(hub_url, state_dir, *, trace=False, quiet=False, timing=None):
    """Raises on a missing capability; returns the verified summary on success."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    log = Transcript(state_dir, trace=trace, quiet=quiet)
    timing = timing or DemoTiming()
    flow = DemoFlow(log, timing)
    log.elapsed = lambda: flow.clock() - flow.started
    succeeded = False
    clients = []
    env = agent = colleague = human = monitor = None

    async def register_clients():
        nonlocal env, agent, colleague, human
        await flow.step("demo_env", "注册本地工具与 Event", "调用 configure_capabilities：安装六个工具参数 Schema、speech 模型输入和 activity.state runtime 处理器。")
        env = DemoEnvironment(state_dir=state_dir, emit=log.emit)
        clients.append(env)
        await flow.step("demo_env", "Environment 本地注册已完成", "六个工具共用真实 on_action 分发入口；Event 已绑定本地处理方法。此时尚未向 Agent 发布声明。")
        peers = []
        for peer_class, identifier in ((DemoAgent, "demo_agent"), (DemoAgent, "demo_colleague"), (DemoHuman, "demo_human")):
            await flow.step(identifier, "注册本地接收 Event", "注册 observation/speech 模型输入及 interaction.feedback runtime 处理器；本主体不提供环境工具。")
            peer = peer_class(identifier, state_dir=state_dir, emit=log.emit)
            clients.append(peer)
            peers.append(peer)
            await flow.step(identifier, "接收处理器注册已完成", "Event 声明与实际回调已绑定；Outcome 由框架 on_outcome 接收，随后再向环境交换接收声明。")
        agent, colleague, human = peers

    async def launch():
        await flow.step("demo_env", "连接 Hub 并发布环境能力", "本地注册完成后接入 Hub；收到 discover 才向请求者发送工具与 Event 接收声明。")
        await env.connect(hub_url)
        await env.start()
        for peer in (agent, colleague, human):
            await flow.step(peer.client_id, "请求加入并发现环境能力", "连接 Hub、加入 demo_env；发送 discover，接收环境的工具/Event 声明，再交换自己的接收声明。")
            await peer.connect_join(hub_url)
            await env.ready(peer.client_id)
            await flow.step("hub", "成员加入已确认", f"已确认 {peer.client_id} 加入 demo_env；环境可读取其真实角色 {env.member_role(peer.client_id)}。", delay=0)
            await flow.step(peer.client_id, "双方声明已接收并生效", "已接收 Env 的工具/Event 清单；Env 也已接收本主体 Event 声明，现在按这些 Schema 调用或发送消息。", delay=0)

    async def action(peer, name, params=None, *, action_id=None, delay=None):
        identifier = action_id or gen_id("action")
        await flow.step(peer.client_id, "准备调用工具", f"演示策略选择 {name}；保存原 Action 后向 demo_env 发出请求。", delay=delay)
        await peer.send_action("demo_env", name, params or {}, action_id=identifier)
        await flow.step(peer.client_id, "等待最终 Outcome", "接收中间进度并等待原 Action 的终态；结果原文由接收端持久保存。", delay=0)
        result = await peer.settled(identifier)
        await flow.step(peer.client_id, "最终回执已保存", f"{name} 的实际 Outcome.status={result['status']}；下一步仍由调用者决定。", delay=0)
        return identifier, result

    async def event(sender, receiver, name, data, *, refs=None, event_id=None):
        identifier = event_id or gen_id("event")
        await flow.step(sender.client_id, "准备发送 Event", f"向 {receiver.client_id} 发送 {name}，正文与 refs 保持原始语义。")
        await sender.send_event(receiver.client_id, name, data, event_id=identifier, refs=refs)
        await receiver.wait_for(lambda: receiver.original(identifier) is not None)
        await flow.step(receiver.client_id, "Event 原文已保存", "真实消息已到达接收回调；演示策略可据此继续发言。", delay=0)
        return identifier

    async def stop_roles():
        # Each SDK stop may wait for its receive loop; independent peers can
        # close together, followed by their Environment.
        members = [client for client in clients if client.role != "environment"]
        if members:
            await asyncio.gather(*(client.stop() for client in members))
            for client in members:
                clients.remove(client)
        for client in clients[:]:
            await client.stop()
            clients.remove(client)

    try:
        await flow.stage("configuration", "配置与处理器注册", "先定义各主体能接收什么：工具 params Schema、Event data_schema 与实际 runtime handler。")
        specs = validate_configs()
        log.check("配置：三个完整 receiver specification 与本地 Schema", len(specs) == 3)
        async def missing_handler():
            AgentClient("configuration_probe").configure_capabilities(events=specs["agent"]["events"])
        await log.rejected("Runtime 声明：仅 Schema 没有处理器不能启用", missing_handler)
        await register_clients()
        await flow.stage("join", "主体加入与双向协商", "Environment 提供确定性工具；两个 Agent 与 Human 分别加入，并等待双方能力声明确认。")
        await launch()
        log.check("真实 Hub：三种业务角色加入并完成双向能力协商", all(
            peer.protocol_for("demo_env") == COMPACT_PROTOCOL and
            env.protocol_for(peer.client_id) == COMPACT_PROTOCOL
            for peer in (agent, colleague, human)))
        log.check("工具和 Event 声明：远端完整快照可读", len(agent.specification_for("demo_env")["tools"]) == 6)

        await flow.stage("tools", "主动观测与工具参数校验", "Agent 用固定演示策略探索房间并调用计算器，双方按照已协商 Schema 校验请求。")
        _, observed = await action(agent, "observe")
        log.check("主动观测：完成结果只含自然语言 text", observed["status"] == "completed" and set(observed["data"]) == {"text"})
        _, calculated = await action(agent, "calculate", {"operation": "add", "a": 7, "b": 5})
        log.check("工具：Schema 合法参数完成计算", calculated["status"] == "completed")
        await log.rejected("Schema：拒绝缺少必填参数", lambda: agent.send_action(
            "demo_env", "calculate", {"a": 1, "b": 2}, action_id=gen_id("action")))
        await log.rejected("Schema：拒绝错误枚举", lambda: agent.send_action(
            "demo_env", "calculate", {"operation": "pow", "a": 1, "b": 2}, action_id=gen_id("action")))
        await log.rejected("Schema：拒绝未声明字段", lambda: agent.send_action(
            "demo_env", "set_light", {"on": True, "extra": 1}, action_id=gen_id("action")))
        await log.rejected("Schema：拒绝错误字段类型", lambda: agent.send_action(
            "demo_env", "set_light", {"on": "yes"}, action_id=gen_id("action")))
        await log.rejected("能力清单：拒绝未声明工具", lambda: agent.send_action(
            "demo_env", "delete_world", {}, action_id=gen_id("action")))

        await flow.stage("execution", "世界修改、原结果重放与业务拒绝", "环境将世界变更与 Outcome 同次提交；同 ID 重试返回原结果，权限和业务失败分别有明确终态。")
        writes_before = env.light_write_count
        light_id, light_result = await action(agent, "set_light", {"on": True})
        await flow.step(agent.client_id, "重发原 Action", "复用 set_light 的原 ID 和参数；环境账本重放原 Outcome，不再次修改灯光。")
        await agent.send_action("demo_env", "set_light", {"on": True}, action_id=light_id)
        # The next request is a wire barrier: the Environment's serial receiver
        # handles the retry before it handles this query. No fixed sleep needed.
        _, query_result = await action(agent, "get_operation_result", {"action_id": light_id})
        log.check("重试：同 Action ID 重放原 Outcome，世界仅修改一次",
                  env.light_on and env.light_write_count == writes_before + 1 and
                  env.stored_outcomes(agent.client_id, light_id) == [light_result] and
                  agent.stored_outcomes(light_id) == [light_result])
        log.check("查询：自身有独立 Outcome，原结果另按原 ID 重放", query_result["refs"] != [light_id])
        await log.rejected("身份冲突：同 Action ID 不可改参数", lambda: agent.send_action(
            "demo_env", "set_light", {"on": False}, action_id=light_id), expected=(ProtocolConflictError,))
        await log.rejected("Outcome：拒绝同一 Action 的矛盾终态", lambda: env.send_outcome(
            agent.client_id, {"id": gen_id("outcome"), "refs": [light_id], "status": "failed", "data": {"text": "不能推翻既有终态。"}}), expected=(ProtocolConflictError,))
        await log.rejected("Outcome：data 中拒绝 text 之外的字段", lambda: env.send_outcome(
            agent.client_id, {"id": gen_id("outcome"), "refs": [light_id], "status": "completed", "data": {"text": "正文", "result": 1}}))
        _, rejected = await action(human, "set_light", {"on": False})
        log.check("业务拒绝：Human 修改灯光返回 rejected", rejected["status"] == "rejected" and env.light_on)
        _, failed = await action(agent, "calculate", {"operation": "div", "a": 1, "b": 0})
        log.check("业务失败：failed 的原因由 text 说明", failed["status"] == "failed")
        _, hidden = await action(human, "get_operation_result", {"action_id": light_id})
        log.check("历史权限：不能查询其他调用者的动作", hidden["status"] == "rejected")

        await flow.stage("continuous", "持续动作、超时与取消", "观察 accepted/running/final；本地等待超时不取消远端动作，显式 cancel 有自己的 Action。")
        await flow.step(agent.client_id, "启动持续动作", f"调用真实 wait 工具，等待 {timing.wait_seconds:g} 秒，观察独立的中间 Outcome。")
        wait_id = gen_id("action")
        await agent.send_action("demo_env", "wait", {"seconds": timing.wait_seconds}, action_id=wait_id)
        try:
            # Start the short local timeout before progress can finish. Narration
            # never sleeps inside this timing-sensitive protocol section.
            await agent.await_action(wait_id, timeout=0.001)
        except ActionTimeoutError as error:
            log.check("等待超时：仅本地 unknown，不取消或自动重发", error.status == "unknown")
        else:
            raise AssertionError("The wait should still be running")
        await agent.wait_for(lambda: any(item["status"] == "running" for item in agent.action_outcomes(wait_id)))
        await flow.step(agent.client_id, "已收到持续动作进度", "已保存 running 回执；从原 Action 的结果流读取最终 Outcome。", delay=0)
        completed = await agent.settled(wait_id)
        await flow.step("demo_env", "持续动作已结束", f"原 wait 返回 {completed['status']}，中间回执和最终回执各自保留原 ID。", delay=0)
        wait_results = agent.stored_outcomes(wait_id)
        log.check("持续动作：accepted → running → completed，独立 Outcome ID",
                  [item["status"] for item in wait_results] == ["accepted", "running", "completed"] and
                  len({item["id"] for item in wait_results}) == 3 and
                  all(item["refs"] == [wait_id] for item in wait_results))

        await flow.step(agent.client_id, "准备取消示例", "启动另一个持续动作，并在收到 running 后立即发出 cancel。")
        cancelled_id = gen_id("action")
        await agent.send_action("demo_env", "wait", {"seconds": 3}, action_id=cancelled_id)
        await agent.wait_for(lambda: agent.action_status(cancelled_id) == "running")
        cancel_id, cancel_result = await action(agent, "cancel", {"action_id": cancelled_id}, delay=0)
        cancelled = await agent.settled(cancelled_id)
        log.check("取消：原持续动作 cancelled，取消请求另有 completed",
                  cancelled["status"] == "cancelled" and cancel_result["status"] == "completed" and
                  cancel_result["refs"] == [cancel_id])
        log.check("Outcome：六种状态全部实际出现", {
            item["status"] for identifier in (light_id, wait_id, cancelled_id)
            for item in agent.stored_outcomes(identifier)} | {rejected["status"], failed["status"]}
                  == {"accepted", "running", "completed", "rejected", "failed", "cancelled"})

        await flow.stage("events", "环境感知与 Agent 活动反馈", "环境提供自然语言提示；Agent 报告自身 activity.state；已声明的触觉反馈由 runtime 处理。")
        await flow.step("demo_env", "主动提示 Agent", "向 Agent 发送 observation；Agent 收到自然语言后自行选择下一步。")
        source_id = gen_id("event")
        await env.send_event(agent.client_id, "observation", {"text": "门口亮起了一盏提示灯，你可以自行决定是否观察。"}, event_id=source_id)
        await agent.wait_for(lambda: agent.original(source_id) is not None)
        log.check("主动提示：默认 Event 仅 text，进入模型输入回调", agent.original(source_id)["data"] == {"text": "门口亮起了一盏提示灯，你可以自行决定是否观察。"})
        default_id = gen_id("event")
        await env.send_event(agent.client_id, "ambient.notice", {"text": "普通新事件名称默认也按自然语言输入处理。"}, event_id=default_id)
        await agent.wait_for(lambda: agent.original(default_id) is not None)
        log.check("普通 Event：未声明业务名称也只能携 text", agent.original(default_id)["name"] == "ambient.notice")
        await flow.step(agent.client_id, "向环境报告活动状态", "activity.state 只更新自身行为展示；refs 关联此前收到的提示。")
        control_id = gen_id("event")
        await agent.send_event("demo_env", "activity.state", {"text": "我在观察房间。", "state": "working"}, event_id=control_id, refs=[source_id])
        # A query forms a deterministic barrier for the Environment handler.
        await action(agent, "observe")
        log.check("双向 Event：Agent runtime 状态通知更新环境展示", env.activity_states.get(agent.client_id) == "working")
        await flow.step("demo_env", "发送已声明的触觉反馈", "interaction.feedback 按接收方 Schema 校验，交给已安装的 runtime handler。")
        feedback_id = gen_id("event")
        feedback = {"text": "手柄轻微震动，提示操作已被环境感知。", "channel": "haptic", "intensity": 0.2}
        calls_before = agent.feedback_calls
        await env.send_event(agent.client_id, "interaction.feedback", feedback, event_id=feedback_id, refs=[control_id, source_id])
        await agent.wait_for(lambda: agent.original(feedback_id) is not None)
        await env.send_event(agent.client_id, "interaction.feedback", feedback, event_id=feedback_id, refs=[control_id, source_id])
        await action(agent, "observe")
        log.check("Runtime Schema：反馈由实际 handler 解析，有序 refs 保留，重复只处理一次",
                  agent.feedback_calls == calls_before + 1 and
                  agent.original(feedback_id)["refs"] == [control_id, source_id])
        human_feedback_id = gen_id("event")
        await env.send_event(human.client_id, "interaction.feedback", feedback, event_id=human_feedback_id)
        await human.wait_for(lambda: human.original(human_feedback_id) is not None)
        log.check("Human 输入：同一已声明反馈 Schema 也由 Human handler 消费", human.feedback_calls == 1)
        await log.rejected("Event Schema：拒绝默认 text 外的未声明字段", lambda: env.send_event(
            agent.client_id, "observation", {"text": "通知", "extra": True}, event_id=gen_id("event")))
        await log.rejected("Event Schema：拒绝反馈强度越界", lambda: env.send_event(
            agent.client_id, "interaction.feedback", {**feedback, "intensity": 2}, event_id=gen_id("event")))
        await log.rejected("Event refs：拒绝引用已知 Action ID", lambda: agent.send_event(
            "demo_env", "speech", {"text": "引用类型错误"}, event_id=gen_id("event"), refs=[light_id]), expected=(ProtocolConflictError,))
        await log.rejected("Event 身份：同 ID 不可更改正文", lambda: env.send_event(
            agent.client_id, "interaction.feedback", {**feedback, "text": "不同正文"}, event_id=feedback_id, refs=[control_id, source_id]), expected=(ProtocolConflictError,))

        await flow.stage("renegotiation", "接收能力更新与重新协商", "Agent 增加 demo.notice 接收声明，重新交换完整 specification 后使用更新的契约。")
        # Schema declares receivers. Add a real model declaration then exchange
        # complete snapshots again; discovery does not install runtime behavior.
        updated = validate_configs()["agent"]
        updated["events"].append({"name": "demo.notice", "description": "新增自然语言通知", "handler": "model"})
        agent.configure_capabilities(events=updated["events"])
        await agent.send_discover("demo_env")
        await agent.ready("demo_env")
        await env.ready(agent.client_id)
        log.check("能力更新：重新交换完整 receiver snapshot", any(
            item["name"] == "demo.notice" for item in env.specification_for(agent.client_id)["events"]))
        notice_id = gen_id("event")
        await env.send_event(agent.client_id, "demo.notice", {"text": "这条消息使用刚声明的新接收能力。"}, event_id=notice_id)
        await agent.wait_for(lambda: agent.original(notice_id) is not None)

        await flow.stage("conversations", "公聊、Agent 私聊与 Human 私聊", "公共提示广播给所有成员；私聊先独立协商，回复通过 Event refs 建立因果关联。")
        await flow.step("demo_env", "向全体成员广播", "同一公共 Event 投递给多个成员；这不等同于同接收者重复补发。")
        broadcast_id = gen_id("event")
        await env.broadcast_event("observation", {"text": "公共提示：演示房间中的所有成员都可以收到这条消息。"}, event_id=broadcast_id)
        for peer in (agent, colleague, human):
            await peer.wait_for(lambda peer=peer: peer.original(broadcast_id) is not None)
        log.check("公聊：环境 text 广播到所有已协商成员")
        for target in (colleague, human):
            await flow.step(agent.client_id, "建立私聊接收契约", f"与 {target.client_id} 独立协商；Environment 不会自动收到私聊副本。")
            await agent.send_discover(target.client_id)
            await agent.ready(target.client_id)
            await target.ready(agent.client_id)
            first = await event(agent, target, "speech", {"text": f"你好，{target.client_id}，这是一条私聊。"})
            reply = await event(target, agent, "speech", {"text": "我收到了，可以自然地接着聊。"}, refs=[first])
            log.check(f"私聊：Agent ↔ {target.role} 双向协商和因果引用", agent.original(reply)["refs"] == [first])
            log.check(f"私聊隔离：{target.client_id} 的正文不复制给 Environment", all(
                record["content"]["id"] not in {first, reply} for record in env.speeches))

        await flow.stage("stream-monitor", "流片段与独立监控", "Stream 传递增量片段，Monitor 通过订阅确认接收内部遥测；两者都不替代业务 Outcome。")
        await flow.step("demo_env", "发送流片段", "依次发送 sequence=0 和结束片段 sequence=1，保留 is_end。")
        stream_id = gen_id("stream")
        await env.send(Envelope(sender="demo_env", recipient=agent.client_id, payload=MessagePayload(
            type="stream", content={"id": stream_id, "sequence": 0, "chunk": "增量片段", "is_end": False})))
        await env.send(Envelope(sender="demo_env", recipient=agent.client_id, payload=MessagePayload(
            type="stream", content={"id": stream_id, "sequence": 1, "chunk": "结束片段", "is_end": True})))
        # Query barrier also waits for both stream messages in the peer receive loop.
        await action(agent, "observe")
        chunks = [row["content"] for row in log.records if row["event"] == "stream" and row["content"]["id"] == stream_id]
        log.check("Star stream：增量片段与结束标记保留，不代替 Outcome", [row["sequence"] for row in chunks] == [0, 1] and chunks[-1]["is_end"])

        await flow.step("monitor", "订阅 Agent 遥测", "连接 Hub，发送 monitor.ctrl，并等待 Hub 的真实 subscribed 通知。")
        from .monitor import DemoMonitor
        monitor = DemoMonitor(emit=lambda record: log.emit({
            "component": "monitor", "event": "monitor." + record["name"], **record}))
        await monitor.connect(hub_url)
        await monitor.start()
        await agent.enable_monitoring()
        await monitor.subscribe_to_client(agent.client_id)
        await monitor.ready(agent.client_id)
        await flow.step(agent.client_id, "发送内部遥测", "Monitor 已确认订阅，发送一条 demo.trace 并等待实际到达。")
        await agent.send_monitor_data("demo.trace", {"text": "内部遥测单独使用 Star monitor。"})
        await monitor.wait_record("demo.trace")
        log.check("Star monitor：真实订阅确认和遥测转发")
        await agent.disable_monitoring()
        await monitor.stop()
        monitor = None

        await flow.stage("delivery", "持久接收、ACK 与漏确认模拟", "接收端验证并保存完整 Envelope 后确认投递；环境核验接收者并维护持久 outbox。")
        await flow.step("demo_env", "核验已有投递确认", "等待真实 ACK 清空原投递队列。")
        async def delivery_settled():
            while env.outbox_count:
                await asyncio.sleep(0.01)
        await asyncio.wait_for(delivery_settled(), 5)
        log.check("投递 ACK：完整 Envelope 已落盘，环境核验接收者并清空 outbox", env.ack_count > 0)
        errors_before = [error for client in clients for error in client.errors]
        log.check("正常网络路径：没有未处理协议或业务回调错误", not errors_before)

        # Simulate lost ACK after valid reception and durable storage. It is a
        # transport demonstration: the logical Event was already received.
        await flow.step(agent.client_id, "模拟消息已收但确认暂未送达", "仅本次不发 ACK：Event 原文仍被保存，环境保留原 Envelope UUID。")
        agent.ack_enabled = False
        pending_id = gen_id("event")
        await env.send_event(agent.client_id, "observation", {"text": "这条原消息已落盘，但本次确认暂未送达环境。"}, event_id=pending_id)
        await agent.wait_for(lambda: agent.original(pending_id) is not None)
        pending = env.pending_deliveries(agent.client_id)
        original_delivery = next(item for item in pending if item["payload"]["content"]["id"] == pending_id)
        log.check("漏 ACK：接收方保存原文，环境仍保留原投递 UUID", env.outbox_count == 1)

        # Restart both applications while preserving their own durable stores.
        # No model/JSON-text parsing invents a success during recovery.
        await flow.stage("recovery", "应用重启与原消息恢复", "关闭角色实例后从同一 SQLite 账本恢复，重新加入、协商并查询原 Action，再补发未确认投递。")
        await flow.step("demo", "重启业务主体", "先停止 Agent/Human 和 Environment 的接收循环；Hub 保持运行。")
        count_before_restart = env.light_write_count
        await stop_roles()
        await register_clients()
        await launch()
        log.check("实例恢复：应用从 SQLite 还原原 Action 绑定", agent.original_action(light_id) is not None)
        recovery_id, _ = await action(agent, "get_operation_result", {"action_id": light_id})
        await agent.wait_for(lambda: agent.action_status(light_id) == "completed")
        log.check("恢复查询：收到原 Outcome ID，不重复修改世界",
                  agent.action_outcomes(light_id) == [light_result] and
                  env.stored_outcomes(agent.client_id, light_id) == [light_result] and
                  env.light_write_count == count_before_restart)
        await agent.send_action("demo_env", "set_light", {"on": True}, action_id=light_id)
        await action(agent, "observe")
        log.check("重启后重试：原请求、原结果、原副作用次数保持不变", env.light_write_count == count_before_restart)
        await flow.step("demo_env", "补发未确认的原 Envelope", "重用原 UUID 和完整原文；接收者重新确认后清除 outbox。")
        await env.replay_pending(agent.client_id)
        await asyncio.wait_for(delivery_settled(), 5)
        received_deliveries = [row["envelope"] for row in log.records
                              if row["event"] == "wire.receive" and row["component"] == agent.client_id
                              and row["envelope"]["id"] == original_delivery["id"]]
        log.check("原投递恢复：同 Envelope UUID 和完整原文重放后 ACK 清队列",
                  env.outbox_count == 0 and len(received_deliveries) == 2 and
                  all(item == original_delivery for item in received_deliveries))
        log.check("最终网络路径：所有接收者无错误", not [error for client in clients for error in client.errors])
        await flow.stage("shutdown", "关闭主体与保存演示记录", "全部业务检查完成；停止角色并断开连接，保存完整原文、流程注释及验证结果。")
        await flow.step("demo", "关闭演示主体", "停止所有接收循环，关闭 SQLite 连接；本地临时 Hub 由启动器随后关闭。")
        await stop_roles()
        for name, passed in chronology_checks(log.records).items():
            log.check(name, passed)
        summary = {"protocol": COMPACT_PROTOCOL, "passed": True, "checks": log.checks,
                   "check_count": len(log.checks), "outcome_statuses": sorted({
                       item["status"] for item in (completed, cancelled, failed, rejected, light_result)} |
                       {"accepted", "running"}), "light_write_count": env.light_write_count,
                   "recovered_action_id": light_id, "recovered_outcome_id": light_result["id"],
                   "recovery_query_id": recovery_id,
                   "replayed_delivery_id": original_delivery["id"], "state_directory": str(state_dir.resolve())}
        (state_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if log.display:
            log.display.summary = summary
        succeeded = True
        flow.finish(success=True)
        return summary
    finally:
        if monitor is not None:
            await monitor.stop()
        try:
            await stop_roles()
        finally:
            flow.finish(success=succeeded)
            log.close()


async def run_demo(*, hub_url=None, state_dir=None, trace=False, quiet=False, timing=None):
    with tempfile.TemporaryDirectory(prefix="star-protocol-demo-") as temporary:
        directory = Path(state_dir) if state_dir is not None else Path(temporary)
        if hub_url:
            return await run_scenario(hub_url, directory, trace=trace, quiet=quiet, timing=timing)
        async with local_hub() as url:
            result = await run_scenario(url, directory, trace=trace, quiet=quiet, timing=timing)
        if state_dir is None and not quiet:
            ProtocolDisplay().message("默认临时状态已清理；使用 --state-dir 保留完整记录。", style="dim")
        return result


def main():
    parser = argparse.ArgumentParser(description="完整 Star Protocol 0.3.0 演示；默认自动启动真实本地 Hub。")
    parser.add_argument("--hub", help="使用已有 Hub，例如 ws://127.0.0.1:8765")
    parser.add_argument("--state-dir", type=Path, help="保留 SQLite、transcript.jsonl 和 summary.json 的目录")
    parser.add_argument("--trace", action="store_true", help="在关系树中展开完整三层报文、Schema 和检查明细")
    parser.add_argument("--timing", type=Path, help="自定义演示时间配置 JSON；默认 config/demo-timing.json")
    parser.add_argument("--stage-delay", type=float, help="每阶段模拟停顿秒数，0..10")
    parser.add_argument("--step-delay", type=float, help="每步骤模拟停顿秒数，0..10")
    parser.add_argument("--wait-seconds", type=float, help="真实 wait 工具的等待秒数，0.05..3")
    parser.add_argument("--fast", action="store_true", help="阶段与步骤停顿归零；真实工具仍按 wait-seconds 执行")
    arguments = parser.parse_args()
    try:
        timing = load_timing(arguments.timing, stage_delay=arguments.stage_delay,
                             step_delay=arguments.step_delay, wait_seconds=arguments.wait_seconds)
        if arguments.fast:
            timing = DemoTiming(stage_delay=0, step_delay=0, wait_seconds=timing.wait_seconds)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    try:
        asyncio.run(run_demo(hub_url=arguments.hub, state_dir=arguments.state_dir, trace=arguments.trace, timing=timing))
    except KeyboardInterrupt:
        ProtocolDisplay().message("演示已停止。", style="yellow")


if __name__ == "__main__":
    main()
