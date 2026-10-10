"""The demo timeline is presentation metadata, with detached Rich snapshots."""

from concurrent.futures import ThreadPoolExecutor
import io

from rich.console import Console

from examples.protocol_demo.display import ProtocolDisplay
from star_protocol.models import Envelope, MessagePayload


def view(*, trace=False):
    output = io.StringIO()
    display = ProtocolDisplay(console=Console(file=output, width=160, color_system=None), live=True, trace=trace)
    return display, output


def start(display, stage_id="connect", *, title="连接主体", elapsed=0):
    display.emit({"event": "flow.stage.start", "stage_id": stage_id, "title": title,
                  "description": "Hub 路由；Environment 声明工具；Agent 声明接收能力。", "elapsed": elapsed})


def step(display, *, stage_id="connect", number=1, actor="demo_agent", text="等待环境响应", wait=1.25):
    display.emit({"event": "flow.step", "stage_id": stage_id, "stage_number": 1, "step_number": number,
                  "actor": actor, "operation": "发送请求", "text": text, "wait_seconds": wait,
                  "elapsed": 2.5, "presentation": True})


def packet(display, kind, content, *, event="wire.send", stage_id="connect", sender="demo_agent", recipient="demo_env"):
    envelope = Envelope(sender=sender, recipient=recipient, payload=MessagePayload(type=kind, content=content))
    display.emit({"event": event, "stage_id": stage_id, "component": sender,
                  "envelope": envelope.model_dump(), "elapsed": 3})
    return envelope


def rendered(display, tree):
    output = io.StringIO()
    Console(file=output, width=160, color_system=None).print(tree)
    return output.getvalue()


def test_redirected_output_shows_steps_and_simulated_wait_before_finish():
    display, output = view()
    display.start()
    start(display)
    step(display, text="[bold]completed 只是原文[/bold]")
    printed = output.getvalue()
    assert "阶段 01 连接主体" in printed
    assert "Agent demo_agent" in printed
    assert "T+002.50s" in printed and "模拟停顿 1.25 秒" in printed
    assert "[bold]completed 只是原文[/bold]" in printed
    assert display.phases["connect"]["status"] == "running"
    assert not display.messages and not display._finished
    display.emit({"event": "flow.step.end", "stage_id": "connect", "step_number": 1,
                  "elapsed": 3.75, "presentation": True, "wait_seconds": 0})
    assert len(display.phases["connect"]["steps"]) == 1
    saved_step = display.phases["connect"]["steps"][0]
    assert saved_step["wait_seconds"] == 1.25 and saved_step["paused"] is False
    current = rendered(display, display.build_live_tree())
    assert "模拟停顿已结束" in current and "模拟停顿 1.25 秒" not in current


def test_phase_merges_original_ids_and_retains_real_action_outcome_relationships():
    display, output = view()
    start(display)
    step(display)
    action = packet(display, "action", {"id": "request", "name": "wait", "params": {"seconds": 3}})
    display.emit({"event": "wire.receive", "stage_id": "connect", "component": "demo_env", "envelope": action.model_dump()})
    for status in ("running", "completed"):
        packet(display, "outcome", {"id": status, "refs": ["request"], "status": status, "data": {"text": status}},
               sender="demo_env", recipient="demo_agent")
    phase = display.phases["connect"]
    assert len(phase["messages"]) == 3
    assert len(phase["messages"][("action", "request")]["observations"]) == 2
    assert "O01 outcome running → A01" in output.getvalue()
    display.emit({"event": "runtime.event", "stage_id": "connect", "component": "environment", "sender": "demo_agent",
                  "content": {"id": "state", "name": "activity.state", "data": {"text": "状态正文"}}})
    assert display.phases["connect"]["messages"][("event", "state")]["recipient"] == "demo_env"
    before_end = len(output.getvalue())
    display.emit({"event": "flow.stage.end", "stage_id": "connect", "title": "连接主体", "elapsed": 5.2, "status": "completed"})
    assert "O01 running" not in output.getvalue()[before_end:]
    assert "用时 5.20s" in output.getvalue()[before_end:]
    tree = display.build_tree()
    assert "全流程时间轴" in tree.children[0].label.plain
    group = next(child for child in tree.children if "Action → Outcome" in child.label.plain)
    assert any(getattr(child.label, "plain", "").startswith("O01 running") for child in group.children[0].children)
    assert "本阶段主体与职责" in rendered(display, tree)
    assert "T+005.20s" in rendered(display, tree)
    final_text = rendered(display, tree)
    assert "观察记录" in final_text and "逻辑记录" not in final_text
    assert "等待环境响应" not in final_text and "Environment environment" not in final_text


def test_active_step_is_first_and_live_view_omits_accumulated_schema_json():
    display, _ = view()
    start(display, "old", title="已经结束")
    display.emit({"event": "flow.stage.end", "stage_id": "old", "elapsed": 1, "status": "completed"})
    start(display, "now", title="当前持续动作", elapsed=1)
    for number in range(1, 12):
        step(display, stage_id="now", number=number, text=f"当前步骤 {number}")
    display.specifications["demo_env"] = {"protocol": "agent-env-compact/2", "tools": [
        {"name": "old_large_schema", "parameters": {"type": "object"}}]}
    live = display.build_live_tree()
    phase = live.renderables[0].renderable
    assert "步骤 11" in phase.children[0].label.plain
    assert "当前步骤 11" in phase.children[0].children[0].label.plain
    printed = rendered(display, live)
    assert printed.index("当前步骤 11") < printed.index("已经结束")
    assert "old_large_schema" not in printed
    assert "old_large_schema" in rendered(display, display.build_tree())


def test_input_and_already_built_tree_remain_immutable_after_more_emits():
    display, _ = view(trace=True)
    start(display)
    source = {"event": "flow.step", "stage_id": "connect", "stage_number": 1, "step_number": 1,
              "actor": "demo_agent", "operation": "原步骤", "text": "原讲解", "elapsed": 1, "presentation": True}
    display.emit(source)
    source["text"] = "被改写"
    tree = display.build_tree()
    before = rendered(display, tree)
    step(display, number=2, text="后一个步骤")
    display.emit({"event": "flow.stage.end", "stage_id": "connect", "elapsed": 4, "status": "interrupted"})
    assert rendered(display, tree) == before
    assert "被改写" not in before and "后一个步骤" not in before
    after = rendered(display, display.build_tree())
    assert "演示阶段 interrupted（中断）" in after
    assert "模拟停顿已中断" in after
    assert "原讲解" in after and "后一个步骤" in after
    assert display._phase_label(display.phases["connect"]).style == "red"


def test_concurrent_emit_and_snapshot_do_not_iterate_mutating_dicts():
    display, _ = view()
    start(display)

    def sender(index):
        for sequence in range(10):
            packet(display, "event", {"id": f"event-{index}-{sequence}", "name": "observation", "data": {"text": "原文"}})

    def reader():
        for _ in range(30):
            rendered(display, display.build_live_tree())
            display.build_tree()

    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(sender, index) for index in range(3)] + [workers.submit(reader)]
        for future in futures:
            future.result(timeout=20)
    assert len(display.messages) == len(display.phases["connect"]["messages"]) == 30
