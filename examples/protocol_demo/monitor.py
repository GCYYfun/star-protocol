"""Monitor demonstration with Hub-confirmed subscription and deterministic waits."""

import asyncio
import copy
from collections.abc import Callable

from star_protocol.client.monitor import MonitorClient


class DemoMonitor(MonitorClient):
    """Collect actual monitor data; readiness comes from Hub notification."""

    def __init__(self, client_id="demo_monitor", *, emit: Callable[[dict], None] | None = None):
        super().__init__(client_id, auto_reconnect=False)
        self.emit = emit or (lambda record: None)
        self.records: list[dict] = []
        self.errors: list[dict] = []
        self._confirmed_targets: set[str] = set()
        self._changed = asyncio.Condition()

    def confirmed(self, target: str) -> bool:
        """Return whether the Hub has confirmed this subscription."""
        return target in self._confirmed_targets

    async def ready(self, target: str, timeout=5):
        """Wait for monitor.notify subscribed; sending ctrl is not confirmation."""
        async with self._changed:
            await asyncio.wait_for(
                self._changed.wait_for(lambda: self.confirmed(target)), timeout)

    async def wait_record(self, name: str, timeout=5) -> dict:
        """Wait for a received monitor.data entry, including already received data."""
        async with self._changed:
            await asyncio.wait_for(
                self._changed.wait_for(lambda: any(record["name"] == name
                                                   for record in self.records)), timeout)
            return copy.deepcopy(next(record for record in self.records
                                      if record["name"] == name))

    async def _handle_monitor_notify(self, content: dict):
        await super()._handle_monitor_notify(content)
        target = content.get("target_client_id")
        async with self._changed:
            if content.get("event") == "subscribed" and target:
                self._confirmed_targets.add(target)
            elif content.get("event") == "unsubscribed" and target:
                self._confirmed_targets.discard(target)
            self._changed.notify_all()
        self.emit({"source": "hub", "name": f"monitor.{content.get('event')}",
                   "data": copy.deepcopy(content)})

    async def on_connected(self):
        await super().on_connected()
        self._confirmed_targets.clear()

    async def on_disconnected(self):
        await super().on_disconnected()
        async with self._changed:
            self._confirmed_targets.clear()
            self._changed.notify_all()

    async def on_monitor_data(self, client_id: str, data_type: str, data: dict):
        record = {"source": client_id, "name": data_type, "data": copy.deepcopy(data)}
        async with self._changed:
            self.records.append(record)
            self._changed.notify_all()
        self.emit(copy.deepcopy(record))

    async def on_error(self, error: dict):
        self.errors.append(copy.deepcopy(error))
        self.emit({"source": "hub", "name": "error", "data": copy.deepcopy(error)})
        await super().on_error(error)
        async with self._changed:
            self._changed.notify_all()
