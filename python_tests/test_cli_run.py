# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

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
            stdout="temperature=25\n",
            stderr="diagnostic\n",
            timed_out=timed_out,
        ),
    )


def test_run_command_forwards_output_and_returns_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = SimpleNamespace(name="normal-temperature-flow")
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
    assert "temperature=25" in output.out
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
    monkeypatch.setattr(cli, "load_scenario", lambda path: object())
    monkeypatch.setattr(
        cli,
        "ScenarioRunner",
        lambda: SimpleNamespace(run=lambda scenario, cwd: result),
    )

    assert cli.main(("run", "scenario.yaml")) == expected


def test_run_command_maps_interrupt_to_130(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "load_scenario", lambda path: object())
    monkeypatch.setattr(
        cli,
        "ScenarioRunner",
        lambda: SimpleNamespace(run=lambda scenario, cwd: (_ for _ in ()).throw(KeyboardInterrupt())),
    )

    assert cli.main(("run", "scenario.yaml")) == 130
    assert "interrupted" in capsys.readouterr().err
