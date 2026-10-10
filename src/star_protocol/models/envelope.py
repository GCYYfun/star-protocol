"""Star Envelope: strict category dispatch with lossless content dictionaries."""

import json
import time
import uuid
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .payloads import SystemPayload, MessagePayload, BroadcastPayload, MonitorPayload

MAX_MESSAGE_BYTES = 512 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError(f"Non-finite JSON number: {value}")


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), ge=0)
    type: Literal["system", "message", "broadcast", "monitor"] = "message"
    sender: str = Field(min_length=1, max_length=256)
    recipient: str = Field(min_length=1, max_length=256)
    payload: Any

    @field_validator("id")
    @classmethod
    def uuid_id(cls, value):
        uuid.UUID(value)
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def category_payload(cls, value, info):
        category = info.data.get("type", "message")
        model = {"system": SystemPayload, "message": MessagePayload,
                 "broadcast": BroadcastPayload, "monitor": MonitorPayload}.get(category)
        if model is None:
            raise ValueError("Unknown Envelope category")
        if isinstance(value, BaseModel):
            value = value.model_dump()
        return model.model_validate(value)

    @model_validator(mode="after")
    def size_limit(self):
        encoded = json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("Envelope exceeds 512 KiB")
        return self

    @classmethod
    def model_validate_json(cls, json_data, *, strict=None, context=None, **kwargs):
        data = json.loads(json_data, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
        if type(data) is not dict or not {"id", "timestamp", "type", "sender", "recipient", "payload"} <= data.keys():
            raise ValueError("Wire Envelope requires id, timestamp, type, sender, recipient and payload")
        return cls.model_validate(data, strict=strict, context=context, **kwargs)
