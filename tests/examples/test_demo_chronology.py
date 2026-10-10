"""Sequence checks detect misleading ordering and preserve replay semantics."""

from copy import deepcopy

import pytest

from examples.protocol_demo.chronology import chronology_checks


ENV_SPEC = {
    "protocol": "agent-env-compact/2",
    "tools": [{"name": "observe"}],
    "events": [],
}
PEER_SPEC = {
    "protocol": "agent-env-compact/2",
    "tools": [],
    "events": [{"name": "speech", "handler": "model"}],
}


def stamp(rows):
    for position, row in enumerate(rows, 1):
        row.update(seq=position, elapsed=position / 100)
    return rows


def packet(identifier, sender, recipient, kind, content, *, envelope_type="message"):
    return {
        "id": identifier,
        "sender": sender,
        "recipient": recipient,
        "type": envelope_type,
        "payload": {"type": kind, "content": deepcopy(content)},
    }


def trace():
    rows = []

    def emit(event, component, *, envelope=None, **details):
        row = {"event": event, "component": component, **details}
        if envelope:
            row["envelope"] = deepcopy(envelope)
        rows.append(row)

    def wire(event, component, envelope, **details):
        emit(event, component, envelope=envelope, **details)

    def received(actor, envelope):
        wire("wire.receive", actor, envelope, parsed=True)

    def stored(actor, envelope, storage):
        wire("wire.stored", actor, envelope, storage=storage)

    def dispatch(actor, envelope, route):
        emit(
            "handler.dispatch",
            actor,
            sender=envelope["sender"],
            payload_type=envelope["payload"]["type"],
            content=deepcopy(envelope["payload"]["content"]),
            route=route,
        )

    def ack(actor, source, suffix):
        envelope = packet(
            "ack-" + suffix,
            actor,
            "demo_env",
            "notify",
            {"event": "ACK", "msg": {"envelope_id": source["id"]}},
            envelope_type="system",
        )
        wire("wire.send.start", actor, envelope)
        received("demo_env", envelope)
        emit("delivery_ack", "demo_env", sender=actor, envelope_id=source["id"])
        wire("wire.handled", "demo_env", envelope)

    for actor, role, specification in (
        ("demo_env", "environment", ENV_SPEC),
        ("demo_agent", "agent", PEER_SPEC),
        ("demo_human", "human", PEER_SPEC),
    ):
        emit(
            "capability.registered",
            actor,
            role=role,
            specification=deepcopy(specification),
        )
    for actor in ("demo_agent", "demo_human"):
        discover = packet(
            "discover-" + actor,
            actor,
            "demo_env",
            "discover",
            {"protocols": ["agent-env-compact/2"]},
        )
        wire("wire.send.start", actor, discover)
        received("demo_env", discover)
        env_spec = packet(
            "env-spec-" + actor, "demo_env", actor, "specification", ENV_SPEC
        )
        wire("wire.send.start", "demo_env", env_spec)
        received(actor, env_spec)
        peer_spec = packet(
            "peer-spec-" + actor, actor, "demo_env", "specification", PEER_SPEC
        )
        wire("wire.send.start", actor, peer_spec)
        # SDK callback is intentionally later than its automatic reverse send.
        emit("specification", actor, sender="demo_env", content=deepcopy(ENV_SPEC))
        stored(actor, env_spec, "envelopes")
        received("demo_env", peer_spec)
        emit("specification", "demo_env", sender=actor, content=deepcopy(PEER_SPEC))
        wire("wire.handled", "demo_env", peer_spec)

    action = packet(
        "action-delivery",
        "demo_agent",
        "demo_env",
        "action",
        {"id": "a1", "name": "observe", "params": {}},
    )
    stored("demo_agent", action, "actions")
    wire("wire.send.start", "demo_agent", action)
    received("demo_env", action)
    stored("demo_env", action, "inbox")
    dispatch("demo_env", action, "tool")
    outcome = packet(
        "outcome-delivery",
        "demo_env",
        "demo_agent",
        "outcome",
        {
            "id": "o1",
            "refs": ["a1"],
            "status": "completed",
            "data": {"text": "安静的房间。"},
        },
    )
    stored("demo_env", outcome, "outbox")
    wire("wire.send.start", "demo_env", outcome)
    received("demo_agent", outcome)
    dispatch("demo_agent", outcome, "outcome")
    # Send completion is not required to precede remote arrival.
    wire("send", "demo_env", outcome)
    stored("demo_agent", outcome, "envelopes")
    ack("demo_agent", outcome, "outcome")
    wire("wire.handled", "demo_env", action)

    event = packet(
        "event-delivery",
        "demo_env",
        "demo_agent",
        "event",
        {"id": "e1", "name": "speech", "data": {"text": "提示。"}},
    )
    stored("demo_env", event, "outbox")
    wire("wire.send.start", "demo_env", event)
    received("demo_agent", event)
    dispatch("demo_agent", event, "model")
    stored("demo_agent", event, "envelopes")
    ack("demo_agent", event, "event")

    activity = packet(
        "activity-delivery",
        "demo_agent",
        "demo_env",
        "event",
        {
            "id": "e2",
            "name": "activity.state",
            "data": {"text": "正在观察。", "state": "working"},
        },
    )
    stored("demo_agent", activity, "originals")
    wire("wire.send.start", "demo_agent", activity)
    received("demo_env", activity)
    stored("demo_env", activity, "inbox")
    dispatch("demo_env", activity, "runtime")
    wire("wire.handled", "demo_env", activity)

    broadcast = packet(
        "broadcast-delivery",
        "demo_env",
        "@env",
        "event",
        {"id": "e3", "name": "speech", "data": {"text": "公共提示。"}},
        envelope_type="broadcast",
    )
    wire("wire.send.start", "demo_env", broadcast)
    for actor in ("demo_agent", "demo_human"):
        received(actor, broadcast)
        dispatch(actor, broadcast, "model")
        stored(actor, broadcast, "envelopes")

    # Same physical UUID again, but no second logical Event callback.
    wire("wire.send.start", "demo_env", event, replay=True)
    received("demo_agent", event)
    stored("demo_agent", event, "envelopes")
    ack("demo_agent", event, "event-replay")
    return stamp(rows)


def index(rows, event, actor=None, envelope_id=None, storage=None, kind=None):
    return next(
        position
        for position, row in enumerate(rows)
        if row["event"] == event
        and (actor is None or row["component"] == actor)
        and (envelope_id is None or row.get("envelope", {}).get("id") == envelope_id)
        and (storage is None or row.get("storage") == storage)
        and (kind is None or row.get("payload_type") == kind)
    )


def move_before(
    rows, event, target, *, actor=None, envelope_id=None, storage=None, kind=None
):
    source = index(rows, event, actor, envelope_id, storage, kind)
    row = rows.pop(source)
    destination = index(rows, *target)
    rows.insert(destination, row)
    stamp(rows)


def test_complete_sequence_accepts_reverse_callback_broadcast_replay_and_late_send_completion():
    checks = chronology_checks(trace())
    assert len(checks) == 7 and all(checks.values())


@pytest.mark.parametrize(
    "case, message",
    [
        ("receive_before_send", "no prior send start"),
        ("send_before_original", "Action sent before its original"),
        ("handler_before_inbox", "preceded durable inbox"),
        ("handler_before_receive", "callback invoked before parsed"),
        ("saved_before_callback", "fresh input saved as handled"),
        ("ack_before_saved", "ACK sent before"),
        ("confirmation_before_ack", "confirmed delivery before ACK arrival"),
        ("outcome_before_action", "Outcome sent before handling"),
    ],
)
def test_rejects_reversed_business_boundaries(case, message):
    rows = trace()
    if case == "receive_before_send":
        move_before(
            rows,
            "wire.receive",
            ("wire.send.start", "demo_agent", "action-delivery"),
            actor="demo_env",
            envelope_id="action-delivery",
        )
    elif case == "send_before_original":
        move_before(
            rows,
            "wire.send.start",
            ("wire.stored", "demo_agent", "action-delivery", "actions"),
            actor="demo_agent",
            envelope_id="action-delivery",
        )
    elif case == "handler_before_inbox":
        move_before(
            rows,
            "handler.dispatch",
            ("wire.stored", "demo_env", "action-delivery", "inbox"),
            actor="demo_env",
            kind="action",
        )
    elif case == "handler_before_receive":
        move_before(
            rows,
            "handler.dispatch",
            ("wire.receive", "demo_agent", "outcome-delivery"),
            actor="demo_agent",
            kind="outcome",
        )
    elif case == "saved_before_callback":
        move_before(
            rows,
            "wire.stored",
            ("handler.dispatch", "demo_agent", None, None, "outcome"),
            actor="demo_agent",
            envelope_id="outcome-delivery",
            storage="envelopes",
        )
    elif case == "ack_before_saved":
        move_before(
            rows,
            "wire.send.start",
            ("wire.stored", "demo_agent", "outcome-delivery", "envelopes"),
            actor="demo_agent",
            envelope_id="ack-outcome",
        )
    elif case == "confirmation_before_ack":
        move_before(
            rows,
            "delivery_ack",
            ("wire.receive", "demo_env", "ack-outcome"),
            actor="demo_env",
        )
    elif case == "outcome_before_action":
        move_before(
            rows,
            "wire.stored",
            ("handler.dispatch", "demo_env", None, None, "action"),
            actor="demo_env",
            envelope_id="outcome-delivery",
            storage="outbox",
        )
        move_before(
            rows,
            "wire.send.start",
            ("handler.dispatch", "demo_env", None, None, "action"),
            actor="demo_env",
            envelope_id="outcome-delivery",
        )
    with pytest.raises(AssertionError, match=message):
        chronology_checks(rows)


def test_requires_registration_before_own_specification_publication():
    rows = trace()
    registration = rows.pop(index(rows, "capability.registered", "demo_env"))
    rows.insert(
        index(rows, "wire.send.start", "demo_env", "env-spec-demo_agent") + 1,
        registration,
    )
    with pytest.raises(AssertionError, match="no prior local registration"):
        chronology_checks(stamp(rows))


@pytest.mark.parametrize("field", ["seq", "elapsed"])
def test_rejects_backwards_global_observation(field):
    rows = trace()
    rows[5][field] = rows[4][field] - 1
    with pytest.raises(AssertionError, match="strictly increase|nondecreasing"):
        chronology_checks(rows)


@pytest.mark.parametrize("case", ["broadcast", "replay"])
def test_each_broadcast_receiver_and_each_replay_must_finish_durable_storage(case):
    rows = trace()
    if case == "broadcast":
        rows.pop(
            index(rows, "wire.stored", "demo_human", "broadcast-delivery", "envelopes")
        )
        message = "no later durable completion"
    else:
        stored = [
            position
            for position, row in enumerate(rows)
            if row["event"] == "wire.stored"
            and row.get("storage") == "envelopes"
            and row.get("envelope", {}).get("id") == "event-delivery"
        ]
        rows.pop(stored[-1])
        message = "ACK sent before"
    with pytest.raises(AssertionError, match=message):
        chronology_checks(stamp(rows))


def test_new_discovery_cannot_reuse_old_installed_receiver_snapshot():
    rows = trace()
    at = index(rows, "wire.stored", "demo_agent", "action-delivery", "actions")
    discover = packet(
        "rediscover",
        "demo_agent",
        "demo_env",
        "discover",
        {"protocols": ["agent-env-compact/2"]},
    )
    rows.insert(
        at,
        {"event": "wire.send.start", "component": "demo_agent", "envelope": discover},
    )
    with pytest.raises(
        AssertionError, match="before both receiver declarations were installed"
    ):
        chronology_checks(stamp(rows))


def test_install_callback_cannot_reuse_a_consumed_old_arrival():
    rows = trace()
    at = index(rows, "wire.stored", "demo_agent", "action-delivery", "actions")
    rows.insert(
        at,
        {
            "event": "specification",
            "component": "demo_agent",
            "sender": "demo_env",
            "content": deepcopy(ENV_SPEC),
        },
    )
    with pytest.raises(AssertionError, match="unconsumed parsed arrival"):
        chronology_checks(stamp(rows))


def test_rejects_an_empty_or_incomplete_proof():
    with pytest.raises(AssertionError, match="empty transcript"):
        chronology_checks([])
    rows = trace()[
        : index(trace(), "wire.stored", "demo_agent", "action-delivery", "actions")
    ]
    with pytest.raises(AssertionError, match="missing sequence coverage"):
        chronology_checks(rows)
