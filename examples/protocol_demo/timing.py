"""Local presentation timing for the demo, never a wire-protocol capability.

Construct ``DemoTiming()`` for quick programmatic runs.  CLI entrypoints use
``load_timing()`` to load the editable, deliberately slower viewing defaults.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import ValidationError

from star_protocol.models.payloads import validate_schema_instance

CONFIG_DIR = Path(__file__).resolve().parent / "config"
DEFAULT_TIMING_PATH = CONFIG_DIR / "demo-timing.json"
TIMING_SCHEMA_PATH = CONFIG_DIR / "demo-timing.schema.json"


@dataclass(frozen=True)
class DemoTiming:
    """Seconds between stages, semantic steps, and the demo's wait operation."""

    stage_delay: float = 0.0
    step_delay: float = 0.0
    wait_seconds: float = 0.15

    def __post_init__(self) -> None:
        limits = {"stage_delay": (0.0, 10.0), "step_delay": (0.0, 10.0),
                  "wait_seconds": (0.05, 3.0)}
        for field, (minimum, maximum) in limits.items():
            value = getattr(self, field)
            # bool is an int subclass, but cannot represent a chosen duration.
            if type(value) not in (int, float):
                raise ValueError(f"{field} must be a number, not {type(value).__name__}")
            if not minimum <= value <= maximum or not math.isfinite(value):
                raise ValueError(f"{field} must be finite and between {minimum:g} and {maximum:g} seconds")
            object.__setattr__(self, field, float(value))


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise ValueError(f"Non-finite JSON number: {value}")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object,
                          parse_constant=_invalid_constant)
    except ValueError as error:
        raise ValueError(f"Invalid timing JSON in {path}: {error}") from error


def load_timing(
    path: Path | None = None, *, stage_delay: float | None = None,
    step_delay: float | None = None, wait_seconds: float | None = None,
) -> DemoTiming:
    """Load a complete strict configuration, then apply supplied CLI overrides.

    Overrides do not repair a malformed or incomplete configuration.  Use None
    for an unchanged value; zero remains a valid presentation-delay override.
    """
    config_path = DEFAULT_TIMING_PATH if path is None else Path(path)
    values = _read_json(config_path)
    schema = _read_json(TIMING_SCHEMA_PATH)
    try:
        validate_schema_instance(schema, values)
    except ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "configuration"
        raise ValueError(f"Invalid demo timing in {config_path} ({location}): {error.message}") from error
    overrides = {"stage_delay": stage_delay, "step_delay": step_delay,
                 "wait_seconds": wait_seconds}
    values.update({key: value for key, value in overrides.items() if value is not None})
    return DemoTiming(**values)
