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

Data faults apply only to reads. This separation is intentional: the scenario
runner writes test data into the device, and those writes must not consume an
error intended for the application under test. Disconnect is device-wide and
therefore affects both directions.

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
data. End-to-end scenario cleanup must either drain the FIFO or reload the
module until a separate full reset operation is added.

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
- Poll wakes and reports the documented error bits.
- The read following the last EIO returns to normal FIFO behavior.
- Invalid configurations leave the previous fault unchanged.
- Kernel logs contain no warning, oops, or lockdep report.
