# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import errno
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class ApplicationLogError(ValueError):
    """Raised when an application JSONL event stream is invalid."""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"stdout[{line}]: {message}")
        self.line = line
        self.message = message


@dataclass(frozen=True)
class ApplicationLogEvent:
    line: int
    timestamp_ms: int
    event: str
    fields: Mapping[str, Any]


@dataclass(frozen=True)
class RecoveryWindow:
    first_error_timestamp_ms: int
    recovery_timestamp_ms: int
    recovery_latency_ms: int
    observed_retries: int
    reported_retries: int


@dataclass(frozen=True)
class RecoveryMetrics:
    observed_eio_count: int
    application_retry_count: int
    recoveries: tuple[RecoveryWindow, ...]
    first_error_timestamp_ms: int | None
    recovery_timestamp_ms: int | None
    recovery_latency_ms: int | None


@dataclass(frozen=True)
class RetryAssertion:
    expected: int
    observed: int
    passed: bool


@dataclass(frozen=True)
class RecoveryLatencyAssertion:
    maximum_ms: int
    observed_ms: int | None
    passed: bool


@dataclass(frozen=True)
class EventCountAssertion:
    event: str
    expected: int
    observed: int
    within_ms: int | None
    passed: bool


@dataclass(frozen=True)
class StdoutAssertion:
    operator: str
    text: str
    passed: bool


@dataclass(frozen=True)
class DisconnectAssertion:
    expected: bool
    observed: bool
    passed: bool


@dataclass(frozen=True)
class KernelWarningAssertion:
    expected: int
    observed: int | None
    available: bool
    passed: bool


def _require_nonnegative_integer(
    value: object, *, line: int, field: str
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ApplicationLogError(line, f"{field} must be a non-negative integer")
    return value


def parse_application_log(text: str) -> tuple[ApplicationLogEvent, ...]:
    """Parse the monitor's JSONL stdout into validated application events."""

    events: list[ApplicationLogEvent] = []
    previous_timestamp: int | None = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue

        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ApplicationLogError(line_number, "invalid JSON") from exc

        if not isinstance(value, dict):
            raise ApplicationLogError(line_number, "event must be a JSON object")

        timestamp_ms = _require_nonnegative_integer(
            value.get("timestamp_ms"), line=line_number, field="timestamp_ms"
        )
        if previous_timestamp is not None and timestamp_ms < previous_timestamp:
            raise ApplicationLogError(
                line_number, "timestamp_ms must be monotonically non-decreasing"
            )

        event = value.get("event")
        if not isinstance(event, str) or not event.strip():
            raise ApplicationLogError(line_number, "event must be a non-empty string")

        fields = {
            key: field_value
            for key, field_value in value.items()
            if key not in {"timestamp_ms", "event"}
        }
        events.append(
            ApplicationLogEvent(
                line=line_number,
                timestamp_ms=timestamp_ms,
                event=event,
                fields=fields,
            )
        )
        previous_timestamp = timestamp_ms

    return tuple(events)


def calculate_recovery_metrics(
    events: Sequence[ApplicationLogEvent],
) -> RecoveryMetrics:
    """Calculate retry and completed recovery observations from application events."""

    observed_eio_count = 0
    application_retry_count = 0
    recoveries: list[RecoveryWindow] = []
    first_observed_error_timestamp_ms: int | None = None
    first_error_timestamp_ms: int | None = None
    active_retry_count = 0

    for event in events:
        if event.event == "READ_RETRY":
            retry_errno = _require_nonnegative_integer(
                event.fields.get("errno"), line=event.line, field="errno"
            )
            _require_nonnegative_integer(
                event.fields.get("retry"), line=event.line, field="retry"
            )
            application_retry_count += 1
            active_retry_count += 1
            if retry_errno == errno.EIO:
                observed_eio_count += 1
            if first_observed_error_timestamp_ms is None:
                first_observed_error_timestamp_ms = event.timestamp_ms
            if first_error_timestamp_ms is None:
                first_error_timestamp_ms = event.timestamp_ms

        elif event.event == "RECOVERY_SUCCESS":
            reported_retries = _require_nonnegative_integer(
                event.fields.get("retries"), line=event.line, field="retries"
            )
            if first_error_timestamp_ms is None:
                raise ApplicationLogError(
                    event.line, "RECOVERY_SUCCESS has no preceding READ_RETRY"
                )
            recoveries.append(
                RecoveryWindow(
                    first_error_timestamp_ms=first_error_timestamp_ms,
                    recovery_timestamp_ms=event.timestamp_ms,
                    recovery_latency_ms=event.timestamp_ms
                    - first_error_timestamp_ms,
                    observed_retries=active_retry_count,
                    reported_retries=reported_retries,
                )
            )
            first_error_timestamp_ms = None
            active_retry_count = 0

    first_recovery = recoveries[0] if recoveries else None
    return RecoveryMetrics(
        observed_eio_count=observed_eio_count,
        application_retry_count=application_retry_count,
        recoveries=tuple(recoveries),
        first_error_timestamp_ms=first_observed_error_timestamp_ms,
        recovery_timestamp_ms=(
            first_recovery.recovery_timestamp_ms if first_recovery else None
        ),
        recovery_latency_ms=(
            first_recovery.recovery_latency_ms if first_recovery else None
        ),
    )


def evaluate_retry_count(metrics: RecoveryMetrics, expected: int) -> RetryAssertion:
    expected_count = _require_nonnegative_integer(
        expected, line=0, field="expected retry count"
    )
    return RetryAssertion(
        expected=expected_count,
        observed=metrics.application_retry_count,
        passed=metrics.application_retry_count == expected_count,
    )


def evaluate_recovery_latency(
    metrics: RecoveryMetrics, maximum_ms: int
) -> RecoveryLatencyAssertion:
    maximum = _require_nonnegative_integer(
        maximum_ms, line=0, field="maximum recovery latency"
    )
    observed = max(
        (window.recovery_latency_ms for window in metrics.recoveries),
        default=None,
    )
    return RecoveryLatencyAssertion(
        maximum_ms=maximum,
        observed_ms=observed,
        passed=observed is not None and observed <= maximum,
    )


def evaluate_event_assertions(
    events: Sequence[ApplicationLogEvent],
    definitions: Sequence[Mapping[str, Any]],
) -> tuple[EventCountAssertion, ...]:
    """Evaluate validated scenario event-count assertions against application logs."""

    origin_timestamp_ms = events[0].timestamp_ms if events else None
    results: list[EventCountAssertion] = []

    for definition in definitions:
        event = definition.get("event")
        if not isinstance(event, str) or not event:
            raise ValueError("assertion event must be a non-empty string")

        expected = definition.get("count")
        if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0:
            raise ValueError("assertion count must be a positive integer")

        within_ms = definition.get("within_ms")
        if within_ms is not None and (
            isinstance(within_ms, bool)
            or not isinstance(within_ms, int)
            or within_ms < 0
        ):
            raise ValueError("assertion within_ms must be a non-negative integer")

        observed = sum(
            1
            for item in events
            if item.event == event
            and (
                within_ms is None
                or (
                    origin_timestamp_ms is not None
                    and item.timestamp_ms - origin_timestamp_ms <= within_ms
                )
            )
        )
        results.append(
            EventCountAssertion(
                event=event,
                expected=expected,
                observed=observed,
                within_ms=within_ms,
                passed=observed == expected,
            )
        )

    return tuple(results)


def evaluate_stdout_assertion(
    stdout: str,
    definition: Mapping[str, Any],
) -> tuple[StdoutAssertion, ...]:
    results: list[StdoutAssertion] = []
    contains = definition.get("contains")
    if isinstance(contains, str):
        results.append(
            StdoutAssertion(
                operator="contains",
                text=contains,
                passed=contains in stdout,
            )
        )
    not_contains = definition.get("not_contains")
    if isinstance(not_contains, str):
        results.append(
            StdoutAssertion(
                operator="not_contains",
                text=not_contains,
                passed=not_contains not in stdout,
            )
        )
    if not results:
        raise ValueError("stdout assertion requires contains or not_contains")
    return tuple(results)


def evaluate_disconnect(
    events: Sequence[ApplicationLogEvent], expected: bool
) -> DisconnectAssertion:
    if not isinstance(expected, bool):
        raise ValueError("disconnect expected value must be a boolean")
    observed = any(event.event == "DEVICE_DISCONNECTED" for event in events)
    return DisconnectAssertion(
        expected=expected,
        observed=observed,
        passed=observed is expected,
    )


def evaluate_kernel_warnings(
    warnings: Sequence[str],
    expected: int,
    *,
    available: bool,
) -> KernelWarningAssertion:
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise ValueError("kernel warning count must be a non-negative integer")
    observed = len(warnings) if available else None
    return KernelWarningAssertion(
        expected=expected,
        observed=observed,
        available=available,
        passed=available and observed == expected,
    )
