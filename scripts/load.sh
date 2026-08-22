#!/usr/bin/env bash
# SPDX-License-Identifier: MIT

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
module_path="${project_root}/kernel/vdevlab_core.ko"

wait_for_device() {
    local attempt

    for attempt in {1..50}; do
        [[ -e /dev/vdevlab0 ]] && return 0
        sleep 0.1
    done

    echo "error: /dev/vdevlab0 was not created" >&2
    return 1
}

if [[ "${EUID}" -ne 0 ]]; then
    echo "error: load.sh requires root privileges" >&2
    exit 1
fi

if [[ ! -s "${module_path}" ]]; then
    echo "error: kernel module is missing; run scripts/setup.sh first" >&2
    exit 1
fi

if grep -q '^vdevlab_core ' /proc/modules; then
    echo "error: vdevlab_core is already loaded" >&2
    exit 1
fi

insmod "${module_path}"
if ! wait_for_device; then
    rmmod vdevlab_core 2>/dev/null || true
    exit 1
fi

echo "PASS load: vdevlab_core and /dev/vdevlab0 are ready"
