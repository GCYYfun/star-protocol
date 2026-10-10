"""Check observed demo order without treating callbacks as network arrival.

This verifier expects one complete demo transcript, including local registration
and sender observations. It compares physical deliveries per receiver, leaving
logical Event/Outcome replay and broadcast fan-out distinct from execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from typing import Any


@dataclass
class _Delivery:
    row: dict
    stored: dict[str, dict] = field(default_factory=dict)
    dispatches: list[dict] = field(default_factory=list)


def _actor(identifier: str) -> str:
    return "demo_env" if identifier == "environment" else identifier


def _packet(row: dict) -> tuple[dict, str, dict]:
    envelope = row.get("envelope", {})
    payload = envelope.get("payload", {})
    return envelope, payload.get("type", ""), payload.get("content", {})


def _signature(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _require(condition: bool, message: str, row: dict | None = None) -> None:
    if condition:
        return
    where = ""
    if row is not None:
        envelope = row.get("envelope", {})
        where = (
            f" [seq={row.get('seq')}, actor={row.get('component')}, "
            f"event={row.get('event')}, envelope={envelope.get('id', '-')}]"
        )
    raise AssertionError("Demo chronology: " + message + where)


def chronology_checks(records: list[dict]) -> dict[str, bool]:
    """Raise an actionable assertion on missing coverage or reversed order.

    ``wire.receive`` means parsed arrival at the local router. Completion of a
    send may occur after a peer has received it; only ``wire.send.start`` is a
    happens-before boundary. ACK checks use the acknowledged Envelope UUID,
    never the most recent logical Action or Outcome.
    """
    _require(bool(records), "empty transcript")
    previous_seq = 0
    previous_elapsed = -1.0
    for row in records:
        seq, elapsed = row.get("seq"), row.get("elapsed")
        _require(
            type(seq) is int and seq > previous_seq, "seq must strictly increase", row
        )
        _require(
            type(elapsed) in {int, float}
            and math.isfinite(elapsed)
            and elapsed >= previous_elapsed,
            "elapsed must be finite and nondecreasing",
            row,
        )
        previous_seq, previous_elapsed = seq, elapsed

    roles: dict[str, str] = {}
    registrations: dict[str, dict] = {}
    starts: dict[tuple[str, str], dict] = {}
    stored_outgoing: dict[tuple[str, str, str], dict] = {}
    deliveries: dict[tuple[str, str], _Delivery] = {}
    all_deliveries: list[_Delivery] = []
    active_content: dict[tuple[str, str, str], _Delivery] = {}
    spec_arrivals: dict[tuple[str, str], list[dict]] = {}
    pending_specs: dict[tuple[str, str], list[dict]] = {}
    installed: dict[tuple[str, str], dict] = {}
    reverse_specs: dict[tuple[str, str], list[dict]] = {}
    processed: set[tuple[str, str, str]] = set()
    action_handlers: dict[tuple[str, str, str], dict] = {}
    ack_arrivals: dict[tuple[str, str, str], dict] = {}
    coverage = dict(
        spec=0,
        arrived=0,
        actions=0,
        events=0,
        outcomes=0,
        saved=0,
        ack_sent=0,
        ack_confirmed=0,
        returned=0,
    )

    for row in records:
        event = row.get("event")
        component = _actor(row.get("component", ""))
        if event == "capability.registered":
            registrations[component] = row
            roles[component] = row["role"]
            continue
        if component not in roles:
            # Hub and Monitor have separate control/telemetry routes.
            if event in {"wire.send.start", "wire.receive", "handler.dispatch"}:
                _require(
                    component in {"hub", "monitor", "demo", ""},
                    "packet actor has no prior local registration",
                    row,
                )
            continue
        envelope, kind, content = _packet(row)
        envelope_id = envelope.get("id")
        sender = _actor(envelope.get("sender", row.get("sender", "")))
        recipient = _actor(envelope.get("recipient", ""))

        if event == "wire.send.start":
            _require(
                sender == component, "send actor differs from Envelope sender", row
            )
            if kind == "discover":
                installed.pop((component, recipient), None)
                installed.pop((recipient, component), None)
            if kind == "specification":
                _require(
                    component in registrations,
                    "declaration sent before local registration",
                    row,
                )
                _require(
                    _signature(content)
                    == _signature(registrations[component]["specification"]),
                    "sent declaration differs from installed local snapshot",
                    row,
                )
                coverage["spec"] += 1
                if (
                    roles[component] in {"agent", "human"}
                    and roles.get(recipient) == "environment"
                ):
                    candidates = pending_specs.get((component, recipient), [])
                    _require(
                        bool(candidates),
                        "reverse declaration sent before environment declaration arrived",
                        row,
                    )
                    reverse_specs.setdefault((component, recipient), []).append(row)
            if envelope.get("type") == "message" and kind == "action":
                _require(
                    (component, envelope_id, "actions") in stored_outgoing,
                    "Action sent before its original request was saved",
                    row,
                )
                _require(
                    (component, recipient) in installed
                    and (recipient, component) in installed,
                    "Action sent before both receiver declarations were installed",
                    row,
                )
            if (
                envelope.get("type") == "message"
                and kind == "event"
                and roles[component] != "environment"
            ):
                _require(
                    (component, envelope_id, "originals") in stored_outgoing,
                    "outgoing Event sent before its original was saved",
                    row,
                )
            if (
                envelope.get("type") == "message"
                and kind in {"outcome", "event"}
                and roles[component] == "environment"
            ):
                _require(
                    (component, envelope_id, "outbox") in stored_outgoing,
                    "environment delivery sent before durable outbox storage",
                    row,
                )
            if kind == "outcome":
                refs = content.get("refs", [])
                _require(
                    len(refs) == 1
                    and (component, recipient, refs[0]) in action_handlers,
                    "Outcome sent before handling its original Action",
                    row,
                )
                coverage["returned"] += 1
            if kind == "notify" and content.get("event") == "VILLAGE_DELIVERY_ACK":
                target = content.get("msg", {}).get("envelope_id")
                delivery = deliveries.get((component, target))
                _require(
                    delivery is not None and "envelopes" in delivery.stored,
                    "ACK sent before the exact received Envelope was saved",
                    row,
                )
                original, original_kind, _ = _packet(delivery.row)
                _require(
                    _actor(original.get("sender", "")) == recipient
                    and original_kind in {"outcome", "event"}
                    and original.get("type") == "message",
                    "ACK does not identify a message from its recipient",
                    row,
                )
                coverage["ack_sent"] += 1
            starts[(component, envelope_id)] = row

        elif event == "wire.receive":
            _require(row.get("parsed") is True, "arrival is missing parsed=True", row)
            if sender in roles:
                start = starts.get((sender, envelope_id))
                _require(
                    start is not None, "received packet has no prior send start", row
                )
                original, start_kind, start_content = _packet(start)
                _require(
                    kind == start_kind
                    and _signature(content) == _signature(start_content),
                    "received packet differs from its sending observation",
                    row,
                )
                _require(
                    original.get("recipient") == envelope.get("recipient")
                    or original.get("type") == "broadcast",
                    "received packet has an unexpected destination",
                    row,
                )
                coverage["arrived"] += 1
            delivery = _Delivery(row)
            all_deliveries.append(delivery)
            deliveries[(component, envelope_id)] = delivery
            if content.get("id"):
                active_content[(component, kind, content["id"])] = delivery
            if kind == "specification":
                spec_arrivals.setdefault((component, sender), []).append(row)
                pending_specs.setdefault((component, sender), []).append(row)
            if kind == "notify" and content.get("event") == "VILLAGE_DELIVERY_ACK":
                target = content.get("msg", {}).get("envelope_id")
                ack_arrivals[(component, sender, target)] = row

        elif event == "wire.stored":
            storage = row.get("storage")
            if storage in {"actions", "originals", "outbox"}:
                stored_outgoing[(component, envelope_id, storage)] = row
            if storage in {"inbox", "envelopes"}:
                delivery = deliveries.get((component, envelope_id))
                _require(
                    delivery is not None,
                    "received Envelope saved before parsed arrival",
                    row,
                )
                delivery.stored[storage] = row
                if storage == "envelopes" and kind in {"outcome", "event"}:
                    key = (component, kind, content["id"])
                    _require(
                        bool(delivery.dispatches) or key in processed,
                        "fresh input saved as handled before its actual callback",
                        row,
                    )
                    coverage["saved"] += 1

        elif event == "specification":
            sender = _actor(row["sender"])
            arrivals = pending_specs.get((component, sender), [])
            matching = next(
                (
                    item
                    for item in arrivals
                    if _signature(_packet(item)[2]) == _signature(row["content"])
                ),
                None,
            )
            _require(
                matching is not None,
                "declaration installed without an unconsumed parsed arrival",
                row,
            )
            arrivals.remove(matching)
            installed[(component, sender)] = row

        elif event == "handler.dispatch":
            kind, content = row["payload_type"], row["content"]
            key = (component, kind, content["id"])
            delivery = active_content.get(key)
            _require(
                delivery is not None, "callback invoked before parsed arrival", row
            )
            _require(
                not delivery.dispatches,
                "one physical delivery dispatched more than once",
                row,
            )
            _require(
                _signature(_packet(delivery.row)[2]) == _signature(content),
                "callback content differs from received packet",
                row,
            )
            if roles[component] == "environment":
                _require(
                    "inbox" in delivery.stored,
                    "environment callback preceded durable inbox storage",
                    row,
                )
            if kind == "action":
                _require(
                    roles[component] == "environment",
                    "tool dispatched outside the Environment",
                    row,
                )
                sender = _actor(row["sender"])
                action_handlers[(component, sender, content["id"])] = row
                coverage["actions"] += 1
            elif kind in {"event", "outcome"}:
                _require(
                    "envelopes" not in delivery.stored,
                    "input callback invoked after full Envelope completion storage",
                    row,
                )
                coverage["events" if kind == "event" else "outcomes"] += 1
            delivery.dispatches.append(row)
            processed.add(key)

        elif event == "delivery_ack":
            target, sender = row["envelope_id"], _actor(row["sender"])
            _require(
                (component, sender, target) in ack_arrivals,
                "environment confirmed delivery before ACK arrival",
                row,
            )
            coverage["ack_confirmed"] += 1

        elif event == "wire.handled":
            delivery = deliveries.get((component, envelope_id))
            _require(
                delivery is not None, "message completed before parsed arrival", row
            )
            if roles[component] == "environment" and kind in {
                "action",
                "event",
                "outcome",
            }:
                _require(
                    "inbox" in delivery.stored,
                    "business handling completed before inbox storage",
                    row,
                )

    for delivery in all_deliveries:
        row = delivery.row
        component = _actor(row["component"])
        envelope, kind, _ = _packet(row)
        if kind not in {"action", "event", "outcome"}:
            continue
        table = "inbox" if roles[component] == "environment" else "envelopes"
        _require(
            table in delivery.stored,
            "business arrival has no later durable completion",
            row,
        )
        if kind == "action":
            _require(
                bool(delivery.dispatches),
                "received Action has no actual tool dispatch",
                row,
            )

    for (receiver, sender), arrivals in spec_arrivals.items():
        if (
            roles.get(receiver) not in {"agent", "human"}
            or roles.get(sender) != "environment"
        ):
            continue
        sent = reverse_specs.get((receiver, sender), [])
        for position, arrival in enumerate(arrivals):
            next_seq = (
                arrivals[position + 1]["seq"]
                if position + 1 < len(arrivals)
                else float("inf")
            )
            _require(
                any(arrival["seq"] < row["seq"] < next_seq for row in sent),
                "environment declaration had no later reverse declaration",
                arrival,
            )

    _require(
        any(role == "environment" for role in roles.values())
        and any(role == "agent" for role in roles.values()),
        "registration coverage requires Agent and Environment",
    )
    for name, count in coverage.items():
        _require(count > 0, "missing sequence coverage: " + name)
    return {
        "时间顺序：观测序号严格递增，经过时间不倒退": True,
        "注册与协商：本地注册、声明到达、反向声明及双方安装": True,
        "消息到达：接收对应此前开始发送的原报文": True,
        "工具调用：先保存原请求，环境落盘后分派工具": True,
        "Event 与 Outcome：先到达，再处理并保存完整报文": True,
        "投递确认：保存后发送 ACK，环境收到后确认": True,
        "结果返回：原 Action 实际处理后发送关联 Outcome": True,
    }
