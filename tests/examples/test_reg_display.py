"""Registration, received capabilities and callbacks remain observable facts."""

from copy import deepcopy
import io

from rich.console import Console

from examples.protocol_demo.contracts import load_specification
from examples.protocol_demo.display import ProtocolDisplay
from star_protocol.models import Envelope, MessagePayload


def view():
    output = io.StringIO()
    return ProtocolDisplay(console=Console(file=output, width=200, color_system=None), live=True), output


def registration(display, actor, role, config):
    specification = load_specification(config)
    class_name = "DemoEnvironment" if role == "environment" else "DemoAgent" if role == "agent" else "DemoHuman"
    bindings = {"tools": {tool["name"]: {"entrypoint": class_name + ".on_action", "dispatch": tool["name"]}
                           for tool in specification["tools"]},
                "events": {event["name"]: {"handler": event["handler"],
                           "entrypoint": class_name + ("._feedback" if event["handler"] == "runtime" else ".on_event")}
                           for event in specification["events"]}}
    record = {"event": "capability.registered", "component": actor, "role": role,
              "specification": specification, "bindings": bindings, "presentation": True}
    display.emit(record)
    return record


def wire(display, kind, content, sender, receiver, *, event="wire.receive", component=None, stage_id=None):
    envelope = Envelope(sender=sender, recipient=receiver, payload=MessagePayload(type=kind, content=content))
    display.emit({"event": event, "component": component or receiver, "envelope": envelope.model_dump(), "stage_id": stage_id})
    return envelope


def dispatch(display, content, kind, sender, receiver, handler, route, *, stage_id=None, **details):
    record = {"event": "handler.dispatch", "component": receiver, "sender": sender,
              "payload_type": kind, "content": content, "handler": handler, "route": route,
              "presentation": True, "stage_id": stage_id, **details}
    display.emit(record)
    return record


def render(display, tree):
    output = io.StringIO()
    Console(file=output, width=200, color_system=None).print(tree)
    return output.getvalue()


def test_environment_registration_exposes_every_tool_and_actual_binding_without_trace():
    display, output = view()
    record = registration(display, "demo_env", "environment", "environment")
    text = output.getvalue()
    assert "本地注册成功 · Environment demo_env" in text and "tools · 6" in text
    for tool in record["specification"]["tools"]:
        assert tool["name"] in text and "分支 " + tool["name"] in text
    assert "DemoEnvironment.on_action" in text
    assert "on: boolean · 必填" in text and "operation: string · 必填" in text
    assert 'enum=["add", "sub", "mul", "div"]' in text
    assert "seconds: number · 必填 · minimum=0.05, maximum=3" in text
    assert "speech · model" in text and "activity.state · runtime" in text
    assert not display.messages and not display.specifications
    before = output.getvalue()
    display.emit(deepcopy(record))
    repeated = output.getvalue()[len(before):]
    assert "本地重新注册" in repeated and "同内容" in repeated and "tools · 6" not in repeated
    assert display.registrations["demo_env"]["observations"] == 2
    final = render(display, display.build_tree())
    assert "本地真实绑定" in final and "DemoEnvironment.on_action" in final


def test_agent_registration_has_zero_tools_runtime_schema_refs_and_framework_outcomes():
    display, output = view()
    registration(display, "demo_agent", "agent", "agent")
    text = output.getvalue()
    assert "tools · 0" in text and "未暴露工具" in text
    assert "events · 3" in text and "DemoAgent._feedback" in text
    assert "text: string · 必填" in text and "intensity: number · 必填 · minimum=0, maximum=1" in text
    assert 'channel: string · 必填 · enum=["haptic"]' in text
    assert "框架 Outcome 接收 → on_outcome" in text and "不属于 Tool / Event 注册" in text
    assert not display.messages


def test_actual_specification_receipt_direction_is_independent_and_wire_callback_merge():
    display, output = view()
    specification = load_specification("environment")
    envelope = wire(display, "specification", specification, "demo_env", "demo_agent", event="wire.send", component="demo_env")
    sent = output.getvalue()
    assert "发送完成 specification" in sent and "已校验并安装接收声明" not in sent
    record = {"event": "wire.receive", "component": "demo_agent", "envelope": envelope.model_dump()}
    display.emit(record)
    assert "已校验并安装接收声明" not in output.getvalue()
    assert "安装结果见独立的 specification 回调" in output.getvalue()
    display.emit({"event": "specification", "component": "demo_agent", "sender": "demo_env", "content": specification})
    display.emit(record)
    text = output.getvalue()
    assert text.count("已校验并安装接收声明") == 1
    assert "Environment demo_env → Agent demo_agent" in text
    assert "Agent demo_agent → Environment demo_env · tools: observe, set_light, calculate" in text
    assert "Agent demo_agent → Environment demo_env · events: speech [model], activity.state [runtime]" in text
    reverse = load_specification("agent")
    wire(display, "specification", reverse, "demo_agent", "demo_env", component="environment")
    display.emit({"event": "specification", "component": "environment", "sender": "demo_agent", "content": reverse})
    text = output.getvalue()
    assert text.count("已校验并安装接收声明") == 2
    assert "Environment demo_env → Agent demo_agent · tools: 无（对端 tools=0）" in text
    assert "Environment demo_env → Agent demo_agent · events: observation [model], speech [model], interaction.feedback [runtime]" in text


def test_discover_send_and_receive_are_actual_observations_not_extra_handshakes():
    display, output = view()
    envelope = wire(display, "discover", {"protocols": ["agent-env-compact/2"]}, "demo_agent", "demo_env", event="wire.send", component="demo_agent")
    record = {"event": "wire.receive", "component": "demo_env", "envelope": envelope.model_dump()}
    display.emit(record)
    display.emit(record)
    assert output.getvalue().count("发送完成 discover") == 1
    assert output.getvalue().count("收到 discover") == 1
    assert "specification" not in output.getvalue()


def test_actual_handlers_display_params_text_status_and_business_data_once():
    display, output = view()
    action = {"id": "calculation", "name": "calculate", "params": {"operation": "add", "a": 7, "b": 5}}
    wire(display, "action", action, "demo_agent", "demo_env")
    dispatch(display, action, "action", "demo_agent", "demo_env", "DemoEnvironment.on_action", "tool")
    outcome = {"id": "progress", "refs": ["calculation"], "status": "running", "data": {"text": "completed 是这段原文的单词；当前依然执行中。"}}
    wire(display, "outcome", outcome, "demo_env", "demo_agent")
    dispatch(display, outcome, "outcome", "demo_env", "demo_agent", "DemoAgent.on_outcome", "outcome")
    feedback = {"id": "feedback", "name": "interaction.feedback", "data": {"text": "[bold]真实反馈[/bold]", "channel": "haptic", "intensity": 0.2}}
    wire(display, "event", feedback, "demo_env", "demo_agent")
    record = dispatch(display, feedback, "event", "demo_env", "demo_agent", "DemoAgent._feedback", "runtime")
    text = output.getvalue()
    assert "Action.params" in text and 'operation: "add"' in text
    assert "tool → DemoEnvironment.on_action · 分支 calculate" in text
    assert "Outcome.status: running" in text and "refs → A01" in text
    assert "data.text: completed 是这段原文" in text
    assert "runtime → DemoAgent._feedback" in text
    assert "[bold]真实反馈[/bold]" in text and 'channel: "haptic"' in text and "intensity: 0.2" in text
    assert len(display.messages) == 3 and len(display.handler_observations) == 3
    display.emit(record)
    assert output.getvalue() == text
    final = render(display, display.build_tree())
    assert "实际处理器: DemoEnvironment.on_action" in final and "实际处理器: DemoAgent._feedback" in final


def test_handler_observation_before_content_is_metadata_and_live_latest_body_is_visible():
    display, output = view()
    display.emit({"event": "flow.stage.start", "stage_id": "tools", "title": "工具交互", "elapsed": 0})
    display.emit({"event": "flow.step", "stage_id": "tools", "stage_number": 1, "step_number": 1, "actor": "demo_agent",
                  "operation": "调用工具", "text": "等实际处理", "elapsed": 0.2, "wait_seconds": 0})
    content = {"id": "request", "name": "set_light", "params": {"on": True}}
    dispatch(display, content, "action", "demo_agent", "demo_env", "DemoEnvironment.on_action", "tool", stage_id="tools")
    assert not display.messages
    live = render(display, display.build_live_tree())
    assert "实际处理 · Agent demo_agent → Environment demo_env" in live
    assert "Action.params" in live and "on: true" in live and "DemoEnvironment.on_action" in live
    display.emit({"event": "action", "sender": "demo_agent", "component": "environment", "content": content, "stage_id": "tools"})
    assert len(display.messages) == 1
    final = render(display, display.build_tree())
    assert "实际处理器: DemoEnvironment.on_action" in final
    assert "Environment environment" not in output.getvalue()


def test_callback_then_wire_receipt_pairs_once_and_fresh_rediscovery_still_shows():
    display, output = view()
    specification = load_specification("environment")
    callback = {"event": "specification", "component": "demo_agent", "sender": "demo_env", "content": specification}
    for _ in range(2):
        display.emit(callback)
        envelope = wire(display, "specification", specification, "demo_env", "demo_agent")
        display.emit({"event": "wire.receive", "component": "demo_agent", "envelope": envelope.model_dump()})
    assert output.getvalue().count("已校验并安装接收声明") == 2
    assert not display._specification_callbacks[("demo_env", "demo_agent")]
    assert not display._specification_inbound[("demo_env", "demo_agent")]


def test_ledger_replay_is_an_actual_handler_invocation_without_world_dispatch_claim():
    display, output = view()
    content = {"id": "light", "name": "set_light", "params": {"on": True}}
    wire(display, "action", content, "demo_agent", "demo_env")
    handler = "examples.protocol_demo.environment.DemoEnvironment.on_action"
    dispatch(display, content, "action", "demo_agent", "demo_env", handler, "tool", dispatch_mode="new")
    before_replay = len(output.getvalue())
    for _ in range(2):
        dispatch(display, content, "action", "demo_agent", "demo_env", handler, "tool", dispatch_mode="ledger_replay")
    replay_text = output.getvalue()[before_replay:]
    assert replay_text.count("读取原 Action 账本") == 2
    assert "重放既有 Outcome；未执行世界分支" in replay_text and "分支 set_light" not in replay_text
    assert "DemoEnvironment.on_action" in replay_text and "examples.protocol_demo.environment" not in replay_text
    assert len(display.messages) == 1 and len(display.handler_observations["light"]) == 3
    final = render(display, display.build_tree())
    assert "读取原账本，重放原 Outcome；未执行世界分支 · 实际观测 2 次" in final
    display.trace = True
    assert handler in render(display, display.build_tree())


def test_default_registration_method_names_are_compact_but_trace_retains_modules():
    display, output = view()
    record = registration(display, "demo_env", "environment", "environment")
    for binding in record["bindings"]["tools"].values():
        binding["entrypoint"] = "examples.protocol_demo.environment." + binding["entrypoint"]
    display.emit(record)
    assert "examples.protocol_demo.environment" not in output.getvalue()
    assert "DemoEnvironment.on_action" in output.getvalue()
    display.trace = True
    assert "examples.protocol_demo.environment.DemoEnvironment.on_action" in render(display, display.build_tree())
