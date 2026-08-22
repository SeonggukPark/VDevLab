# Third-party notices

Current VDevLab source code is MIT, except for the loadable kernel module,
which is available under `GPL-2.0-only OR MIT`. The existing `v0.1.0` tag
retains its original GPL-2.0-only grant. The third-party projects below retain
their own copyright and license terms. No third-party source is copied into
this repository.

## Runtime and build packages

| Project | Use | Upstream license reference |
|---|---|---|
| PyYAML 6.0.3 | YAML parsing | MIT; `https://github.com/yaml/pyyaml/blob/6.0.3/LICENSE` |
| pytest 8.4.2 | Test runner | MIT; `https://github.com/pytest-dev/pytest/blob/8.4.2/LICENSE` |
| setuptools 84.0.0 | Python build backend | MIT; `https://github.com/pypa/setuptools/blob/v84.0.0/LICENSE` |
| Linux kernel headers | External module API and build | See `COPYING` and `LICENSES/` in the corresponding Linux source tree |

Python itself, GCC, GNU Make, Git, and Ubuntu packages are environment
prerequisites and are not redistributed with VDevLab. Consult the package or
distribution metadata for their complete notices.

## CI actions

The workflow references `actions/checkout@v6` and `actions/setup-python@v6`.
They run in GitHub Actions and are not vendored into this repository. Both
upstream repositories publish MIT license terms.

Before distributing a binary bundle, regenerate a software bill of materials
for that bundle and include the license texts required by the exact packaged
dependencies.
