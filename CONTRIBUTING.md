# Contributing to VDevLab

Thank you for improving VDevLab. Contributions should keep the fault contract
deterministic, the runtime cleanup complete, and the evidence reproducible.

## Before starting

1. Search the existing issues and open one before beginning a substantial
   change. Describe the observable behavior and how it will be verified.
2. Keep one issue and one purpose per branch. Suggested branch names are
   `issue-<number>/<short-description>`.
3. Discuss changes to the ioctl UAPI, scenario schema, report schema, locking,
   or cleanup contract before implementation.

Use the bug or feature issue form when possible. Security-sensitive reports
should not include credentials, private logs, or machine identifiers in a
public issue.

## Userspace development path

Parser, scheduler, analysis, report, and CLI work can be prepared without
loading a kernel module. VDevLab supports Python 3.10 through 3.12.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --editable '.[test]'
.venv/bin/python -m pytest
.venv/bin/vdevlab validate examples/scenarios/*.yaml
```

The complete Python suite currently contains 139 tests. Treat that count as a
reference, not as a substitute for a zero exit status, because contributions
may add tests.

## Linux build path

Kernel and C userspace changes require Linux, a C toolchain, and headers that
match the running kernel.

```bash
sudo apt-get update
sudo apt-get install --yes \
  build-essential git linux-headers-$(uname -r) python3 python3-venv
./scripts/setup.sh
```

Run the smallest relevant runtime Gate, then run the complete demo before
requesting review for a kernel behavior change:

```bash
make contract-test
make smoke-test
sudo ./scripts/demo.sh
```

The runtime Gate is complete only when the expected fault counts and reports
pass, no new warning/oops/panic/lockdep message appears, and the module, device
node, monitor process, and active fault are gone after cleanup.

## Change requirements

- Add a regression test that would fail without the change.
- Preserve monotonic timing and deterministic event ordering.
- Document user-visible CLI, ioctl, scenario, report, or fault behavior.
- Keep scenario and report compatibility rules in mind; incompatible document
  changes require a new `schema_version` and migration notes.
- Add `SPDX-License-Identifier: MIT` to new source files.
- Preserve `GPL-2.0-only OR MIT` on the loadable kernel module source.
- Do not commit build products, virtual environments, generated reports, VM
  logs containing machine details, secrets, or submission-only artifacts.
- Update `CHANGELOG.md` for a user-visible change.

## Documentation changes

Commands in README and reference documents are testable interfaces. Run each
changed command in the environment it claims to support. Keep relative links
valid and use exact field names and exit behavior.

## Pull requests

Complete the pull-request template with:

- the related issue and change type;
- the problem, resulting behavior, and compatibility impact;
- exact verification commands, OS, kernel, compiler, and Python versions;
- kernel log and repeated-run evidence when applicable;
- a self-review of locking, wake-up, process termination, reset, and unload
  paths touched by the change.

CI compiles the kernel and userspace components and runs the userspace tests.
It cannot load the module on a hosted runner, so the author must attach Ubuntu
runtime evidence for changes to kernel behavior.

By contributing, you agree that your contribution is licensed under the
applicable project license: MIT by default, or `GPL-2.0-only OR MIT` for the
loadable kernel module source.
