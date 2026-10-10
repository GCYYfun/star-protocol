"""Presentation keeps actual refs, status and transport identity semantics."""

import io

from rich.console import Console

from examples.protocol_demo.display import ProtocolDisplay
from star_protocol.models import BroadcastPayload, Envelope, MessagePayload, SystemPayload


def display(*, trace=False):
    output = io.StringIO()
    console = Console(file=output, width=160, color_system=None)
    return ProtocolDisplay(console=console, live=True, trace=trace), output


def emit_wire(view, kind, content, *, sender="demo_env", recipient="demo_agent", name="wire.receive"):
    packet = Envelope(sender=sender, recipient=recipient, payload=MessagePayload(type=kind, content=content))
    view.emit({"event": name, "component": recipient, "envelope": packet.model_dump()})
    return packet


def text_of(view, output):
    view.console.print(view.build_tree())
    return output.getvalue()


def test_outcomes_attach_to_explicit_action_and_do_not_infer_status_from_text():
    view, output = display()
    emit_wire(view, "action", {"id": "action-a", "name": "wait", "params": {"seconds": 3}},
              sender="demo_agent", recipient="demo_env", name="wire.send")
    result = {"id": "outcome-a", "refs": ["action-a"], "status": "running", "data": {"text": "文字中出现 completed 不代表动作完成。"}}
    emit_wire(view, "outcome", result)
    view.emit({"event": "outcome", "component": "demo_agent", "sender": "demo_env", "content": result})
    tree = view.build_tree()
    actions = next(branch for branch in tree.children if "Action → Outcome" in branch.label.plain)
    action = actions.children[0]
    outcome = next(branch for branch in action.children if getattr(branch.label, "plain", "").startswith("O01"))
    assert outcome.label.plain == "O01 running"
    assert view.messages["action-a"]["recipients"] == ["demo_env"]
    assert "[0] → A01 wait" in text_of(view, output)
    assert len([node for node in view.messages.values() if node["kind"] == "outcome"]) == 1


def test_event_first_ref_only_attaches_visually_and_other_refs_keep_order():
    view, output = display()
    for identifier, refs in (("source", []), ("control", ["source"]), ("feedback", ["control", "source"])):
        content = {"id": identifier, "name": identifier, "data": {"text": identifier}}
        if refs:
            content["refs"] = refs
        emit_wire(view, "event", content)
    tree = view.build_tree()
    group = next(branch for branch in tree.children if "Event 因果引用" in branch.label.plain)
    source = group.children[0]
    control = next(branch for branch in source.children if branch.label.plain.startswith("E02"))
    feedback = next(branch for branch in control.children if branch.label.plain.startswith("E03"))
    assert "feedback" in feedback.label.plain
    rendered = text_of(view, output)
    assert "[0] → E02 control" in rendered and "[1] → E01 source" in rendered


def test_unknown_and_cyclic_event_refs_do_not_invent_source_records_or_recurse():
    view, output = display()
    for identifier, ref in (("unknown-child", "unavailable-history"), ("cycle-a", "cycle-b"), ("cycle-b", "cycle-a")):
        emit_wire(view, "event", {"id": identifier, "name": identifier,
                                  "refs": [ref], "data": {"text": identifier}})
    rendered = text_of(view, output)
    assert "原事件未在本次展示中出现" in rendered
    assert "unavailable-history" not in view.messages
    assert "cycle-a" in rendered and "cycle-b" in rendered


def test_delivery_replay_reuses_uuid_and_ack_is_only_confirmed_by_environment():
    view, output = display()
    packet = emit_wire(view, "event", {"id": "event-original", "name": "observation", "data": {"text": "原文"}})
    ack = Envelope(type="system", sender="demo_agent", recipient="demo_env", payload=SystemPayload(
        type="notify", content={"event": "ACK", "msg": {"envelope_id": packet.id}}))
    view.emit({"component": "demo_agent", "event": "wire.send", "envelope": ack.model_dump()})
    view.emit({"component": "environment", "event": "delivery_replay", "envelope": packet.model_dump()})
    view.emit({"component": "demo_agent", "event": "wire.receive", "envelope": packet.model_dump()})
    assert view.deliveries[packet.id]["ack"] is False
    assert "ACK 未由环境确认" in text_of(view, output)
    view.emit({"component": "environment", "event": "delivery_ack", "envelope_id": packet.id})
    assert view.deliveries[packet.id]["ack"] is True
    assert view.messages["event-original"]["deliveries"] == [packet.id]


def test_trace_expands_three_wire_layers_and_user_markup_remains_literal():
    view, output = display(trace=True)
    packet = emit_wire(view, "event", {"id": "literal-event", "name": "speech", "data": {"text": "[bold]普通原文[/bold]"}})
    rendered = text_of(view, output)
    assert "Envelope → Payload → Content" in rendered
    assert "payload · object" in rendered and "content · object" in rendered
    assert packet.id in rendered
    assert "[bold]普通原文[/bold]" in rendered


def test_broadcast_received_once_by_multiple_people_is_not_transport_replay():
    view, output = display()
    packet = Envelope(type="broadcast", sender="demo_env", recipient="@env", payload=BroadcastPayload(
        type="event", content={"id": "public", "name": "observation", "data": {"text": "公共通知"}}))
    for receiver in ("demo_agent", "demo_colleague", "demo_human"):
        view.emit({"component": receiver, "event": "wire.receive", "envelope": packet.model_dump()})
    rendered = text_of(view, output)
    assert "同 UUID 补发" not in rendered
    assert view.deliveries[packet.id]["receivers"] == {"demo_agent": 1, "demo_colleague": 1, "demo_human": 1}
