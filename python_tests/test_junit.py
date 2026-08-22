# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from xml.etree import ElementTree

import pytest

from vdevlab.junit import report_to_junit_xml
from vdevlab.report import ReportStatus, ScenarioReport


def _report(status: ReportStatus) -> ScenarioReport:
    assertions = (
        {
            "type": "event_count",
            "event": "TEMPERATURE",
            "expected": 1,
            "observed": 0,
            "passed": False,
        },
    ) if status is ReportStatus.FAIL else ()
    error = (
        {"type": "RunnerError", "message": "device <unavailable>"}
        if status is ReportStatus.ERROR
        else None
    )
    application = (
        {"exit_code": -15, "timed_out": True}
        if status is ReportStatus.TIMEOUT
        else {"exit_code": 0, "timed_out": False}
    )
    return ScenarioReport(
        status=status,
        scenario_name="sensor<&scenario",
        application=application,
        observations={},
        assertions=assertions,
        timeline=(),
        error=error,
    )


@pytest.mark.parametrize(
    ("status", "failures", "errors", "outcome"),
    (
        (ReportStatus.PASS, "0", "0", None),
        (ReportStatus.FAIL, "1", "0", "failure"),
        (ReportStatus.ERROR, "0", "1", "error"),
        (ReportStatus.TIMEOUT, "0", "1", "error"),
    ),
)
def test_junit_status_mapping_is_parseable(
    status: ReportStatus,
    failures: str,
    errors: str,
    outcome: str | None,
) -> None:
    root = ElementTree.fromstring(report_to_junit_xml(_report(status)))

    assert root.tag == "testsuite"
    assert root.attrib == {
        "name": "vdevlab",
        "tests": "1",
        "failures": failures,
        "errors": errors,
        "skipped": "0",
    }
    case = root.find("testcase")
    assert case is not None
    assert case.attrib == {
        "classname": "vdevlab.scenario",
        "name": "sensor<&scenario",
    }
    if outcome is None:
        assert case.find("failure") is None
        assert case.find("error") is None
    else:
        assert case.find(outcome) is not None


def test_junit_failure_contains_failed_assertion() -> None:
    root = ElementTree.fromstring(report_to_junit_xml(_report(ReportStatus.FAIL)))
    failure = root.find("testcase/failure")

    assert failure is not None
    assert failure.attrib == {
        "message": "1 assertion(s) failed",
        "type": "VDevLabAssertionFailure",
    }
    assert '"event": "TEMPERATURE"' in (failure.text or "")


def test_junit_error_and_timeout_have_deterministic_types() -> None:
    error_root = ElementTree.fromstring(
        report_to_junit_xml(_report(ReportStatus.ERROR))
    )
    timeout_root = ElementTree.fromstring(
        report_to_junit_xml(_report(ReportStatus.TIMEOUT))
    )
    error = error_root.find("testcase/error")
    timeout = timeout_root.find("testcase/error")

    assert error is not None
    assert timeout is not None
    assert error.attrib == {
        "message": "device <unavailable>",
        "type": "RunnerError",
    }
    assert timeout.attrib == {
        "message": "scenario timed out",
        "type": "VDevLabTimeout",
    }


def test_junit_serialization_is_stable() -> None:
    report = _report(ReportStatus.FAIL)

    first = report_to_junit_xml(report)
    second = report_to_junit_xml(report)

    assert first == second
    assert first.startswith("<?xml version='1.0' encoding='utf-8'?>")
    assert first.endswith("\n")
