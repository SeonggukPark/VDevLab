# Changelog

All notable user-visible changes are recorded here. The project follows
Semantic Versioning, while scenario and report schemas have independent
integer versions.

## [Unreleased]

### Added

- Focused deterministic read-delay scenario with observable output, kernel
  warning assertions, parser coverage, and documented timing tolerance.
- Focused two-byte partial-read scenario that verifies FIFO remainder
  preservation through the sample monitor's line-buffering path.
- Optional deterministic JUnit XML projection for CI test-report viewers while
  preserving schema v1 causal JSON as the detailed evidence source.

## [0.1.0] - 2026-08-22

### Added

- Contributor workflow, roadmap, dependency inventory, and third-party notices.
- Structured bug and feature request forms.
- Explicit licensing and schema-versioning policy.
- Architecture, alternative-tool comparison, support boundary, known
  limitations, and accepted design decisions.
- Linux character device with deterministic counted EIO, delay, partial-read,
  disconnect, reconnect, and reset contracts.
- `vdevlab-ctl` fault-control utility and kernel contract suite.
- `vtemp-monitor` reference client with monotonic structured logs, retry,
  recovery, thermal warning, and disconnect handling.
- Version 1 YAML scenario parser, monotonic runner, assertions, and causal JSON
  report generator.
- Recovery and disconnect scenarios with one-command build, run, verification,
  report, and cleanup automation.
- Ubuntu build CI and runtime evidence procedures.

### Verified

- 139 Python tests and all three checked-in scenarios pass.
- Recovery and disconnect reports pass 8/8 and 7/7 assertions respectively.
- Module lifecycle passed 20 cycles, smoke testing passed 10 cycles, and the
  complete demo passed five consecutive cycles.
- Fresh-clone runtime gates passed on Ubuntu 22.04 with Linux
  `6.8.0-136-generic` and `6.8.0-138-generic`, with zero new kernel warnings
  and zero residual device, module, or monitor state.

[Unreleased]: https://github.com/SeonggukPark/VDevLab/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/SeonggukPark/VDevLab/releases/tag/v0.1.0
