# Star Protocol Python SDK

Python SDK 0.3.0 implements the negotiated `agent-env-compact/2` application contract over Star Envelope routing. The application version is separate from the package version. This is a breaking Content/API upgrade from 0.2.0; legacy `success/ref_id` results are rejected rather than silently translated.

Install this checkout with `uv sync`. Run the Hub with `uv run uvicorn app:create_hub_app --factory` (see `app.py`). Agent, Environment and Human clients share strict lossless parsing, explicit capability negotiation, model text input and installed runtime Event handlers. Star system, monitor and stream payloads remain available.

## Complete protocol demo

Run a real local Hub with two Agents, one Human, one Environment and one Monitor; the scenario performs assertions and exits without calling an LLM or paid service:

```bash
uv run python -m examples.protocol_demo
uv run python -m examples.protocol_demo --state-dir .demo-state --trace
uv run python -m examples.protocol_demo --stage-delay 1 --step-delay 0.5 --wait-seconds 2
uv run python -m examples.protocol_demo --fast
```

The second command retains SQLite records, `transcript.jsonl` and `summary.json`. Rich output shows the operation flow by stage, identifying the active actors, operations and time, then retains a relationship tree grouping receiver capabilities, Action → Outcome, Event references, delivery recovery, Stream and Monitor. `--trace` expands message hierarchy, schemas and check details in that tree while the transcript keeps raw JSON records. Short ID aliases are display-only; full IDs remain available in trace and saved records. Rich is declared in the development dependencies and installed by `uv sync`. Editable receiver snapshots demonstrate Tool schemas, model/runtime Event declarations and local `$defs` / `$ref`. The demo covers all six Outcome statuses, bidirectional negotiation and renewed receiver snapshots, continuous actions, causal references, invalid inputs, immutable replay, instance recovery, durable delivery acknowledgements, original-envelope replay after a lost ACK, Star stream chunks and confirmed Monitor subscriptions with telemetry. See [examples/README.md](examples/README.md) for the coverage matrix, complete wire messages and separate role commands.



Local registration is shown before connecting: Environment tools all dispatch through `DemoEnvironment.on_action`; Agent/Human declare model Events handled by `on_event` and runtime feedback bound to `_receive_feedback`. Outcome uses the separate framework `on_outcome` callback. The default Rich view shows receiver entries, Schema field summaries, actual handler names, message direction, request parameters and text. Registration observations follow successful local configuration, and dispatch observations follow actual callback entry. Bidirectional specifications describe existing receiver behavior; receiving a remote Schema does not install functions. See the example guide for the four-step discovery exchange and each invocation path.

The CLI loads `examples/protocol_demo/config/demo-timing.json` by default: `stage_delay=0.7`, `step_delay=0.3`, `wait_seconds=1.2` seconds. `--timing PATH` selects another configuration; the individual time flags override its values. Stage and step delays accept finite numbers from 0 to 10 seconds; the normally completing wait example accepts 0.05 to 3 seconds. The cancellation example independently starts a three-second wait and cancels it after actual running progress. `--fast` removes presentation pauses while keeping real waits and protocol confirmations. These settings do not simulate network latency or add protocol fields. Presentation annotations are saved as separate `flow.*` records and never sent to the Hub.

## Content contracts

| Payload type | Content |
|---|---|
| action | `id`, `name`, `params` |
| outcome | `id`, `refs: [action_id]`, `status`, `data: {text}` |
| event | `id`, `name`, `data`, optional ordered `refs` |
| discover | `protocols` |
| specification | `protocol`, `tools`, `events` |

Outcome statuses are `accepted`, `running`, `completed`, `rejected`, `failed`, `cancelled`. Only the last four finish the Action. Multiple intermediate results do not resolve a final wait. Duplicate IDs preserve immutable content; conflicting IDs and contradictory terminal results raise `ProtocolConflictError`. Timeout raises `ActionTimeoutError` with local `status="unknown"`; it does not cancel remote execution or retry a write.

## Agent

```python
from star_protocol import AgentClient, ActionTimeoutError
from star_protocol.models import gen_id

class MyAgent(AgentClient):
    async def on_specification(self, sender, content):
        # The entire receiver snapshot is available: protocol/tools/events.
        self.ready.set()

    async def on_outcome(self, sender, content):
        print(content["status"], content["data"]["text"])

# Configure receiver schemas and actual runtime handlers before connecting.
agent = MyAgent("agent")
agent.configure_capabilities(events=[], runtime_handlers={})
# connect/start/join_environment triggers discover and a two-way specification
# exchange. Await your on_specification signal before sending business traffic.

action_id = gen_id("action")
# Persist {id, name, params, recipient} here, before the first send.
await agent.send_action("env", "MOVE", {"x": 1}, action_id=action_id)
try:
    final = await agent.await_action(action_id, timeout=30)
except ActionTimeoutError:
    # Keep the original operation unresolved. After reconnect/negotiation,
    # resend the SAME stored Action or query the environment's declared tool.
    pass
```

`request_action(..., action_id=..., timeout=...)` combines send and terminal wait. `restore_action(recipient, content)` registers a durable original Action before receiving its replay. Environment uses `restore_received_action(sender, content)` to hydrate its own durable binding before sending the original Outcome after restart. `action_status(id)` and `action_outcomes(id)` expose the local received record. These SDK records are in memory; the application must persist them for crash recovery.

## Environment and receiver capabilities

```python
from star_protocol import EnvironmentClient
from star_protocol.models import gen_id

env = EnvironmentClient("env")
env.configure_capabilities(tools=[{
    "name": "MOVE", "description": "移动到坐标",
    "parameters": {"type": "object", "properties": {"x": {"type": "integer"}},
                   "required": ["x"], "additionalProperties": False},
}], events=[], runtime_handlers={})

# In an overridden on_action(sender, content), durably bind the immutable Action
# and commit world state plus its final Outcome atomically before sending it.
await env.send_outcome("agent", {
    "id": gen_id("outcome"), "refs": [content["id"]],
    "status": "completed", "data": {"text": "已到达坐标1。"},
})
```

Override `on_discover(sender)` to return either the tool list or the entire `protocol/tools/events` snapshot. Receiving specification calls `on_specification(sender, content)` on all three business clients. Agent's default full callback bridges the old tool-only callback; overriding the full callback avoids a second callback. Agent/Human automatically discover on join; either peer replies with its configured complete snapshot. `protocol_for(peer)` is ready only after both snapshots are exchanged. Reconnect requires fresh negotiation.

Each Event definition has `name`, `description`, `handler` (`model` or `runtime`), optional `data_schema`. Register runtime callbacks with `configure_capabilities(runtime_handlers={name: async_callback})`; each receives `(sender, full_content)` and dispatches once after successful handling. Declaring a runtime Event without its handler fails. Ordinary Event names use text-only model input by default; extra keys require the receiver's declared data schema. SDK does not infer group permissions or trade decisions from text.

`send_event(..., event_id=..., refs=...)` and Human/Environment equivalents preserve caller IDs and references. `broadcast_event(..., event_id=..., refs=...)` targets the Environment's members and permits only default text data. Structured Conversation controls should be sent to each authorized, negotiated recipient. Transparent forwarding preserves Content; a new authorized projection receives a new ID.

## Validation and responsibility

Wire parsing rejects missing IDs, duplicate keys, non-finite numbers, illegal Envelope/Payload combinations, unknown compact fields and limits above 512 KiB. Tool parameters and Event data use JSON Schema with FormatChecker after receiver negotiation. Receiver schemas support local `$ref`; external schema loading requires an explicit application adapter. Canonical schemas use bounded immutable validation caches. Hub binds sender to the authenticated WebSocket connection, requires both snapshots before business routing, checks Action/Outcome ownership, preserves logical IDs and does not copy private peer messages to the Environment. Transport delivery UUID is distinct from a logical Content ID.

Durable reception/ACK, world atomicity, ledger replay ordering, authorization, retention and resolution of references to unavailable historical records remain application/connector duties. SDK validates known reference types but cannot invent inaccessible history. Conversation 2.0 handlers and an environment's Interaction rules must be implemented in the application; a remote Schema does not install behavior. Production writes require a durable operation store. The complete example in `examples/protocol_demo/` supplies an application-owned SQLite ledger for its demonstration world; it does not extend SDK guarantees to arbitrary external services.

## Tests

```bash
uv run pytest tests -q
```

Tests cover strict roundtrip, schema/size failures, progress before terminal, identity reuse, late timeout recovery, exact runtime dispatch, full bidirectional discovery over real WebSocket connections, Hub ownership and source authentication.


## Durable connector delivery

Persist and validate the complete received Envelope before calling
`send_delivery_ack(original_sender, envelope.id)`. This sends authenticated
`system.notify` with `event=VILLAGE_DELIVERY_ACK` and
`msg={envelope_id: <transport UUID>}`. An Environment overrides
`on_delivery_ack(sender, envelope_id)` to check its recorded expected receiver
and remove that delivery from its durable queue. Sending over WebSocket alone
does not prove durable reception. The SDK does not invent a connector database;
applications own persistence, original-envelope replay, and retry order.

Application callbacks are deduplicated only after successful completion. If an
Outcome or Event callback fails before durable storage, replaying the same
immutable logical ID invokes it again. Explicit Action replay still reaches the
Environment ledger so it can return its saved original Outcomes.
The default `EnvironmentClient.on_action` rejects missing business handlers and
replays that original rejection from memory on retry. Subclasses overriding
`on_action` must implement their own execution/replay ledger; the SDK deliberately
does not skip that callback based on its in-memory result history. Persist writes
and original results atomically before sending them, including intermediate
Outcomes for asynchronous actions. The complete demo supplies a persistent application ledger and preserves original
results for its local demonstration operations; see `examples/README.md`.
