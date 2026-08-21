# Changelog

All notable user-visible changes are recorded here. The project follows
Semantic Versioning, while scenario and report schemas have independent
integer versions.

## [Unreleased]

### Added

- Contributor workflow, roadmap, dependency inventory, and third-party notices.
- Structured bug and feature request forms.
- Explicit licensing and schema-versioning policy.

## [0.1.0] - Unreleased

### Added

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

[Unreleased]: https://github.com/SeonggukPark/VDevLab/commits/main
[0.1.0]: https://github.com/SeonggukPark/VDevLab/tree/main
