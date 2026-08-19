# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from collections.abc import Callable
import errno
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import threading

import pytest

from vdevlab.runner import (
    ApplicationProcess,
    ApplicationTimeoutError,
    EventDispatchError,
    FaultConfiguration,
    LinuxDeviceBackend,
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


def test_linux_backend_opens_and_closes_device(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[str, int]] = []
    closed: list[int] = []

    monkeypatch.setattr(
        "vdevlab.runner.os.open",
        lambda path, flags: opened.append((path, flags)) or 17,
    )
    monkeypatch.setattr("vdevlab.runner.os.close", closed.append)
    monkeypatch.setattr("vdevlab.runner._system_ioctl", lambda *args: 0)

    with LinuxDeviceBackend("/dev/vdevlab-test") as backend:
        assert backend.device_path == "/dev/vdevlab-test"

    backend.close()
    assert opened[0][0] == "/dev/vdevlab-test"
    assert opened[0][1] != 0
    assert closed == [17]


@pytest.mark.parametrize(
    ("configuration", "expected"),
    (
        (FaultConfiguration("eio", repeat=3), (1, 3, 0, 0)),
        (FaultConfiguration("delay", delay_ms=125), (2, 0, 125, 0)),
        (FaultConfiguration("disconnect"), (3, 0, 0, 0)),
        (FaultConfiguration("partial-read", partial_read_bytes=2), (4, 0, 0, 2)),
    ),
)
def test_linux_backend_packs_fault_ioctl(
    monkeypatch: pytest.MonkeyPatch,
    configuration: FaultConfiguration,
    expected: tuple[int, int, int, int],
) -> None:
    calls: list[tuple[int, int, bytes]] = []
    monkeypatch.setattr("vdevlab.runner.os.open", lambda path, flags: 23)
    monkeypatch.setattr("vdevlab.runner.os.close", lambda fd: None)
    monkeypatch.setattr(
        "vdevlab.runner._system_ioctl",
        lambda fd, request, payload=b"": calls.append((fd, request, payload)) or 0,
    )

    with LinuxDeviceBackend("/dev/vdevlab0") as backend:
        backend.set_fault(configuration)

    assert len(calls) == 1
    assert calls[0][0] == 23
    assert calls[0][1] == 0x40105601
    assert struct.unpack("=IIII", calls[0][2]) == expected


def test_linux_backend_dispatches_clear_and_reset_ioctl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[int] = []
    monkeypatch.setattr("vdevlab.runner.os.open", lambda path, flags: 29)
    monkeypatch.setattr("vdevlab.runner.os.close", lambda fd: None)
    monkeypatch.setattr(
        "vdevlab.runner._system_ioctl",
        lambda fd, request: requests.append(request) or 0,
    )

    with LinuxDeviceBackend("/dev/vdevlab0") as backend:
        backend.clear_fault()
        backend.reset()

    assert requests == [0x5603, 0x5604]


def test_linux_backend_retries_interrupted_and_partial_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks: list[bytes] = []
    results: list[BaseException | int] = [InterruptedError(), 2, 3]

    def fake_write(fd: int, data: memoryview) -> int:
        chunks.append(bytes(data))
        result = results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr("vdevlab.runner.os.open", lambda path, flags: 31)
    monkeypatch.setattr("vdevlab.runner.os.close", lambda fd: None)
    monkeypatch.setattr("vdevlab.runner.os.write", fake_write)
    monkeypatch.setattr("vdevlab.runner._system_ioctl", lambda *args: 0)

    with LinuxDeviceBackend("/dev/vdevlab0") as backend:
        backend.write(b"hello")

    assert chunks == [b"hello", b"hello", b"llo"]
    assert results == []


def test_linux_backend_rejects_zero_progress_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vdevlab.runner.os.open", lambda path, flags: 37)
    monkeypatch.setattr("vdevlab.runner.os.close", lambda fd: None)
    monkeypatch.setattr("vdevlab.runner.os.write", lambda fd, data: 0)
    monkeypatch.setattr("vdevlab.runner._system_ioctl", lambda *args: 0)

    with LinuxDeviceBackend("/dev/vdevlab0") as backend:
        with pytest.raises(OSError) as captured:
            backend.write(b"data")

    assert captured.value.errno == errno.EIO


def test_linux_backend_rejects_operations_after_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vdevlab.runner.os.open", lambda path, flags: 41)
    monkeypatch.setattr("vdevlab.runner.os.close", lambda fd: None)
    monkeypatch.setattr("vdevlab.runner._system_ioctl", lambda *args: 0)
    backend = LinuxDeviceBackend("/dev/vdevlab0")
    backend.close()

    with pytest.raises(RunnerError, match="closed"):
        backend.reset()


def test_application_process_captures_both_streams_and_exit_code() -> None:
    script = (
        "import sys; "
        "print('temperature=42', flush=True); "
        "print('diagnostic', file=sys.stderr, flush=True); "
        "raise SystemExit(7)"
    )

    process = ApplicationProcess((sys.executable, "-c", script))
    result = process.collect()

    assert result.command == (sys.executable, "-c", script)
    assert result.exit_code == 7
    assert result.stdout.splitlines() == ["temperature=42"]
    assert result.stderr.splitlines() == ["diagnostic"]
    assert process.poll() == 7


def test_application_process_drains_large_stdout_and_stderr() -> None:
    size = 256 * 1024
    script = (
        "import sys; "
        f"sys.stdout.write('O' * {size}); sys.stdout.flush(); "
        f"sys.stderr.write('E' * {size}); sys.stderr.flush()"
    )

    result = ApplicationProcess((sys.executable, "-c", script)).collect()

    assert result.exit_code == 0
    assert result.stdout == "O" * size
    assert result.stderr == "E" * size


def test_application_process_decodes_invalid_utf8_with_replacement() -> None:
    script = "import os; os.write(1, bytes([0xff])); os.write(2, bytes([0xfe]))"

    result = ApplicationProcess((sys.executable, "-c", script)).collect()

    assert result.stdout == "\ufffd"
    assert result.stderr == "\ufffd"


def test_application_process_creates_platform_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options: dict[str, object] = {}

    class StubProcess:
        pid = 101
        returncode = 0

        def communicate(self) -> tuple[bytes, bytes]:
            return b"out", b"err"

        def poll(self) -> int:
            return 0

    def fake_popen(command: tuple[str, ...], **kwargs: object) -> StubProcess:
        options.update(kwargs)
        return StubProcess()

    monkeypatch.setattr("vdevlab.runner.subprocess.Popen", fake_popen)

    process = ApplicationProcess(("program", "argument"), cwd="workdir")
    result = process.collect()

    assert process.pid == 101
    assert result.stdout == "out"
    assert result.stderr == "err"
    assert options["cwd"] == "workdir"
    assert options["stdin"] is subprocess.DEVNULL
    assert options["stdout"] is subprocess.PIPE
    assert options["stderr"] is subprocess.PIPE
    if os.name == "nt":
        assert options["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
        assert "start_new_session" not in options
    else:
        assert options["start_new_session"] is True
        assert "creationflags" not in options


def test_application_process_collect_is_repeatable() -> None:
    process = ApplicationProcess((sys.executable, "-c", "print('once')"))

    first = process.collect()
    second = process.collect()

    assert first == second


@pytest.mark.parametrize(
    "command",
    ((), ("",), ("program", "")),
)
def test_application_process_rejects_invalid_command(command: tuple[str, ...]) -> None:
    with pytest.raises(RunnerError, match="non-empty strings"):
        ApplicationProcess(command)


def test_application_process_collect_reports_timeout() -> None:
    process = ApplicationProcess((sys.executable, "-c", "import time; time.sleep(30)"))

    try:
        with pytest.raises(ApplicationTimeoutError) as captured:
            process.collect(timeout_ms=25)

        assert captured.value.command == (sys.executable, "-c", "import time; time.sleep(30)")
        assert captured.value.timeout_ms == 25
    finally:
        process.terminate(grace_ms=100)


def test_application_process_timeout_terminates_process() -> None:
    process = ApplicationProcess((sys.executable, "-c", "import time; time.sleep(30)"))

    result = process.collect_with_timeout(timeout_ms=25, terminate_grace_ms=1000)

    assert result.timed_out is True
    assert result.forced is False
    assert result.exit_code != 0
    assert process.poll() is not None


def test_application_process_forces_kill_after_grace_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released = threading.Event()
    signals: list[object] = []

    class StubbornProcess:
        pid = 211
        returncode: int | None = None

        def communicate(self) -> tuple[bytes, bytes]:
            released.wait(2)
            return b"partial-out", b"partial-err"

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            signals.append("terminate")

        def kill(self) -> None:
            signals.append("kill")
            self.returncode = 9
            released.set()

    process_stub = StubbornProcess()
    monkeypatch.setattr("vdevlab.runner.subprocess.Popen", lambda *args, **kwargs: process_stub)

    if os.name == "nt":
        expected_signals: list[object] = ["terminate", "kill"]
    else:
        def fake_killpg(pid: int, sent_signal: signal.Signals) -> None:
            signals.append(sent_signal)
            if sent_signal == signal.SIGKILL:
                process_stub.returncode = -int(signal.SIGKILL)
                released.set()

        monkeypatch.setattr("vdevlab.runner.os.killpg", fake_killpg)
        expected_signals = [signal.SIGTERM, signal.SIGKILL]

    process = ApplicationProcess(("stubborn",))
    result = process.collect_with_timeout(timeout_ms=10, terminate_grace_ms=10)

    assert signals == expected_signals
    assert result.timed_out is True
    assert result.forced is True
    assert result.stdout == "partial-out"
    assert result.stderr == "partial-err"


@pytest.mark.parametrize(
    ("method", "value", "message"),
    (
        ("collect", 0, "timeout_ms"),
        ("collect", True, "timeout_ms"),
        ("terminate", -1, "grace_ms"),
    ),
)
def test_application_process_rejects_invalid_timeouts(
    method: str,
    value: int,
    message: str,
) -> None:
    process = ApplicationProcess((sys.executable, "-c", "pass"))

    try:
        with pytest.raises(RunnerError, match=message):
            getattr(process, method)(value)
    finally:
        process.collect()
