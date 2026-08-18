# Fault model

VDevLab faults model failures observed by a userspace program consuming data
from `/dev/vdevlab0`. They do not attempt to emulate a particular sensor or
hardware bus.

## Scope

Only one fault is active at a time. A fault set through `VDEVLAB_IOC_SET_FAULT`
replaces the previous fault. `VDEVLAB_IOC_CLEAR_FAULT` returns the device to the
normal fault state.

| Fault | Read | Write | Poll |
|---|---|---|---|
| `NONE` | Normal FIFO read | Normal FIFO write | FIFO readiness |
| `EIO` | Returns `-EIO` for the configured count | Normal | `POLLERR` while pending |
| `DELAY` | Delays the read once per system call | Normal | FIFO readiness |
| `DISCONNECT` | Returns `-ENODEV` | Returns `-ENODEV` | `POLLERR | POLLHUP` |
| `PARTIAL_READ` | Returns at most the configured byte count | Normal | FIFO readiness |

Data faults apply only to reads. This separation is intentional: the scenario
runner writes test data into the device, and those writes must not consume an
error intended for the application under test. Disconnect is device-wide and
therefore affects both directions.

## Delay

A delay configuration contains a positive millisecond value from 1 through
`VDEVLAB_MAX_DELAY_MS`. The delay is applied at most once during each `read()`
system call, including a call that sleeps waiting for data and later retries its
internal read loop. Runtime tests use `CLOCK_MONOTONIC` and accept a measured
duration from 80% of the configured delay through 1000 milliseconds for a
100-millisecond request. The lower allowance accounts for timer granularity;
the upper bound detects accidental repeated or unbounded delay.

## Partial read

A partial-read configuration contains a positive byte limit from 1 through
`VDEVLAB_MAX_PARTIAL_READ`. A successful read returns no more than this limit,
the caller's buffer size, or the available FIFO data, whichever is smallest.
The fault remains active until it is cleared or replaced. It never discards the
unreturned portion of the FIFO data.

## Counted EIO

An EIO configuration contains a positive `repeat` value. Each read atomically
consumes one occurrence under the fault mutex and returns `-EIO`. The read that
consumes the last occurrence also returns `-EIO`, then the active state becomes
`NONE`.

For example, `vdevlab-ctl set eio 3` produces this contract:

```text
read 1 -> -EIO, remaining=2
read 2 -> -EIO, remaining=1
read 3 -> -EIO, remaining=0 and fault becomes NONE
read 4 -> normal FIFO behavior
```

The accepted range is 1 through `VDEVLAB_MAX_FAULT_REPEAT`. A zero or excessive
count is rejected with `-EINVAL` before it can change the active state.

## Blocking reads and poll

A reader can already be asleep when a scenario activates EIO or disconnect.
The ioctl handler wakes the read wait queue, and the wait predicate treats both
faults as readable events. This ensures the existing system call observes the
fault instead of going back to sleep.

`poll()` reports `POLLERR` for pending EIO and `POLLERR | POLLHUP` for
disconnect. Delay does not create readiness by itself; it applies when a read
system call handles the device.

## Concurrency boundary

Fault state transitions and EIO count consumption are protected by
`vdevlab_fault_lock`. FIFO contents are protected independently by
`vdevlab_fifo_lock`. The implementation does not hold either mutex while
sleeping for a delay.

An I/O operation already in progress when a fault is changed may complete under
the state it observed. Operations starting after the ioctl completes observe
the new state. Tests should synchronize on completion of the control ioctl
before asserting subsequent I/O results.

## Reset behavior

`VDEVLAB_IOC_CLEAR_FAULT` clears the active fault but does not discard FIFO
data. Clearing a disconnect is the reconnect operation: existing file
descriptors resume normal I/O and queued FIFO data is preserved.

`VDEVLAB_IOC_RESET` atomically restores the observable device state for a new
scenario by clearing the active fault and discarding all queued FIFO data. The
implementation wakes both read and write wait queues after either operation.

## Required verification

On an Ubuntu host or VM with matching kernel headers, build and run the
contract suite with:

```bash
make contract-test
```

The command builds the module and userspace tools, loads the module, runs the
contract checks, unloads the module, and scans new kernel log entries for
warning, oops, panic, and lockdep patterns.

- EIO returns exactly the configured number of errors.
- Concurrent readers cannot consume the same EIO occurrence.
- Injection writes do not reduce the EIO count.
- A blocked reader wakes when EIO or disconnect is activated.
- A blocked writer wakes when disconnect is activated.
- Poll wakes and reports the documented error bits.
- The read following the last EIO returns to normal FIFO behavior.
- Delay is measured with a monotonic clock and is applied once per read call.
- Partial reads preserve the unread FIFO remainder.
- Reconnect preserves FIFO data; full reset discards it.
- Invalid configurations leave the previous fault unchanged.
- Unsupported ioctl commands return `-ENOTTY`.
- Kernel logs contain no warning, oops, or lockdep report.
