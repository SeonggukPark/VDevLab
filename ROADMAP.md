# VDevLab roadmap

The roadmap describes intended direction, not a compatibility promise. Work is
accepted through issues and reviewed against deterministic behavior, cleanup,
and reproducible evidence.

## v0.1 — Reproducible resilience lab

- Counted EIO, delay, partial-read, disconnect, reconnect, and full-reset
  contracts at a real character-device boundary.
- Reference temperature client with retry and recovery logs.
- Version 1 YAML scenarios and causal JSON reports.
- One-command recovery and disconnect demo on the verified Ubuntu environment.
- Public contribution, dependency, licensing, and release documentation.

## v0.2 — More evidence formats

- Delay-focused and partial-read-focused scenarios.
- JUnit XML output for CI systems.
- Recovery latency distributions and repeated-run summaries.
- A 100-cycle stability Gate with machine-readable results, available through
  `scripts/run-stability-test.sh`.

## v0.3 — Backend extensibility

- A documented device-backend extension interface.
- Feasibility prototypes for umockdev and `i2c-stub` integration.
- Clear capability reporting when a backend cannot reproduce a kernel-level
  read or poll contract.

## Non-goals

VDevLab is not a hardware timing simulator, a full device emulator, or a
replacement for hardware-in-the-loop qualification. It focuses on observable
Linux client resilience at read, write, poll, process, and cleanup boundaries.
