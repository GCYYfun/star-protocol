"""Pacing yields to receive work and is never a protocol message or result."""

import asyncio
from copy import deepcopy

import pytest

from examples.protocol_demo.flow import DemoFlow
from examples.protocol_demo.timing import DemoTiming


class Records:
    stage_id = None

    def __init__(self):
        self.records = []

    def emit(self, record):
        self.records.append(deepcopy(record))


@pytest.mark.asyncio
async def test_pacing_applies_config_and_records_completed_wait_without_wire_content():
    records = Records()
    now = [0.0]
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    flow = DemoFlow(records, DemoTiming(stage_delay=1, step_delay=0.5), sleep=sleep, clock=lambda: now[0])
    await flow.stage("join", "加入", "准备主体")
    await flow.step("demo_agent", "发送请求", "按照真实能力协商结果执行")
    await flow.step("demo_agent", "取消敏感操作", "这个步骤不额外暂停", delay=0)
    flow.finish(success=True)
    assert slept == [1, 0.5]
    assert records.records[-1]["event"] == "flow.stage.end"
    assert records.records[-1]["elapsed"] == 1.5
    ended = [record for record in records.records if record["event"] == "flow.step.end"]
    assert len(ended) == 3 and all(record["wait_seconds"] == 0 for record in ended)
    assert all(record["presentation"] is True and "envelope" not in record and "content" not in record for record in records.records)


@pytest.mark.asyncio
async def test_presentation_pause_does_not_block_independent_receiver_work():
    records = Records()
    release = asyncio.Event()

    async def sleep(seconds):
        await release.wait()

    flow = DemoFlow(records, DemoTiming(step_delay=1), sleep=sleep)
    await flow.stage("execution", "执行", "模拟演示")
    paused = asyncio.create_task(flow.step("demo_agent", "观察停顿", "接收循环继续工作"))
    await asyncio.sleep(0)
    assert not paused.done()
    # A separate receive-loop task can still commit incoming work while the
    # scenario driver is paused. No delay is placed inside an SDK callback.
    incoming = asyncio.create_task(asyncio.sleep(0, result="received"))
    assert await incoming == "received"
    assert not paused.done()
    release.set()
    await paused
    assert records.records[-1]["event"] == "flow.step.end"


@pytest.mark.asyncio
async def test_cancellation_marks_phase_interrupted_without_claiming_wait_finished():
    records = Records()
    release = asyncio.Event()

    async def sleep(seconds):
        await release.wait()

    flow = DemoFlow(records, DemoTiming(step_delay=1), sleep=sleep)
    await flow.stage("execution", "执行", "模拟演示")
    paused = asyncio.create_task(flow.step("demo_agent", "观察停顿", "正在等待"))
    await asyncio.sleep(0)
    paused.cancel()
    with pytest.raises(asyncio.CancelledError):
        await paused
    flow.finish(success=False)
    assert records.records[-1]["status"] == "interrupted"
    assert not any(record["event"] == "flow.step.end" and record["step_number"] == 2 for record in records.records)
