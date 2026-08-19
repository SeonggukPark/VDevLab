# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

import yaml


SCHEMA_VERSION = 1
MAX_DURATION_MS = 86_400_000
MAX_EIO_REPEAT = 1_000_000
MAX_PARTIAL_READ_BYTES = 4096

_DURATION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)(ms|s)$")
_ROOT_FIELDS = {"schema_version", "device", "application", "scenario", "assertions"}
_LOG_EVENTS = {
    "MONITOR_STARTED",
    "TEMPERATURE",
    "THERMAL_WARNING",
    "READ_RETRY",
    "RECOVERY_SUCCESS",
    "DEVICE_DISCONNECTED",
    "READ_FAILED",
    "INVALID_INPUT",
    "INPUT_TOO_LONG",
}


class ScenarioError(ValueError):
    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


ScenarioValidationError = ScenarioError


@dataclass(frozen=True)
class ScenarioDefinition:
    source: str
    schema_version: int
    device_path: str
    command: tuple[str, ...]
    startup_timeout_ms: int
    name: str
    timeout_ms: int
    events: tuple[Mapping[str, Any], ...]
    assertions: tuple[Mapping[str, Any], ...]


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioValidationError(path, "must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise ScenarioError(path, "field names must be strings")
    return value


def _required(mapping: Mapping[str, Any], fields: set[str], path: str) -> None:
    missing = sorted(fields - mapping.keys())
    if missing:
        raise ScenarioValidationError(
            path, f"missing required field(s): {', '.join(missing)}"
        )


def _allowed(mapping: Mapping[str, Any], fields: set[str], path: str) -> None:
    unexpected = sorted(mapping.keys() - fields)
    if unexpected:
        raise ScenarioValidationError(
            path, f"unexpected field(s): {', '.join(unexpected)}"
        )


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ScenarioValidationError(path, "must be a non-empty string")
    return value


def _bounded_integer(value: Any, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScenarioValidationError(path, "must be an integer")
    if value < minimum or value > maximum:
        raise ScenarioValidationError(path, f"must be between {minimum} and {maximum}")
    return value


def parse_duration(value: Any, path: str = "duration") -> int:
    if not isinstance(value, str):
        raise ScenarioValidationError(path, "must use an ms or s suffix")

    match = _DURATION_PATTERN.fullmatch(value)
    if not match:
        raise ScenarioValidationError(path, "must be an integer duration such as 250ms or 2s")

    magnitude = int(match.group(1))
    milliseconds = magnitude if match.group(2) == "ms" else magnitude * 1000
    if milliseconds > MAX_DURATION_MS:
        raise ScenarioValidationError(path, "must not exceed 24h")
    return milliseconds


def _parse_device(value: Any) -> str:
    device = _mapping(value, "device")
    _required(device, {"path"}, "device")
    _allowed(device, {"path"}, "device")
    path = _non_empty_string(device["path"], "device.path")
    if not path.startswith("/dev/"):
        raise ScenarioValidationError("device.path", "must be an absolute /dev path")
    return path


def _parse_application(value: Any) -> tuple[tuple[str, ...], int]:
    application = _mapping(value, "application")
    _required(application, {"command"}, "application")
    _allowed(application, {"command", "startup_timeout"}, "application")

    command = application["command"]
    if not isinstance(command, list) or not command:
        raise ScenarioValidationError("application.command", "must be a non-empty list")
    parsed_command = tuple(
        _non_empty_string(argument, f"application.command[{index}]")
        for index, argument in enumerate(command)
    )

    startup_timeout_ms = parse_duration(
        application.get("startup_timeout", "2s"), "application.startup_timeout"
    )
    return parsed_command, startup_timeout_ms


def _parse_fault_event(event: Mapping[str, Any], path: str) -> dict[str, Any]:
    _required(event, {"type"}, path)
    fault_type = _non_empty_string(event["type"], f"{path}.type")
    normalized: dict[str, Any] = {"action": "fault", "type": fault_type}

    if fault_type == "eio":
        _required(event, {"at", "action", "type", "repeat"}, path)
        _allowed(event, {"at", "action", "type", "repeat"}, path)
        normalized["repeat"] = _bounded_integer(
            event["repeat"], f"{path}.repeat", 1, MAX_EIO_REPEAT
        )
    elif fault_type == "delay":
        _required(event, {"at", "action", "type", "duration"}, path)
        _allowed(event, {"at", "action", "type", "duration"}, path)
        normalized["duration_ms"] = parse_duration(
            event["duration"], f"{path}.duration"
        )
    elif fault_type == "partial-read":
        _required(event, {"at", "action", "type", "bytes"}, path)
        _allowed(event, {"at", "action", "type", "bytes"}, path)
        normalized["bytes"] = _bounded_integer(
            event["bytes"], f"{path}.bytes", 1, MAX_PARTIAL_READ_BYTES
        )
    elif fault_type == "disconnect":
        _required(event, {"at", "action", "type"}, path)
        _allowed(event, {"at", "action", "type"}, path)
    else:
        raise ScenarioValidationError(
            f"{path}.type", "must be one of: delay, disconnect, eio, partial-read"
        )

    return normalized


def _parse_event(value: Any, index: int, timeout_ms: int) -> tuple[int, int, dict[str, Any]]:
    path = f"scenario.events[{index}]"
    event = _mapping(value, path)
    _required(event, {"at", "action"}, path)

    at_ms = parse_duration(event["at"], f"{path}.at")
    if at_ms > timeout_ms:
        raise ScenarioValidationError(f"{path}.at", "must not exceed scenario.timeout")

    action = _non_empty_string(event["action"], f"{path}.action")
    if action == "write":
        _required(event, {"at", "action", "data"}, path)
        _allowed(event, {"at", "action", "data"}, path)
        normalized = {
            "action": action,
            "data": _non_empty_string(event["data"], f"{path}.data"),
        }
    elif action == "fault":
        normalized = _parse_fault_event(event, path)
    elif action in {"clear", "reset"}:
        _allowed(event, {"at", "action"}, path)
        normalized = {"action": action}
    else:
        raise ScenarioValidationError(
            f"{path}.action", "must be one of: clear, fault, reset, write"
        )

    normalized["at_ms"] = at_ms
    return at_ms, index, normalized


def _parse_scenario(value: Any) -> tuple[str, int, tuple[Mapping[str, Any], ...]]:
    scenario = _mapping(value, "scenario")
    _required(scenario, {"name", "timeout", "events"}, "scenario")
    _allowed(scenario, {"name", "timeout", "events"}, "scenario")

    name = _non_empty_string(scenario["name"], "scenario.name")
    timeout_ms = parse_duration(scenario["timeout"], "scenario.timeout")
    events = scenario["events"]
    if not isinstance(events, list) or not events:
        raise ScenarioValidationError("scenario.events", "must be a non-empty list")

    parsed = [_parse_event(event, index, timeout_ms) for index, event in enumerate(events)]
    for index in range(1, len(parsed)):
        if parsed[index][0] < parsed[index - 1][0]:
            raise ScenarioError(
                f"scenario.events[{index}].at",
                "must not be earlier than the previous event",
            )
    return name, timeout_ms, tuple(item[2] for item in parsed)


def _parse_assertions(value: Any, timeout_ms: int) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or not value:
        raise ScenarioValidationError("assertions", "must be a non-empty list")

    parsed: list[Mapping[str, Any]] = []
    for index, raw_assertion in enumerate(value):
        path = f"assertions[{index}]"
        assertion = _mapping(raw_assertion, path)
        _required(assertion, {"event", "count"}, path)
        _allowed(assertion, {"event", "count", "within", "max_latency"}, path)

        event = _non_empty_string(assertion["event"], f"{path}.event")
        if event not in _LOG_EVENTS:
            raise ScenarioValidationError(f"{path}.event", "is not a supported log event")
        normalized: dict[str, Any] = {
            "event": event,
            "count": _bounded_integer(assertion["count"], f"{path}.count", 1, 1_000_000),
        }
        if "within" in assertion:
            within_ms = parse_duration(assertion["within"], f"{path}.within")
            if within_ms > timeout_ms:
                raise ScenarioValidationError(
                    f"{path}.within", "must not exceed scenario.timeout"
                )
            normalized["within_ms"] = within_ms
        if "max_latency" in assertion:
            if event != "RECOVERY_SUCCESS":
                raise ScenarioValidationError(
                    f"{path}.max_latency",
                    "is only valid for RECOVERY_SUCCESS",
                )
            maximum_latency_ms = parse_duration(
                assertion["max_latency"], f"{path}.max_latency"
            )
            if maximum_latency_ms > timeout_ms:
                raise ScenarioValidationError(
                    f"{path}.max_latency", "must not exceed scenario.timeout"
                )
            normalized["max_latency_ms"] = maximum_latency_ms
        parsed.append(normalized)

    return tuple(parsed)


def parse_scenario(text: str, source: str = "<memory>") -> ScenarioDefinition:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ScenarioValidationError("$", "invalid YAML") from error

    root = _mapping(document, "$")
    _required(root, _ROOT_FIELDS, "$")
    _allowed(root, _ROOT_FIELDS, "$")

    raw_schema_version = root["schema_version"]
    if isinstance(raw_schema_version, bool) or not isinstance(raw_schema_version, int):
        raise ScenarioError("schema_version", "must be an integer")
    if raw_schema_version != SCHEMA_VERSION:
        raise ScenarioError("schema_version", f"must equal {SCHEMA_VERSION}")
    schema_version = raw_schema_version
    device_path = _parse_device(root["device"])
    command, startup_timeout_ms = _parse_application(root["application"])
    name, timeout_ms, events = _parse_scenario(root["scenario"])
    assertions = _parse_assertions(root["assertions"], timeout_ms)

    return ScenarioDefinition(
        source=source,
        schema_version=schema_version,
        device_path=device_path,
        command=command,
        startup_timeout_ms=startup_timeout_ms,
        name=name,
        timeout_ms=timeout_ms,
        events=events,
        assertions=assertions,
    )


def load_scenario(path: str | Path) -> ScenarioDefinition:
    scenario_path = Path(path)
    try:
        text = scenario_path.read_text(encoding="utf-8")
    except OSError as error:
        message = error.strerror or "cannot read file"
        raise ScenarioValidationError(str(scenario_path), message) from error
    return parse_scenario(text, source=str(scenario_path))
