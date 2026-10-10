import copy
import json
import pytest

from star_protocol.models import (
    Envelope, MessagePayload, BroadcastPayload, SystemPayload, MonitorPayload,
    COMPACT_PROTOCOL, validate_compact_content,
)


OUTCOME = {"id": "result-1", "refs": ["request-1"], "status": "running", "data": {"text": "仍在执行"}}
EVENT = {"id": "fact-2", "name": "world.changed", "refs": ["fact-1"], "data": {"text": "发生变化"}}


@pytest.mark.parametrize("kind,content", [
    ("action", {"id": "request-1", "name": "LOOK", "params": {}}),
    ("outcome", OUTCOME),
    ("event", EVENT),
    ("discover", {"protocols": [COMPACT_PROTOCOL]}),
    ("specification", {"protocol": COMPACT_PROTOCOL, "tools": [], "events": []}),
])
def test_discriminator_roundtrip_preserves_complete_content(kind, content):
    envelope = Envelope(sender="agent", recipient="env", payload=MessagePayload(type=kind, content=content))
    decoded = Envelope.model_validate_json(envelope.model_dump_json())
    assert decoded.payload.content == content
    assert decoded.model_dump() == envelope.model_dump()


@pytest.mark.parametrize("bad", [
    {"refs": ["request-1"], "status": "completed", "data": {"text": "ok"}},
    {"id": "result", "ref_id": "request", "success": True, "data": {"text": "ok"}},
    {**OUTCOME, "refs": []},
    {**OUTCOME, "refs": ["request-1", "request-2"]},
    {**OUTCOME, "refs": ["result-1"]},
    {**OUTCOME, "status": "unknown"},
    {**OUTCOME, "data": {"text": ""}},
    {**OUTCOME, "data": {"text": "ok", "result": 1}},
    {**OUTCOME, "error": "old field"},
])
def test_invalid_outcomes_are_rejected_without_dictionary_fallback(bad):
    with pytest.raises(ValueError):
        Envelope(sender="env", recipient="agent", payload={"type": "outcome", "content": bad})


@pytest.mark.parametrize("bad", [
    {"name": "LOOK", "params": {}},
    {"id": "a", "name": "LOOK"},
    {"id": "a", "name": "LOOK", "params": {}, "extra": True},
    {"id": "a", "name": "LOOK", "params": {"count": float("nan")}},
    {"id": "a", "name": "LOOK", "params": {"position": (1, 2)}},
])
def test_invalid_action_shape(bad):
    with pytest.raises(ValueError):
        MessagePayload(type="action", content=bad)


def test_event_refs_and_receiver_schema():
    for refs in ([], ["fact-1", "fact-1"], ["fact-2"], [str(i) for i in range(33)]):
        with pytest.raises(ValueError):
            MessagePayload(type="event", content={**EVENT, "refs": refs})
    with pytest.raises(ValueError):
        validate_compact_content("event", {**EVENT, "data": {"text": "ok", "state": "idle"}})
    definition = {"name": "world.changed", "description": "状态", "handler": "runtime", "data_schema": {
        "type": "object", "properties": {"text": {"type": "string"}, "state": {"enum": ["idle"]}},
        "required": ["text", "state"], "additionalProperties": False}}
    validate_compact_content("event", {**EVENT, "data": {"text": "ok", "state": "idle"}}, [definition])
    with pytest.raises(ValueError):
        MessagePayload(type="event", content={**EVENT, "data": {"text": "ok", "event_id": "nested"}})


def test_wire_rejects_duplicate_keys_and_wrong_category():
    envelope = Envelope(sender="e", recipient="a", payload=MessagePayload(type="outcome", content=OUTCOME))
    raw = envelope.model_dump_json().replace('"running"', '"running","status":"completed"')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        Envelope.model_validate_json(raw)
    with pytest.raises(ValueError):
        Envelope(sender="e", recipient="a", type="broadcast", payload={"type": "action", "content": {"id": "a", "name": "LOOK", "params": {}}})
    missing = envelope.model_dump()
    missing.pop("id")
    with pytest.raises(ValueError):
        Envelope.model_validate_json(json.dumps(missing))


def test_limits_and_base_control_compatibility():
    with pytest.raises(ValueError):
        MessagePayload(type="outcome", content={**OUTCOME, "data": {"text": "x" * 32001}})
    with pytest.raises(ValueError):
        Envelope(sender="e", recipient="a", payload=MessagePayload(type="action", content={"id": "a", "name": "UPLOAD", "params": {"text": "x" * 524288}}))
    with pytest.raises(ValueError):
        Envelope(sender="e", recipient="a", timestamp=-1, payload=MessagePayload(type="outcome", content=OUTCOME))
    for category, model, kind, content in (
        ("system", SystemPayload, "notify", {"event": "joined", "msg": "ok", "env_id": "e"}),
        ("monitor", MonitorPayload, "notify", {"event": "subscribed", "msg": "ok", "target_client_id": "a"}),
        ("message", MessagePayload, "stream", {"id": "s", "sequence": 0, "chunk": "text", "is_end": True}),
        ("broadcast", BroadcastPayload, "event", EVENT),
    ):
        envelope = Envelope(sender="e", recipient="a", type=category, payload=model(type=kind, content=content))
        assert Envelope.model_validate_json(envelope.model_dump_json()).payload.content == content


def test_directory_rejects_legacy_extra_fields_and_duplicate_names():
    spec = {"protocol": COMPACT_PROTOCOL, "tools": [{"name": "LOOK", "description": "look", "parameters": {"type": "object"}}], "events": []}
    for mutation in ("output_schema", "params_schema"):
        bad = copy.deepcopy(spec)
        bad["tools"][0][mutation] = {}
        with pytest.raises(ValueError):
            MessagePayload(type="specification", content=bad)
    spec["tools"] *= 2
    with pytest.raises(ValueError):
        MessagePayload(type="specification", content=spec)


def test_schema_declarations_cannot_trigger_implicit_network_retrieval():
    from star_protocol.models import MessagePayload, COMPACT_PROTOCOL
    with pytest.raises(ValueError):
        MessagePayload(type="specification",content={"protocol":COMPACT_PROTOCOL,"tools":[{
            "name":"READ","description":"read","parameters":{"$ref":"https://example.org/schema.json"}}],"events":[]})


def test_registered_data_schema_does_not_remove_required_natural_language_text():
    from star_protocol.models import validate_compact_content
    definition={"name":"control","description":"rule","handler":"runtime","data_schema":{
        "type":"object","properties":{"value":{"type":"integer"}},"required":["value"]}}
    with pytest.raises(ValueError):
        validate_compact_content("event",{"id":"control-id","name":"control","data":{"value":1}},[definition])
