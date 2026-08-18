# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from vdevlab.runner import (
    EventDispatchError,
    FaultConfiguration,
    RunnerError,
    ScenarioScheduler,
)
from vdevlab.scenario import load_scenario


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        assert duration >= 0
        self.sleeps.append(duration)
        self.now += duration

    def advance(self, duration: float) -> None:
        self.now += duration


class FakeBackend:
    def __init__(self, after_call: Callable[[], None] | None = None) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.after_call = after_call

    def _record(self, action: str, value: object | None = None) -> None:
        self.calls.append((action, value))
        if self.after_call is not None:
            self.after_call()

    def reset(self) -> None:
        self._record("reset")

    def clear_fault(self) -> None:
        self._record("clear")

    def write(self, data: bytes) -> None:
        self._record("write", data)

    def set_fault(self, configuration: FaultConfiguration) -> None:
        self._record("fault", configuration)


def test_scheduler_uses_absolute_monotonic_deadlines() -> None:
    clock = FakeClock()
    backend = FakeBackend()
    scheduler = ScenarioScheduler(clock.monotonic, clock.sleep)

    records = scheduler.run(
        (
            {"at_ms": 0, "action": "reset"},
            {"at_ms": 100, "action": "write", "data": "25\n"},
            {"at_ms": 250, "action": "clear"},
        ),
        backend,
    )

    assert [record.started_ms for record in records] == pytest.approx([0, 100, 250])
    assert clock.sleeps == pytest.approx([0.1, 0.15])
    assert backend.calls == [
        ("reset", None),
        ("write", b"25\n"),
        ("clear", None),
    ]


def test_scheduler_does_not_add_delay_after_slow_dispatch() -> None:
    clock = FakeClock()
    backend = FakeBackend(after_call=lambda: clock.advance(0.2))
    scheduler = ScenarioScheduler(clock.monotonic, clock.sleep)

    records = scheduler.run(
        (
            {"at_ms": 0, "action": "reset"},
            {"at_ms": 100, "action": "clear"},
            {"at_ms": 500, "action": "reset"},
        ),
        backend,
    )

    assert [record.started_ms for record in records] == pytest.approx([0, 200, 500])
    assert clock.sleeps == pytest.approx([0.1])


def test_equal_deadlines_preserve_yaml_order() -> None:
    clock = FakeClock()
    backend = FakeBackend()

    ScenarioScheduler(clock.monotonic, clock.sleep).run(
        (
            {"at_ms": 50, "action": "write", "data": "first"},
            {"at_ms": 50, "action": "write", "data": "second"},
        ),
        backend,
    )

    assert backend.calls == [("write", b"first"), ("write", b"second")]
    assert clock.sleeps == pytest.approx([0.05])


def test_scheduler_dispatches_every_fault_configuration() -> None:
    clock = FakeClock()
    backend = FakeBackend()

    ScenarioScheduler(clock.monotonic, clock.sleep).run(
        (
            {"at_ms": 0, "action": "fault", "type": "eio", "repeat": 3},
            {
                "at_ms": 0,
                "action": "fault",
                "type": "delay",
                "duration_ms": 125,
            },
            {
                "at_ms": 0,
                "action": "fault",
                "type": "partial-read",
                "bytes": 2,
            },
            {"at_ms": 0, "action": "fault", "type": "disconnect"},
        ),
        backend,
    )

    assert backend.calls == [
        ("fault", FaultConfiguration("eio", repeat=3)),
        ("fault", FaultConfiguration("delay", delay_ms=125)),
        ("fault", FaultConfiguration("partial-read", partial_read_bytes=2)),
        ("fault", FaultConfiguration("disconnect")),
    ]


def test_parsed_normal_scenario_dispatches_without_conversion() -> None:
    scenario_path = Path(__file__).parents[1] / "examples" / "scenarios" / "normal.yaml"
    scenario = load_scenario(scenario_path)
    clock = FakeClock()
    backend = FakeBackend()

    records = ScenarioScheduler(clock.monotonic, clock.sleep).run(
        scenario.events,
        backend,
    )

    assert [record.scheduled_ms for record in records] == [0, 100, 200]
    assert backend.calls == [
        ("reset", None),
        ("write", b"25\n"),
        ("write", b"42\n"),
    ]


def test_dispatch_failure_identifies_event_and_preserves_cause() -> None:
    class FailingBackend(FakeBackend):
        def write(self, data: bytes) -> None:
            raise OSError("device unavailable")

    clock = FakeClock()

    with pytest.raises(EventDispatchError) as captured:
        ScenarioScheduler(clock.monotonic, clock.sleep).run(
            ({"at_ms": 25, "action": "write", "data": "42\n"},),
            FailingBackend(),
        )

    assert captured.value.index == 0
    assert captured.value.action == "write"
    assert isinstance(captured.value.__cause__, OSError)


@pytest.mark.parametrize(
    "event",
    (
        {"at_ms": -1, "action": "reset"},
        {"at_ms": True, "action": "reset"},
        {"at_ms": "1", "action": "reset"},
    ),
)
def test_scheduler_rejects_invalid_normalized_deadlines(event: dict[str, object]) -> None:
    clock = FakeClock()

    with pytest.raises(RunnerError, match="invalid at_ms"):
        ScenarioScheduler(clock.monotonic, clock.sleep).run((event,), FakeBackend())
