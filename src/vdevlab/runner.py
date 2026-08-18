# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import time
from typing import Any, Protocol


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
