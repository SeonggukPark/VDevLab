# Dependencies

VDevLab keeps its Python dependency set intentionally small and pins versions
used by the reproducible setup. `pyproject.toml` is the authoritative package
configuration.

## Python

| Package | Version | Scope | Purpose |
|---|---:|---|---|
| Python | 3.10–3.12 | runtime | Scenario runner, assertions, and reporting |
| PyYAML | 6.0.3 | runtime | Parse scenario YAML before strict validation |
| pytest | 8.4.2 | test | Userspace unit and CLI tests |
| setuptools | 84.0.0 | build | Build editable/installable Python package |

Install the runtime and test dependencies through the project metadata:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --editable '.[test]'
```

## Linux system requirements

| Component | Verified value | Purpose |
|---|---|---|
| Ubuntu | 22.04 LTS | Runtime Gate environment |
| Linux | 6.8.0-136-generic and 6.8.0-138-generic x86-64 | Verified module runtime |
| GCC | 12 | Kernel and C userspace build |
| GNU Make | Ubuntu 22.04 package | Build orchestration |
| matching kernel headers | `linux-headers-$(uname -r)` | Kernel module build |
| Git | Ubuntu package | Clone and contribution workflow |

Other recent Linux kernels may work, but they have not passed the same runtime
Gate. The build requires headers for the target or running kernel selected by
`KDIR`.

## Dependency update procedure

1. Update one dependency group at a time in `pyproject.toml` or CI.
2. Recreate the virtual environment and run `./scripts/setup.sh`.
3. Run `sudo ./scripts/demo.sh` on the verified Ubuntu runtime when the update
   can affect scenario execution or reports.
4. Record compatibility and license changes in `CHANGELOG.md` and
   `THIRD_PARTY_NOTICES.md`.
