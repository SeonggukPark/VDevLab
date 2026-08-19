#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_path="${project_root}/.venv"

require_command() {
    local command_name="$1"
    local package_hint="$2"

    if ! command -v "${command_name}" >/dev/null 2>&1; then
        echo "error: ${command_name} is required; install ${package_hint}" >&2
        return 1
    fi
}

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "error: VDevLab setup requires Linux" >&2
    exit 1
fi

require_command make "build-essential"
require_command cc "build-essential"
require_command python3 "python3"

if [[ ! -d "/lib/modules/$(uname -r)/build" ]]; then
    echo "error: kernel headers for $(uname -r) are required" >&2
    echo "hint: install linux-headers-$(uname -r)" >&2
    exit 1
fi

if [[ ! -x "${venv_path}/bin/python" ]]; then
    if ! python3 -m venv "${venv_path}"; then
        echo "error: failed to create ${venv_path}" >&2
        echo "hint: install python3-venv" >&2
        exit 1
    fi
fi

"${venv_path}/bin/python" -m pip install --editable "${project_root}[test]"
"${venv_path}/bin/python" -m pytest "${project_root}/python_tests"
"${venv_path}/bin/vdevlab" validate "${project_root}"/examples/scenarios/*.yaml
make -C "${project_root}" all

echo "PASS setup: Python tests, scenarios, kernel module, and userspace binaries"
