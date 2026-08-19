# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from vdevlab.report import (
    REPORT_SCHEMA_VERSION,
    ReportStatus,
    build_error_report,
    build_scenario_report,
)
from vdevlab.runner import ApplicationResult, DispatchRecord, ScenarioRunResult
from vdevlab.scenario import load_scenario


ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "examples" / "reports"
SCENARIO = load_scenario(ROOT / "examples" / "scenarios" / "recovery.yaml")
DISCONNECT_SCENARIO = load_scenario(
    ROOT / "examples" / "scenarios" / "disconnect.yaml"
)

PASSING_LOG = """\
{"timestamp_ms":100000,"event":"MONITOR_STARTED"}
{"timestamp_ms":100110,"event":"READ_RETRY","retry":1,"max_retries":3,"errno":5}
{"timestamp_ms":100120,"event":"READ_RETRY","retry":2,"max_retries":3,"errno":5}
{"timestamp_ms":100130,"event":"READ_RETRY","retry":3,"max_retries":3,"errno":5}
{"timestamp_ms":100210,"event":"RECOVERY_SUCCESS","retries":3}
{"timestamp_ms":100210,"event":"TEMPERATURE","temperature_c":42.0}
"""


def _dispatch(
    index: int,
    action: str,
    scheduled_ms: int,
    timestamp_ms: float,
) -> DispatchRecord:
    return DispatchRecord(
        index=index,
        action=action,
        scheduled_ms=scheduled_ms,
        started_ms=float(scheduled_ms),
        finished_ms=float(scheduled_ms),
        monotonic_started_ms=timestamp_ms,
        monotonic_finished_ms=timestamp_ms,
    )


def _result(
    stdout: str = PASSING_LOG,
    *,
    exit_code: int = 0,
    timed_out: bool = False,
) -> ScenarioRunResult:
    return ScenarioRunResult(
        scenario_name=SCENARIO.name,
        dispatches=(
            _dispatch(0, "reset", 0, 100000.0),
            _dispatch(1, "fault", 100, 100100.0),
            _dispatch(2, "write", 200, 100200.0),
        ),
        application=ApplicationResult(
            command=SCENARIO.command,
            exit_code=exit_code,
            stdout=stdout,
            stderr="",
            timed_out=timed_out,
        ),
        kernel_log_available=True,
    )


def test_build_passing_causal_report() -> None:
    report = build_scenario_report(SCENARIO, _result())
    document = report.to_dict()

    assert report.status is ReportStatus.PASS
    assert document["schema_version"] == REPORT_SCHEMA_VERSION
    assert document["observations"] == {
        "observed_eio_count": 3,
        "application_retry_count": 3,
        "fault_injection_timestamp_ms": 100100,
        "first_error_timestamp_ms": 100110,
        "recovery_timestamp_ms": 100210,
        "recovery_latency_ms": 100,
        "fault_to_first_error_ms": 10,
        "fault_to_recovery_ms": 110,
        "recoveries": [
            {
                "first_error_timestamp_ms": 100110,
                "recovery_timestamp_ms": 100210,
                "recovery_latency_ms": 100,
                "observed_retries": 3,
                "reported_retries": 3,
            }
        ],
        "disconnected": False,
        "kernel_log": {
            "available": True,
            "warning_count": 0,
            "warnings": [],
            "error": None,
        },
    }
    assert all(item["passed"] for item in document["assertions"])
    assert [item["event"] for item in document["timeline"]] == [
        "RESET_DISPATCHED",
        "MONITOR_STARTED",
        "FAULT_INJECTED",
        "READ_RETRY",
        "READ_RETRY",
        "READ_RETRY",
        "WRITE_DISPATCHED",
        "RECOVERY_SUCCESS",
        "TEMPERATURE",
    ]


def test_failed_assertion_produces_fail_report() -> None:
    two_retry_log = PASSING_LOG.replace(
        '{"timestamp_ms":100130,"event":"READ_RETRY","retry":3,"max_retries":3,"errno":5}\n',
        "",
    ).replace('"retries":3', '"retries":2')

    report = build_scenario_report(SCENARIO, _result(two_retry_log))

    assert report.status is ReportStatus.FAIL
    failed = [item for item in report.assertions if not item["passed"]]
    assert len(failed) == 1
    assert failed[0]["event"] == "READ_RETRY"
    assert failed[0]["expected"] == 3
    assert failed[0]["observed"] == 2


def test_forbidden_stdout_event_produces_fail_report() -> None:
    stdout = PASSING_LOG + (
        '{"timestamp_ms":100220,"event":"READ_FAILED","errno":5}\n'
    )

    report = build_scenario_report(SCENARIO, _result(stdout))

    assert report.status is ReportStatus.FAIL
    stdout_assertion = next(
        item
        for item in report.assertions
        if item["type"] == "stdout" and item["operator"] == "not_contains"
    )
    assert stdout_assertion == {
        "type": "stdout",
        "operator": "not_contains",
        "text": "READ_FAILED",
        "passed": False,
    }


def test_dispatch_timestamp_uses_application_log_resolution() -> None:
    result = _result()
    fault = replace(
        result.dispatches[1],
        monotonic_started_ms=100100.9,
        monotonic_finished_ms=100101.1,
    )
    result = replace(
        result,
        dispatches=(result.dispatches[0], fault, result.dispatches[2]),
    )

    report = build_scenario_report(SCENARIO, result)

    assert report.observations["fault_injection_timestamp_ms"] == 100100
    assert report.observations["fault_to_first_error_ms"] == 10
    fault_index = next(
        index
        for index, item in enumerate(report.timeline)
        if item["event"] == "FAULT_INJECTED"
    )
    retry_index = next(
        index
        for index, item in enumerate(report.timeline)
        if item["event"] == "READ_RETRY"
    )
    assert fault_index < retry_index


def test_passing_report_example_matches_generator() -> None:
    expected = (REPORTS / "recovery-pass.json").read_text()

    assert build_scenario_report(SCENARIO, _result()).to_json() == expected


def test_failing_report_example_matches_generator() -> None:
    two_retry_log = PASSING_LOG.replace(
        '{"timestamp_ms":100130,"event":"READ_RETRY","retry":3,"max_retries":3,"errno":5}\n',
        "",
    ).replace('"retries":3', '"retries":2')
    expected = (REPORTS / "recovery-fail.json").read_text()

    assert build_scenario_report(SCENARIO, _result(two_retry_log)).to_json() == expected


def test_nonzero_exit_produces_fail_report() -> None:
    report = build_scenario_report(SCENARIO, _result(exit_code=7))

    assert report.status is ReportStatus.FAIL
    assert report.application is not None
    assert report.application["exit_code"] == 7
    exit_assertion = next(
        item for item in report.assertions if item["type"] == "process_exit_code"
    )
    assert exit_assertion == {
        "type": "process_exit_code",
        "expected": 0,
        "observed": 7,
        "passed": False,
    }


def test_timeout_produces_timeout_report() -> None:
    report = build_scenario_report(SCENARIO, _result(timed_out=True))

    assert report.status is ReportStatus.TIMEOUT
    assert report.application is not None
    assert report.application["timed_out"] is True


def test_unavailable_required_kernel_log_produces_error_report() -> None:
    result = replace(
        _result(),
        kernel_log_available=False,
        kernel_log_error="Operation not permitted",
    )

    report = build_scenario_report(SCENARIO, result)

    assert report.status is ReportStatus.ERROR
    assert report.error == {
        "type": "KernelLogUnavailable",
        "message": "Operation not permitted",
    }
    kernel_assertion = next(
        item for item in report.assertions if item["type"] == "kernel_warnings"
    )
    assert kernel_assertion["available"] is False
    assert kernel_assertion["passed"] is False


def test_observed_kernel_warning_produces_fail_report() -> None:
    result = replace(
        _result(),
        kernel_warnings=("WARNING: vdevlab test warning",),
    )

    report = build_scenario_report(SCENARIO, result)

    assert report.status is ReportStatus.FAIL
    assert report.observations["kernel_log"]["warning_count"] == 1


def test_disconnect_assertion_uses_structured_application_event() -> None:
    stdout = """\
{"timestamp_ms":100000,"event":"MONITOR_STARTED"}
{"timestamp_ms":100100,"event":"TEMPERATURE","temperature_c":25.0}
{"timestamp_ms":100210,"event":"DEVICE_DISCONNECTED","errno":19}
"""
    result = ScenarioRunResult(
        scenario_name=DISCONNECT_SCENARIO.name,
        dispatches=(
            _dispatch(0, "reset", 0, 100000.0),
            _dispatch(1, "write", 100, 100100.0),
            _dispatch(2, "fault", 200, 100200.0),
        ),
        application=ApplicationResult(
            command=DISCONNECT_SCENARIO.command,
            exit_code=0,
            stdout=stdout,
            stderr="",
        ),
        kernel_log_available=True,
    )

    report = build_scenario_report(DISCONNECT_SCENARIO, result)

    assert report.status is ReportStatus.PASS
    assert report.observations["disconnected"] is True
    disconnect_assertion = next(
        item for item in report.assertions if item["type"] == "disconnect"
    )
    assert disconnect_assertion["observed"] is True
    assert disconnect_assertion["passed"] is True


def test_invalid_application_log_produces_error_report() -> None:
    report = build_scenario_report(SCENARIO, _result("not-json\n"))

    assert report.status is ReportStatus.ERROR
    assert report.error == {
        "type": "ApplicationLogError",
        "message": "stdout[1]: invalid JSON",
    }
    assert [item["event"] for item in report.timeline] == [
        "RESET_DISPATCHED",
        "FAULT_INJECTED",
        "WRITE_DISPATCHED",
    ]


def test_external_execution_error_produces_error_report() -> None:
    report = build_error_report(SCENARIO.name, RuntimeError("device unavailable"))

    assert report.status is ReportStatus.ERROR
    assert report.application is None
    assert report.error == {
        "type": "RuntimeError",
        "message": "device unavailable",
    }


def test_report_serialization_is_stable_json() -> None:
    report = build_scenario_report(SCENARIO, _result())

    first = report.to_json()
    second = report.to_json()

    assert first == second
    assert first.endswith("\n")
    assert json.loads(first) == report.to_dict()
    assert first.index('"schema_version"') < first.index('"status"')
