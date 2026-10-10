"""Local observability of installed demo capabilities and actual callbacks.

These presentation records never become protocol Envelope or Content fields.
"""

from __future__ import annotations

import copy
from typing import Any, Callable


def qualified_name(handler: Callable) -> str:
    """Name the actual callable, including the declaring module and method."""
    return f"{handler.__module__}.{handler.__qualname__}"


def summarize_registration(client, specification: dict, runtime_handlers: dict) -> dict:
    """Describe a successful SDK installation using its complete live snapshot."""
    return {
        "component": client.client_id,
        "role": client.role,
        "event": "capability.registered",
        "presentation": True,
        "specification": copy.deepcopy(specification),
        "bindings": {
            "tools": {
                definition["name"]: {
                    "entrypoint": qualified_name(client.on_action),
                    "dispatch": definition["name"],
                }
                for definition in specification["tools"]
            },
            "events": {
                definition["name"]: {
                    "handler": definition["handler"],
                    "entrypoint": qualified_name(
                        runtime_handlers[definition["name"]]
                        if definition["handler"] == "runtime" else client.on_event
                    ),
                }
                for definition in specification["events"]
            },
        },
    }


def handler_dispatch(client, sender: str, payload_type: str, content: dict,
                     handler: Callable, route: str, **details: Any) -> dict[str, Any]:
    """Record an invoked local handler without modifying the received Content."""
    return {
        "component": client.client_id,
        "role": client.role,
        "event": "handler.dispatch",
        "presentation": True,
        "sender": sender,
        "payload_type": payload_type,
        "content": copy.deepcopy(content),
        "handler": qualified_name(handler),
        "route": route,
        **details,
    }
