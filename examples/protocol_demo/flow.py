"""Narrated demo pacing; these records are never sent as protocol messages."""

import asyncio
import time

from .timing import DemoTiming


class DemoFlow:
    def __init__(self, transcript, timing: DemoTiming, *, sleep=asyncio.sleep, clock=time.monotonic):
        self.transcript = transcript
        self.timing = timing
        self.sleep = sleep
        self.clock = clock
        self.started = clock()
        self.stage_id = None
        self.stage_title = None
        self.stage_number = 0
        self.step_number = 0

    def _emit(self, event, **details):
        self.transcript.emit({"component": "demo", "event": event,
                              "stage_id": self.stage_id, "stage_number": self.stage_number,
                              "elapsed": round(self.clock() - self.started, 3),
                              "presentation": True, **details})

    async def stage(self, identifier, title, description):
        self.end_stage()
        self.stage_id, self.stage_title = identifier, title
        self.stage_number += 1
        self.transcript.stage_id = identifier
        self._emit("flow.stage.start", title=title, description=description)
        await self.step("demo", "进入阶段", description, delay=self.timing.stage_delay)

    async def step(self, actor, operation, text, *, delay=None):
        """Pause only the scenario driver; receive handlers remain runnable."""
        seconds = self.timing.step_delay if delay is None else delay
        self.step_number += 1
        self._emit("flow.step", actor=actor, operation=operation, text=text,
                   wait_seconds=seconds, step_number=self.step_number)
        if seconds:
            await self.sleep(seconds)
        self._emit("flow.step.end", actor=actor, operation=operation,
                   wait_seconds=0, step_number=self.step_number)

    def end_stage(self, *, status="completed"):
        if self.stage_id is not None:
            self._emit("flow.stage.end", title=self.stage_title, status=status)
            self.stage_id = None
            self.transcript.stage_id = None

    def finish(self, *, success):
        self.end_stage(status="completed" if success else "interrupted")
