"""Compact capabilities, guarded dispatch and local Action result tracking.

The SDK does not provide durable world execution or Conversation business rules.
Applications must persist actions/results before acknowledging or executing them.
"""

import asyncio
import copy
import json
from typing import Any

from star_protocol.models.payloads import validate_schema_instance

from star_protocol.models.payloads import (
    COMPACT_PROTOCOL, TERMINAL_STATUSES, MessagePayload, validate_compact_content,
    validate_content,
)
from star_protocol.models import Envelope


class ProtocolConflictError(ValueError):
    """Immutable logical identity or Outcome owner/state was violated."""


class ActionTimeoutError(TimeoutError):
    """No terminal result was confirmed locally; remote execution is unknown."""

    def __init__(self, action_id: str):
        self.action_id = action_id
        self.status = "unknown"
        super().__init__(f"Action {action_id} remains locally unconfirmed")


class CompactClientMixin:
    def _initialize_compact(self) -> None:
        self._own_specification = {"protocol": COMPACT_PROTOCOL, "tools": [], "events": []}
        self._runtime_handlers = {}
        self._peer_specifications = {}
        self._sent_specifications = set()
        self._sent_peer_specifications = {}
        self._logical_records = {}
        self._action_records = {}
        self._outcome_waiters = {}
        self._delivered_events = set()
        self._delivered_outcomes = set()

    def configure_capabilities(self, *, tools=None, events=None, runtime_handlers=None) -> None:
        """Install local receiver contracts and actual async runtime handlers.

        Call before connecting. Runtime handlers receive (sender, full_content).
        Model events are delivered to on_event. Re-declare the complete snapshot
        to each peer when capabilities change.
        """
        specification = copy.deepcopy(self._own_specification)
        if tools is not None:
            specification["tools"] = tools
        if events is not None:
            specification["events"] = events
        handlers = self._runtime_handlers if runtime_handlers is None else runtime_handlers
        validate_content("specification", specification)
        for definition in specification["events"]:
            if definition["handler"] == "runtime" and not callable(handlers.get(definition["name"])):
                raise ValueError(f"Runtime Event {definition['name']} has no installed handler")
        self._own_specification = copy.deepcopy(specification)
        self._runtime_handlers = dict(handlers)

    def protocol_for(self, peer: str):
        if peer in self._sent_specifications and peer in self._peer_specifications:
            return self._peer_specifications[peer]["protocol"]
        return None

    def specification_for(self, peer: str):
        return copy.deepcopy(self._peer_specifications.get(peer))

    async def send_specification(self, recipient: str, tools=None, *, events=None,
                                 protocol: str = COMPACT_PROTOCOL) -> None:
        if protocol != COMPACT_PROTOCOL:
            raise ValueError("Unsupported compact protocol")
        snapshot = copy.deepcopy(self._own_specification)
        if tools is not None:
            snapshot["tools"] = copy.deepcopy(tools)
        if events is not None:
            snapshot["events"] = copy.deepcopy(events)
        validate_content("specification", snapshot)
        for definition in snapshot["events"]:
            if definition["handler"] == "runtime" and not callable(self._runtime_handlers.get(definition["name"])):
                raise ValueError("A runtime declaration requires an installed handler")
        envelope = Envelope(type="message", sender=self.client_id, recipient=recipient,
                            payload=MessagePayload(type="specification", content=snapshot))
        await self.send(envelope)
        self._sent_specifications.add(recipient)
        self._sent_peer_specifications[recipient] = snapshot

    async def send_discover(self, recipient: str) -> None:
        # A fresh exchange must validate both snapshots again.
        self._sent_specifications.discard(recipient)
        self._sent_peer_specifications.pop(recipient, None)
        self._peer_specifications.pop(recipient, None)
        await self.send(Envelope(type="message", sender=self.client_id, recipient=recipient,
                                payload=MessagePayload(type="discover", content={"protocols": [COMPACT_PROTOCOL]})))

    async def _compact_capability_message(self, envelope: Envelope) -> bool:
        payload = envelope.payload
        if payload.type == "discover":
            if COMPACT_PROTOCOL not in payload.content["protocols"]:
                await self.on_error({"code": 406, "msg": "No common application protocol"})
                return True
            self._sent_specifications.discard(envelope.sender)
            self._sent_peer_specifications.pop(envelope.sender, None)
            self._peer_specifications.pop(envelope.sender, None)
            discovered = await self.on_discover(envelope.sender)
            if isinstance(discovered, dict):
                validate_content("specification", discovered)
                if discovered["protocol"] != COMPACT_PROTOCOL:
                    raise ValueError("Discovery selected an unsupported protocol")
                await self.send_specification(envelope.sender, discovered["tools"], events=discovered["events"])
            elif discovered is not None:
                await self.send_specification(envelope.sender, discovered)
            else:
                await self.send_specification(envelope.sender)
            return True
        if payload.type == "specification":
            content = payload.content
            if content["protocol"] != COMPACT_PROTOCOL:
                raise ValueError("Peer selected an unsupported application protocol")
            self._peer_specifications[envelope.sender] = copy.deepcopy(content)
            if self.role == "agent" and hasattr(self, "_tools"):
                self._tools = copy.deepcopy(content["tools"])
            if envelope.sender not in self._sent_specifications:
                await self.send_specification(envelope.sender)
            await self.on_specification(envelope.sender, copy.deepcopy(content))
            return True
        return False

    async def on_discover(self, sender: str):
        return copy.deepcopy(self._own_specification["tools"])

    async def on_specification(self, sender: str, content: dict) -> None:
        """Complete bidirectional snapshot; override to install application state."""
        pass

    def _remember_content(self, kind: str, content: dict) -> bool:
        logical_id = content["id"]
        signature = (kind, json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        previous = self._logical_records.get(logical_id)
        if previous is not None and previous != signature:
            raise ProtocolConflictError(f"Logical ID {logical_id} was reused with different content")
        self._logical_records[logical_id] = signature
        return previous is None

    def _require_peer(self, peer: str) -> dict:
        if self.protocol_for(peer) != COMPACT_PROTOCOL:
            raise ValueError(f"Application contract has not been negotiated with {peer}")
        return self._peer_specifications[peer]

    def _compact_before_send(self, envelope: Envelope) -> None:
        if envelope.sender != self.client_id:
            raise ValueError("Sender must be the client's authenticated identity")
        if envelope.type not in ("message", "broadcast"):
            return
        payload = envelope.payload
        kind, content = payload.type, payload.content
        if kind in ("discover", "specification", "stream"):
            return
        if envelope.type == "broadcast":
            if kind != "event":
                return
            # Broadcast has no single receiver schema. Only base text events may
            # use it; structured controls must be addressed per negotiated peer.
            validate_compact_content(kind, content)
        else:
            peer = self._require_peer(envelope.recipient)
            validate_compact_content(kind, content, peer["events"])
            if kind == "action":
                tool = next((item for item in peer["tools"] if item["name"] == content["name"]), None)
                if tool is None:
                    raise ValueError(f"Undeclared tool: {content['name']}")
                validate_schema_instance(tool["parameters"],content["params"])
        if kind == "event":
            for ref in content.get("refs", []):
                record = self._logical_records.get(ref)
                if record and record[0] != "event":
                    raise ProtocolConflictError("Event refs must target Event records")
        self._remember_content(kind, content)
        if kind == "action":
            original = self._action_records.get(content["id"])
            owner = (self.client_id, envelope.recipient)
            if original and original["owner"] != owner:
                raise ProtocolConflictError("Action ID was reused for a different peer")
            if not original:
                self._action_records[content["id"]] = {"owner": owner, "content": copy.deepcopy(content), "status": "unknown", "outcomes": [], "terminal": None}
        elif kind == "outcome":
            action = self._action_records.get(content["refs"][0])
            if not action or action["owner"] != (envelope.recipient, self.client_id):
                raise ProtocolConflictError("Outcome does not belong to this sender/recipient Action")
            self._record_outcome(action, content)

    def _record_outcome(self, action: dict, content: dict) -> None:
        if any(item["id"] == content["id"] for item in action["outcomes"]):
            return
        terminal = action["terminal"]
        if terminal and content["status"] in TERMINAL_STATUSES:
            raise ProtocolConflictError("Action already has a different immutable terminal Outcome")
        action["outcomes"].append(copy.deepcopy(content))
        if terminal:
            return  # Late progress is retained without reversing final status.
        if content["status"] == "accepted" and action["status"] == "running":
            return
        action["status"] = content["status"]
        if content["status"] in TERMINAL_STATUSES:
            action["terminal"] = copy.deepcopy(content)

    async def _compact_before_receive(self, envelope: Envelope) -> bool:
        """Return True when a replay or registered runtime handler consumed it."""
        kind, content = envelope.payload.type, envelope.payload.content
        if kind in ("discover", "specification", "stream"):
            return False
        self._require_peer(envelope.sender)
        declared = self._sent_peer_specifications[envelope.sender]
        validate_compact_content(kind, content, declared["events"])
        if kind == "action":
            tool = next((item for item in declared["tools"] if item["name"] == content["name"]), None)
            if tool is None:
                raise ValueError(f"Undeclared local tool: {content['name']}")
            validate_schema_instance(tool["parameters"],content["params"])
            self._remember_content(kind, content)
            owner = (envelope.sender, self.client_id)
            action = self._action_records.get(content["id"])
            if action and action["owner"] != owner:
                raise ProtocolConflictError("Action ID belongs to a different sender")
            self._action_records.setdefault(content["id"], {"owner": owner, "content": copy.deepcopy(content), "status": "unknown", "outcomes": [], "terminal": None})
            return False  # Environment ledger must replay, never execute again.
        if kind == "outcome":
            action_id = content["refs"][0]
            action = self._action_records.get(action_id)
            if not action or action["owner"] != (self.client_id, envelope.sender):
                raise ProtocolConflictError("Outcome has no matching Action owner/target")
            self._remember_content(kind, content)
            self._record_outcome(action, content)
            if content["id"] in self._delivered_outcomes:
                return True
            future = self._outcome_waiters.get(action_id)
            if action["terminal"] and future and not future.done():
                future.set_result(copy.deepcopy(action["terminal"]))
            return False
        # Reject known cross-type references. Missing historical references are
        # retained for the application's authorized durable record resolver.
        for ref in content.get("refs", []):
            record = self._logical_records.get(ref)
            if record and record[0] != "event":
                raise ProtocolConflictError("Event refs must target Event records")
        self._remember_content(kind, content)
        if content["id"] in self._delivered_events:
            return True
        definition = next((item for item in declared["events"] if item["name"] == content["name"]), None)
        if definition and definition["handler"] == "runtime":
            await self._runtime_handlers[content["name"]](envelope.sender, copy.deepcopy(content))
            self._delivered_events.add(content["id"])
            return True
        return False

    def action_status(self, action_id: str):
        record = self._action_records.get(action_id)
        return record["status"] if record else "unknown"

    def action_outcomes(self, action_id: str):
        record = self._action_records.get(action_id)
        return copy.deepcopy(record["outcomes"]) if record else []

    def restore_action(self, recipient: str, content: dict) -> None:
        """Register an application's durable Action before receiving replay."""
        validate_content("action", content)
        self._remember_content("action", content)
        previous = self._action_records.get(content["id"])
        if previous and previous["owner"] != (self.client_id, recipient):
            raise ProtocolConflictError("Restored Action belongs to another peer")
        self._action_records.setdefault(content["id"], {"owner": (self.client_id, recipient), "content": copy.deepcopy(content), "status": "unknown", "outcomes": [], "terminal": None})

    def restore_received_action(self, sender: str, content: dict) -> None:
        """Hydrate an Environment's durable inbound binding before result replay."""
        validate_content("action", content)
        self._remember_content("action", content)
        previous = self._action_records.get(content["id"])
        if previous and previous["owner"] != (sender, self.client_id):
            raise ProtocolConflictError("Restored inbound Action has a different owner")
        self._action_records.setdefault(content["id"], {"owner": (sender, self.client_id), "content": copy.deepcopy(content), "status": "unknown", "outcomes": [], "terminal": None})

    async def await_action(self, action_id: str, *, timeout: float | None = None) -> dict:
        record = self._action_records.get(action_id)
        if record is None:
            raise ValueError("Unknown local Action")
        if record["terminal"]:
            return copy.deepcopy(record["terminal"])
        future = self._outcome_waiters.setdefault(action_id, asyncio.get_running_loop().create_future())
        try:
            if timeout is None:
                return await asyncio.shield(future)
            return await asyncio.wait_for(asyncio.shield(future), timeout)
        except TimeoutError as exc:
            # No cancellation, remote terminal or automatic resend is inferred.
            raise ActionTimeoutError(action_id) from exc

    async def request_action(self, recipient: str, action_name: str, params=None,
                             *, action_id: str, timeout: float | None = None) -> dict:
        await self.send_action(recipient, action_name, params, action_id=action_id)
        return await self.await_action(action_id, timeout=timeout)
