# Alternatives and fit

VDevLab is not intended to replace general emulators or every Linux testing
facility. It occupies a narrow point: deterministic, application-visible
`read(2)` and `poll(2)` faults through a real kernel character-device path,
with retry and recovery evidence produced by one command.

## Comparison

| Approach | Primary boundary | Strongest fit | Trade-off relative to VDevLab |
|---|---|---|---|
| QEMU system/device emulation | Guest machine, bus, and device model | Booting an OS or firmware against modeled hardware | Much broader fidelity and setup; a new device model is more work when the question is only how one Linux process handles counted errno and recovery |
| Renode | Embedded CPU, platform, and peripheral models | Deterministic firmware and multi-node embedded tests | Excellent platform inspection and Robot Framework integration, but not the native host Linux `/dev` file-operations path targeted here |
| umockdev | Preloaded userspace access to `/sys`, `/dev`, `/proc`, uevents, ioctl, and scripted I/O | Fast, often unprivileged regression tests from recorded devices | Does not execute VDevLab's kernel locking, wait queues, fault consumption, or poll implementation |
| CUSE/libfuse | Character-device requests served by a userspace daemon | Implementing a custom `/dev` endpoint without placing device logic in a custom module | Preserves a character-device interface but moves request handling and failure state to a daemon, so it does not test a custom kernel driver's internal wake-up and cleanup behavior |
| Linux fault injection | Kernel allocation, usercopy, block/MMC request, function, and other subsystem hooks | Stressing generic kernel failure paths and subsystem recovery | Broad and powerful, but not a ready-made contract for exactly N consumer reads returning EIO followed by application retry/recovery reporting |
| VDevLab | Native Linux character-device `read`, `write`, `poll`, ioctl, process, and cleanup | Small Linux device clients whose recovery behavior must be repeatable and reviewable | Narrow model, privileged setup, and no hardware/bus fidelity |

## QEMU

[QEMU system emulation](https://www.qemu.org/docs/master/system/introduction.html)
models a machine with CPUs, memory, and devices. Its
[device documentation](https://www.qemu.org/docs/master/system/device-emulation.html)
describes front ends presented to a guest, host-resource back ends, buses, and
pass-through. It is the better choice when the guest driver must see a
specific PCI, USB, storage, network, or board-level device model, or when the
whole guest boot path matters.

VDevLab instead runs the client directly on the Linux host or VM and focuses on
one character-device contract. It avoids building a complete machine or bus
model when the desired observation is `poll` readiness, a counted `EIO`, retry,
recovery latency, and cleanup.

## Renode

[Renode testing](https://renode.readthedocs.io/en/latest/introduction/testing.html)
integrates with Robot Framework, supports snapshots, parallel test execution,
and direct inspection of simulated state. Its
[peripheral modeling guide](https://renode.readthedocs.io/en/latest/advanced/writing-peripherals.html)
covers SVD tags, Python peripherals, and C# models for buses and advanced
logic. Renode is the stronger choice for firmware, SoC peripherals, registers,
interrupts, and multi-node embedded scenarios.

VDevLab does not execute firmware or describe a board. It is the smaller fit
when an existing Linux userspace process already consumes a device file and
the test needs real Linux read/poll semantics rather than platform simulation.

## umockdev

[umockdev](https://github.com/martinpitt/umockdev) can record devices, sysfs
attributes, udev properties, ioctls, and reads/writes. Its preload library
redirects application access into a testbed, which makes it attractive for
fast regression tests without loading a custom module.

That interception is also the key boundary difference. An umockdev test can
prove client behavior against recorded or scripted responses, but it does not
prove VDevLab's `kfifo`, mutex, wait-queue, poll-mask, ioctl state transition,
or module lifecycle contracts. A future VDevLab userspace backend could use
umockdev for convenience if reports clearly identify that capability gap.

## CUSE

[libfuse's CUSE example](https://github.com/libfuse/libfuse/blob/master/example/cuse.c)
demonstrates a character device whose operations are implemented by a
userspace process. CUSE is attractive when rapid device behavior iteration or
userspace debugging matters more than exercising custom kernel-driver
internals.

VDevLab selected a kernel module because its central claims include atomic EIO
consumption, blocked-reader wake-up, poll error bits, independent FIFO/fault
locking, and module cleanup. A CUSE backend would be a useful separate
capability, not evidence for those kernel-path claims.

## Linux fault injection

The kernel's
[fault-injection infrastructure](https://docs.kernel.org/fault-injection/fault-injection.html)
supports facilities including allocation, usercopy, futex, block request, MMC
request, RPC, and injectable-function failures. It is the right tool when the
target is an existing kernel subsystem or a low-level failure site already
covered by those hooks.

VDevLab adds a domain-specific experiment around an application-facing device
contract: exact read-error count, scenario time, structured retry logs,
recovery latency, causal JSON, and cleanup. It does not replace kernel fault
injection for memory pressure, block-layer behavior, or broad kernel testing.

## When VDevLab is not a fit

Use another approach when the requirement is primarily:

- register-, interrupt-, DMA-, bus-, or electrical-level device fidelity;
- firmware execution, CPU instruction emulation, or whole-system boot testing;
- validation against real hardware timing or hardware-in-the-loop equipment;
- performance, throughput, power, or hard real-time measurement;
- non-Linux portability or testing without permission to load a module;
- security isolation, hostile multi-tenant execution, kernel fuzzing, or formal
  verification;
- many devices, multiple simultaneous fault types, or distributed scenarios.

VDevLab can complement those systems: use a fast client-level scenario during
development, then repeat the critical recovery behavior in the higher-fidelity
environment required for qualification.
