# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from typing import Any, Mapping, Sequence

from .analysis import (
    ApplicationLogError,
    ApplicationLogEvent,
    calculate_recovery_metrics,
    evaluate_event_assertions,
    evaluate_recovery_latency,
    parse_application_log,
)
from .runner import DispatchRecord, ScenarioRunResult
from .scenario import ScenarioDefinition


REPORT_SCHEMA_VERSION = 1


class ReportStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class ScenarioReport:
    status: ReportStatus
    scenario_name: str
    application: Mapping[str, Any] | None
    observations: Mapping[str, Any]
    assertions: tuple[Mapping[str, Any], ...]
    timeline: tuple[Mapping[str, Any], ...]
    error: Mapping[str, str] | None = None
    schema_version: int = REPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "scenario": {"name": self.scenario_name},
            "application": self.application,
            "observations": dict(self.observations),
            "assertions": [dict(item) for item in self.assertions],
            "timeline": [dict(item) for item in self.timeline],
            "error": dict(self.error) if self.error is not None else None,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"


def _application_document(result: ScenarioRunResult) -> dict[str, Any]:
    application = result.application
    return {
        "command": list(application.command),
        "exit_code": application.exit_code,
        "timed_out": application.timed_out,
        "forced": application.forced,
        "stdout": application.stdout,
        "stderr": application.stderr,
    }


def _dispatch_timeline(
    scenario: ScenarioDefinition,
    dispatches: Sequence[DispatchRecord],
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for dispatch in dispatches:
        definition = scenario.events[dispatch.index]
        details = {
            key: value
            for key, value in definition.items()
            if key not in {"action", "at_ms"}
        }
        timeline.append(
            {
                "source": "scenario",
                "event": "FAULT_INJECTED"
                if dispatch.action == "fault"
                else f"{dispatch.action.upper()}_DISPATCHED",
                "timestamp_ms": dispatch.monotonic_finished_ms,
                "event_index": dispatch.index,
                "scheduled_ms": dispatch.scheduled_ms,
                "duration_ms": dispatch.finished_ms - dispatch.started_ms,
                "details": details,
            }
        )
    return timeline


def _application_timeline(
    events: Sequence[ApplicationLogEvent],
) -> list[dict[str, Any]]:
    return [
        {
            "source": "application",
            "event": event.event,
            "timestamp_ms": event.timestamp_ms,
            "line": event.line,
            "details": dict(event.fields),
        }
        for event in events
    ]


def _sorted_timeline(events: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        sorted(
            events,
            key=lambda item: (
                float(item["timestamp_ms"]),
                0 if item["source"] == "scenario" else 1,
            ),
        )
    )


def _first_fault_timestamp(
    scenario: ScenarioDefinition,
    dispatches: Sequence[DispatchRecord],
) -> float | None:
    for dispatch in dispatches:
        if scenario.events[dispatch.index].get("action") == "fault":
            return dispatch.monotonic_finished_ms
    return None


def _causal_duration(end_ms: int | None, start_ms: float | None) -> float | None:
    if end_ms is None or start_ms is None:
        return None
    return end_ms - start_ms


def build_scenario_report(
    scenario: ScenarioDefinition,
    result: ScenarioRunResult,
) -> ScenarioReport:
    application = _application_document(result)
    dispatch_timeline = _dispatch_timeline(scenario, result.dispatches)

    try:
        events = parse_application_log(result.application.stdout)
        metrics = calculate_recovery_metrics(events)
    except ApplicationLogError as error:
        return ScenarioReport(
            status=ReportStatus.ERROR,
            scenario_name=scenario.name,
            application=application,
            observations={},
            assertions=(),
            timeline=_sorted_timeline(dispatch_timeline),
            error={"type": type(error).__name__, "message": str(error)},
        )

    event_assertions = evaluate_event_assertions(events, scenario.assertions)
    assertion_documents: list[Mapping[str, Any]] = [
        {"type": "event_count", **asdict(assertion)}
        for assertion in event_assertions
    ]
    assertion_documents.append(
        {
            "type": "process_exit_code",
            "expected": 0,
            "observed": result.application.exit_code,
            "passed": result.application.exit_code == 0,
        }
    )
    for definition in scenario.assertions:
        maximum_ms = definition.get("max_latency_ms")
        if isinstance(maximum_ms, int) and not isinstance(maximum_ms, bool):
            assertion_documents.append(
                {
                    "type": "recovery_latency",
                    **asdict(evaluate_recovery_latency(metrics, maximum_ms)),
                }
            )

    fault_timestamp_ms = _first_fault_timestamp(scenario, result.dispatches)
    observations = {
        "observed_eio_count": metrics.observed_eio_count,
        "application_retry_count": metrics.application_retry_count,
        "fault_injection_timestamp_ms": fault_timestamp_ms,
        "first_error_timestamp_ms": metrics.first_error_timestamp_ms,
        "recovery_timestamp_ms": metrics.recovery_timestamp_ms,
        "recovery_latency_ms": metrics.recovery_latency_ms,
        "fault_to_first_error_ms": _causal_duration(
            metrics.first_error_timestamp_ms, fault_timestamp_ms
        ),
        "fault_to_recovery_ms": _causal_duration(
            metrics.recovery_timestamp_ms, fault_timestamp_ms
        ),
        "recoveries": [asdict(window) for window in metrics.recoveries],
    }

    assertions_passed = all(
        bool(assertion["passed"]) for assertion in assertion_documents
    )
    if result.application.timed_out:
        status = ReportStatus.TIMEOUT
    elif not assertions_passed:
        status = ReportStatus.FAIL
    else:
        status = ReportStatus.PASS

    return ScenarioReport(
        status=status,
        scenario_name=scenario.name,
        application=application,
        observations=observations,
        assertions=tuple(assertion_documents),
        timeline=_sorted_timeline(
            [*dispatch_timeline, *_application_timeline(events)]
        ),
    )


def build_error_report(scenario_name: str, error: BaseException) -> ScenarioReport:
    return ScenarioReport(
        status=ReportStatus.ERROR,
        scenario_name=scenario_name,
        application=None,
        observations={},
        assertions=(),
        timeline=(),
        error={"type": type(error).__name__, "message": str(error)},
    )
