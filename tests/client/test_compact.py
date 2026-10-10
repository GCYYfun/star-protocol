import asyncio
import copy
import pytest

from star_protocol.client import AgentClient, EnvironmentClient
from star_protocol.client.compact import ActionTimeoutError, ProtocolConflictError
from star_protocol.models import COMPACT_PROTOCOL, Envelope, MessagePayload, SystemPayload


TOOL = {"name": "MOVE", "description": "移动", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"], "additionalProperties": False}}


class Agent(AgentClient):
    def __init__(self):
        super().__init__("agent", auto_reconnect=False)
        self.specifications = []
        self.results = []
        self.events = []

    async def on_specification(self, sender, content):
        self.specifications.append((sender, content))

    async def on_outcome(self, sender, content):
        self.results.append(content)

    async def on_event(self, sender, content):
        self.events.append(content)


class World(EnvironmentClient):
    def __init__(self):
        super().__init__("env", auto_reconnect=False)
        self.configure_capabilities(tools=[TOOL])
        self.actions = []
        self.specifications = []

    async def on_action(self, sender, content):
        self.actions.append(content)

    async def on_specification(self, sender, content):
        self.specifications.append((sender, content))


def connect_memory_wire(agent, world):
    """Exercise real BaseClient validation without sockets or sleeps."""
    peers = {"agent": agent, "env": world}
    pending = asyncio.Queue()
    for peer in peers.values():
        async def send_envelope(envelope, *, queue=pending):
            await queue.put(Envelope.model_validate_json(envelope.model_dump_json()))
        peer._messaging.send_envelope = send_envelope

    async def drain():
        while not pending.empty():
            message = await pending.get()
            await peers[message.recipient]._handle_message(message)
    return drain


async def pair():
    agent, world = Agent(), World()
    drain = connect_memory_wire(agent, world)
    await agent.send_discover("env")
    await drain()
    return agent, world, drain


@pytest.mark.asyncio
async def test_full_bidirectional_negotiation_and_declared_tool_validation():
    agent, world, drain = await pair()
    assert agent.protocol_for("env") == COMPACT_PROTOCOL
    assert world.protocol_for("agent") == COMPACT_PROTOCOL
    assert agent.specifications[0][1]["tools"] == [TOOL]
    assert world.specifications[0][1] == {"protocol": COMPACT_PROTOCOL, "tools": [], "events": []}
    with pytest.raises(Exception):
        await agent.send_action("env", "MOVE", {"x": 1, "undeclared": True}, action_id="bad")
    with pytest.raises(ValueError):
        await agent.send_action("env", "DELETE", {}, action_id="bad")
    await agent.send_action("env", "MOVE", {"x": 1}, action_id="saved-before-send")
    await drain()
    assert world.actions[0]["id"] == "saved-before-send"


@pytest.mark.asyncio
async def test_progress_does_not_complete_wait_and_replays_dedupe():
    agent, world, drain = await pair()
    await agent.send_action("env", "MOVE", {"x": 1}, action_id="move")
    await drain()
    waiting = asyncio.create_task(agent.await_action("move"))
    await asyncio.sleep(0)
    for identifier, status in (("o1", "accepted"), ("o2", "running")):
        content = {"id": identifier, "refs": ["move"], "status": status, "data": {"text": status}}
        await world.send_outcome("agent", content)
        await drain()
        assert not waiting.done()
    final = {"id": "o3", "refs": ["move"], "status": "completed", "data": {"text": "到达"}}
    await world.send_outcome("agent", final)
    await drain()
    assert await waiting == final
    await world.send_outcome("agent", final)
    await drain()
    assert len(agent.results) == 3
    assert agent.action_status("move") == "completed"
    with pytest.raises(ProtocolConflictError):
        await world.send_outcome("agent", {**final, "id": "o4", "status": "failed"})


@pytest.mark.asyncio
async def test_timeout_is_local_unknown_and_later_terminal_still_arrives():
    agent, world, drain = await pair()
    await agent.send_action("env", "MOVE", {"x": 1}, action_id="move")
    await drain()
    with pytest.raises(ActionTimeoutError) as error:
        await agent.await_action("move", timeout=0.001)
    assert error.value.action_id == "move" and error.value.status == "unknown"
    assert agent.action_status("move") == "unknown"
    final = {"id": "done", "refs": ["move"], "status": "completed", "data": {"text": "ok"}}
    await world.send_outcome("agent", final)
    await drain()
    assert await agent.await_action("move") == final
    assert len(world.actions) == 1


@pytest.mark.asyncio
async def test_runtime_handler_required_exactly_once_and_refs_preserved():
    agent, world = Agent(), World()
    received = []
    event = {"name": "state", "description": "状态", "handler": "runtime", "data_schema": {
        "type": "object", "properties": {"text": {"type": "string"}, "state": {"enum": ["idle"]}},
        "required": ["text", "state"], "additionalProperties": False}}
    with pytest.raises(ValueError, match="no installed handler"):
        agent.configure_capabilities(events=[event])
    async def handler(sender, content):
        received.append((sender, copy.deepcopy(content)))
    agent.configure_capabilities(events=[event], runtime_handlers={"state": handler})
    drain = connect_memory_wire(agent, world)
    await agent.send_discover("env")
    await drain()
    await world.send_event("agent", "observation", {"text": "源事件"}, event_id="source")
    await drain()
    await world.send_event("agent", "state", {"text": "空闲", "state": "idle"}, event_id="state", refs=["source"])
    await drain()
    await world.send_event("agent", "state", {"text": "空闲", "state": "idle"}, event_id="state", refs=["source"])
    await drain()
    assert len(received) == 1 and received[0][1]["refs"] == ["source"]
    assert len(agent.events) == 1
    with pytest.raises(ProtocolConflictError):
        await world.send_event("agent", "state", {"text": "改变正文", "state": "idle"}, event_id="state", refs=["source"])


@pytest.mark.asyncio
async def test_runtime_dispatch_failure_can_recover_with_same_immutable_event():
    agent, world = Agent(), World()
    calls = []
    async def handler(sender, content):
        calls.append(content["id"])
        if len(calls) == 1:
            raise RuntimeError("Temporary receiver failure")
    definition = {"name": "notice", "description": "通知", "handler": "runtime"}
    agent.configure_capabilities(events=[definition], runtime_handlers={"notice": handler})
    drain = connect_memory_wire(agent, world)
    await agent.send_discover("env")
    await drain()
    await world.send_event("agent", "notice", {"text": "消息"}, event_id="retry-event")
    with pytest.raises(RuntimeError):
        await drain()
    await world.send_event("agent", "notice", {"text": "消息"}, event_id="retry-event")
    await drain()
    await world.send_event("agent", "notice", {"text": "消息"}, event_id="retry-event")
    await drain()
    assert calls == ["retry-event", "retry-event"]


@pytest.mark.asyncio
async def test_action_retry_identity_conflict_and_owner_validation():
    agent, world, drain = await pair()
    await agent.send_action("env", "MOVE", {"x": 1}, action_id="move")
    await drain()
    await agent.send_action("env", "MOVE", {"x": 1}, action_id="move")
    await drain()
    assert [action["id"] for action in world.actions] == ["move", "move"]
    with pytest.raises(ProtocolConflictError):
        await agent.send_action("env", "MOVE", {"x": 2}, action_id="move")
    forged = Envelope(sender="env", recipient="agent", payload=MessagePayload(type="outcome", content={"id": "forged", "refs": ["unrelated"], "status": "completed", "data": {"text": "ok"}}))
    with pytest.raises(ProtocolConflictError):
        await agent._handle_message(forged)


@pytest.mark.asyncio
async def test_no_business_before_negotiation_and_unknown_version_not_enabled():
    agent, world = Agent(), World()
    drain = connect_memory_wire(agent, world)
    with pytest.raises(ValueError, match="not been negotiated"):
        await agent.send_action("env", "MOVE", {"x": 1}, action_id="move")
    with pytest.raises(ValueError, match="unsupported application protocol"):
        await agent._handle_message(Envelope(sender="env", recipient="agent", payload=MessagePayload(type="specification", content={"protocol": "other/1", "tools": [], "events": []})))
    assert agent.protocol_for("env") is None


@pytest.mark.asyncio
async def test_failed_outcome_application_handler_can_receive_same_original_again():
    agent, world, drain = await pair()
    await agent.send_action("env", "MOVE", {"x": 1}, action_id="move")
    await drain()
    received = []
    async def fail_once(sender, content):
        received.append(copy.deepcopy(content))
        if len(received) == 1:
            raise OSError("durable store unavailable")
    agent.on_outcome = fail_once
    final = {"id":"final", "refs":["move"], "status":"completed", "data":{"text":"到达"}}
    await world.send_outcome("agent", final)
    with pytest.raises(OSError):
        await drain()
    await world.send_outcome("agent", final)
    await drain()
    await world.send_outcome("agent", final)
    await drain()
    assert received == [final, final]
    assert agent.action_outcomes("move") == [final]


@pytest.mark.asyncio
async def test_per_peer_tool_subset_does_not_replace_environment_catalog():
    agent, world, drain = await pair()
    await world.send_specification("agent", [])
    await drain()
    assert world._own_specification["tools"] == [TOOL]
    with pytest.raises(ValueError, match="Undeclared"):
        await agent.send_action("env", "MOVE", {"x":1}, action_id="hidden")


@pytest.mark.asyncio
async def test_received_action_can_be_restored_for_original_outcome_replay():
    agent, world, drain = await pair()
    original = {"id":"persisted", "name":"MOVE", "params":{"x":1}}
    agent.restore_action("env", original)
    world.restore_received_action("agent", original)
    final = {"id":"persisted-outcome", "refs":["persisted"], "status":"completed", "data":{"text":"原结果"}}
    await world.send_outcome("agent", final)
    await drain()
    assert agent.results == [final]


@pytest.mark.asyncio
async def test_default_environment_callback_replays_original_rejection_on_action_retry():
    agent = Agent()
    world = EnvironmentClient("env", auto_reconnect=False)
    world.configure_capabilities(tools=[TOOL])
    drain = connect_memory_wire(agent, world)
    await agent.send_discover("env")
    await drain()
    sent = []
    original_send = world._messaging.send_envelope
    async def capture(envelope):
        sent.append(Envelope.model_validate_json(envelope.model_dump_json()))
        await original_send(envelope)
    world._messaging.send_envelope = capture
    await agent.send_action("env", "MOVE", {"x": 1}, action_id="default-rejected")
    await drain()
    original = copy.deepcopy(agent.results[0])
    assert original["status"] == "rejected"
    await agent.send_action("env", "MOVE", {"x": 1}, action_id="default-rejected")
    await drain()
    # Real BaseClient dispatch invokes the default callback twice, but the
    # second wire response keeps the first logical Outcome ID and every field.
    assert [frame.payload.content for frame in sent] == [original, original]
    assert world.action_outcomes("default-rejected") == [original]
    assert agent.results == [original]


@pytest.mark.asyncio
async def test_delivery_ack_routes_actual_sender_to_connector_callback():
    agent, world, _ = await pair()
    acknowledgements, notifications, sent = [], [], []

    async def receive_ack(sender, envelope_id):
        acknowledgements.append((sender, envelope_id))

    async def receive_notify(event, content):
        notifications.append((event, content))

    async def capture(frame):
        sent.append(Envelope.model_validate_json(frame.model_dump_json()))

    world.on_delivery_ack = receive_ack
    world.on_system_notify = receive_notify
    agent._messaging.send_envelope = capture
    original = Envelope(
        sender="env", recipient="agent",
        payload=MessagePayload(type="event", content={
            "id": "logical-event-id", "name": "observation", "data": {"text": "收到原文"},
        }),
    )
    await agent.send_delivery_ack("env", original.id)
    acknowledgement = sent[0]
    assert acknowledgement.type == "system"
    assert acknowledgement.sender == "agent" and acknowledgement.recipient == "env"
    assert acknowledgement.payload.type == "notify"
    assert acknowledgement.payload.content == {"event": "ACK", "msg": {"envelope_id": original.id}}
    assert acknowledgement.id != original.id
    assert acknowledgement.payload.content["msg"]["envelope_id"] != original.payload.content["id"]

    # Retrying the same physical ACK is safe: the durable connector owns
    # idempotent pending-delivery removal, so the SDK must not swallow retries.
    await world._messaging.route_message(acknowledgement)
    await world._messaging.route_message(acknowledgement)
    assert acknowledgements == [("agent", original.id), ("agent", original.id)]
    assert notifications == []

    notice = Envelope(type="system", sender="hub", recipient="env", payload=SystemPayload(
        type="notify", content={"event": "client_joined", "msg": {"client_id": "other", "role": "agent"}},
    ))
    await world._messaging.route_message(notice)
    assert notifications == [("client_joined", notice.payload.content)]


@pytest.mark.asyncio
@pytest.mark.parametrize("msg", [
    {},
    {"envelope_id": "550e8400-e29b-41d4-a716-446655440000", "extra": True},
    {"envelope_id": "logical-event-id"},
    {"envelope_id": None},
    "550e8400-e29b-41d4-a716-446655440000",
])
async def test_client_rejects_malformed_ack_before_callbacks(msg, caplog):
    world = World()
    acknowledgements, notifications = [], []

    async def receive_ack(sender, envelope_id):
        acknowledgements.append((sender, envelope_id))

    async def receive_notify(event, content):
        notifications.append((event, content))

    world.on_delivery_ack = receive_ack
    world.on_system_notify = receive_notify
    acknowledgement = Envelope(type="system", sender="agent", recipient="env", payload=SystemPayload(
        type="notify", content={"event": "ACK", "msg": msg},
    ))
    with pytest.raises((ValueError, TypeError, AttributeError)):
        await world._handle_system(acknowledgement)
    # The public message dispatcher isolates handler errors and logs them;
    # malformed ACKs still cannot reach either application callback.
    await world._messaging.route_message(acknowledgement)
    assert any("Error routing message:" in record.message for record in caplog.records)
    assert acknowledgements == [] and notifications == []


@pytest.mark.asyncio
async def test_client_does_not_send_ack_for_logical_content_id():
    agent = Agent()
    sent = []

    async def capture(frame):
        sent.append(frame)

    agent._messaging.send_envelope = capture
    with pytest.raises(ValueError):
        await agent.send_delivery_ack("env", "logical-event-id")
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode",["success","timeout","cancel","stop"])
async def test_join_waiters_are_cleaned_on_success_timeout_or_cancellation(mode):
    agent=Agent()
    async def send(frame):
        if mode=="success":
            agent._join_confirmed.set()
    async def joined(peer): pass
    agent.send=send
    agent.on_joined_environment=joined
    before=set(asyncio.all_tasks())
    task=asyncio.create_task(agent.join_with_retry("env",timeout=0.01,retry_interval=0.01))
    if mode in {"cancel","stop"}:
        await asyncio.sleep(0)
        if mode=="stop":
            await agent.stop()
        else:
            task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    elif mode=="timeout":
        with pytest.raises(TimeoutError): await task
    else:
        await task
    await asyncio.sleep(0)
    assert not [pending for pending in asyncio.all_tasks()-before if not pending.done()]
    assert agent._pending_env is None


@pytest.mark.asyncio
async def test_environment_member_role_is_hub_metadata_before_application_callback():
    world=World()
    observed=[]
    async def joined(identity): observed.append((identity,world.member_role(identity)))
    world.on_client_joined=joined
    await world.on_system_notify("client_joined",{"msg":{"client_id":"human","role":"human"}})
    assert observed==[("human","human")]
    await world.on_system_notify("client_left",{"msg":{"client_id":"human","reason":"leave"}})
    assert world.member_role("human") is None
