"""Regression for strict Envelope construction on the real Hub monitor route."""

import asyncio

import pytest

from examples.protocol_demo.monitor import DemoMonitor
from examples.protocol_demo.runner import local_hub
from star_protocol import AgentClient
from star_protocol.models import Envelope


class CapturingMonitor(DemoMonitor):
    def __init__(self, client_id):
        super().__init__(client_id)
        self.deliveries = []

    async def _handle_monitor_message(self, envelope):
        if envelope.payload.type == "data":
            self.deliveries.append(envelope.model_dump())
        await super()._handle_monitor_message(envelope)


@pytest.mark.asyncio
async def test_real_hub_monitor_subscription_forwards_valid_recipient_to_each_receiver():
    async with local_hub() as url:
        agent = AgentClient("telemetry-agent", monitorable=True, auto_reconnect=False)
        monitors = [CapturingMonitor("monitor-one"), CapturingMonitor("monitor-two")]
        clients = [agent, *monitors]
        try:
            for client in clients:
                await client.connect(url)
                await client.start()
            for monitor in monitors:
                assert not monitor.confirmed(agent.client_id)
                await monitor.subscribe_to_client(agent.client_id)
                await monitor.ready(agent.client_id)
            await agent.enable_monitoring()
            await agent.send_monitor_data("demo.trace", {"text": "真实 Hub 遥测。"})
            records = await asyncio.gather(*(monitor.wait_record("demo.trace")
                                             for monitor in monitors))
            assert records == [{"source": agent.client_id, "name": "demo.trace",
                                "data": {"text": "真实 Hub 遥测。"}}] * 2
            deliveries = [next(envelope for envelope in monitor.deliveries
                               if envelope["payload"]["content"]["name"] == "demo.trace")
                          for monitor in monitors]
            for monitor, delivery in zip(monitors, deliveries, strict=True):
                Envelope.model_validate(delivery)
                assert delivery["recipient"] == monitor.client_id
                assert delivery["sender"] == agent.client_id
                assert not monitor.errors
            assert deliveries[0]["id"] != deliveries[1]["id"]
        finally:
            for client in reversed(clients):
                await client.stop()
