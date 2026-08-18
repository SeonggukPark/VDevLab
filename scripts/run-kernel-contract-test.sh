#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
module_path="${project_root}/kernel/vdevlab_core.ko"
test_path="${project_root}/tests/vdevlab-contract-test"
control_path="${project_root}/tools/vdevlab-ctl"
module_loaded=0
load_cycles="${VDEVLAB_LOAD_CYCLES:-20}"
log_dir="${project_root}/logs"
log_path="${log_dir}/kernel-contract-$(date -u +%Y%m%dT%H%M%SZ).log"

mkdir -p "${log_dir}"
exec > >(tee "${log_path}") 2>&1

wait_for_device() {
    local attempt

    for attempt in {1..50}; do
        [[ -e /dev/vdevlab0 ]] && return 0
        sleep 0.1
    done

    echo "FAIL setup: /dev/vdevlab0 was not created" >&2
    return 1
}

wait_for_device_removal() {
    local attempt

    for attempt in {1..50}; do
        [[ ! -e /dev/vdevlab0 ]] && return 0
        sleep 0.1
    done

    echo "FAIL cleanup: /dev/vdevlab0 remains after module unload" >&2
    return 1
}

cleanup() {
    if [[ -x "${control_path}" && -e /dev/vdevlab0 ]]; then
        sudo "${control_path}" clear >/dev/null 2>&1 || true
    fi

    if [[ "${module_loaded}" -eq 1 ]]; then
        sudo rmmod vdevlab_core || true
        module_loaded=0
    fi
}

trap cleanup EXIT INT TERM

if grep -q '^vdevlab_core ' /proc/modules; then
    echo "error: vdevlab_core is already loaded; unload it before this test" >&2
    exit 1
fi

if [[ "${EUID}" -eq 0 ]]; then
    echo "error: run this script as a normal user; it invokes sudo where needed" >&2
    exit 1
fi

if [[ ! "${load_cycles}" =~ ^[1-9][0-9]*$ ]]; then
    echo "error: VDEVLAB_LOAD_CYCLES must be a positive integer" >&2
    exit 1
fi

echo "Runtime log: ${log_path}"

make -C "${project_root}" all

before_lines="$(sudo dmesg | wc -l)"

sudo insmod "${module_path}"
module_loaded=1
wait_for_device

sudo "${test_path}"

sudo rmmod vdevlab_core
module_loaded=0
wait_for_device_removal

for ((cycle = 2; cycle <= load_cycles; cycle++)); do
    sudo insmod "${module_path}"
    module_loaded=1
    wait_for_device
    sudo rmmod vdevlab_core
    module_loaded=0
    wait_for_device_removal
done

echo "PASS module-lifecycle: ${load_cycles} load/unload cycles"

new_kernel_log="$(sudo dmesg | tail -n "+$((before_lines + 1))")"
printf '%s\n' "${new_kernel_log}"

if printf '%s\n' "${new_kernel_log}" | grep -Eq \
    'BUG:|Oops:|WARNING:|kernel panic|general protection fault|lockdep'; then
    echo "FAIL kernel-log: warning/oops pattern detected" >&2
    exit 1
fi

echo "PASS kernel-log: no warning/oops pattern detected"
echo "PASS cleanup: module and device node removed"
