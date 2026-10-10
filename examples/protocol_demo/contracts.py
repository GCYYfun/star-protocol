"""Load the demo's editable receiver specifications and validate their schemas.

A specification describes what its owner receives: tools are callable on this
receiver; events name inputs handled by its model or registered runtime handler.
Permissions remain an environment policy, separate from parameter validation.
"""

import json
from pathlib import Path

from star_protocol.models.payloads import COMPACT_PROTOCOL, validate_content

CONFIG_DIR = Path(__file__).resolve().parent / "config"
ROLES = ("environment", "agent", "human")


def load_specification(role: str) -> dict:
    """Read a fresh configuration, reject unknown roles, and check its contract."""
    if role not in ROLES:
        raise ValueError(f"Unknown receiver role: {role!r}; choose one of {ROLES}")
    specification = json.loads((CONFIG_DIR / f"{role}.json").read_text(encoding="utf-8"))
    validate_content("specification", specification)
    if specification["protocol"] != COMPACT_PROTOCOL:
        raise ValueError(f"Demo requires {COMPACT_PROTOCOL}")
    return specification


def validate_configs() -> dict[str, dict]:
    """Validate all three receiver directories without starting a network client."""
    return {role: load_specification(role) for role in ROLES}
