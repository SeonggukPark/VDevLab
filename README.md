# VDevLab

[![CI](https://github.com/SeonggukPark/VDevLab/actions/workflows/ci.yml/badge.svg)](https://github.com/SeonggukPark/VDevLab/actions/workflows/ci.yml)

VDevLab is a deterministic Linux device-client resilience lab. It injects
counted I/O faults at a real character-device `read()` and `poll()` boundary,
runs versioned YAML scenarios, and produces one causal JSON timeline connecting
fault injection, observed errno, application retry, recovery, and cleanup.

The included temperature monitor demonstrates the contract without requiring
physical sensor hardware. It is intentionally small so the same scenarios and
reports can be adapted to other Linux device clients.

## What the demo proves

- Exactly three injected `EIO` results produce exactly three application retries.
- A later payload returns the client to normal operation and records recovery latency.
- Disconnect wakes the waiting client and produces a structured disconnect event.
- stdout, exit code, recovery latency, disconnect, and kernel warnings are asserted.
- Every run removes the process, active fault, kernel module, and device node.

## Verified environment

The runtime Gate currently covers:

- Ubuntu 22.04 LTS
- Linux `6.8.0-136-generic` and `6.8.0-138-generic` on x86-64
- GCC 12
- Python 3.10

Other recent Ubuntu kernels may work but have not completed the same runtime Gate.
The kernel headers must match the running kernel.

## Quick start

Install the build, kernel-header, and Python virtual-environment prerequisites:

```bash
sudo apt-get update
sudo apt-get install --yes \
  build-essential git linux-headers-$(uname -r) python3 python3-venv
```

Clone the repository and run the complete demo:

```bash
git clone https://github.com/SeonggukPark/VDevLab.git
cd VDevLab
sudo ./scripts/demo.sh
```

`demo.sh` builds the kernel module and userspace programs, runs all Python tests,
validates the scenarios, loads `/dev/vdevlab0`, executes the recovery and
disconnect scenarios, checks both reports, and unloads the module. Build steps
run as the invoking user even when the entry command uses `sudo`.

A successful run ends with output similar to:

```text
result: name=three-eio-recovery exit_code=0 timed_out=false forced=false events=3 status=PASS
result: name=device-disconnect exit_code=0 timed_out=false forced=false events=3 status=PASS
PASS report: recovery schema v1 assertions and kernel log
PASS report: disconnect schema v1 assertions and kernel log
PASS unload: fault state cleared, module removed, and device node absent
PASS demo: recovery and disconnect scenarios
```

Reports are written under `reports/`:

```text
reports/recovery-YYYYMMDDTHHMMSSZ.json
reports/disconnect-YYYYMMDDTHHMMSSZ.json
```

Deterministic schema examples are checked in at
[`examples/reports/recovery-pass.json`](examples/reports/recovery-pass.json) and
[`examples/reports/recovery-fail.json`](examples/reports/recovery-fail.json).
The focused [`delay.yaml`](examples/scenarios/delay.yaml) scenario demonstrates
the existing deterministic read-delay contract and its documented timing
tolerance without changing the schema or kernel UAPI.

## Individual commands

Prepare and validate the project without loading the kernel module:

```bash
./scripts/setup.sh
```

Validate scenario files directly:

```bash
.venv/bin/vdevlab validate examples/scenarios/*.yaml
```

Load or unload the module explicitly:

```bash
sudo ./scripts/load.sh
sudo ./scripts/unload.sh
```

The unload script is idempotent and can also be used as a manual cleanup step.

## Project layout

- `kernel/`: character device and deterministic fault contracts
- `tools/`: fault-control utility
- `examples/`: sample monitor, YAML scenarios, and report examples
- `src/vdevlab/`: scenario parser, runner, assertions, and report generator
- `tests/`: kernel/userspace contract test
- `python_tests/`: parser, scheduler, process, assertion, report, and CLI tests
- `scripts/`: setup, module lifecycle, smoke, contract, and demo automation
- `docs/`: fault model, scenario format, and sample-monitor references

## Design documentation

- [`docs/architecture.md`](docs/architecture.md): components, runtime flow,
  concurrency, cleanup, support boundary, and known limitations
- [`docs/alternatives.md`](docs/alternatives.md): comparison with QEMU, Renode,
  umockdev, CUSE, and Linux fault injection
- [`docs/adr/0001-kernel-module.md`](docs/adr/0001-kernel-module.md): why the
  reference backend is a Linux kernel module
- [`docs/adr/0002-read-path-faults.md`](docs/adr/0002-read-path-faults.md): why
  data faults apply to consumer reads rather than scenario injection writes

## Contributing

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md). It contains the userspace-only
test path, the Ubuntu kernel runtime Gate, documentation expectations, and the
pull-request checklist. Planned work is tracked in [`ROADMAP.md`](ROADMAP.md).

## Versioning

VDevLab follows Semantic Versioning for project releases. Scenario and report
documents are versioned independently through their top-level
`schema_version`. Version 1 readers reject unknown schema versions instead of
silently interpreting them. Implementation fixes and clarifications that do not
change the accepted document shape remain within a schema version. Adding or
removing a field, changing its type or meaning, or changing accepted values
requires a new schema version. The supported versions and migration notes are
recorded in `CHANGELOG.md`.

## License

The kernel module, UAPI header, C userspace programs, Python package, tests,
automation scripts, examples, and project documentation are licensed under
GPL-2.0-only. Source files use `SPDX-License-Identifier: GPL-2.0-only`; the full
license text is in [`LICENSE`](LICENSE).

Third-party packages are not relicensed by this project. Their versions,
purposes, and upstream license references are listed in
[`DEPENDENCIES.md`](DEPENDENCIES.md) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
