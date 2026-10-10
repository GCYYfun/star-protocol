"""Rich presentation of protocol hierarchy and explicit reference relationships.

This is a display projection. It never changes a packet or infers business
success, causality or delivery confirmation from natural-language text.
"""

from __future__ import annotations

from collections import OrderedDict
import asyncio
from copy import deepcopy
import json
from threading import RLock
import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree


STATUS_STYLE = {"accepted": "cyan", "running": "yellow", "completed": "green",
                "rejected": "red", "failed": "bold red", "cancelled": "magenta"}
KIND_PREFIX = {"action": "A", "outcome": "O", "event": "E", "delivery": "D", "stream": "S"}
ACTOR_ROLE = {"demo_env": "Environment", "environment": "Environment", "demo_agent": "Agent",
              "demo_colleague": "Agent", "demo_human": "Human", "monitor": "Monitor", "hub": "Hub", "demo": "演示编排"}
CONTENT_EVENTS = {"action": "action", "outcome": "outcome", "model.event": "event",
                  "runtime.event": "event", "model_event": "event", "runtime_event": "event"}


def json_tree(label, value):
    """Treeify a JSON value without interpreting user strings as Rich markup."""
    tree = Tree(Text(str(label), style="bold"), guide_style="dim")

    def populate(parent, data):
        if isinstance(data, dict):
            for key, item in data.items():
                if isinstance(item, (dict, list)):
                    branch = parent.add(Text(f"{key} · {'object' if isinstance(item, dict) else 'array'}", style="cyan"))
                    populate(branch, item)
                else:
                    line = Text(f"{key}: ", style="cyan")
                    line.append(json.dumps(item, ensure_ascii=False), style="white")
                    parent.add(line)
            if not data:
                parent.add(Text("{}", style="dim"))
        elif isinstance(data, list):
            for index, item in enumerate(data):
                if isinstance(item, (dict, list)):
                    branch = parent.add(Text(f"[{index}]", style="cyan"))
                    populate(branch, item)
                else:
                    parent.add(Text(f"[{index}]: {json.dumps(item, ensure_ascii=False)}"))
            if not data:
                parent.add(Text("[]", style="dim"))
        else:
            parent.add(Text(json.dumps(data, ensure_ascii=False)))
    populate(tree, value)
    return tree


class ProtocolDisplay:
    """Live process first, followed by the complete causal tree on completion.

    Presentation-only flow records describe the demo, never protocol business
    status. IDs retain stable aliases; full packets remain in trace trees and
    transcript.jsonl. refs[0] is only a visual attachment, not a new rule.
    """

    def __init__(self, *, trace=False, console=None, title="Star Protocol", live=False):
        self._lock = RLock()
        self.trace = trace
        self.console = console or Console()
        self.title = title
        self.live = live
        self.messages = OrderedDict()
        self.deliveries = OrderedDict()
        self.specifications = OrderedDict()
        self.registrations = OrderedDict()
        self.handler_observations = OrderedDict()
        self._negotiation_seen = set()
        self._specification_inbound = {}
        self._specification_callbacks = {}
        self._specification_callback_count = 0
        self._last_dispatch = None
        self.checks = []
        self.telemetry = OrderedDict()
        self.streams = OrderedDict()
        self._aliases = {}
        self._counts = {}
        self._live = None
        self._started = False
        self._finished = False
        self._callback_seen = set()
        self._last_check = None
        self.summary = None
        self.phases = OrderedDict()
        self.timeline = []
        self._record_counter = 0
        self._current_phase = None
        self._started_at = time.monotonic()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_value is not None and not isinstance(exc_value, (asyncio.CancelledError, KeyboardInterrupt)):
            self.message(f"演示中断：{exc_value}", style="bold red")
        self.finish()
        return False

    def start(self):
        if self._started:
            return
        self._started = True
        if self.live and self.console.is_terminal:
            self._live = Live(self.build_live_tree(), console=self.console, refresh_per_second=4,
                              vertical_overflow="ellipsis", transient=True)
            self._live.start()
        elif self.live:
            self.console.print(Panel(Text("正在运行真实 Hub 演示；按观察序号展示双方收发与处理，结束时分别显示完整时间轴和因果关系树。"), title=Text(self.title)))

    def message(self, text, style=None):
        self.console.print(text if isinstance(text, Text) else Text(str(text), style=style or ""))

    def json(self, value, title=None):
        self.console.print(json_tree(title or "数据", value))

    def alias(self, kind, identifier):
        key = (kind, identifier)
        if key not in self._aliases:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            self._aliases[key] = f"{KIND_PREFIX.get(kind, 'R')}{self._counts[kind]:02d}"
        return self._aliases[key]

    def _actor(self, identifier):
        registration = self.registrations.get(identifier)
        role = {"agent": "Agent", "environment": "Environment", "human": "Human"}.get(registration.get("role")) if registration else ACTOR_ROLE.get(identifier)
        return f"{role} {identifier}" if role and role != identifier else str(identifier)

    def _snapshot(self, owner, content):
        self.specifications[owner] = content

    def _content(self, kind, content, sender, recipient, delivery=None):
        identifier = content.get("id")
        if not identifier:
            return
        self.alias(kind, identifier)
        node = self.messages.setdefault(identifier, {"kind": kind, "content": content,
                                                     "sender": sender, "recipients": [], "deliveries": [], "handlers": []})
        if recipient and recipient not in node["recipients"]:
            node["recipients"].append(recipient)
        if delivery and delivery not in node["deliveries"]:
            node["deliveries"].append(delivery)
        if kind == "outcome":
            for ref in content.get("refs", []):
                self.alias("action", ref)

    def emit(self, record):
        # Live refreshes on another thread. Input packets are copied and each
        # generated renderable is a detached snapshot, never a mutable mapping.
        with self._lock:
            self._emit(deepcopy(record))

    def _emit(self, record):
        self._record_counter += 1
        record["_source_seq"] = record.get("seq")
        record.setdefault("seq", self._record_counter)
        name = record.get("event", "")
        if name.startswith("flow."):
            self._observe_timeline(record)
            self._flow(record)
            if self._live:
                self._live.update(self.build_live_tree())
            return
        if name == "capability.registered":
            self._observe_timeline(record)
            self._registration(record)
            if self._live:
                self._live.update(self.build_live_tree())
            return
        if name == "handler.dispatch":
            if not self._handler_dispatch(record):
                return
            self._observe_timeline(record)
            self._stage_message(record)
            if self._live:
                self._live.update(self.build_live_tree())
            return
        envelope = record.get("envelope")
        if envelope:
            identifier = envelope["id"]
            payload = envelope["payload"]
            kind, content = payload["type"], payload["content"]
            item = self.deliveries.setdefault(identifier, {"envelope": envelope, "receive_count": 0, "receivers": {},
                                                          "replay_count": 0, "ack_sent": False, "ack": False})
            self.alias("delivery", identifier)
            if name == "wire.receive":
                item["receive_count"] += 1
                receiver = record.get("component", envelope["recipient"])
                item["receivers"][receiver] = item["receivers"].get(receiver, 0) + 1
            if name == "delivery_replay":
                item["replay_count"] += 1
            if kind in {"action", "outcome", "event"}:
                self._content(kind, content, envelope["sender"], envelope["recipient"], identifier)
            elif kind == "specification" and name != "wire.receive":
                # A parsed inbound packet is not an installed declaration.
                self._snapshot(envelope["sender"], content)
            elif kind == "stream":
                stream_id = content.get("id", identifier)
                self.alias("stream", stream_id)
                stream = self.streams.setdefault(stream_id, {"sender": envelope["sender"], "recipient": envelope["recipient"], "chunks": OrderedDict()})
                stream["chunks"][content.get("sequence", len(stream["chunks"]))] = content
            if kind == "notify" and content.get("event") == "VILLAGE_DELIVERY_ACK" and name in {"wire.send", "send", "delivery_replay"}:
                target = content.get("msg", {}).get("envelope_id")
                if target in self.deliveries:
                    self.deliveries[target]["ack_sent"] = True
        elif name == "specification":
            self._snapshot(record["sender"], record["content"])
        elif name in CONTENT_EVENTS:
            content = record["content"]
            kind = CONTENT_EVENTS[name]
            sender = record.get("sender", record.get("component", "?"))
            recipient = record.get("component")
            if recipient == "environment":
                recipient = "demo_env"
            self._content(kind, content, sender, recipient)
            if kind == "event":
                route = "runtime" if "runtime" in name else "model"
                node = self.messages[content["id"]]
                handler = f"{route} → {recipient or '?'}"
                if handler not in node["handlers"]:
                    node["handlers"].append(handler)
        elif name == "delivery_ack":
            target = record.get("envelope_id")
            if target in self.deliveries:
                self.deliveries[target]["ack"] = True
        elif name == "check":
            self.checks.append(record)
            self._last_check = record["name"]
        elif name.startswith("monitor."):
            source = record.get("source", "monitor")
            telemetry_name = record.get("name", name)
            key = (source, telemetry_name)
            self.telemetry[key] = record.get("data", {})
        elif name == "error":
            self.json(record.get("content"), title="协议处理错误")

        self._observe_timeline(record)
        if envelope and envelope["payload"]["type"] == "discover" and name in {"wire.send", "wire.receive", "send"}:
            self._show_discover(record, envelope)
        elif envelope and envelope["payload"]["type"] == "specification" and name in {"wire.send", "wire.receive", "send"}:
            self._show_specification(record, envelope=envelope)
        elif name == "specification":
            self._show_specification(record)
        self._stage_message(record)
        if self._live:
            self._live.update(self.build_live_tree())
        elif not self.live and not record.get("stage_id") and name != "specification":
            self._interactive(record)

    @staticmethod
    def _fingerprint(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _method_name(self, value):
        value = str(value)
        return value if self.trace else ".".join(value.split(".")[-2:])

    @staticmethod
    def _normal_actor(identifier):
        return "demo_env" if identifier == "environment" else identifier

    def _schema_fields(self, parent, schema):
        """Readable local Schema constraints without expanding all $defs."""
        def resolve(node):
            node = dict(node)
            visited = set()
            for _ in range(8):
                ref = node.get("$ref")
                if not ref or ref in visited or not ref.startswith("#/"):
                    break
                visited.add(ref)
                target = schema
                try:
                    for segment in ref[2:].split("/"):
                        target = target[segment.replace("~1", "/").replace("~0", "~")]
                except (KeyError, TypeError):
                    break
                node = {**target, **{key: value for key, value in node.items() if key != "$ref"}}
            return node

        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if not properties:
            parent.add(Text("无参数字段" if schema.get("type") == "object" else "类型: " + str(schema.get("type", "未约束")), style="dim"))
        for name, raw in properties.items():
            field = resolve(raw)
            type_name = field.get("type", " / ".join(str(resolve(item).get("type", "分支")) for item in field.get("oneOf", field.get("anyOf", []))) or "未约束")
            text = f"{name}: {type_name} · {'必填' if name in required else '可选'}"
            if "enum" in field:
                text += " · enum=" + json.dumps(field["enum"], ensure_ascii=False)
            elif "const" in field:
                text += " · const=" + json.dumps(field["const"], ensure_ascii=False)
            bounds = [f"{key}={field[key]}" for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems", "format") if key in field]
            if bounds:
                text += " · " + ", ".join(bounds)
            parent.add(Text(text, style="dim"))
        parent.add(Text("additionalProperties=" + json.dumps(schema.get("additionalProperties", True)), style="dim"))

    def _registration(self, record):
        actor = self._normal_actor(record["component"])
        fingerprint = self._fingerprint({"specification": record["specification"], "bindings": record.get("bindings", {})})
        previous = self.registrations.get(actor)
        if previous and previous["fingerprint"] == fingerprint:
            previous["observations"] += 1
            self.console.print(Text(f"本地重新注册 · {self._actor(actor)} · 同内容，沿用已展示的工具 / Event 绑定。", style="dim"))
            return
        self.registrations[actor] = {**record, "fingerprint": fingerprint, "observations": 1}
        tree = Tree(Text(f"本地注册成功 · {self._actor(actor)}", style="bold green"))
        self._capabilities(tree, record["specification"], bindings=record.get("bindings", {}))
        self._framework_receivers(tree, record.get("role"))
        self.console.print(tree)

    @staticmethod
    def _framework_receivers(parent, role):
        if role in {"agent", "human"}:
            parent.add(Text("框架 Outcome 接收 → on_outcome · 按 refs 找原 Action；不属于 Tool / Event 注册。", style="dim"))

    def _show_discover(self, record, envelope):
        direction = "收到" if record.get("event") == "wire.receive" else "发送完成"
        key = ("discover", envelope["id"], direction)
        if key in self._negotiation_seen:
            return
        self._negotiation_seen.add(key)
        tree = Tree(Text(f"实际协商 · {self._actor(envelope['sender'])} → {self._actor(envelope['recipient'])} · {direction} discover", style="cyan"))
        if record.get("event") == "wire.receive":
            tree.add(Text("报文已解包；接收端尚需执行协议校验和响应。", style="dim"))
        tree.add(Text("请求对方接收能力 · protocols=" + json.dumps(envelope["payload"]["content"].get("protocols", [])), style="dim"))
        self.console.print(tree)

    def _show_specification(self, record, *, envelope=None):
        if envelope:
            sender = envelope["sender"]
            receiver = self._normal_actor(record.get("component", envelope["recipient"]))
            specification = envelope["payload"]["content"]
            if record.get("event") != "wire.receive":
                key = ("specification", envelope["id"], "发送")
                if key not in self._negotiation_seen:
                    self._negotiation_seen.add(key)
                    tree = Tree(Text(f"实际协商 · {self._actor(sender)} → {self._actor(envelope['recipient'])} · 发送完成 specification", style="cyan"))
                    tree.add(Text(f"声明本端接收能力：{len(specification.get('tools', []))} tools / {len(specification.get('events', []))} events", style="dim"))
                    self.console.print(tree)
                return
            key = ("specification", sender, receiver, envelope["id"])
            if key in self._negotiation_seen:
                return
            self._negotiation_seen.add(key)
            fingerprint = self._fingerprint(specification)
            edge = (sender, receiver)
            callbacks = self._specification_callbacks.setdefault(edge, [])
            paired = next((item for item in callbacks if item["fingerprint"] == fingerprint), None)
            if paired is not None:
                # Legacy observation points may follow the installation callback.
                # Pair identity only; never move an observation in the timeline.
                callbacks.remove(paired)
            else:
                self._specification_inbound.setdefault(edge, []).append({"fingerprint": fingerprint, "id": envelope["id"]})
            tree = Tree(Text(f"实际收到 specification · {self._actor(sender)} → {self._actor(receiver)}", style="cyan"))
            tree.add(Text("仅表示报文解包；安装结果见独立的 specification 回调。", style="dim"))
            self.console.print(tree)
            return

        sender, receiver = record["sender"], self._normal_actor(record.get("component", "?"))
        specification = record["content"]
        fingerprint = self._fingerprint(specification)
        edge = (sender, receiver)
        inbound = self._specification_inbound.setdefault(edge, [])
        paired = next((item for item in inbound if item["fingerprint"] == fingerprint), None)
        if paired is not None:
            inbound.remove(paired)
        else:
            callbacks = self._specification_callbacks.setdefault(edge, [])
            if any(item["fingerprint"] == fingerprint for item in callbacks):
                return
            self._specification_callback_count += 1
            callbacks.append({"fingerprint": fingerprint, "id": self._specification_callback_count})
        tree = Tree(Text(f"已校验并安装接收声明 · {self._actor(receiver)} ← {self._actor(sender)}", style="bold cyan"))
        tree.add(Text(f"下列工具和 Event 由 {self._actor(sender)} 接收。", style="dim"))
        self._capabilities(tree, specification)
        tools = ", ".join(item["name"] for item in specification.get("tools", [])) or "无（对端 tools=0）"
        events = ", ".join(item["name"] + " [" + item["handler"] + "]" for item in specification.get("events", [])) or "无"
        tree.add(Text(f"调用格式：{self._actor(receiver)} → {self._actor(sender)} · tools: {tools}", style="blue"))
        tree.add(Text(f"发送格式：{self._actor(receiver)} → {self._actor(sender)} · events: {events}", style="cyan"))
        self.console.print(tree)

    def _handler_dispatch(self, record):
        content = record.get("content", {})
        identifier = content.get("id")
        kind = record.get("payload_type")
        if not identifier or kind not in {"action", "event", "outcome"}:
            return False
        receiver = self._normal_actor(record.get("component", "?"))
        observation = {**record, "receiver": receiver, "sender": self._normal_actor(record.get("sender", "?"))}
        records = self.handler_observations.setdefault(identifier, [])
        mode = record.get("dispatch_mode", "new")
        identity = record["_source_seq"] if record.get("_source_seq") is not None else (record.get("elapsed"), record.get("stage_id"))
        key = (receiver, record.get("route"), record.get("handler"), mode, identity)
        if mode != "ledger_replay" and any((item["receiver"], item.get("route"), item.get("handler"), item.get("dispatch_mode", "new"),
                                          item["_source_seq"] if item.get("_source_seq") is not None else (item.get("elapsed"), item.get("stage_id"))) == key for item in records):
            return False
        records.append(observation)
        self._last_dispatch = observation
        self._callback_seen.add((kind, identifier, receiver))
        if receiver == "demo_env":
            self._callback_seen.add((kind, identifier, "environment"))
        if not self._live:
            self.console.print(self._dispatch_tree(observation))
        return True

    def _dispatch_tree(self, observation, *, compact=False):
        content = observation["content"]
        kind, identifier = observation["payload_type"], content["id"]
        title = Text(f"实际处理 · {self._actor(observation['sender'])} → {self._actor(observation['receiver'])} · ", style="bold")
        title.append(self.alias(kind, identifier) + " " + kind, style="cyan")
        tree = Tree(title, guide_style="dim")
        route, handler = observation.get("route", "?"), self._method_name(observation.get("handler", "?"))
        text = f"{route} → {handler}"
        if kind == "action":
            if observation.get("dispatch_mode") == "ledger_replay":
                text += " · 读取原 Action 账本，重放既有 Outcome；未执行世界分支。"
            else:
                text += " · 分支 " + content.get("name", "?")
            tree.add(Text(text, style="blue"))
            tree.add(json_tree("Action.params", content.get("params", {})))
        else:
            tree.add(Text(text, style="magenta" if route == "runtime" else "cyan"))
            if kind == "outcome":
                status = content.get("status", "?")
                tree.add(Text("Outcome.status: " + status, style=STATUS_STYLE.get(status, "white")))
                refs = content.get("refs", [])
                tree.add(Text("refs → " + ", ".join(self.alias("action", ref) for ref in refs), style="dim"))
            else:
                tree.add(Text("Event.name: " + content.get("name", "?"), style="cyan"))
                refs = content.get("refs", [])
                if refs:
                    tree.add(Text("refs → " + ", ".join(self.alias("event", ref) for ref in refs), style="dim"))
            data = content.get("data", {})
            body = data.get("text", "")
            if body:
                visible = body[:180] + "…（完整原文见最终协议树）" if compact and len(body) > 180 else body
                tree.add(Text("data.text: " + visible))
            controls = {key: value for key, value in data.items() if key != "text"}
            if controls:
                tree.add(json_tree("data · 已声明的业务字段", controls))
        return tree

    def _elapsed(self, record=None):
        value = (record or {}).get("elapsed")
        return float(value) if isinstance(value, (int, float)) else time.monotonic() - self._started_at

    @staticmethod
    def _stamp(seconds):
        return f"T+{max(0.0, seconds):06.2f}s"

    def _observe_timeline(self, record):
        """Preserve observation order without modifying or inferring protocol state."""
        name = record.get("event", "")
        included = {"capability.registered", "handler.dispatch", "specification", "delivery_ack", "delivery_replay",
                    "wire.send.start", "wire.send", "send", "wire.receive", "wire.stored", "wire.handled"}
        if name not in included and not name.startswith("flow."):
            return
        item = {"seq": record["seq"], "elapsed": self._elapsed(record), "record": record}
        self.timeline.append(item)
        if not self._live:
            self.console.print(self._timeline_label(item))

    def _timeline_label(self, item):
        record = item["record"]
        name = record.get("event", "")
        label = Text(f"#{item['seq']:04d} · {self._stamp(item['elapsed'])} · ", style="dim")
        actor = self._normal_actor(record.get("actor", "demo") if name == "flow.step" else record.get("component", "demo"))
        envelope = record.get("envelope")
        if name == "flow.stage.start":
            label.append(f"演示阶段开始 · {record.get('title', record.get('stage_id', '?'))}", style="bold cyan")
        elif name == "flow.stage.end":
            label.append(f"演示阶段结束 · {record.get('stage_id', '?')} · {record.get('status', 'completed')}", style="green" if record.get("status", "completed") == "completed" else "red")
        elif name == "flow.step":
            label.append(f"{self._actor(actor)} · {record.get('operation', '演示说明')}")
            if record.get("wait_seconds"):
                label.append(f" · 停顿设置 {record['wait_seconds']:g} 秒", style="yellow")
        elif name == "flow.step.end":
            label.append(f"演示步骤 {record.get('step_number', '?')} · 停顿结束", style="dim")
        elif name == "capability.registered":
            specification = record.get("specification", {})
            label.append(f"{self._actor(actor)} · 本地注册成功 · {len(specification.get('tools', []))} tools / {len(specification.get('events', []))} events", style="green")
        elif name == "specification":
            specification = record.get("content", {})
            label.append(f"{self._actor(actor)} · 已校验并安装 {self._actor(record.get('sender', '?'))} 的接收声明 · {len(specification.get('tools', []))} tools / {len(specification.get('events', []))} events", style="cyan")
        elif name == "handler.dispatch":
            content = record.get("content", {})
            kind = record.get("payload_type", "?")
            logical = self.alias(kind, content.get("id", "?"))
            method = self._method_name(record.get("handler", "?"))
            label.append(f"{self._actor(actor)} · 进入 {method} · {logical} {kind}", style="cyan")
            if kind == "action":
                label.append(" · 读取原账本并重放 Outcome" if record.get("dispatch_mode") == "ledger_replay" else " · 工具 " + content.get("name", "?"))
            elif kind == "outcome":
                label.append(" · " + content.get("status", "?"), style=STATUS_STYLE.get(content.get("status"), "white"))
                label.append(" → " + ", ".join(self.alias("action", ref) for ref in content.get("refs", [])), style="dim")
            else:
                label.append(" · " + content.get("name", "?") + " · " + record.get("route", "?"))
        elif name == "delivery_ack":
            label.append(f"{self._actor(actor)} · 确认 ACK · {self.alias('delivery', record.get('envelope_id', '?'))}", style="magenta")
        elif envelope:
            kind, content = envelope["payload"]["type"], envelope["payload"]["content"]
            delivery = self.alias("delivery", envelope["id"])
            logical = self.alias(kind, content["id"]) + " " if kind in {"action", "outcome", "event", "stream"} and content.get("id") else ""
            subject = logical + kind
            if kind == "action":
                subject += " " + content.get("name", "?")
            elif kind == "outcome":
                subject += " " + content.get("status", "?") + " → " + ", ".join(self.alias("action", ref) for ref in content.get("refs", []))
            elif kind == "event":
                subject += " " + content.get("name", "?")
                if content.get("refs"):
                    subject += " · refs → " + ", ".join(self.alias("event", ref) for ref in content["refs"])
            elif kind == "notify":
                subject += " " + str(content.get("event", "?"))
                if content.get("event") == "VILLAGE_DELIVERY_ACK":
                    target = content.get("msg", {}).get("envelope_id")
                    if target:
                        subject += " → " + self.alias("delivery", target)
            verb = {"wire.send.start": "开始发送", "wire.send": "发送完成", "send": "发送完成",
                    "wire.receive": "收到（已解包，待接收校验）", "wire.stored": "持久化完成",
                    "wire.handled": "接收处理完成", "delivery_replay": "补发完成（原 UUID）"}.get(name, name)
            if name == "wire.stored":
                verb += " " + str(record.get("storage", "原始报文"))
            if name == "wire.send.start" and record.get("replay"):
                verb += "（补发原 UUID）"
            incoming = name in {"wire.receive", "wire.handled"} or (name == "wire.stored" and actor != envelope["sender"])
            peer = envelope["sender"] if incoming else envelope["recipient"]
            direction = " ← " if incoming else " → "
            label.append(f"{self._actor(actor)} · {verb} · {subject} · {delivery}", style="magenta" if kind == "notify" else "cyan")
            label.append(direction + self._actor(peer), style="dim")
        else:
            label.append(f"{self._actor(actor)} · {name}")
        return label

    def _flow(self, record):
        name = record["event"]
        stage_id = record.get("stage_id")
        if not stage_id:
            return
        phase = self.phases.setdefault(stage_id, {
            "id": stage_id, "title": record.get("title", stage_id), "description": "",
            "number": record.get("stage_number", len(self.phases) + 1), "steps": [],
            "messages": OrderedDict(), "status": "running", "started": self._elapsed(record),
        })
        if name == "flow.stage.start":
            phase.update(title=record.get("title", stage_id), description=record.get("description", ""),
                         started=self._elapsed(record), status="running")
            self._current_phase = stage_id
            if not self._live:
                tree = Tree(self._phase_label(phase))
                if phase["description"]:
                    tree.add(Text(phase["description"]))
                tree.add(Text("演示讲解；阶段状态不代表任何 Action 的业务结果。", style="dim"))
                self.console.print(tree)
        elif name == "flow.step":
            phase["number"] = record.get("stage_number", phase["number"])
            record["paused"] = bool(record.get("wait_seconds", 0))
            phase["steps"].append(record)
            self._current_phase = stage_id
            if not self._live:
                tree = Tree(Text(f"阶段 {phase['number']:02d} · {phase['title']}", style="bold cyan"))
                self._add_step(tree, record)
                self.console.print(tree)
        elif name == "flow.step.end":
            number = record.get("step_number")
            step = next((item for item in reversed(phase["steps"]) if item.get("step_number") == number), None)
            if step is not None:
                step["paused"] = False
                step["wait_ended"] = self._elapsed(record)
                if not self._live and step.get("wait_seconds", 0):
                    tree = Tree(Text(f"阶段 {phase['number']:02d} · 步骤 {number}", style="dim"))
                    tree.add(Text(f"{self._stamp(step['wait_ended'])} · 模拟停顿已结束", style="dim"))
                    self.console.print(tree)
        elif name == "flow.stage.end":
            # Only the explicit runner phase status is displayed here. Text or
            # observed Outcomes cannot imply the success of a whole scenario.
            phase["status"] = record.get("status", "completed")
            phase["ended"] = self._elapsed(record)
            for step in phase["steps"]:
                if step.get("paused", False):
                    step["paused"] = False
                    step["wait_ended"] = phase["ended"]
                    step["wait_interrupted"] = phase["status"] != "completed"
            if self._current_phase == stage_id:
                self._current_phase = None
            self.console.print(self._phase_tree(phase, compact=True, ended_summary=True))

    def _phase_label(self, phase):
        status = phase["status"]
        style = "green" if status == "completed" else "red" if status in {"failed", "interrupted"} else "cyan"
        status_text = status + "（中断）" if status == "interrupted" else status
        stamp = self._stamp(phase.get("ended", phase["started"]))
        duration = f" · 用时 {max(0.0, phase['ended'] - phase['started']):.2f}s" if "ended" in phase else ""
        return Text(f"{stamp} · 阶段 {phase['number']:02d} {phase['title']} · 演示阶段 {status_text}{duration}", style=style)

    def _add_step(self, parent, step):
        elapsed = self._elapsed(step)
        actor = self._actor(step.get("actor", "demo"))
        number = step.get("step_number", "?")
        label = Text(f"{self._stamp(elapsed)} · 步骤 {number} · {actor} → ", style="dim")
        label.append(str(step.get("operation", "演示说明")), style="bold")
        branch = parent.add(label)
        if step.get("text"):
            branch.add(Text(str(step["text"])))
        wait = step.get("wait_seconds", 0)
        if wait:
            if step.get("paused", False):
                branch.add(Text(f"模拟停顿 {float(wait):g} 秒 · 用于观察流程；不是协议时钟或工具执行结果。", style="yellow"))
            elif step.get("wait_interrupted"):
                branch.add(Text(f"模拟停顿已中断 · 原设置 {float(wait):g} 秒", style="red"))
            elif "wait_ended" in step:
                branch.add(Text(f"模拟停顿已结束 · 设定 {float(wait):g} 秒", style="dim"))
        return branch

    def _stage_message(self, record):
        stage_id = record.get("stage_id")
        phase = self.phases.get(stage_id)
        if phase is None:
            return
        name = record.get("event", "")
        envelope = record.get("envelope")
        content = record.get("content", {})
        if envelope:
            kind, content = envelope["payload"]["type"], envelope["payload"]["content"]
            identifier = content.get("id", envelope["id"])
            sender, recipient = envelope["sender"], envelope["recipient"]
        elif name in CONTENT_EVENTS or name == "handler.dispatch":
            kind = record["payload_type"] if name == "handler.dispatch" else CONTENT_EVENTS[name]
            identifier = content.get("id")
            sender = record.get("sender", record.get("component", "?"))
            recipient = record.get("component", "?")
        elif name == "check":
            identifier, kind = record["name"], "check"
            sender = recipient = "demo"
        elif name == "delivery_ack":
            identifier, kind = record.get("envelope_id"), "ack"
            sender = recipient = record.get("component", "environment")
        elif name == "specification":
            identifier, kind = record.get("sender"), "specification"
            sender = identifier
            recipient = record.get("component", "?")
        elif name.startswith("monitor."):
            sender, recipient = record.get("source", "hub"), record.get("component", "monitor")
            identifier, kind = sender + ":" + record.get("name", name), "monitor"
        else:
            return
        if not identifier:
            return
        sender = "demo_env" if sender == "environment" else sender
        recipient = "demo_env" if recipient == "environment" else recipient
        key = (kind, identifier)
        new = key not in phase["messages"]
        item = phase["messages"].setdefault(key, {
            "kind": kind, "id": identifier, "name": content.get("name", content.get("event", content.get("op", kind))),
            "sender": sender, "recipient": recipient, "elapsed": self._elapsed(record), "observations": [],
        })
        if kind == "monitor":
            item["name"] = record.get("name", name)
        component = record.get("component", "?")
        if component == "environment":
            component = "demo_env"
        observation = {"event": name, "component": component, "sender": sender, "recipient": recipient}
        if observation not in item["observations"]:
            item["observations"].append(observation)
        # Redirected output reveals progress before completion; full JSON stays
        # in the final tree rather than being repeated after every callback.
        if new and not self._live and name in CONTENT_EVENTS and not self.handler_observations.get(identifier):
            tree = Tree(Text(f"阶段 {phase['number']:02d} · 协议消息", style="dim"))
            tree.add(self._phase_message_label(item))
            self.console.print(tree)

    def _phase_message_label(self, item):
        kind, identifier = item["kind"], item["id"]
        label = Text(self._stamp(item["elapsed"]) + " · ", style="dim")
        if identifier in self.messages and kind in {"action", "outcome", "event"}:
            label.append_text(self._label(identifier, self.messages[identifier]))
            if kind == "outcome":
                action_id = self.messages[identifier]["content"].get("refs", ["?"])[0]
                label.append(f" → {self.alias('action', action_id)}", style="dim")
            elif kind == "event":
                refs = self.messages[identifier]["content"].get("refs", [])
                if refs:
                    label.append(" · refs → " + ", ".join(self.alias("event", ref) for ref in refs), style="dim")
        elif kind == "check":
            label.append("✓ " + identifier, style="green")
        elif kind == "ack":
            label.append(f"ACK · {self.alias('delivery', identifier)} · 环境已确认", style="magenta")
        elif kind == "stream":
            label.append(self.alias("stream", identifier) + " stream", style="cyan")
        else:
            label.append(kind + " · " + str(item["name"]), style="cyan")
        if kind in {"outcome", "stream", "specification", "monitor", "ctrl", "notify", "discover"}:
            label.append(f" · {self._actor(item['sender'])} → {self._actor(item['recipient'])}", style="dim")
        observations = item["observations"]
        if observations:
            directions = []
            for observation in observations:
                event = observation["event"]
                operation = "补发" if event == "delivery_replay" else "发送" if event in {"wire.send", "send"} else "接收" if event == "wire.receive" else "回调"
                detail = operation + " " + self._actor(observation["component"])
                if detail not in directions:
                    directions.append(detail)
            label.append(" · " + " / ".join(directions), style="dim")
        return label

    def _phase_tree(self, phase, *, compact=False, active=False, ended_summary=False):
        tree = Tree(self._phase_label(phase), guide_style="dim")
        if active and phase["steps"]:
            # The current step is above accumulated roles/history even on a
            # short terminal. Older steps remain in the final process tree.
            self._add_step(tree, phase["steps"][-1])
        if active and self._last_dispatch and self._last_dispatch.get("stage_id") == phase["id"]:
            tree.add(self._dispatch_tree(self._last_dispatch, compact=True))
        if phase["description"] and not ended_summary:
            tree.add(Text(phase["description"], style="dim"))
        actors = OrderedDict()
        for step in phase["steps"]:
            actor = step.get("actor", "demo")
            operation = str(step.get("operation", "演示说明"))
            if operation not in actors.setdefault(actor, []):
                actors[actor].append(operation)
        if actors:
            roles = tree.add(Text("本阶段主体与职责", style="bold"))
            for actor, operations in actors.items():
                visible = operations[-2:] if active else operations[:2] if compact else operations[:4]
                text = "；".join(visible)
                if len(operations) > len(visible):
                    text += f"；共 {len(operations)} 类操作"
                roles.add(Text(f"{self._actor(actor)}：{text}"))
        if not compact and not active:
            for step in phase["steps"]:
                self._add_step(tree, step)
        elif active and len(phase["steps"]) > 1:
            tree.add(Text(f"前 {len(phase['steps']) - 1} 个步骤详见 --trace / transcript.jsonl。", style="dim"))
        if active:
            observations = [item for item in self.timeline if item["record"].get("stage_id") == phase["id"]]
            if observations:
                group = tree.add(Text(f"最近观察记录 · 按实际顺序 · 共 {len(observations)} 条", style="dim"))
                for item in observations[-6:]:
                    group.add(self._timeline_label(item))
                if len(observations) > 6:
                    group.add(Text("全部观察序号和收发步骤在最终时间轴 / transcript.jsonl 中。", style="dim"))
        return tree

    def build_live_tree(self):
        """Bounded active view: capability JSON can never hide current work."""
        with self._lock:
            phase = self.phases.get(self._current_phase)
            if phase is None and self.phases:
                phase = next(reversed(self.phases.values()))
            if phase is None:
                current = Tree(Text("准备演示 · 等待第一个流程阶段", style="bold cyan"))
            else:
                current = self._phase_tree(phase, active=True)
            completed = Tree(Text("流程进度 · 演示讲解", style="bold"))
            previous = [item for item in self.phases.values() if item is not phase]
            for item in previous[-3:]:
                completed.add(self._phase_label(item))
            completed.add(Text(f"已记录 {len(self.messages)} 条 Action / Outcome / Event；{len(self.checks)} 项检查通过。", style="dim"))
            if self.trace:
                completed.add(Text("trace 完整三层报文、Schema 和 refs 关系在结束后的协议树中展开。", style="dim"))
            return Group(Panel(current, title=Text(self.title + " · 当前流程")), completed)

    def _interactive(self, record):
        name, content = record.get("event"), record.get("content")
        envelope = record.get("envelope")
        if envelope and name in {"wire.send", "send", "delivery_replay"}:
            payload = envelope["payload"]
            if payload["type"] in {"action", "outcome", "event"}:
                node = self.messages[payload["content"]["id"]]
                refs = node["content"].get("refs", [])
                if node["kind"] == "outcome":
                    target = self.messages.get(refs[0])
                    root = Tree(self._label(refs[0], target or {
                        "kind": "action", "content": {}, "sender": "?", "recipients": []}))
                elif node["kind"] == "event" and refs and refs[0] in self.messages:
                    root = Tree(self._label(refs[0], self.messages[refs[0]]))
                else:
                    root = Tree(Text("发送 · " + payload["type"], style="bold cyan"))
                self._add_message(root, node)
                self.console.print(root)
            return
        if name in CONTENT_EVENTS and content:
            key = (CONTENT_EVENTS[name], content["id"], record.get("component"))
            if key in self._callback_seen:
                return
            self._callback_seen.add(key)
            node = self.messages[content["id"]]
            if node["kind"] == "action":
                root = Tree(Text("Action 接收", style="bold blue"))
                self._add_message(root, node)
            elif node["kind"] == "outcome":
                action_id = content["refs"][0]
                action = self.messages.get(action_id)
                root = Tree(self._label(action_id, action or {"kind": "action", "content": {}, "sender": "?", "recipients": []}))
                self._add_message(root, node)
            else:
                refs = content.get("refs", [])
                if refs and refs[0] in self.messages:
                    root = Tree(self._label(refs[0], self.messages[refs[0]]))
                    self._add_message(root, node)
                else:
                    root = Tree(Text("Event 输入", style="bold cyan"))
                    self._add_message(root, node)
            self.console.print(root)
        elif name == "specification":
            root = Tree(Text(f"已收到接收能力 · {record['sender']}", style="cyan"))
            self._capabilities(root, record["content"])
            self.console.print(root)
        elif name.startswith("monitor."):
            root = Tree(Text(f"Monitor · {record.get('source', 'hub')} → {record.get('name', name)}", style="cyan"))
            root.add(json_tree("data", record.get("data", {})))
            self.console.print(root)

    def _label(self, identifier, node):
        content, kind = node["content"], node["kind"]
        label = Text(self.alias(kind, identifier) + " ", style="bold")
        if kind == "outcome":
            status = content.get("status", "?")
            label.append(status, style=STATUS_STYLE.get(status, "white"))
        else:
            label.append(content.get("name", "原 Action · 本次未展示请求"), style="cyan" if kind == "event" else "blue")
            recipients = node.get("recipients", [])
            destinations = ", ".join(self._actor(item) for item in recipients if item != "@env")
            if "@env" in recipients:
                destinations = "广播 @env" + (f"（{destinations}）" if destinations else "")
            if destinations:
                label.append(f" · {self._actor(node['sender'])} → {destinations}", style="dim")
        if len(node.get("deliveries", [])) > 1:
            label.append(f" · 复用原ID，{len(node['deliveries'])}次投递", style="yellow")
        return label

    def _references(self, branch, content, kind):
        refs = content.get("refs", [])
        if not refs:
            return
        root = branch.add(Text("refs · 按原顺序", style="dim"))
        for index, ref in enumerate(refs):
            target = self.messages.get(ref)
            ref_kind = "action" if kind == "outcome" else "event"
            description = self.alias(ref_kind, ref)
            if target:
                description += " " + target["content"].get("name", target["content"].get("status", ""))
            elif kind == "event":
                description += " · 原事件未在本次展示中出现"
            root.add(Text(f"[{index}] → {description}", style="dim"))

    def _add_message(self, parent, node):
        content, kind = node["content"], node["kind"]
        branch = parent.add(self._label(content["id"], node))
        if self.trace:
            branch.add(Text(f"Content.id: {content['id']}", style="dim"))
        if kind == "action":
            params = content.get("params", {})
            if params:
                branch.add(json_tree("params", params))
            if content.get("name") in {"cancel", "get_operation_result"} and "action_id" in params:
                relation = "取消目标" if content["name"] == "cancel" else "查询目标"
                branch.add(Text(f"{relation} → {self.alias('action', params['action_id'])} · 业务参数 action_id", style="magenta"))
        else:
            self._references(branch, content, kind)
            data = content.get("data", {})
            text = data.get("text", "")
            if text:
                visible = text if self.trace or len(text) <= 240 else text[:240] + "…（trace 中查看全文）"
                branch.add(Text(visible))
            controls = {key: value for key, value in data.items() if key != "text"}
            if controls:
                branch.add(json_tree("data · Schema 声明的字段", controls))
            if node.get("handlers") and not self.handler_observations.get(content["id"]):
                branch.add(Text("解析: " + ", ".join(node["handlers"]), style="dim"))
        observed_handlers = OrderedDict()
        for observed in self.handler_observations.get(content["id"], []):
            key = (observed["receiver"], observed.get("route"), observed.get("handler"), observed.get("dispatch_mode", "new"))
            previous = observed_handlers.setdefault(key, {"record": observed, "count": 0})
            previous["count"] += 1
        for item in observed_handlers.values():
            observed = item["record"]
            method = self._method_name(observed.get("handler", "?"))
            description = f"实际处理器: {method} · {observed.get('route', '?')} → {self._actor(observed['receiver'])}"
            if kind == "action":
                description += " · 读取原账本，重放原 Outcome；未执行世界分支" if observed.get("dispatch_mode") == "ledger_replay" else " · 分支 " + content.get("name", "?")
            if item["count"] > 1:
                description += f" · 实际观测 {item['count']} 次"
            branch.add(Text(description, style="dim"))
        if self.trace and node.get("deliveries"):
            deliveries = branch.add(Text("投递 · 同一 UUID 的收发合并", style="dim"))
            for identifier in node["deliveries"]:
                packet = self.deliveries[identifier]["envelope"]
                deliveries.add(json_tree(self.alias("delivery", identifier) + " Envelope → Payload → Content", packet))
        return branch

    def _capabilities(self, branch, specification, *, bindings=None):
        branch.add(Text(f"protocol: {specification.get('protocol', '?')}", style="dim"))
        for directory in ("tools", "events"):
            entries = specification.get(directory, [])
            group = branch.add(Text(f"{directory} · {len(entries)}", style="cyan"))
            if not entries:
                group.add(Text("未暴露工具" if directory == "tools" else "未声明具名 Event", style="dim"))
            for item in entries:
                label = item["name"] + (f" · {item['handler']}" if "handler" in item else "")
                if item.get("tags"):
                    label += " · " + ", ".join(item["tags"])
                row = group.add(Text(label))
                binding = (bindings or {}).get(directory, {}).get(item["name"])
                if binding:
                    entrypoint = self._method_name(binding.get("entrypoint", "?"))
                    dispatch = " · 分支 " + str(binding["dispatch"]) if "dispatch" in binding else ""
                    row.add(Text("实际绑定 → " + entrypoint + dispatch, style="magenta"))
                schema = item.get("parameters", item.get("data_schema"))
                if schema is not None:
                    if self.trace:
                        row.add(json_tree("parameters Schema" if directory == "tools" else "data_schema", schema))
                    else:
                        fields = row.add(Text("params Schema" if directory == "tools" else "data_schema", style="dim"))
                        self._schema_fields(fields, schema)
                elif directory == "events":
                    row.add(Text("默认 data.text: string · 必填；没有额外业务字段。", style="dim"))

    def build_tree(self):
        with self._lock:
            return self._build_tree()

    def _build_tree(self):
        root = Tree(Text(self.title + " · agent-env-compact/2", style="bold cyan"), guide_style="dim")
        if self.timeline:
            flow = root.add(Text("全流程时间轴 · 按实际观察顺序；与下方因果树分开", style="bold cyan"))
            flow.add(Text("序号保留原始记录顺序；收到（解包）不等于安装、执行或持久化。", style="dim"))
            records = flow.add(Text(f"观察记录 · {len(self.timeline)} 条 · 不合并同 ID 的不同收发步骤", style="bold"))
            for item in self.timeline:
                branch = records.add(self._timeline_label(item))
                record = item["record"]
                if self.trace and record.get("event") == "flow.step":
                    if record.get("text"):
                        branch.add(Text(str(record["text"])))
                    phase = self.phases.get(record.get("stage_id"), {})
                    step = next((step for step in phase.get("steps", []) if step.get("step_number") == record.get("step_number")), record)
                    if step.get("wait_interrupted"):
                        branch.add(Text("模拟停顿已中断", style="red"))
                    elif step.get("wait_seconds"):
                        branch.add(Text(f"模拟停顿 {'进行中' if step.get('paused') else '已结束'} · 设定 {step['wait_seconds']:g} 秒", style="dim"))
            if self.phases:
                phases = flow.add(Text("阶段概览 · 本阶段主体与职责", style="bold"))
                for phase in self.phases.values():
                    phases.add(self._phase_tree(phase, compact=True, ended_summary=True))
        if self._last_check:
            root.add(Text(f"检查: {len(self.checks)} 项通过 · {self._last_check}", style="green"))
        if self.specifications or self.registrations:
            actors = root.add(Text("主体与接收能力 · 最近声明及本地真实绑定", style="bold"))
            actor_order = {"Environment": 0, "Agent": 1, "Human": 2}
            snapshots = OrderedDict(self.specifications)
            for actor, registration in self.registrations.items():
                snapshots.setdefault(actor, registration["specification"])
            for actor, specification in sorted(snapshots.items(), key=lambda item: actor_order.get(ACTOR_ROLE.get(item[0]), 3)):
                branch = actors.add(Text(self._actor(actor), style="bold"))
                registration = self.registrations.get(actor)
                self._capabilities(branch, specification, bindings=registration.get("bindings") if registration else None)
                if registration:
                    self._framework_receivers(branch, registration.get("role"))

        actions = [(identifier, node) for identifier, node in self.messages.items() if node["kind"] == "action"]
        outcomes = [(identifier, node) for identifier, node in self.messages.items() if node["kind"] == "outcome"]
        if actions or outcomes:
            group = root.add(Text("Action → Outcome · 仅 refs 建立结果关联", style="bold blue"))
            action_branches = {}
            for identifier, node in actions:
                action_branches[identifier] = self._add_message(group, node)
            for identifier, node in outcomes:
                ref = node["content"]["refs"][0]
                if ref not in action_branches:
                    action_branches[ref] = group.add(Text(f"{self.alias('action', ref)} 原 Action · 本次未展示请求", style="dim"))
                self._add_message(action_branches[ref], node)

        events = OrderedDict((identifier, node) for identifier, node in self.messages.items() if node["kind"] == "event")
        if events:
            group = root.add(Text("Event 因果引用 · 按 refs[0] 展开，其余引用保留原序", style="bold cyan"))
            parents = {}
            for identifier, node in events.items():
                refs = node["content"].get("refs", [])
                parents[identifier] = refs[0] if refs and refs[0] in events and refs[0] != identifier else None
            # A directed graph can have cycles. Never invent a tree parent for
            # a cycle or recurse forever; keep such nodes flat with their refs.
            for identifier in events:
                current, path = identifier, []
                while current is not None and current not in path:
                    path.append(current)
                    current = parents.get(current)
                if current is not None:
                    for item in path[path.index(current):]:
                        parents[item] = None
            visited = set()

            def add_event(identifier, parent):
                if identifier in visited:
                    return
                visited.add(identifier)
                branch = self._add_message(parent, events[identifier])
                for child, parent_id in parents.items():
                    if parent_id == identifier:
                        add_event(child, branch)
            for identifier, parent in parents.items():
                if parent is None:
                    add_event(identifier, group)

        special = [(identifier, item) for identifier, item in self.deliveries.items()
                   if item["replay_count"] or any(count > 1 for count in item["receivers"].values())]
        confirmed = sum(item["ack"] for item in self.deliveries.values())
        if self.deliveries:
            group = root.add(Text(f"投递与恢复 · {confirmed} 个原投递已确认 ACK", style="bold magenta"))
            for identifier, item in special:
                packet = item["envelope"]
                content = packet["payload"]["content"]
                logical_id = content.get("id")
                node = self.messages.get(logical_id)
                logical = self.alias(node["kind"], logical_id) if node else "控制消息"
                branch = group.add(Text(f"{self.alias('delivery', identifier)} → {logical} · 同 UUID 补发 · 接收 {item['receive_count']} 次", style="yellow"))
                branch.add(Text("ACK 已由环境确认" if item["ack"] else "ACK 未由环境确认", style="green" if item["ack"] else "yellow"))
                if self.trace:
                    branch.add(Text("Envelope.id: " + identifier, style="dim"))
            if not special:
                group.add(Text("尚未观察到原 Envelope UUID 补发", style="dim"))

        if self.streams:
            group = root.add(Text("Stream · 片段不会替代 Outcome", style="bold"))
            for identifier, stream in self.streams.items():
                branch = group.add(Text(f"{self.alias('stream', identifier)} · {stream['sender']} → {stream['recipient']}"))
                for index, content in stream["chunks"].items():
                    branch.add(Text(f"sequence={index} · is_end={content.get('is_end')} · {content.get('chunk')}"))
        if self.telemetry:
            group = root.add(Text("Monitor · 独立的控制与遥测通道", style="bold"))
            for (source, name), data in self.telemetry.items():
                if not self.trace and name not in {"demo.trace", "monitor.subscribed", "monitor.unsubscribed", "error"}:
                    continue
                branch = group.add(Text(f"{source} → {name}"))
                branch.add(json_tree("data", data))
        if self.trace:
            other = [(identifier, item["envelope"]) for identifier, item in self.deliveries.items()
                     if item["envelope"]["payload"]["type"] not in {"action", "outcome", "event"}]
            if other:
                group = root.add(Text("其他已记录的报文 · system / discovery / stream / monitor", style="bold"))
                for identifier, packet in other:
                    group.add(json_tree(f"{self.alias('delivery', identifier)} Envelope → Payload → Content", packet))
        if self.trace and self.checks:
            checks = root.add(Text(f"验证明细 · {len(self.checks)} 项通过", style="bold green"))
            for item in self.checks:
                branch = checks.add(Text("✓ " + item["name"], style="green"))
                if item.get("reason"):
                    branch.add(Text(str(item["reason"]).splitlines()[0], style="dim"))
        if self.summary:
            group = root.add(Text("运行结果", style="bold green"))
            group.add(Text(f"{self.summary['check_count']} 项检查通过 · 六种 Outcome 状态已验证"))
            group.add(Text("记录目录: " + self.summary["state_directory"], style="dim"))
        return root

    def finish(self):
        if self._finished:
            return
        self._finished = True
        if self._live:
            self._live.update(self.build_live_tree(), refresh=True)
            self._live.stop()
            # Live may crop a tall tree to the TTY height. The final static tree
            # is printed once in full so all causal paths remain scrollable.
            self.console.print(self.build_tree())
        elif self.live:
            self.console.print(self.build_tree())
