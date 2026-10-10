import json
import pytest
from starlette.websockets import WebSocketDisconnect

from star_protocol.models import COMPACT_PROTOCOL, Envelope, MessagePayload
from star_protocol.server.router import MessageRouter
from star_protocol.server.connection import Session, ClientRole


TOOL = {"name": "LOOK", "description": "观测", "parameters": {"type": "object", "additionalProperties": False}}


class Socket:
    def __init__(self, inbound=None):
        self.inbound = list(inbound or [])
        self.sent = []

    async def accept(self):
        pass

    async def close(self, *args, **kwargs):
        pass

    async def receive_text(self):
        if self.inbound:
            return self.inbound.pop(0)
        raise WebSocketDisconnect()

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def router_pair():
    router = MessageRouter()
    agent, env = Socket(), Socket()
    manager = router.connection_manager
    manager._sessions["agent"] = Session("agent", ClientRole.AGENT, agent, current_env="env")
    manager._sessions["env"] = Session("env", ClientRole.ENVIRONMENT, env)
    manager._environments["env"] = {"agent"}
    manager._client_to_env["agent"] = "env"
    return router, agent, env


async def negotiate(router):
    for sender, recipient, tools in (("env", "agent", [TOOL]), ("agent", "env", [])):
        await router.route_message(Envelope(sender=sender, recipient=recipient, payload=MessagePayload(type="specification", content={"protocol": COMPACT_PROTOCOL, "tools": tools, "events": []})))


@pytest.mark.asyncio
async def test_hub_preserves_progress_refs_and_requires_both_snapshots():
    router, agent, env = router_pair()
    action = Envelope(sender="agent", recipient="env", payload=MessagePayload(type="action", content={"id": "action", "name": "LOOK", "params": {}}))
    await router.route_message(action)
    assert agent.sent[-1]["payload"]["type"] == "error"
    assert not env.sent
    await negotiate(router)
    await router.route_message(action)
    assert env.sent[-1]["payload"]["content"]["id"] == "action"
    outcome = {"id": "progress", "refs": ["action"], "status": "running", "data": {"text": "继续观测"}}
    await router.route_message(Envelope(sender="env", recipient="agent", payload=MessagePayload(type="outcome", content=outcome)))
    assert agent.sent[-1]["payload"]["content"] == outcome


@pytest.mark.asyncio
async def test_hub_rejects_missing_id_instead_of_inventing_one():
    router, agent, env = router_pair()
    await negotiate(router)
    # Bypass construction only to exercise the router's defensive revalidation.
    payload = MessagePayload.model_construct(type="action", content={"name": "LOOK", "params": {}})
    invalid = Envelope.model_construct(id="550e8400-e29b-41d4-a716-446655440000", timestamp=0, type="message", sender="agent", recipient="env", payload=payload)
    count = len(env.sent)
    await router.route_message(invalid)
    assert len(env.sent) == count
    assert agent.sent[-1]["payload"]["content"]["code"] == 400
    assert "id" not in payload.content


@pytest.mark.asyncio
async def test_socket_identity_is_authoritative_and_malformed_message_does_not_disconnect():
    forged = Envelope(sender="someone-else", recipient="env", payload=MessagePayload(type="discover", content={"protocols": [COMPACT_PROTOCOL]}))
    socket = Socket(['{"invalid":true}', forged.model_dump_json()])
    router = MessageRouter()
    await router.handle_connection(socket, "agent", "actual-agent")
    errors = [message["payload"]["content"] for message in socket.sent if message["payload"]["type"] == "error"]
    assert [error["code"] for error in errors] == [400, 403]


@pytest.mark.asyncio
async def test_hub_never_copies_direct_private_event_to_environment():
    router, agent, env = router_pair()
    other = Socket()
    router.connection_manager._sessions["other"] = Session("other", ClientRole.HUMAN, other, current_env="env")
    router.connection_manager._environments["env"].add("other")
    router.connection_manager._client_to_env["other"] = "env"
    for sender, recipient in (("agent", "other"), ("other", "agent")):
        await router.route_message(Envelope(sender=sender, recipient=recipient, payload=MessagePayload(type="specification", content={"protocol": COMPACT_PROTOCOL, "tools": [], "events": []})))
    event = {"id": "private", "name": "speech", "data": {"text": "私聊"}, "refs": ["prior"]}
    await router.route_message(Envelope(sender="agent", recipient="other", payload=MessagePayload(type="event", content=event)))
    assert other.sent[-1]["payload"]["content"] == event
    assert not env.sent


@pytest.mark.asyncio
async def test_delivery_ack_authenticates_environment_and_preserves_receiver_identity():
    from star_protocol.models import SystemPayload
    router, agent, env = router_pair()
    identifier = "550e8400-e29b-41d4-a716-446655440000"
    ack = Envelope(type="system",sender="agent",recipient="env",payload=SystemPayload(type="notify",content={"event":"VILLAGE_DELIVERY_ACK","msg":{"envelope_id":identifier}}))
    await router.handle_system_message(ack)
    assert env.sent[-1]["sender"] == "agent"
    assert env.sent[-1]["payload"]["content"] == ack.payload.content
    invalid = ack.model_copy(update={"recipient":"not-my-environment"})
    await router.handle_system_message(invalid)
    assert agent.sent[-1]["payload"]["content"]["code"] == 403


@pytest.mark.asyncio
async def test_hub_after_restart_does_not_invent_original_action_binding():
    router, agent, env = router_pair()
    await negotiate(router)
    # A receiver's durable journal, not a restarted Hub's volatile cache, owns
    # the original binding. SDK receivers still reject unowned results.
    final={"id":"original-result","refs":["original-action"],"status":"completed","data":{"text":"原结果"}}
    await router.route_message(Envelope(sender="env",recipient="agent",payload=MessagePayload(type="outcome",content=final)))
    assert agent.sent[-1]["payload"]["content"] == final
