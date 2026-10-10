"""Strict local timing configuration never changes protocol capabilities."""

from dataclasses import FrozenInstanceError
import json

import pytest

from examples.protocol_demo.timing import DemoTiming, load_timing


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "timing.json"
    path.write_text(json.dumps({"stage_delay": 0.7, "step_delay": 0.3,
                                "wait_seconds": 1.2}), encoding="utf-8")
    return path


def test_programmatic_defaults_are_fast_and_immutable():
    timing = DemoTiming()
    assert timing == DemoTiming(stage_delay=0, step_delay=0, wait_seconds=0.15)
    with pytest.raises(FrozenInstanceError):
        timing.stage_delay = 1


def test_editable_viewing_defaults_are_slower():
    assert load_timing() == DemoTiming(stage_delay=0.7, step_delay=0.3, wait_seconds=1.2)


def test_overrides_preserve_zero_and_unchanged_values(config_file):
    assert load_timing(config_file, stage_delay=0, step_delay=0) == DemoTiming(0, 0, 1.2)
    assert load_timing(config_file, wait_seconds=0.05) == DemoTiming(0.7, 0.3, 0.05)


@pytest.mark.parametrize("field,value", [
    ("stage_delay", -0.01), ("stage_delay", 10.01),
    ("step_delay", -0.01), ("step_delay", 10.01),
    ("wait_seconds", 0.049), ("wait_seconds", 3.01),
    ("stage_delay", float("nan")), ("step_delay", float("inf")),
    ("wait_seconds", float("-inf")), ("stage_delay", True),
    ("step_delay", "0.3"), ("wait_seconds", None),
    ("stage_delay", 10**1000),
])
def test_constructor_rejects_invalid_or_non_numeric_durations(field, value):
    with pytest.raises(ValueError, match=field):
        DemoTiming(**{field: value})


def test_inclusive_bounds():
    assert DemoTiming(0, 10, 0.05).wait_seconds == 0.05
    assert DemoTiming(10, 0, 3).stage_delay == 10


@pytest.mark.parametrize("text,reason", [
    ('{"stage_delay":0,"stage_delay":1,"step_delay":0,"wait_seconds":0.15}', "Duplicate JSON key"),
    ('{"stage_delay":NaN,"step_delay":0,"wait_seconds":0.15}', "Non-finite JSON number"),
    ('{"stage_delay":0,"step_delay":Infinity,"wait_seconds":0.15}', "Non-finite JSON number"),
    ('{"stage_delay":0,"step_delay":0,"wait_seconds":-Infinity}', "Non-finite JSON number"),
    ('{"stage_delay":0,"step_delay":0,"wait_seconds":0.15,"extra":1}', "Additional properties"),
    ('{"stage_delay":0,"step_delay":0}', "required property"),
    ('{"stage_delay":true,"step_delay":0,"wait_seconds":0.15}', "not of type"),
    ('{"stage_delay":0,"step_delay":"0.3","wait_seconds":0.15}', "not of type"),
    ('{"stage_delay":0,"step_delay":0,"wait_seconds":null}', "not of type"),
    ('{"stage_delay":1e999,"step_delay":0,"wait_seconds":0.15}', "greater than"),
    ('[0,0,0.15]', "not of type"),
])
def test_loader_rejects_ambiguous_or_invalid_json(config_file, text, reason):
    config_file.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        load_timing(config_file)


def test_override_cannot_repair_an_incomplete_config(config_file):
    config_file.write_text('{"stage_delay":0,"step_delay":0}', encoding="utf-8")
    with pytest.raises(ValueError, match="required property"):
        load_timing(config_file, wait_seconds=0.2)


@pytest.mark.parametrize("overrides", [{"stage_delay": True}, {"step_delay": 11},
                                      {"wait_seconds": float("nan")}])
def test_overrides_are_validated(config_file, overrides):
    with pytest.raises(ValueError):
        load_timing(config_file, **overrides)
