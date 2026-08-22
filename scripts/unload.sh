#!/usr/bin/env bash
# SPDX-License-Identifier: MIT

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
control_path="${project_root}/tools/vdevlab-ctl"

wait_for_device_removal() {
    local attempt

    for attempt in {1..50}; do
        [[ ! -e /dev/vdevlab0 ]] && return 0
        sleep 0.1
    done

    echo "error: /dev/vdevlab0 remains after module unload" >&2
    return 1
}

if [[ "${EUID}" -ne 0 ]]; then
    echo "error: unload.sh requires root privileges" >&2
    exit 1
fi

if [[ -x "${control_path}" && -e /dev/vdevlab0 ]]; then
    "${control_path}" reset >/dev/null
fi

if grep -q '^vdevlab_core ' /proc/modules; then
    rmmod vdevlab_core
fi

wait_for_device_removal
echo "PASS unload: fault state cleared, module removed, and device node absent"
