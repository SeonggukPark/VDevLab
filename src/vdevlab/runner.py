# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
import errno
import os
import signal
import struct
import subprocess
import threading
import time
from typing import Any, Protocol

from .scenario import ScenarioDefinition

try:
    from fcntl import ioctl as _system_ioctl
except ImportError:
    _system_ioctl = None


_FAULT_TYPES = {
    "eio": 1,
    "delay": 2,
    "disconnect": 3,
    "partial-read": 4,
}
_FAULT_STRUCT = struct.Struct("=IIII")

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_NONE = 0
_IOC_WRITE = 1


def _ioctl_number(direction: int, number: int, size: int = 0) -> int:
    return (
        (direction << _IOC_DIRSHIFT)
        | (ord("V") << _IOC_TYPESHIFT)
        | (number << _IOC_NRSHIFT)
        | (size << _IOC_SIZESHIFT)
    )


_VDEVLAB_IOC_SET_FAULT = _ioctl_number(_IOC_WRITE, 0x01, _FAULT_STRUCT.size)
_VDEVLAB_IOC_CLEAR_FAULT = _ioctl_number(_IOC_NONE, 0x03)
_VDEVLAB_IOC_RESET = _ioctl_number(_IOC_NONE, 0x04)


@dataclass(frozen=True)
class FaultConfiguration:
    fault_type: str
    repeat: int = 0
    delay_ms: int = 0
    partial_read_bytes: int = 0


@dataclass(frozen=True)
class DispatchRecord:
    index: int
    action: str
    scheduled_ms: int
    started_ms: float
    finished_ms: float
    monotonic_started_ms: float
    monotonic_finished_ms: float


@dataclass(frozen=True)
class ApplicationResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    forced: bool = False


@dataclass(frozen=True)
class ScenarioRunResult:
    scenario_name: str
    dispatches: tuple[DispatchRecord, ...]
    application: ApplicationResult


class DeviceBackend(Protocol):
    def reset(self) -> None: ...

    def clear_fault(self) -> None: ...

    def write(self, data: bytes) -> None: ...

    def set_fault(self, configuration: FaultConfiguration) -> None: ...


class RunnerError(RuntimeError):
    pass


class EventDispatchError(RunnerError):
    def __init__(self, index: int, action: str, cause: BaseException) -> None:
        self.index = index
        self.action = action
        self.cause = cause
        super().__init__(f"event {index} ({action}) failed: {cause}")


class ApplicationTimeoutError(RunnerError):
    def __init__(self, command: Sequence[str], timeout_ms: int) -> None:
        self.command = tuple(command)
        self.timeout_ms = timeout_ms
        super().__init__(f"application exceeded timeout of {timeout_ms}ms")


class ApplicationProcess:
    def __init__(
        self,
        command: Sequence[str],
        cwd: str | os.PathLike[str] | None = None,
    ) -> None:
        if not command or any(not isinstance(argument, str) or not argument for argument in command):
            raise RunnerError("application command must contain non-empty strings")

        self.command = tuple(command)
        options: dict[str, Any] = {
            "cwd": cwd,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True

        self._process = subprocess.Popen(self.command, **options)
        self._output: tuple[bytes, bytes] | None = None
        self._collector_error: BaseException | None = None
        self._collector = threading.Thread(
            target=self._collect_output,
            name="vdevlab-output-collector",
            daemon=True,
        )
        self._collector.start()

    @property
    def pid(self) -> int:
        return self._process.pid

    def poll(self) -> int | None:
        return self._process.poll()

    def collect(self, timeout_ms: int | None = None) -> ApplicationResult:
        timeout_seconds = self._timeout_seconds(timeout_ms, "timeout_ms")
        self._collector.join(timeout_seconds)
        if self._collector.is_alive():
            assert timeout_ms is not None
            raise ApplicationTimeoutError(self.command, timeout_ms)
        return self._result()

    def collect_with_timeout(
        self,
        timeout_ms: int,
        terminate_grace_ms: int = 1000,
    ) -> ApplicationResult:
        try:
            return self.collect(timeout_ms)
        except ApplicationTimeoutError:
            result = self.terminate(terminate_grace_ms)
            return replace(result, timed_out=True)

    def terminate(self, grace_ms: int = 1000) -> ApplicationResult:
        grace_seconds = self._timeout_seconds(grace_ms, "grace_ms")
        if self.poll() is not None:
            return self.collect()

        self._signal_group(force=False)
        self._collector.join(grace_seconds)
        forced = self._collector.is_alive()
        if forced:
            self._signal_group(force=True)
        result = self.collect()
        return replace(result, forced=forced)

    def _result(self) -> ApplicationResult:
        if self._collector_error is not None:
            raise RunnerError("failed to collect application output") from self._collector_error
        if self._output is None or self._process.returncode is None:
            raise RunnerError("application output collector ended without a result")

        stdout, stderr = self._output
        return ApplicationResult(
            command=self.command,
            exit_code=self._process.returncode,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )

    def _signal_group(self, force: bool) -> None:
        try:
            if os.name == "nt":
                if force:
                    self._process.kill()
                else:
                    self._process.terminate()
            else:
                os.killpg(self.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            return

    @staticmethod
    def _timeout_seconds(value: int | None, name: str) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RunnerError(f"{name} must be a positive integer")
        return value / 1000

    def _collect_output(self) -> None:
        try:
            self._output = self._process.communicate()
        except BaseException as error:
            self._collector_error = error


class LinuxDeviceBackend:
    def __init__(self, device_path: str) -> None:
        if _system_ioctl is None:
            raise RunnerError("Linux ioctl support is unavailable on this platform")
        self.device_path = device_path
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        self._fd: int | None = os.open(device_path, flags)

    def __enter__(self) -> LinuxDeviceBackend:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def reset(self) -> None:
        assert _system_ioctl is not None
        _system_ioctl(self._fileno(), _VDEVLAB_IOC_RESET)

    def clear_fault(self) -> None:
        assert _system_ioctl is not None
        _system_ioctl(self._fileno(), _VDEVLAB_IOC_CLEAR_FAULT)

    def write(self, data: bytes) -> None:
        remaining = memoryview(data)
        while remaining:
            try:
                written = os.write(self._fileno(), remaining)
            except InterruptedError:
                continue
            if written == 0:
                raise OSError(errno.EIO, "device write made no progress")
            remaining = remaining[written:]

    def set_fault(self, configuration: FaultConfiguration) -> None:
        try:
            fault_type = _FAULT_TYPES[configuration.fault_type]
        except KeyError as error:
            raise RunnerError(
                f"unsupported fault type: {configuration.fault_type}"
            ) from error

        payload = _FAULT_STRUCT.pack(
            fault_type,
            configuration.repeat,
            configuration.delay_ms,
            configuration.partial_read_bytes,
        )
        assert _system_ioctl is not None
        _system_ioctl(self._fileno(), _VDEVLAB_IOC_SET_FAULT, payload)

    def _fileno(self) -> int:
        if self._fd is None:
            raise RunnerError("device backend is closed")
        return self._fd


class ScenarioScheduler:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper

    def run(
        self,
        events: Sequence[Mapping[str, Any]],
        backend: DeviceBackend,
    ) -> tuple[DispatchRecord, ...]:
        origin = self._clock()
        records: list[DispatchRecord] = []

        for index, event in enumerate(events):
            scheduled_ms = self._scheduled_ms(event, index)
            deadline = origin + scheduled_ms / 1000
            remaining = deadline - self._clock()
            if remaining > 0:
                self._sleeper(remaining)

            started = self._clock()
            action = str(event.get("action", "<missing>"))
            try:
                self._dispatch(event, backend)
            except Exception as error:
                raise EventDispatchError(index, action, error) from error
            finished = self._clock()

            records.append(
                DispatchRecord(
                    index=index,
                    action=action,
                    scheduled_ms=scheduled_ms,
                    started_ms=(started - origin) * 1000,
                    finished_ms=(finished - origin) * 1000,
                    monotonic_started_ms=started * 1000,
                    monotonic_finished_ms=finished * 1000,
                )
            )

        return tuple(records)

    @staticmethod
    def _scheduled_ms(event: Mapping[str, Any], index: int) -> int:
        value = event.get("at_ms")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RunnerError(f"event {index} has an invalid at_ms value")
        return value

    @staticmethod
    def _dispatch(event: Mapping[str, Any], backend: DeviceBackend) -> None:
        action = event.get("action")
        if action == "reset":
            backend.reset()
        elif action == "clear":
            backend.clear_fault()
        elif action == "write":
            data = event.get("data")
            if not isinstance(data, str):
                raise RunnerError("write event data must be a string")
            backend.write(data.encode("utf-8"))
        elif action == "fault":
            backend.set_fault(ScenarioScheduler._fault_configuration(event))
        else:
            raise RunnerError(f"unsupported event action: {action}")

    @staticmethod
    def _fault_configuration(event: Mapping[str, Any]) -> FaultConfiguration:
        fault_type = event.get("type")
        if fault_type == "eio":
            return FaultConfiguration(fault_type=fault_type, repeat=int(event["repeat"]))
        if fault_type == "delay":
            return FaultConfiguration(
                fault_type=fault_type,
                delay_ms=int(event["duration_ms"]),
            )
        if fault_type == "partial-read":
            return FaultConfiguration(
                fault_type=fault_type,
                partial_read_bytes=int(event["bytes"]),
            )
        if fault_type == "disconnect":
            return FaultConfiguration(fault_type=fault_type)
        raise RunnerError(f"unsupported fault type: {fault_type}")


class ScenarioRunner:
    def __init__(
        self,
        backend_factory: Callable[[str], DeviceBackend] = LinuxDeviceBackend,
        application_factory: Callable[..., ApplicationProcess] = ApplicationProcess,
        scheduler: ScenarioScheduler | None = None,
        clock: Callable[[], float] = time.monotonic,
        terminate_grace_ms: int = 1000,
    ) -> None:
        ApplicationProcess._timeout_seconds(terminate_grace_ms, "terminate_grace_ms")
        self._backend_factory = backend_factory
        self._application_factory = application_factory
        self._scheduler = scheduler or ScenarioScheduler(clock=clock)
        self._clock = clock
        self._terminate_grace_ms = terminate_grace_ms

    def run(
        self,
        scenario: ScenarioDefinition,
        cwd: str | os.PathLike[str] | None = None,
    ) -> ScenarioRunResult:
        backend = self._backend_factory(scenario.device_path)
        application: ApplicationProcess | None = None
        started = self._clock()

        try:
            application = self._application_factory(scenario.command, cwd=cwd)
            dispatches = self._scheduler.run(scenario.events, backend)
            elapsed_ms = int((self._clock() - started) * 1000)
            remaining_ms = scenario.timeout_ms - elapsed_ms
            if remaining_ms <= 0:
                application_result = replace(
                    application.terminate(self._terminate_grace_ms),
                    timed_out=True,
                )
            else:
                application_result = application.collect_with_timeout(
                    remaining_ms,
                    self._terminate_grace_ms,
                )
            result = ScenarioRunResult(
                scenario_name=scenario.name,
                dispatches=dispatches,
                application=application_result,
            )
        except BaseException:
            if application is not None and application.poll() is None:
                application.terminate(self._terminate_grace_ms)
            self._cleanup_backend(backend, suppress_errors=True)
            raise

        self._cleanup_backend(backend, suppress_errors=False)
        return result

    @staticmethod
    def _cleanup_backend(backend: DeviceBackend, suppress_errors: bool) -> None:
        errors: list[BaseException] = []
        try:
            backend.reset()
        except BaseException as error:
            errors.append(error)
        try:
            close = getattr(backend, "close", None)
            if close is not None:
                close()
        except BaseException as error:
            errors.append(error)

        if errors and not suppress_errors:
            raise RunnerError("failed to reset and close device backend") from errors[0]
