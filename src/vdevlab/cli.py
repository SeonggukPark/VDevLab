# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import argparse
from collections.abc import Sequence
from glob import glob, has_magic
from pathlib import Path
import sys

from . import __version__
from .junit import report_to_junit_xml
from .report import (
    ReportStatus,
    ScenarioReport,
    build_error_report,
    build_scenario_report,
)
from .runner import RunnerError, ScenarioRunner
from .scenario import ScenarioValidationError, load_scenario


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vdevlab")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate scenario YAML")
    validate.add_argument("paths", nargs="+", help="scenario YAML path")

    run = commands.add_parser("run", help="run a scenario against its device")
    run.add_argument("path", help="scenario YAML path")
    run.add_argument("--cwd", default=".", help="application working directory")
    run.add_argument("--report", help="write a causal JSON report to this path")
    run.add_argument("--junit-xml", help="write a JUnit XML report to this path")
    return parser


def _write_reports(
    json_path: str | None,
    junit_path: str | None,
    report: ScenarioReport,
) -> None:
    if json_path is not None:
        Path(json_path).write_text(report.to_json(), encoding="utf-8")
    if junit_path is not None:
        Path(junit_path).write_text(report_to_junit_xml(report), encoding="utf-8")


def _write_error_report(
    json_path: str | None,
    junit_path: str | None,
    scenario_name: str,
    error: BaseException,
) -> bool:
    try:
        _write_reports(
            json_path,
            junit_path,
            build_error_report(scenario_name, error),
        )
    except OSError as report_error:
        print(f"error: cannot write report: {report_error}", file=sys.stderr)
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)

    if arguments.command == "validate":
        paths: list[str] = []
        for path in arguments.paths:
            matches = sorted(glob(path)) if has_magic(path) else [path]
            paths.extend(matches or [path])

        for path in paths:
            try:
                scenario = load_scenario(path)
            except ScenarioValidationError as error:
                print(f"error: {error}", file=sys.stderr)
                return 2

            print(
                f"valid: {path} name={scenario.name} "
                f"events={len(scenario.events)} assertions={len(scenario.assertions)}"
            )
        return 0

    if arguments.command == "run":
        scenario_name = Path(arguments.path).stem
        try:
            scenario = load_scenario(arguments.path)
            scenario_name = scenario.name
            result = ScenarioRunner().run(scenario, cwd=arguments.cwd)
        except ScenarioValidationError as error:
            _write_error_report(
                arguments.report,
                arguments.junit_xml,
                scenario_name,
                error,
            )
            print(f"error: {error}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            _write_error_report(
                arguments.report,
                arguments.junit_xml,
                scenario_name,
                RuntimeError("interrupted"),
            )
            print("error: interrupted", file=sys.stderr)
            return 130
        except (OSError, RunnerError) as error:
            _write_error_report(
                arguments.report,
                arguments.junit_xml,
                scenario_name,
                error,
            )
            print(f"error: {error}", file=sys.stderr)
            return 1

        report = build_scenario_report(scenario, result)
        try:
            _write_reports(arguments.report, arguments.junit_xml, report)
        except OSError as error:
            print(f"error: cannot write report: {error}", file=sys.stderr)
            return 1

        if result.application.stdout:
            print(result.application.stdout, end="")
        if result.application.stderr:
            print(result.application.stderr, end="", file=sys.stderr)
        print(
            f"result: name={result.scenario_name} "
            f"exit_code={result.application.exit_code} "
            f"timed_out={str(result.application.timed_out).lower()} "
            f"forced={str(result.application.forced).lower()} "
            f"events={len(result.dispatches)} "
            f"status={report.status.value}"
        )

        if report.status is ReportStatus.TIMEOUT:
            return 124
        if result.application.exit_code != 0:
            return result.application.exit_code if 1 <= result.application.exit_code <= 125 else 1
        if report.status is not ReportStatus.PASS:
            return 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
