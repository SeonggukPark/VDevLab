# ADR 0001: Use a kernel module for the reference device backend

- Status: Accepted
- Date: 2026-08-22

## Context

The project must show whether an ordinary Linux device client correctly reacts
to `read(2)` errors, `poll(2)` error readiness, partial data, disconnect,
reconnect, and cleanup. The evidence should cover the same kernel-to-userspace
boundary used by a character-device client, while remaining small enough for a
reproducible competition demo.

## Decision

The reference backend is an out-of-tree Linux character-device module. It
registers `/dev/vdevlab0`, implements `file_operations`, stores test data in a
`kfifo`, exposes a fixed-width ioctl UAPI, and owns fault state and wait queues
inside the kernel.

The module is intentionally synthetic. It models observable device-client
contracts rather than a particular physical sensor or bus.

## Consequences

Positive consequences:

- the client executes real `open`, `read`, `write`, `poll`, and ioctl system
  calls against a kernel character device;
- contract tests can verify mutex-protected EIO consumption, wait-queue wake-up,
  poll masks, reset, module lifecycle, and kernel warnings;
- the module remains small enough for review and a one-command demo.

Costs and constraints:

- runtime verification is Linux-only and needs matching headers and privilege
  to load the module and read relevant kernel logs;
- hosted CI can compile the module but cannot replace the privileged runtime
  Gate;
- the synthetic device does not provide hardware, bus, interrupt, DMA, or
  electrical fidelity.

## Alternatives considered

- QEMU and Renode provide much broader machine and peripheral modeling, but
  require a larger model when the target observation is one Linux process's
  read/poll recovery contract.
- umockdev is faster and can avoid a custom module, but its preload boundary
  cannot prove the module's locking, wait queues, poll implementation, or
  lifecycle.
- CUSE keeps device logic in a userspace daemon, which is useful for other
  tests but moves the central failure-state implementation out of the kernel
  path this project claims to exercise.
- generic Linux fault injection targets important kernel failure sites, but
  does not directly provide the counted client-facing scenario and causal
  recovery report required here.

Detailed references are in [`../alternatives.md`](../alternatives.md).
