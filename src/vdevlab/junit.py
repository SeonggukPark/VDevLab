# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import json
from xml.etree import ElementTree

from .report import ReportStatus, ScenarioReport


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def report_to_junit_xml(report: ScenarioReport) -> str:
    """Serialize one scenario report as a deterministic JUnit test suite."""

    failures = int(report.status is ReportStatus.FAIL)
    errors = int(report.status in {ReportStatus.ERROR, ReportStatus.TIMEOUT})
    suite = ElementTree.Element(
        "testsuite",
        {
            "name": "vdevlab",
            "tests": "1",
            "failures": str(failures),
            "errors": str(errors),
            "skipped": "0",
        },
    )
    properties = ElementTree.SubElement(suite, "properties")
    ElementTree.SubElement(
        properties,
        "property",
        {"name": "vdevlab.report_schema_version", "value": str(report.schema_version)},
    )
    ElementTree.SubElement(
        properties,
        "property",
        {"name": "vdevlab.status", "value": report.status.value},
    )
    case = ElementTree.SubElement(
        suite,
        "testcase",
        {"classname": "vdevlab.scenario", "name": report.scenario_name},
    )

    if report.status is ReportStatus.FAIL:
        failed_assertions = [
            dict(assertion)
            for assertion in report.assertions
            if assertion.get("passed") is False
        ]
        failure = ElementTree.SubElement(
            case,
            "failure",
            {
                "message": f"{len(failed_assertions)} assertion(s) failed",
                "type": "VDevLabAssertionFailure",
            },
        )
        failure.text = _json_text({"failed_assertions": failed_assertions})
    elif report.status is ReportStatus.ERROR:
        error_document = dict(report.error or {})
        error = ElementTree.SubElement(
            case,
            "error",
            {
                "message": str(error_document.get("message", "scenario report error")),
                "type": str(error_document.get("type", "VDevLabError")),
            },
        )
        error.text = _json_text(error_document)
    elif report.status is ReportStatus.TIMEOUT:
        error = ElementTree.SubElement(
            case,
            "error",
            {"message": "scenario timed out", "type": "VDevLabTimeout"},
        )
        error.text = _json_text(
            {
                "application": dict(report.application or {}),
                "status": report.status.value,
            }
        )

    ElementTree.indent(suite, space="  ")
    return (
        ElementTree.tostring(
            suite,
            encoding="utf-8",
            xml_declaration=True,
        ).decode("utf-8")
        + "\n"
    )
