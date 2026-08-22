#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
module_path="${project_root}/kernel/vdevlab_core.ko"
monitor_path="${project_root}/examples/vtemp-monitor"
control_path="${project_root}/tools/vdevlab-ctl"
log_dir="${VDEVLAB_LOG_DIR:-${project_root}/logs}"
smoke_cycles="${VDEVLAB_SMOKE_CYCLES:-10}"
run_id="${VDEVLAB_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
module_loaded=0
monitor_pid=""

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

wait_for_event_count() {
    local log_path="$1"
    local event="$2"
    local expected="$3"
    local attempt
    local observed

    for attempt in {1..100}; do
        observed="$(grep -c "\"event\":\"${event}\"" "${log_path}" || true)"
        if [[ "${observed}" -ge "${expected}" ]]; then
            return 0
        fi
        sleep 0.1
    done

    echo "FAIL log: expected ${expected} ${event} event(s)" >&2
    return 1
}

inject_temperature() {
    printf '%s\n' "$1" | sudo tee /dev/vdevlab0 >/dev/null
}

cleanup() {
    if [[ -n "${monitor_pid}" ]] && kill -0 "${monitor_pid}" 2>/dev/null; then
        sudo kill "${monitor_pid}" 2>/dev/null || true
        wait "${monitor_pid}" 2>/dev/null || true
    fi
    monitor_pid=""

    if [[ -x "${control_path}" && -e /dev/vdevlab0 ]]; then
        sudo "${control_path}" clear >/dev/null 2>&1 || true
    fi

    if [[ "${module_loaded}" -eq 1 ]]; then
        sudo rmmod vdevlab_core 2>/dev/null || true
        module_loaded=0
    fi
}

run_cycle() {
    local cycle="$1"
    local log_path="${log_dir}/vtemp-smoke-${run_id}-${cycle}.jsonl"
    local retry_count

    sudo insmod "${module_path}"
    module_loaded=1
    wait_for_device

    sudo stdbuf -oL -eL "${monitor_path}" --poll-timeout-ms 250 \
        >"${log_path}" 2>&1 &
    monitor_pid="$!"
    wait_for_event_count "${log_path}" "MONITOR_STARTED" 1

    inject_temperature 25
    wait_for_event_count "${log_path}" "TEMPERATURE" 1

    inject_temperature 85
    wait_for_event_count "${log_path}" "THERMAL_WARNING" 1

    sudo "${control_path}" set eio 3 >/dev/null
    wait_for_event_count "${log_path}" "READ_RETRY" 3
    inject_temperature 42
    wait_for_event_count "${log_path}" "RECOVERY_SUCCESS" 1
    wait_for_event_count "${log_path}" "TEMPERATURE" 2

    sudo "${control_path}" set disconnect >/dev/null
    wait_for_event_count "${log_path}" "DEVICE_DISCONNECTED" 1
    if ! wait "${monitor_pid}"; then
        echo "FAIL monitor: process exited with an error" >&2
        return 1
    fi
    monitor_pid=""

    retry_count="$(grep -c '"event":"READ_RETRY"' "${log_path}")"
    if [[ "${retry_count}" -ne 3 ]]; then
        echo "FAIL retry: expected 3 retries, observed ${retry_count}" >&2
        return 1
    fi
    if grep -Ev '^\{"timestamp_ms":[0-9]+,"event":"[A-Z_]+' "${log_path}" \
        >/dev/null; then
        echo "FAIL log: non-structured or missing monotonic timestamp" >&2
        return 1
    fi

    sudo "${control_path}" reconnect >/dev/null
    sudo rmmod vdevlab_core
    module_loaded=0
    wait_for_device_removal

    echo "PASS vtemp-smoke cycle=${cycle} log=${log_path}"
}

trap cleanup EXIT INT TERM

if [[ "${EUID}" -eq 0 ]]; then
    echo "error: run this script as a normal user; it invokes sudo where needed" >&2
    exit 1
fi

if [[ ! "${smoke_cycles}" =~ ^[1-9][0-9]*$ ]]; then
    echo "error: VDEVLAB_SMOKE_CYCLES must be a positive integer" >&2
    exit 1
fi

if grep -q '^vdevlab_core ' /proc/modules; then
    echo "error: vdevlab_core is already loaded; unload it before this test" >&2
    exit 1
fi

mkdir -p "${log_dir}"
make -C "${project_root}" all

for ((cycle = 1; cycle <= smoke_cycles; cycle++)); do
    run_cycle "${cycle}"
done

echo "PASS vtemp-smoke: ${smoke_cycles} consecutive cycle(s)"
