# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from vdevlab.cli import main
from vdevlab.scenario import (
    ScenarioValidationError,
    parse_duration,
    parse_scenario,
)


VALID_DOCUMENT = {
    "schema_version": 1,
    "device": {"path": "/dev/vdevlab0"},
    "application": {
        "command": ["./examples/vtemp-monitor"],
        "startup_timeout": "2s",
    },
    "scenario": {
        "name": "valid-scenario",
        "timeout": "5s",
        "events": [
            {"at": "0ms", "action": "reset"},
            {"at": "100ms", "action": "write", "data": "25\n"},
        ],
    },
    "assertions": [{"event": "TEMPERATURE", "count": 1, "within": "2s"}],
}


def parse_document(document: dict = VALID_DOCUMENT):
    return parse_scenario(yaml.safe_dump(document, sort_keys=False))


def assert_error(document: dict, expected: str) -> None:
    with pytest.raises(ScenarioValidationError, match=expected):
        parse_document(document)


def test_duration_parser_accepts_ms_and_s() -> None:
    assert parse_duration("250ms") == 250
    assert parse_duration("2s") == 2000


@pytest.mark.parametrize("value", [250, "1.5s", "01s", "2m", "-1ms"])
def test_duration_parser_rejects_ambiguous_values(value: object) -> None:
    with pytest.raises(ScenarioValidationError):
        parse_duration(value)


def test_valid_document_is_normalized() -> None:
    scenario = parse_document()

    assert scenario.schema_version == 1
    assert scenario.device_path == "/dev/vdevlab0"
    assert scenario.startup_timeout_ms == 2000
    assert scenario.timeout_ms == 5000
    assert scenario.events[1]["at_ms"] == 100
    assert scenario.assertions[0]["within_ms"] == 2000


@pytest.mark.parametrize("name", ["normal.yaml", "recovery.yaml", "disconnect.yaml"])
def test_checked_in_examples_are_valid(name: str) -> None:
    path = Path(__file__).parents[1] / "examples" / "scenarios" / name
    scenario = parse_scenario(path.read_text(encoding="utf-8"), source=str(path))

    assert scenario.events
    assert scenario.assertions


def test_missing_root_field_has_stable_error() -> None:
    document = deepcopy(VALID_DOCUMENT)
    del document["assertions"]
    assert_error(document, r"\$: missing required field\(s\): assertions")


def test_unexpected_root_field_has_stable_error() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["unknown"] = True
    assert_error(document, r"\$: unexpected field\(s\): unknown")


def test_schema_version_rejects_boolean() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["schema_version"] = True
    assert_error(document, r"schema_version: must be an integer")


def test_unsupported_schema_version_has_stable_error() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["schema_version"] = 2
    assert_error(document, r"schema_version: must equal 1")


def test_non_string_field_name_is_rejected() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["device"][1] = "invalid"
    assert_error(document, r"device: field names must be strings")


def test_device_must_use_dev_path() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["device"]["path"] = "relative-device"
    assert_error(document, r"device.path: must be an absolute /dev path")


def test_application_command_rejects_shell_string() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["application"]["command"] = "./examples/vtemp-monitor"
    assert_error(document, r"application.command: must be a non-empty list")


def test_unknown_action_is_rejected() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = [{"at": "0ms", "action": "sleep"}]
    assert_error(
        document,
        r"scenario.events\[0\].action: must be one of: clear, fault, reset, write",
    )


def test_write_event_rejects_fault_field() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = [
        {"at": "0ms", "action": "write", "data": "25\n", "repeat": 1}
    ]
    assert_error(document, r"scenario.events\[0\]: unexpected field\(s\): repeat")


@pytest.mark.parametrize("repeat", [0, True, 1_000_001])
def test_eio_repeat_range_is_enforced(repeat: object) -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = [
        {"at": "0ms", "action": "fault", "type": "eio", "repeat": repeat}
    ]
    with pytest.raises(ScenarioValidationError):
        parse_document(document)


def test_delay_requires_duration() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = [
        {"at": "0ms", "action": "fault", "type": "delay"}
    ]
    assert_error(document, r"scenario.events\[0\]: missing required field\(s\): duration")


@pytest.mark.parametrize("byte_count", [0, True, 4097])
def test_partial_read_byte_range_is_enforced(byte_count: object) -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = [
        {
            "at": "0ms",
            "action": "fault",
            "type": "partial-read",
            "bytes": byte_count,
        }
    ]
    with pytest.raises(ScenarioValidationError):
        parse_document(document)


def test_event_must_fit_scenario_timeout() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = [{"at": "6s", "action": "reset"}]
    assert_error(
        document, r"scenario.events\[0\].at: must not exceed scenario.timeout"
    )


def test_empty_scenario_is_rejected() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = []
    assert_error(document, r"scenario.events: must be a non-empty list")


def test_event_time_reversal_is_rejected() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = [
        {"at": "2s", "action": "write", "data": "A\n"},
        {"at": "1s", "action": "reset"},
    ]
    assert_error(
        document,
        r"scenario.events\[1\].at: must not be earlier than the previous event",
    )


def test_equal_event_times_preserve_yaml_order() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["scenario"]["events"] = [
        {"at": "2s", "action": "write", "data": "A\n"},
        {"at": "2s", "action": "write", "data": "B\n"},
    ]
    scenario = parse_document(document)

    assert scenario.events[0]["data"] == "A\n"
    assert scenario.events[1]["data"] == "B\n"


def test_assertion_event_must_be_supported() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["assertions"][0]["event"] = "UNKNOWN"
    assert_error(document, r"assertions\[0\].event: is not a supported log event")


def test_assertion_window_must_fit_timeout() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["assertions"][0]["within"] = "6s"
    assert_error(document, r"assertions\[0\].within: must not exceed scenario.timeout")


def test_recovery_assertion_normalizes_maximum_latency() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["assertions"] = [
        {
            "event": "RECOVERY_SUCCESS",
            "count": 1,
            "max_latency": "500ms",
        }
    ]

    scenario = parse_document(document)

    assert scenario.assertions[0]["max_latency_ms"] == 500


def test_maximum_latency_requires_recovery_event() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["assertions"][0]["max_latency"] = "500ms"
    assert_error(
        document,
        r"assertions\[0\].max_latency: is only valid for RECOVERY_SUCCESS",
    )


def test_maximum_latency_must_fit_timeout() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["assertions"] = [
        {
            "event": "RECOVERY_SUCCESS",
            "count": 1,
            "max_latency": "6s",
        }
    ]
    assert_error(
        document,
        r"assertions\[0\].max_latency: must not exceed scenario.timeout",
    )


def test_additional_assertion_types_are_normalized() -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["assertions"] = [
        {
            "type": "stdout",
            "contains": "RECOVERY_SUCCESS",
            "not_contains": "READ_FAILED",
        },
        {"type": "disconnect", "expected": True},
        {"type": "kernel_warnings", "count": 0},
    ]

    scenario = parse_document(document)

    assert scenario.assertions == (
        {
            "type": "stdout",
            "contains": "RECOVERY_SUCCESS",
            "not_contains": "READ_FAILED",
        },
        {"type": "disconnect", "expected": True},
        {"type": "kernel_warnings", "count": 0},
    )


@pytest.mark.parametrize(
    ("assertion", "message"),
    (
        ({"type": "stdout"}, "requires contains or not_contains"),
        ({"type": "stdout", "contains": ""}, r"contains: must be"),
        ({"type": "disconnect", "expected": 1}, r"expected: must be a boolean"),
        ({"type": "kernel_warnings", "count": -1}, r"count: must be between"),
        ({"type": "unknown"}, r"type: must be one of"),
    ),
)
def test_additional_assertions_reject_invalid_values(
    assertion: dict[str, object], message: str
) -> None:
    document = deepcopy(VALID_DOCUMENT)
    document["assertions"] = [assertion]

    assert_error(document, rf"assertions\[0\].*{message}")


def test_invalid_yaml_has_stable_error() -> None:
    with pytest.raises(ScenarioValidationError, match=r"\$: invalid YAML"):
        parse_scenario("[unclosed")


def test_cli_validates_multiple_files(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).parents[1]
    paths = [
        str(root / "examples" / "scenarios" / "normal.yaml"),
        str(root / "examples" / "scenarios" / "recovery.yaml"),
    ]

    assert main(["validate", *paths]) == 0
    assert capsys.readouterr().out.count("valid:") == 2


def test_cli_expands_wildcards_on_windows(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).parents[1]
    pattern = str(root / "examples" / "scenarios" / "*.yaml")

    assert main(["validate", pattern]) == 0
    assert capsys.readouterr().out.count("valid:") == 3


def test_cli_returns_two_for_invalid_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("schema_version: 1\n", encoding="utf-8")

    assert main(["validate", str(path)]) == 2
    assert "missing required field(s)" in capsys.readouterr().err
