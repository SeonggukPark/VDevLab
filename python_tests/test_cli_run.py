# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vdevlab import cli
from vdevlab.runner import ApplicationResult, ScenarioRunResult


def _result(exit_code: int = 0, timed_out: bool = False) -> ScenarioRunResult:
    return ScenarioRunResult(
        scenario_name="normal-temperature-flow",
        dispatches=(),
        application=ApplicationResult(
            command=("monitor",),
            exit_code=exit_code,
            stdout='{"timestamp_ms":1,"event":"MONITOR_STARTED"}\n',
            stderr="diagnostic\n",
            timed_out=timed_out,
        ),
    )


def _scenario() -> SimpleNamespace:
    return SimpleNamespace(
        name="normal-temperature-flow",
        events=(),
        assertions=({"event": "MONITOR_STARTED", "count": 1},),
    )


def test_run_command_forwards_output_and_returns_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = _scenario()
    calls: list[tuple[object, str]] = []

    class FakeRunner:
        def run(self, selected: object, cwd: str) -> ScenarioRunResult:
            calls.append((selected, cwd))
            return _result()

    monkeypatch.setattr(cli, "load_scenario", lambda path: scenario)
    monkeypatch.setattr(cli, "ScenarioRunner", FakeRunner)

    assert cli.main(("run", "scenario.yaml", "--cwd", "workspace")) == 0
    output = capsys.readouterr()
    assert calls == [(scenario, "workspace")]
    assert "MONITOR_STARTED" in output.out
    assert "status=PASS" in output.out
    assert "exit_code=0 timed_out=false forced=false" in output.out
    assert output.err == "diagnostic\n"


@pytest.mark.parametrize(
    ("result", "expected"),
    ((_result(exit_code=7), 7), (_result(exit_code=-15), 1), (_result(timed_out=True), 124)),
)
def test_run_command_maps_failure_status(
    monkeypatch: pytest.MonkeyPatch,
    result: ScenarioRunResult,
    expected: int,
) -> None:
    monkeypatch.setattr(cli, "load_scenario", lambda path: _scenario())
    monkeypatch.setattr(
        cli,
        "ScenarioRunner",
        lambda: SimpleNamespace(run=lambda scenario, cwd: result),
    )

    assert cli.main(("run", "scenario.yaml")) == expected


def test_run_command_writes_json_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "load_scenario", lambda path: _scenario())
    monkeypatch.setattr(
        cli,
        "ScenarioRunner",
        lambda: SimpleNamespace(run=lambda scenario, cwd: _result()),
    )
    report_path = tmp_path / "result.json"

    assert cli.main(("run", "scenario.yaml", "--report", str(report_path))) == 0

    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert document["status"] == "PASS"
    assert document["scenario"]["name"] == "normal-temperature-flow"


def test_run_command_assertion_failure_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scenario = _scenario()
    scenario.assertions = ({"event": "TEMPERATURE", "count": 1},)
    monkeypatch.setattr(cli, "load_scenario", lambda path: scenario)
    monkeypatch.setattr(
        cli,
        "ScenarioRunner",
        lambda: SimpleNamespace(run=lambda selected, cwd: _result()),
    )
    report_path = tmp_path / "failed.json"

    assert cli.main(("run", "scenario.yaml", "--report", str(report_path))) == 1

    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["status"] == "FAIL"


def test_run_command_writes_timeout_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "load_scenario", lambda path: _scenario())
    monkeypatch.setattr(
        cli,
        "ScenarioRunner",
        lambda: SimpleNamespace(
            run=lambda selected, cwd: _result(timed_out=True)
        ),
    )
    report_path = tmp_path / "timeout.json"

    assert cli.main(("run", "scenario.yaml", "--report", str(report_path))) == 124

    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["status"] == "TIMEOUT"


def test_run_command_writes_error_report_for_runner_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "load_scenario", lambda path: _scenario())
    monkeypatch.setattr(
        cli,
        "ScenarioRunner",
        lambda: SimpleNamespace(
            run=lambda scenario, cwd: (_ for _ in ()).throw(
                cli.RunnerError("device unavailable")
            )
        ),
    )
    report_path = tmp_path / "error.json"

    assert cli.main(("run", "scenario.yaml", "--report", str(report_path))) == 1

    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["status"] == "ERROR"
    assert document["error"]["message"] == "device unavailable"


def test_run_command_maps_interrupt_to_130(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "load_scenario", lambda path: _scenario())
    monkeypatch.setattr(
        cli,
        "ScenarioRunner",
        lambda: SimpleNamespace(run=lambda scenario, cwd: (_ for _ in ()).throw(KeyboardInterrupt())),
    )

    assert cli.main(("run", "scenario.yaml")) == 130
    assert "interrupted" in capsys.readouterr().err
