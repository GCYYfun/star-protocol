"""A small durable Environment using the negotiated compact protocol.

The SDK checks wire contracts. This application owns world transitions,
immutable Action results, admission, delivery persistence and cancellation.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from star_protocol import EnvironmentClient
from star_protocol.client.compact import ProtocolConflictError
from star_protocol.models import Envelope, gen_id
from star_protocol.models.payloads import (
    COMPACT_PROTOCOL,
    TERMINAL_STATUSES,
    validate_compact_content,
    validate_schema_instance,
)

from .contracts import load_specification
from .registration import handler_dispatch, summarize_registration


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class DemoEnvironment(EnvironmentClient):
    """A light, calculator and continuous wait with restart-safe results.

    ``emit`` is an optional synchronous callback taking one record dictionary.
    Durable state belongs to this demo application, rather than to the SDK.
    """

    def __init__(
        self,
        client_id: str = "demo_env",
        *,
        state_dir: Path,
        emit: Callable[[dict], None] | None = None,
    ) -> None:
        super().__init__(client_id, auto_reconnect=False)
        self._emit = emit
        self.errors: list[dict] = []
        self.activity_states: dict[str, str] = {}
        self.speeches: list[dict] = []
        self._workers: dict[tuple[str, str], asyncio.Task] = {}
        self._closing = False
        self._readiness = asyncio.Condition()
        self._closed = False
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = state_dir / "environment.sqlite3"
        self._db = sqlite3.connect(self.database_path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS actions (
                sender TEXT NOT NULL, id TEXT NOT NULL, content TEXT NOT NULL,
                PRIMARY KEY(sender,id));
            CREATE TABLE IF NOT EXISTS outcomes (
                sender TEXT NOT NULL, action_id TEXT NOT NULL,
                position INTEGER NOT NULL, content TEXT NOT NULL,
                PRIMARY KEY(sender,action_id,position));
            CREATE TABLE IF NOT EXISTS events (
                sender TEXT NOT NULL, id TEXT NOT NULL, content TEXT NOT NULL,
                PRIMARY KEY(sender,id));
            CREATE TABLE IF NOT EXISTS inbox (
                id TEXT PRIMARY KEY, envelope TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, recipient TEXT NOT NULL, envelope TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS world (
                key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO world VALUES('light_on','false');
            INSERT OR IGNORE INTO world VALUES('light_write_count','0');
            INSERT OR IGNORE INTO world VALUES('ack_count','0');
        """)
        specification = load_specification("environment")
        self.configure_capabilities(
            tools=specification["tools"],
            events=specification["events"],
            runtime_handlers={"activity.state": self._activity_state},
        )
        self._hydrate()

    def configure_capabilities(self, *, tools=None, events=None, runtime_handlers=None) -> None:
        super().configure_capabilities(tools=tools, events=events,
                                       runtime_handlers=runtime_handlers)
        if self._emit:
            self._emit(summarize_registration(self, self._own_specification,
                                              self._runtime_handlers))

    def _notice(self, event: str, **details: Any) -> None:
        if self._emit:
            self._emit({"component": self.client_id, "event": event, **details})

    def _dispatch(self, sender: str, payload_type: str, content: dict,
                  handler: Callable, route: str, **details: Any) -> None:
        if self._emit:
            self._emit(handler_dispatch(self, sender, payload_type, content,
                                        handler, route, **details))

    def _read(self, sql: str, parameters: tuple = ()) -> list[tuple]:
        if not self._closed:
            return self._db.execute(sql, parameters).fetchall()
        with sqlite3.connect(self.database_path) as connection:
            return connection.execute(sql, parameters).fetchall()

    def _world(self, key: str) -> Any:
        return json.loads(self._read("SELECT value FROM world WHERE key=?", (key,))[0][0])

    @property
    def light_on(self) -> bool:
        return self._world("light_on")

    @property
    def light_write_count(self) -> int:
        return self._world("light_write_count")

    @property
    def outbox_count(self) -> int:
        return self._read("SELECT COUNT(*) FROM outbox")[0][0]

    @property
    def ack_count(self) -> int:
        return self._world("ack_count")

    def original_action(self, sender: str, action_id: str) -> dict | None:
        rows = self._read("SELECT content FROM actions WHERE sender=? AND id=?", (sender, action_id))
        return json.loads(rows[0][0]) if rows else None

    def stored_outcomes(self, sender: str, action_id: str) -> list[dict]:
        return [json.loads(row[0]) for row in self._read(
            "SELECT content FROM outcomes WHERE sender=? AND action_id=? ORDER BY position",
            (sender, action_id),
        )]

    def _hydrate(self) -> None:
        for sender, raw in self._read("SELECT sender,content FROM actions ORDER BY rowid"):
            content = json.loads(raw)
            self.restore_received_action(sender, content)
            for result in self.stored_outcomes(sender, content["id"]):
                self._remember_content("outcome", result)
                self._record_outcome(self._action_records[content["id"]], result)
        for sender, raw in self._read("SELECT sender,content FROM events ORDER BY rowid"):
            content = json.loads(raw)
            self._remember_content("event", content)
            self._delivered_events.add(content["id"])
            if content["name"] == "activity.state":
                self.activity_states[sender] = content["data"]["state"]
            elif content["name"] == "speech":
                self.speeches.append({"sender": sender, "content": content})

    async def ready(self, peer: str, timeout: float = 5) -> None:
        async def admitted() -> None:
            async with self._readiness:
                await self._readiness.wait_for(
                    lambda: self.protocol_for(peer) == COMPACT_PROTOCOL
                    and self.member_role(peer) in {"agent", "human"}
                )
        await asyncio.wait_for(admitted(), timeout)

    async def on_specification(self, sender: str, content: dict) -> None:
        async with self._readiness:
            self._readiness.notify_all()
        self._notice("specification", sender=sender, content=content)

    async def on_client_joined(self, client_id: str) -> None:
        async with self._readiness:
            self._readiness.notify_all()
        self._notice("client_joined", client_id=client_id, role=self.member_role(client_id))

    async def on_client_left(self, client_id: str, reason: str = "leave") -> None:
        async with self._readiness:
            self._readiness.notify_all()
        self._notice("client_left", client_id=client_id, reason=reason)

    async def on_error(self, error: dict) -> None:
        self.errors.append(copy.deepcopy(error))
        self._notice("error", content=error)

    def _remember_envelope(self, table: str, envelope: Envelope) -> None:
        # Table is selected only by this application, never from wire input.
        raw = _json(envelope.model_dump())
        previous = self._db.execute(f"SELECT envelope FROM {table} WHERE id=?", (envelope.id,)).fetchone()
        if previous and previous[0] != raw:
            raise ProtocolConflictError("Envelope UUID was reused with different bytes")
        if table == "outbox":
            self._db.execute("INSERT OR IGNORE INTO outbox VALUES(?,?,?)", (envelope.id, envelope.recipient, raw))
        else:
            self._db.execute("INSERT OR IGNORE INTO inbox VALUES(?,?)", (envelope.id, raw))

    async def send(self, envelope: Envelope) -> None:
        durable = envelope.type == "message" and envelope.payload.type in {"event", "outcome"}
        if not durable:
            self._compact_before_send(envelope)
            self._notice("wire.send.start", presentation=True, envelope=envelope.model_dump())
            await self._messaging.send_envelope(envelope)
            self._notice("wire.send", envelope=envelope.model_dump())
            if self._monitorable:
                await self._on_message_sent(envelope)
            return
        self._compact_before_send(envelope)
        with self._db:
            self._remember_envelope("outbox", envelope)
        self._notice("wire.stored", storage="outbox", envelope=envelope.model_dump())
        self._notice("wire.send.start", presentation=True, envelope=envelope.model_dump())
        # Failed delivery leaves the exact original Envelope in the outbox.
        await self._messaging.send_envelope(envelope)
        self._notice("send", recipient=envelope.recipient, envelope=envelope.model_dump())

    def pending_deliveries(self, peer: str) -> list[dict]:
        """Read exact pending wire Envelopes in their original delivery order."""
        return [json.loads(row[0]) for row in self._read(
            "SELECT envelope FROM outbox WHERE recipient=? ORDER BY rowid", (peer,)
        )]

    async def replay_pending(self, peer: str) -> None:
        await self.ready(peer)
        for row in self._read("SELECT envelope FROM outbox WHERE recipient=? ORDER BY rowid", (peer,)):
            envelope = Envelope.model_validate_json(row[0])
            self._compact_before_send(envelope)
            self._notice("wire.send.start", presentation=True, replay=True,
                         envelope=envelope.model_dump())
            await self._messaging.send_envelope(envelope)
            self._notice("delivery_replay", recipient=peer, envelope=envelope.model_dump())

    async def on_delivery_ack(self, sender: str, envelope_id: str) -> None:
        row = self._db.execute("SELECT recipient FROM outbox WHERE id=?", (envelope_id,)).fetchone()
        if row is None:
            return  # An already-applied ACK is idempotent.
        if row[0] != sender:
            await self.on_error({"code": 403, "msg": "Delivery ACK came from an unexpected receiver"})
            return
        with self._db:
            self._db.execute("DELETE FROM outbox WHERE id=?", (envelope_id,))
            self._db.execute("UPDATE world SET value=CAST(value AS INTEGER)+1 WHERE key='ack_count'")
        self._notice("delivery_ack", sender=sender, envelope_id=envelope_id)

    async def _handle_system(self, envelope: Envelope) -> None:
        self._notice("wire.receive", parsed=True, envelope=envelope.model_dump())
        await super()._handle_system(envelope)
        self._notice("wire.handled", envelope=envelope.model_dump())

    async def _handle_message(self, envelope: Envelope) -> None:
        if self._closing:
            return
        # Arrival is observed before automatic capability replies or business
        # callbacks; it does not yet promise acceptance or persistence.
        self._notice("wire.receive", parsed=True, envelope=envelope.model_dump())
        if envelope.payload.type in {"discover", "specification", "stream"}:
            await super()._handle_message(envelope)
            self._notice("wire.handled", envelope=envelope.model_dump())
            return
        try:
            self._require_peer(envelope.sender)
            if self.member_role(envelope.sender) not in {"agent", "human"}:
                raise PermissionError("The sender is not an admitted Agent or Human")
            declared = self._sent_peer_specifications[envelope.sender]
            validate_compact_content(envelope.payload.type, envelope.payload.content, declared["events"])
            if envelope.payload.type == "action":
                tool = next((item for item in declared["tools"] if item["name"] == envelope.payload.content["name"]), None)
                if tool is None:
                    raise ValueError("The requested tool is not declared")
                validate_schema_instance(tool["parameters"], envelope.payload.content["params"])
            with self._db:
                self._remember_envelope("inbox", envelope)
            self._notice("wire.stored", storage="inbox", envelope=envelope.model_dump())
            await super()._handle_message(envelope)
            self._notice("wire.handled", envelope=envelope.model_dump())
            # Hub ACK routing is member -> Environment. Receiving this Action
            # durably does not require an unsupported reverse-direction ACK.
        except Exception as exc:
            await self.on_error({"code": 400, "msg": str(exc)})
            raise

    def _store_event(self, sender: str, content: dict) -> None:
        raw = _json(content)
        previous = self._db.execute("SELECT content FROM events WHERE sender=? AND id=?", (sender, content["id"])).fetchone()
        if previous and previous[0] != raw:
            raise ProtocolConflictError("Event ID was reused with different Content")
        with self._db:
            self._db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?)", (sender, content["id"], raw))

    async def _activity_state(self, sender: str, content: dict) -> None:
        self._store_event(sender, content)
        self._dispatch(sender, "event", content, self._activity_state, "runtime")
        self.activity_states[sender] = content["data"]["state"]
        self._notice("runtime_event", sender=sender, content=content)

    async def on_event(self, sender: str, content: dict) -> None:
        self._store_event(sender, content)
        self._dispatch(sender, "event", content, self.on_event, "model")
        self.speeches.append({"sender": sender, "content": copy.deepcopy(content)})
        self._notice("model_event", sender=sender, content=content)

    def _append_result(self, sender: str, action_id: str, status: str, text: str) -> dict:
        # Caller holds the transaction containing any related world transition.
        existing = self.stored_outcomes(sender, action_id)
        if any(item["status"] in TERMINAL_STATUSES for item in existing):
            raise ProtocolConflictError("The durable Action already has a terminal result")
        result = {"id": gen_id("outcome"), "refs": [action_id], "status": status, "data": {"text": text}}
        self._db.execute("INSERT INTO outcomes VALUES(?,?,?,?)", (sender, action_id, len(existing), _json(result)))
        return result

    async def _replay_results(self, sender: str, action_id: str) -> None:
        for result in self.stored_outcomes(sender, action_id):
            await self.send_outcome(sender, result)

    async def on_action(self, sender: str, content: dict) -> None:
        action_id, name, params = content["id"], content["name"], content["params"]
        existing = self.original_action(sender, action_id)
        if existing is not None:
            if existing != content:
                raise ProtocolConflictError("Action ID was reused with different Content")
            self._dispatch(sender, "action", content, self.on_action, "tool",
                           dispatch_mode="ledger_replay")
            self._notice("action_replay", sender=sender, content=content)
            await self._replay_results(sender, action_id)
            return
        self._dispatch(sender, "action", content, self.on_action, "tool",
                       dispatch_mode="new")
        self._notice("action", sender=sender, content=content)
        original_wait_result: tuple[str, dict] | None = None
        historical_id: str | None = None
        with self._db:
            self._db.execute("INSERT INTO actions VALUES(?,?,?)", (sender, action_id, _json(content)))
            if name == "set_light":
                if self.member_role(sender) != "agent":
                    result = self._append_result(sender, action_id, "rejected", "Human 无权直接修改灯光；动作未执行，请让 Agent 决策并调用。")
                else:
                    self._db.execute("UPDATE world SET value=? WHERE key='light_on'", (_json(params["on"]),))
                    self._db.execute("UPDATE world SET value=CAST(value AS INTEGER)+1 WHERE key='light_write_count'")
                    result = self._append_result(sender, action_id, "completed", f"灯光已{'打开' if params['on'] else '关闭'}。世界修改和本次最终结果已在同一事务中保存。")
            elif name == "observe":
                result = self._append_result(sender, action_id, "completed", f"你在一个安静的房间里；灯光当前{'亮着' if self.light_on else '关闭'}，桌上有计算器。可以调用 set_light、calculate 或 wait。")
            elif name == "calculate":
                a, b, operation = params["a"], params["b"], params["operation"]
                if operation == "div" and b == 0:
                    result = self._append_result(sender, action_id, "failed", "计算失败：除数不能为零。没有修改环境；你可以更改参数或选择其他动作。")
                else:
                    value = {"add": lambda: a + b, "sub": lambda: a - b, "mul": lambda: a * b, "div": lambda: a / b}[operation]()
                    result = self._append_result(sender, action_id, "completed", f"{a} {operation} {b} 的结果是 {value}。")
            elif name == "wait":
                result = self._append_result(sender, action_id, "accepted", f"已接受持续动作，将等待 {params['seconds']} 秒；当前尚无最终结果。")
            elif name == "cancel":
                target_id = params["action_id"]
                target = self.original_action(sender, target_id)
                results = self.stored_outcomes(sender, target_id)
                if target is None or target["name"] != "wait":
                    result = self._append_result(sender, action_id, "rejected", "没有找到属于你的可取消 wait 动作；未取消任何动作。")
                elif any(item["status"] in TERMINAL_STATUSES for item in results):
                    result = self._append_result(sender, action_id, "rejected", "这个 wait 动作已经有最终结果，不能再次取消。")
                else:
                    cancelled = self._append_result(sender, target_id, "cancelled", "持续动作已按调用者的取消请求终止。")
                    original_wait_result = (target_id, cancelled)
                    result = self._append_result(sender, action_id, "completed", "你的取消请求已完成；原 wait 动作已返回 cancelled 最终结果。")
            elif name == "get_operation_result":
                target_id = params["action_id"]
                target = self.original_action(sender, target_id)
                if target is None:
                    result = self._append_result(sender, action_id, "rejected", "没有找到属于你的原动作；不提供其他调用者的记录。")
                else:
                    historical_id = target_id
                    results = self.stored_outcomes(sender, target_id)
                    status = results[-1]["status"] if results else "unconfirmed"
                    result = self._append_result(sender, action_id, "completed", f"已查询你的原动作 {target_id}，最后持久状态为 {status}。原 Outcome 将按原 ID 重放；查询本身不是原动作完成的证据。")
            else:
                result = self._append_result(sender, action_id, "rejected", "没有可执行的业务处理器，动作未执行。")
        if original_wait_result:
            target_id, cancelled = original_wait_result
            worker = self._workers.pop((sender, target_id), None)
            if worker:
                worker.cancel()
            await self.send_outcome(sender, cancelled)
        if historical_id:
            await self._replay_results(sender, historical_id)
        if name == "wait":
            self._workers[(sender, action_id)] = asyncio.create_task(self._wait(sender, action_id, params["seconds"]))
        await self.send_outcome(sender, result)

    async def _wait(self, sender: str, action_id: str, seconds: float) -> None:
        try:
            # Yield without holding the receive loop, so cancellation can arrive.
            await asyncio.sleep(0.01)
            with self._db:
                if any(item["status"] in TERMINAL_STATUSES for item in self.stored_outcomes(sender, action_id)):
                    return
                running = self._append_result(sender, action_id, "running", "持续动作正在等待；你可以继续观测、聊天或发送 cancel。")
            await self.send_outcome(sender, running)
            await asyncio.sleep(seconds)
            with self._db:
                if any(item["status"] in TERMINAL_STATUSES for item in self.stored_outcomes(sender, action_id)):
                    return
                completed = self._append_result(sender, action_id, "completed", f"等待 {seconds} 秒已经结束。")
            await self.send_outcome(sender, completed)
        except asyncio.CancelledError:
            # A stop leaves unfinished work unconfirmed. Only explicit cancel
            # commits a cancelled result; shutdown never invents completion.
            pass
        except Exception as exc:
            if not self._closing:
                await self.on_error({"code": 500, "msg": str(exc)})
        finally:
            self._workers.pop((sender, action_id), None)

    async def stop(self) -> None:
        if self._closed:
            return
        self._closing = True
        workers = list(self._workers.values())
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        await super().stop()
        self._db.close()
        self._closed = True
