# ADR 0002: Apply data faults on the consumer read path

- Status: Accepted
- Date: 2026-08-22

## Context

The scenario runner and the application under test share `/dev/vdevlab0` for
different purposes. The runner writes controlled test payloads; the application
waits for and reads them. If an EIO or delay applied equally to injection
writes, the runner could consume or block a fault intended for the client. The
observed retry count would then depend on orchestration rather than the
application contract.

Disconnect is different: it represents absence of the whole device and must be
visible to both producers and consumers.

## Decision

EIO, delay, and partial-read faults apply only while servicing consumer
`read(2)` calls:

- counted EIO consumes exactly one occurrence per read;
- delay is applied at most once within one read system call;
- partial read limits the returned bytes and preserves the remainder.

Injection writes remain normal for those data faults. Disconnect returns
`ENODEV` to reads and writes. Poll reports `POLLERR` for pending EIO and
`POLLERR | POLLHUP` for disconnect.

Clear removes the active fault without discarding queued data. Reset clears
both the fault and FIFO so scenarios do not inherit state.

## Consequences

Positive consequences:

- requested EIO count maps directly to application-observed EIO and retry
  count;
- the runner can enqueue recovery data without stealing the fault;
- causal reports can connect fault injection, errno, retries, and recovery with
  a stable contract;
- blocked-reader and poll wake-up behavior can be tested independently.

Trade-offs:

- VDevLab does not currently model producer-side transient write errors except
  device-wide disconnect;
- only one fault is active, so compound read/write failure scenarios require a
  future explicit contract rather than implicit interaction;
- an operation already in progress during a fault change may complete under
  the state it observed, so tests synchronize on ioctl completion.

## Alternatives considered

- Applying every fault to both directions is superficially symmetric but makes
  scenario injection compete with the application for the configured fault.
- Using a separate hidden injection channel would preserve symmetry but add a
  second data plane and reduce how closely the demo resembles a small ordinary
  character device.
- Injecting faults inside the sample application would be simpler but would not
  test the kernel I/O boundary or another unmodified client.

The normative behavior is documented in [`../fault-model.md`](../fault-model.md).
