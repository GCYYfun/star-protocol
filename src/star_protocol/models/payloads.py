"""Star payloads and the discriminator-driven agent-env-compact/2 contract."""

import math
import json
from functools import lru_cache
import uuid
from typing import Any, Dict, Literal, Optional, Union
from typing_extensions import NotRequired, TypedDict

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, model_validator

COMPACT_PROTOCOL = "agent-env-compact/2"
TERMINAL_STATUSES = frozenset({"completed", "rejected", "failed", "cancelled"})
OUTCOME_STATUSES = TERMINAL_STATUSES | {"accepted", "running"}


def gen_id(type: str, name: str = "") -> str:
    """Globally unique logical ID; persist it before the first send."""
    return f"{type}-{uuid.uuid4()}"


class ToolDefinition(TypedDict):
    name: str
    description: str
    parameters: Dict[str, Any]
    tags: NotRequired[list[str]]


class EventDefinition(TypedDict):
    name: str
    description: str
    handler: Literal["model", "runtime"]
    data_schema: NotRequired[Dict[str, Any]]


class MessageActionContent(TypedDict):
    id: str
    name: str
    params: Dict[str, Any]


class MessageOutcomeContent(TypedDict):
    id: str
    refs: list[str]
    status: Literal["accepted", "running", "completed", "rejected", "failed", "cancelled"]
    data: Dict[str, str]


class MessageEventContent(TypedDict):
    id: str
    name: str
    data: Dict[str, Any]
    refs: NotRequired[list[str]]


class MessageStreamContent(TypedDict, total=False):
    id: Optional[str]
    sequence: int
    chunk: Any
    is_end: bool


class MessageDiscoverContent(TypedDict):
    protocols: list[str]


class MessageSpecificationContent(TypedDict):
    protocol: str
    tools: list[ToolDefinition]
    events: list[EventDefinition]


class SystemCtrlContent(TypedDict, total=False):
    op: str
    env_id: Optional[str]


class SystemNotifyContent(TypedDict, total=False):
    event: str
    msg: Union[str, Dict[str, Any]]


class SystemErrorContent(TypedDict, total=False):
    code: int
    msg: str
    original_msg_id: Optional[str]
    details: Optional[Any]


class MonitorCtrlContent(TypedDict, total=False):
    op: Literal["enable", "disable", "subscribe", "unsubscribe"]
    level: str
    target_client_id: str


class MonitorDataContent(TypedDict, total=False):
    name: str
    data: Any
    timestamp: int


class MonitorNotifyContent(TypedDict, total=False):
    event: str
    msg: str


BroadcastEventContent = MessageEventContent
BroadcastStreamContent = MessageStreamContent


def validate_json(value: Any) -> None:
    """Reject Python-only values, non-finite numbers and non-string object keys."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            validate_json(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            validate_json(item)
        return
    raise ValueError("Content must contain finite JSON values")


def _object(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    if type(value) is not dict:
        raise ValueError("Expected an object")
    if not required <= value.keys() or not value.keys() <= required | optional:
        raise ValueError(f"Expected fields {sorted(required)}, optional {sorted(optional)}")


def _string(value: Any, maximum: int, label: str) -> None:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        raise ValueError(f"{label} must be a nonempty string of at most {maximum} characters")


def validate_text_data(data: Any) -> None:
    _object(data, {"text"})
    _string(data["text"], 32000, "text")


def _refs(value: Any, message_id: str, *, outcome: bool = False) -> None:
    maximum = 1 if outcome else 32
    if type(value) is not list or not 1 <= len(value) <= maximum:
        raise ValueError(f"refs must contain 1..{maximum} logical message IDs")
    for item in value:
        _string(item, 256, "reference")
    if len(set(value)) != len(value) or message_id in value:
        raise ValueError("refs cannot duplicate an ID or reference the message itself")


@lru_cache(maxsize=512)
def _checked_schema(encoded: str) -> None:
    # The cache owns its parsed value; callers cannot mutate shared validators.
    schema=json.loads(encoded)
    Draft202012Validator.check_schema(schema)
    pending=[schema]
    while pending:
        node=pending.pop()
        if isinstance(node,dict):
            for key in ("$ref","$dynamicRef"):
                if key in node and not node[key].startswith("#"):
                    raise ValueError("Receiver schemas support local references; external retrieval needs an explicit application adapter")
            pending.extend(node.values())
        elif isinstance(node,list):
            pending.extend(node)


def check_schema(schema: dict) -> None:
    _checked_schema(json.dumps(schema,sort_keys=True,separators=(",",":"),ensure_ascii=False))


@lru_cache(maxsize=512)
def _compiled_schema(encoded: str):
    _checked_schema(encoded)
    return Draft202012Validator(json.loads(encoded),format_checker=FormatChecker())


def validate_schema_instance(schema: dict, instance: Any) -> None:
    encoded = json.dumps(schema,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    _compiled_schema(encoded).validate(instance)


def validate_content(kind: str, content: Any) -> None:
    """Select by payload.type, never by a lossy TypedDict union."""
    validate_json(content)
    if type(content) is not dict:
        raise ValueError("content must be an object")
    if kind == "action":
        _object(content, {"id", "name", "params"})
        _string(content["id"], 256, "id")
        _string(content["name"], 128, "name")
        if type(content["params"]) is not dict:
            raise ValueError("params must be an object")
    elif kind == "outcome":
        _object(content, {"id", "refs", "status", "data"})
        _string(content["id"], 256, "id")
        _refs(content["refs"], content["id"], outcome=True)
        if type(content["status"]) is not str or content["status"] not in OUTCOME_STATUSES:
            raise ValueError("Invalid Outcome status")
        validate_text_data(content["data"])
    elif kind == "event":
        _object(content, {"id", "name", "data"}, {"refs"})
        _string(content["id"], 256, "id")
        _string(content["name"], 128, "name")
        data = content["data"]
        if type(data) is not dict:
            raise ValueError("Event data must be an object")
        if {"id", "event_id", "event_type"} & data.keys():
            raise ValueError("Event identity belongs in content, not data")
        # Receiver-specific data is validated after version/capability negotiation.
        _string(data.get("text"), 32000, "text")
        if "refs" in content:
            _refs(content["refs"], content["id"])
    elif kind == "discover":
        _object(content, {"protocols"})
        protocols = content["protocols"]
        if type(protocols) is not list or not 1 <= len(protocols) <= 8:
            raise ValueError("protocols must contain 1..8 versions")
        for protocol in protocols:
            _string(protocol, 64, "protocol")
        if len(set(protocols)) != len(protocols):
            raise ValueError("Duplicate protocol")
    elif kind == "specification":
        _object(content, {"protocol", "tools", "events"})
        _string(content["protocol"], 64, "protocol")
        for directory, required, optional in (
            ("tools", {"name", "description", "parameters"}, {"tags"}),
            ("events", {"name", "description", "handler"}, {"data_schema"}),
        ):
            items = content[directory]
            if type(items) is not list or len(items) > 256:
                raise ValueError(f"{directory} must be an array of at most 256 entries")
            names = set()
            for item in items:
                _object(item, required, optional)
                _string(item["name"], 128, "name")
                _string(item["description"], 32000, "description")
                if item["name"] in names:
                    raise ValueError(f"Duplicate {directory} name")
                names.add(item["name"])
                if directory == "tools":
                    schema = item["parameters"]
                    if "tags" in item:
                        if type(item["tags"]) is not list:
                            raise ValueError("tags must be an array")
                        for tag in item["tags"]:
                            _string(tag, 128, "tag")
                else:
                    if item["handler"] not in ("model", "runtime"):
                        raise ValueError("Event handler must be model or runtime")
                    schema = item.get("data_schema")
                if schema is not None:
                    if type(schema) is not dict:
                        raise ValueError("Schema must be an object")
                    check_schema(schema)
    # The existing Star system, monitor and stream content contracts remain
    # extensible, with their fields preserved rather than silently stripped.


def validate_compact_content(kind: str, content: Any, event_definitions=None) -> None:
    """Validate content, plus the negotiated receiver's Event data contract.

    Ordinary undeclared names use the profile's text-only model input. Runtime
    controls and structured data require an explicitly declared receiver schema.
    """
    validate_content(kind, content)
    if kind != "event":
        return
    definitions = {item["name"]: item for item in (event_definitions or [])}
    definition = definitions.get(content["name"])
    schema = definition.get("data_schema") if definition else None
    if schema is None:
        validate_text_data(content["data"])
    else:
        validate_schema_instance(schema,content["data"])


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    content: Dict[str, Any]

    @model_validator(mode="after")
    def check_content(self):
        validate_content(self.type, self.content)
        return self


class SystemPayload(_Payload):
    type: Literal["error", "ctrl", "notify"]


class MessagePayload(_Payload):
    type: Literal["action", "outcome", "stream", "event", "discover", "specification"]


class BroadcastPayload(_Payload):
    type: Literal["event", "stream"]


class MonitorPayload(_Payload):
    type: Literal["ctrl", "data", "notify"]
