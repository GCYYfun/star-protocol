"""Chronological observations keep actor, packet arrival and installation distinct."""

from copy import deepcopy
import io

from rich.console import Console

from examples.protocol_demo.contracts import load_specification
from examples.protocol_demo.display import ProtocolDisplay
from star_protocol.models import Envelope, MessagePayload, SystemPayload


def view():
    output = io.StringIO()
    display = ProtocolDisplay(console=Console(file=output, width=240, color_system=None), live=True)
    return display, output


def render(display, tree):
    output = io.StringIO()
    Console(file=output, width=240, color_system=None).print(tree)
    return output.getvalue()


def test_timeline_keeps_interleaved_steps_and_packets_in_observed_sequence():
    display, output = view()
    action = Envelope(sender="demo_agent", recipient="demo_env", payload=MessagePayload(
        type="action", content={"id": "request", "name": "observe", "params": {}})).model_dump()
    outcome = Envelope(sender="demo_env", recipient="demo_agent", payload=MessagePayload(
        type="outcome", content={"id": "result", "refs": ["request"], "status": "completed", "data": {"text": "原文"}})).model_dump()
    source = [
        {"event": "flow.stage.start", "stage_id": "tools", "title": "工具调用"},
        {"event": "flow.step", "component": "demo", "actor": "demo_agent", "operation": "准备调用", "step_number": 1},
        {"event": "wire.send.start", "component": "demo_agent", "envelope": action},
        {"event": "wire.send", "component": "demo_agent", "envelope": action},
        {"event": "wire.receive", "component": "demo_env", "envelope": action, "parsed": True},
        {"event": "wire.stored", "component": "demo_env", "envelope": action, "storage": "inbox"},
        {"event": "handler.dispatch", "component": "demo_env", "sender": "demo_agent", "payload_type": "action",
         "content": action["payload"]["content"], "route": "tool", "handler": "DemoEnvironment.on_action"},
        {"event": "flow.step", "component": "demo", "actor": "demo_env", "operation": "返回结果", "step_number": 2},
        {"event": "wire.send.start", "component": "demo_env", "envelope": outcome},
        {"event": "wire.send", "component": "demo_env", "envelope": outcome},
        {"event": "wire.receive", "component": "demo_agent", "envelope": outcome, "parsed": True},
        {"event": "wire.stored", "component": "demo_agent", "envelope": outcome, "storage": "envelopes"},
        {"event": "flow.stage.end", "stage_id": "tools", "status": "completed"},
    ]
    original = deepcopy(source)
    for number, record in enumerate(source, start=31):
        display.emit({"stage_id": "tools", "seq": number, "elapsed": number / 10, **record})
    assert source == original
    assert [item["seq"] for item in display.timeline] == list(range(31, 44))
    text = render(display, display.build_tree())
    assert text.index("#0032") < text.index("#0033") < text.index("#0035") < text.index("#0036") < text.index("#0038") < text.index("#0041")
    assert "Agent demo_agent · 准备调用" in text and "Environment demo_env · 返回结果" in text
    assert "Environment demo_env · 持久化完成 inbox · A01 action observe · D01 ← Agent demo_agent" in text
    assert "Agent demo_agent · 持久化完成 envelopes · O01 outcome completed → A01 · D02 ← Environment demo_env" in text
    assert text.index("全流程时间轴") < text.index("Action → Outcome")
    assert "O01 outcome completed → A01" in output.getvalue()
    assert display.deliveries[action["id"]]["receive_count"] == 1
    assert display.deliveries[outcome["id"]]["receive_count"] == 1
    assert not any(item["replay_count"] for item in display.deliveries.values())
    live = render(display, display.build_live_tree())
    assert "#0032" not in live and "#0041" in live


def test_parsed_specification_is_not_an_installed_snapshot_or_schema():
    display, output = view()
    specification = load_specification("environment")
    envelope = Envelope(sender="demo_env", recipient="demo_agent", payload=MessagePayload(
        type="specification", content=specification)).model_dump()
    display.emit({"event": "wire.receive", "component": "demo_agent", "envelope": envelope, "seq": 1, "elapsed": 0})
    before = output.getvalue()
    assert "仅表示报文解包" in before
    assert "已校验并安装" not in before and "tools · 6" not in before
    assert "demo_env" not in display.specifications
    display.emit({"event": "specification", "component": "demo_agent", "sender": "demo_env", "content": specification, "seq": 2, "elapsed": 0.1})
    assert display.specifications["demo_env"] == specification
    installed = output.getvalue()[len(before):]
    assert "已校验并安装接收声明" in installed and "tools · 6" in installed
    assert [item["record"]["event"] for item in display.timeline] == ["wire.receive", "specification"]


def test_callback_observed_earlier_is_paired_without_reordering_history():
    display, output = view()
    specification = load_specification("environment")
    envelope = Envelope(sender="demo_env", recipient="demo_agent", payload=MessagePayload(
        type="specification", content=specification)).model_dump()
    display.emit({"event": "specification", "component": "demo_agent", "sender": "demo_env", "content": specification, "seq": 7, "elapsed": 0.1})
    display.emit({"event": "wire.receive", "component": "demo_agent", "envelope": envelope, "seq": 8, "elapsed": 0.2})
    assert output.getvalue().count("已校验并安装接收声明") == 1
    assert not display._specification_callbacks[("demo_env", "demo_agent")]
    text = render(display, display.build_tree())
    assert text.index("#0007") < text.index("#0008")
    assert [item["record"]["event"] for item in display.timeline] == ["specification", "wire.receive"]


def test_ack_started_or_persisted_is_not_yet_sent_or_confirmed():
    display, _ = view()
    packet = Envelope(sender="demo_env", recipient="demo_agent", payload=MessagePayload(
        type="event", content={"id": "event", "name": "observation", "data": {"text": "原文"}})).model_dump()
    display.emit({"event": "wire.receive", "component": "demo_agent", "envelope": packet})
    ack = Envelope(type="system", sender="demo_agent", recipient="demo_env", payload=SystemPayload(
        type="notify", content={"event": "ACK", "msg": {"envelope_id": packet["id"]}})).model_dump()
    display.emit({"event": "wire.send.start", "component": "demo_agent", "envelope": ack})
    assert not display.deliveries[packet["id"]]["ack_sent"]
    display.emit({"event": "wire.send", "component": "demo_agent", "envelope": ack})
    assert display.deliveries[packet["id"]]["ack_sent"] and not display.deliveries[packet["id"]]["ack"]
    display.emit({"event": "wire.receive", "component": "demo_env", "envelope": ack})
    assert not display.deliveries[packet["id"]]["ack"]
    display.emit({"event": "delivery_ack", "component": "environment", "envelope_id": packet["id"]})
    assert display.deliveries[packet["id"]]["ack"]


def test_real_handler_observations_in_same_millisecond_keep_distinct_sequences():
    display, _ = view()
    content = {"id": "request", "name": "observe", "params": {}}
    for seq in (10, 11):
        display.emit({"event": "handler.dispatch", "component": "demo_env", "sender": "demo_agent",
                      "payload_type": "action", "content": content, "route": "tool", "handler": "DemoEnvironment.on_action",
                      "stage_id": "tools", "elapsed": 0.001, "seq": seq})
    assert len(display.handler_observations["request"]) == 2
    assert [item["seq"] for item in display.timeline] == [10, 11]
    text = render(display, display.build_tree())
    assert text.index("#0010") < text.index("#0011")
