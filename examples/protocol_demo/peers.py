"""Demo receivers: explicit readiness, durable originals and installed handlers."""

import asyncio
import copy
import json
import sqlite3
from pathlib import Path

from star_protocol import AgentClient, HumanClient, ProtocolConflictError
from star_protocol.models import COMPACT_PROTOCOL

from .contracts import load_specification
from .registration import handler_dispatch, summarize_registration


class DemoPeerMixin:
    def __init__(self, client_id, *, state_dir: Path, emit=None):
        super().__init__(client_id, auto_reconnect=False, monitorable=True)
        self.emit = emit or (lambda record: None)
        self.errors = []
        self._changed = asyncio.Condition()
        self._joined = asyncio.Event()
        self.feedback_calls = 0
        self.ack_count = 0
        self.ack_enabled = True
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.state_dir / f"{client_id}.sqlite3"
        self.db = sqlite3.connect(self.database_path)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY, recipient TEXT NOT NULL, content TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS originals (
                id TEXT PRIMARY KEY, sender TEXT NOT NULL, kind TEXT NOT NULL,
                content TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS envelopes (
                id TEXT PRIMARY KEY, content TEXT NOT NULL);
        """)
        specification = load_specification(self.role)
        self.configure_capabilities(
            tools=specification["tools"], events=specification["events"],
            runtime_handlers={"interaction.feedback": self._receive_feedback},
        )
        for recipient, encoded in self.db.execute("SELECT recipient,content FROM actions"):
            self.restore_action(recipient, json.loads(encoded))
        for kind, encoded in self.db.execute("SELECT kind,content FROM originals"):
            self._remember_content(kind, json.loads(encoded))

    def configure_capabilities(self, *, tools=None, events=None, runtime_handlers=None):
        super().configure_capabilities(tools=tools, events=events,
                                       runtime_handlers=runtime_handlers)
        # Describe the validated installed snapshot, not the unvalidated file.
        self.emit(summarize_registration(self, self._own_specification,
                                         self._runtime_handlers))

    async def _signal(self):
        async with self._changed:
            self._changed.notify_all()

    async def wait_for(self, predicate, *, timeout=5):
        async with self._changed:
            await asyncio.wait_for(self._changed.wait_for(predicate), timeout)

    async def ready(self, peer, *, timeout=5):
        await self.wait_for(lambda: self.protocol_for(peer) == COMPACT_PROTOCOL, timeout=timeout)

    async def connect_join(self, url, environment="demo_env"):
        await self.connect(url)
        await self.start()
        self._joined.clear()
        await self.join_environment(environment)
        await asyncio.wait_for(self._joined.wait(), 5)
        await self.ready(environment)

    async def on_system_notify(self, event, content):
        await super().on_system_notify(event, content)
        if event == "joined":
            self._joined.set()
        await self._signal()

    async def on_specification(self, sender, content):
        self.emit({"component": self.client_id, "event": "specification",
                   "sender": sender, "content": content})
        await self._signal()

    async def on_error(self, error):
        self.errors.append(copy.deepcopy(error))
        self.emit({"component": self.client_id, "event": "error", "content": error})
        await super().on_error(error)
        await self._signal()

    @staticmethod
    def _encode(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _remember(self, sender, kind, content):
        encoded = self._encode(content)
        previous = self.db.execute("SELECT sender,kind,content FROM originals WHERE id=?",
                                   (content["id"],)).fetchone()
        if previous and previous != (sender, kind, encoded):
            raise ProtocolConflictError("Durable original ID/content conflicts")
        if not previous:
            with self.db:
                self.db.execute("INSERT INTO originals VALUES (?,?,?,?)",
                                (content["id"], sender, kind, encoded))
        return previous is None

    async def send(self, envelope):
        # SDK validates the exact receiver contract before this application
        # stores a request, and the request commits before the first network I/O.
        self._compact_before_send(envelope)
        if envelope.type == "message" and envelope.payload.type == "action":
            content = envelope.payload.content
            encoded = self._encode(content)
            old = self.db.execute("SELECT recipient,content FROM actions WHERE id=?",
                                  (content["id"],)).fetchone()
            if old and old != (envelope.recipient, encoded):
                raise ProtocolConflictError("Durable Action target or parameters changed")
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO actions VALUES (?,?,?)",
                                (content["id"], envelope.recipient, encoded))
            self.emit({"component": self.client_id, "event": "wire.stored",
                       "storage": "actions", "envelope": envelope.model_dump()})
        if envelope.type == "message" and envelope.payload.type == "event":
            self._remember(self.client_id, "event", envelope.payload.content)
            self.emit({"component": self.client_id, "event": "wire.stored",
                       "storage": "originals", "envelope": envelope.model_dump()})
        self.emit({"component": self.client_id, "event": "wire.send.start",
                   "presentation": True, "envelope": envelope.model_dump()})
        await self._messaging.send_envelope(envelope)
        self.emit({"component": self.client_id, "event": "wire.send",
                   "envelope": envelope.model_dump()})
        if self._monitorable:
            await self._on_message_sent(envelope)

    def _received(self, envelope):
        # The base receive loop parsed the Envelope, but receiver-specific
        # capability, ownership and Schema checks have not happened yet.
        self.emit({"component": self.client_id, "event": "wire.receive",
                   "parsed": True, "envelope": envelope.model_dump()})

    async def _handle_system(self, envelope):
        self._received(envelope)
        await super()._handle_system(envelope)
        self.emit({"component": self.client_id, "event": "wire.handled",
                   "envelope": envelope.model_dump()})

    async def _handle_message(self, envelope):
        self._received(envelope)
        await super()._handle_message(envelope)
        await self._after_validated(envelope)

    async def _handle_broadcast(self, envelope):
        self._received(envelope)
        await super()._handle_broadcast(envelope)
        await self._after_validated(envelope)

    async def _after_validated(self, envelope):
        # BaseClient completed capability/content/ownership checks and the
        # business callback before this connector commits the full Envelope.
        encoded = self._encode(envelope.model_dump())
        old = self.db.execute("SELECT content FROM envelopes WHERE id=?", (envelope.id,)).fetchone()
        if old and old[0] != encoded:
            raise ProtocolConflictError("Transport UUID reused with different Envelope")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO envelopes VALUES (?,?)", (envelope.id, encoded))
        self.emit({"component": self.client_id, "event": "wire.stored",
                   "storage": "envelopes", "envelope": envelope.model_dump()})
        if (self.ack_enabled and envelope.sender == self.current_env and envelope.type == "message"
                and envelope.payload.type in {"outcome", "event"}):
            await self.send_delivery_ack(envelope.sender, envelope.id)
            self.ack_count += 1
        await self._signal()

    async def on_outcome(self, sender, content):
        self._remember(sender, "outcome", content)
        self.emit(handler_dispatch(self, sender, "outcome", content,
                                   self.on_outcome, "outcome"))
        self.emit({"component": self.client_id, "event": "outcome",
                   "sender": sender, "content": content})
        await self._signal()

    async def on_event(self, sender, content):
        self._remember(sender, "event", content)
        self.emit(handler_dispatch(self, sender, "event", content,
                                   self.on_event, "model"))
        self.emit({"component": self.client_id, "event": "model.event",
                   "sender": sender, "content": content})
        await self._signal()

    async def on_broadcast_event(self, sender, content):
        await self.on_event(sender, content)

    async def _receive_feedback(self, sender, content):
        if sender != self.current_env:
            raise PermissionError("Only the joined environment controls feedback")
        fresh = self._remember(sender, "event", content)
        self.emit(handler_dispatch(self, sender, "event", content,
                                   self._receive_feedback, "runtime"))
        if fresh:
            self.feedback_calls += 1
        self.emit({"component": self.client_id, "event": "runtime.event",
                   "sender": sender, "content": content})
        await self._signal()

    async def on_stream(self, sender, content):
        self.emit({"component": self.client_id, "event": "stream", "sender": sender,
                   "content": content})

    async def on_broadcast_stream(self, sender, content):
        await self.on_stream(sender, content)

    def original(self, logical_id):
        row = self.db.execute("SELECT content FROM originals WHERE id=?", (logical_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def original_action(self, action_id):
        row = self.db.execute("SELECT content FROM actions WHERE id=?", (action_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def stored_outcomes(self, action_id):
        contents = [json.loads(row[0]) for row in self.db.execute(
            "SELECT content FROM originals WHERE kind='outcome' ORDER BY rowid")]
        return [content for content in contents if content["refs"] == [action_id]]

    async def settled(self, action_id, *, timeout=5):
        final = await self.await_action(action_id, timeout=timeout)
        # await_action alone is SDK memory readiness. This second wait proves
        # that the demo's application callback has committed the original.
        await self.wait_for(lambda: self.original(final["id"]) is not None, timeout=timeout)
        return final

    async def stop(self):
        await super().stop()
        self.db.close()


class DemoAgent(DemoPeerMixin, AgentClient):
    pass


class DemoHuman(DemoPeerMixin, HumanClient):
    pass
