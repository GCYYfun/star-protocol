"""The public demo exercises real SDK/Hub contracts without any model service."""

import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import ValidationError

from examples.protocol_demo.contracts import load_specification
from examples.protocol_demo.chronology import chronology_checks
from examples.protocol_demo.runner import run_demo
from examples.protocol_demo.timing import DemoTiming
from star_protocol import AgentClient
from star_protocol.models import Envelope
from star_protocol.models.payloads import validate_schema_instance


@pytest.mark.asyncio
async def test_complete_demo_over_real_websockets_and_durable_restart(tmp_path):
    summary = await run_demo(state_dir=tmp_path, quiet=True)
    assert summary["passed"] is True
    assert summary["outcome_statuses"] == ["accepted", "cancelled", "completed", "failed", "rejected", "running"]
    assert summary["check_count"] >= 40
    frames = [json.loads(line) for line in (tmp_path / "transcript.jsonl").read_text().splitlines()]
    timing_checks = chronology_checks(frames)
    assert timing_checks and all(timing_checks.values())
    assert set(timing_checks) <= set(summary["checks"])
    assert summary["check_count"] == 48 + len(timing_checks)
    local_rejections = [row for row in frames if row["event"] == "check" and "exception" in row]
    assert local_rejections and all(row["not_sent"] for row in local_rejections)
    # The same ORIGINAL transport UUID survives an actual Environment/Agent
    # instance restart; receiving it again cannot create a different receipt.
    replays = [row["envelope"] for row in frames if row["event"] == "wire.receive"
               and row["envelope"]["id"] == summary["replayed_delivery_id"]]
    assert len(replays) == 2 and replays[0] == replays[1]
    for frame in [row["envelope"] for row in frames if "envelope" in row]:
        parsed = Envelope.model_validate_json(json.dumps(frame))
        if parsed.payload.type == "outcome":
            assert set(parsed.payload.content["data"]) == {"text"}
            assert len(parsed.payload.content["refs"]) == 1
    assert json.loads((tmp_path / "summary.json").read_text())["recovered_outcome_id"] == summary["recovered_outcome_id"]
    phases = [row for row in frames if row["event"] == "flow.stage.start"]
    endings = [row for row in frames if row["event"] == "flow.stage.end"]
    assert [row["stage_id"] for row in phases] == [
        "configuration", "join", "tools", "execution", "continuous", "events",
        "renegotiation", "conversations", "stream-monitor", "delivery", "recovery", "shutdown"]
    assert [row["stage_id"] for row in endings] == [row["stage_id"] for row in phases]
    assert all(row["status"] == "completed" for row in endings)
    narrative = [row for row in frames if row["event"].startswith("flow.")]
    assert all(row["presentation"] is True and "envelope" not in row for row in narrative)
    actors = {row["actor"] for row in narrative if row["event"] == "flow.step"}
    assert {"demo_env", "hub", "demo_agent", "demo_colleague", "demo_human", "monitor"} <= actors
    registered = [row for row in frames if row["event"] == "capability.registered"]
    first_registration = {}
    for row in registered:
        first_registration.setdefault(row["component"], row)
    assert set(first_registration) == {"demo_env", "demo_agent", "demo_colleague", "demo_human"}
    assert all(row["stage_id"] == "configuration" for row in first_registration.values())
    assert set(first_registration["demo_env"]["bindings"]["tools"]) == {
        "observe", "set_light", "calculate", "wait", "cancel", "get_operation_result"}
    assert first_registration["demo_agent"]["specification"]["tools"] == []
    dispatches = [row for row in frames if row["event"] == "handler.dispatch"]
    assert any(row["component"] == "demo_env" and row["payload_type"] == "action"
               and row["content"]["name"] == "set_light" and row["dispatch_mode"] == "ledger_replay"
               for row in dispatches)
    assert any(row["component"] == "demo_env" and row["route"] == "runtime"
               and row["handler"].endswith("DemoEnvironment._activity_state") for row in dispatches)
    assert any(row["component"] == "demo_agent" and row["route"] == "runtime"
               and row["handler"].endswith("DemoPeerMixin._receive_feedback") for row in dispatches)
    assert any(row["component"] == "demo_agent" and row["route"] == "outcome"
               and row["handler"].endswith("DemoPeerMixin.on_outcome") for row in dispatches)
    # Receiving a remote Schema exposes that peer's inputs; it never turns
    # Environment tools into locally registered Agent tools.
    received_specs = [row for row in frames if row["event"] == "specification"]
    assert any(row["component"] == "demo_agent" and row["sender"] == "demo_env"
               and len(row["content"]["tools"]) == 6 for row in received_specs)
    assert any(row["component"] == "demo_env" and row["sender"] == "demo_agent"
               and row["content"]["tools"] == [] and len(row["content"]["events"]) >= 3
               for row in received_specs)


def test_demo_config_has_executable_runtime_handlers_and_bounded_local_refs():
    specification = load_specification("agent")
    declaration = next(event for event in specification["events"] if event["handler"] == "runtime")
    # A configuration file alone never installs a handler.
    agent = AgentClient("demo_config_check")
    with pytest.raises(ValueError, match="no installed handler"):
        agent.configure_capabilities(events=specification["events"])
    schema = declaration["data_schema"]
    validate_schema_instance(schema, {"text": "提示", "channel": "haptic", "intensity": 0.25})
    with pytest.raises(ValidationError):
        validate_schema_instance(schema, {"text": "提示", "channel": "haptic", "intensity": 2})
    with pytest.raises(ValidationError):
        validate_schema_instance(schema, {"text": "提示", "channel": "haptic", "intensity": 0.25, "extra": True})


@pytest.mark.parametrize("module", ["examples.protocol_demo", "examples.demo_env", "examples.demo_agent", "examples.demo_human", "examples.demo_monitor"])
def test_documented_cli_entrypoints_load_with_rich(module):
    result = subprocess.run([sys.executable, "-m", module, "--help"],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "--hub" in result.stdout


@pytest.mark.asyncio
async def test_custom_narrative_pauses_preserve_short_wait_and_cancel_results(tmp_path):
    summary = await run_demo(state_dir=tmp_path, quiet=True,
                             timing=DemoTiming(stage_delay=0.005, step_delay=0.002, wait_seconds=0.05))
    assert summary["passed"] is True and summary["check_count"] >= 55
    frames = [json.loads(line) for line in (tmp_path / "transcript.jsonl").read_text().splitlines()]
    steps = [row for row in frames if row["event"] == "flow.step"]
    assert any(row["wait_seconds"] == 0.005 for row in steps)
    assert any(row["wait_seconds"] == 0.002 for row in steps)
    assert next(row for row in steps if row["operation"] == "准备调用工具" and "cancel" in row["text"])["wait_seconds"] == 0
    actions = [row["envelope"]["payload"]["content"] for row in frames if "envelope" in row
               and row["envelope"]["payload"]["type"] == "action"]
    assert {content["params"]["seconds"] for content in actions if content["name"] == "wait"} == {0.05, 3}
    for row in frames:
        if "envelope" in row:
            content = row["envelope"]["payload"]["content"]
            assert "stage_id" not in content and "presentation" not in content
