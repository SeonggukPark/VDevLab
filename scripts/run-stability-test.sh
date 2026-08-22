#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
setup_path="${project_root}/scripts/setup.sh"
smoke_path="${project_root}/scripts/run-vtemp-smoke-test.sh"
unload_path="${project_root}/scripts/unload.sh"
cycles="${VDEVLAB_STABILITY_CYCLES:-100}"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
log_dir="${VDEVLAB_STABILITY_LOG_DIR:-${project_root}/logs/stability-${run_id}}"
summary_path="${VDEVLAB_STABILITY_SUMMARY:-${log_dir}/summary.json}"
runtime_log="${log_dir}/stability.log"
started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
completed_cycles=0
warning_count=0
status="FAIL"
failure_reason=""

if [[ "${EUID}" -eq 0 ]]; then
    echo "error: run this script as a normal user; it invokes sudo where needed" >&2
    exit 1
fi

if [[ ! "${cycles}" =~ ^[1-9][0-9]*$ ]]; then
    echo "error: VDEVLAB_STABILITY_CYCLES must be a positive integer" >&2
    exit 1
fi

mkdir -p "${log_dir}"
mkdir -p "$(dirname "${summary_path}")"
exec > >(tee "${runtime_log}") 2>&1
SECONDS=0

write_summary() {
    local finished_utc="$1"
    local python_path="${project_root}/.venv/bin/python"

    if [[ ! -x "${python_path}" ]]; then
        if command -v python3 >/dev/null 2>&1 && \
           python3 -c 'raise SystemExit(0)' >/dev/null 2>&1; then
            python_path="$(command -v python3)"
        elif command -v python >/dev/null 2>&1 && \
             python -c 'raise SystemExit(0)' >/dev/null 2>&1; then
            python_path="$(command -v python)"
        else
            echo "error: Python is required to write ${summary_path}" >&2
            return 1
        fi
    fi

    "${python_path}" - \
        "${summary_path}" "${status}" "${cycles}" "${completed_cycles}" \
        "${warning_count}" "${SECONDS}" "${started_utc}" "${finished_utc}" \
        "${log_dir}" "${runtime_log}" "${failure_reason}" <<'PY'
import json
from pathlib import Path
import sys

(
    summary_path,
    status,
    requested_cycles,
    completed_cycles,
    warning_count,
    duration_seconds,
    started_utc,
    finished_utc,
    log_directory,
    runtime_log,
    failure_reason,
) = sys.argv[1:]

document = {
    "schema_version": 1,
    "status": status,
    "requested_cycles": int(requested_cycles),
    "completed_cycles": int(completed_cycles),
    "kernel_warning_count": int(warning_count),
    "duration_seconds": int(duration_seconds),
    "started_utc": started_utc,
    "finished_utc": finished_utc,
    "log_directory": log_directory,
    "runtime_log": runtime_log,
    "failure_reason": failure_reason or None,
}
Path(summary_path).write_text(
    json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

finalize() {
    local exit_code=$?
    local finished_utc

    trap - EXIT INT TERM

    if grep -q '^vdevlab_core ' /proc/modules || [[ -e /dev/vdevlab0 ]]; then
        if ! sudo "${unload_path}" >/dev/null 2>&1; then
            exit_code=1
            failure_reason="${failure_reason:-cleanup unload failed}"
        fi
    fi

    if grep -q '^vdevlab_core ' /proc/modules; then
        exit_code=1
        failure_reason="${failure_reason:-kernel module remains after cleanup}"
    elif [[ -e /dev/vdevlab0 ]]; then
        exit_code=1
        failure_reason="${failure_reason:-device node remains after cleanup}"
    elif command -v pgrep >/dev/null 2>&1 && \
         pgrep -x vtemp-monitor >/dev/null; then
        exit_code=1
        failure_reason="${failure_reason:-monitor process remains after cleanup}"
    fi

    completed_cycles="$(grep -Ec '^PASS vtemp-smoke cycle=[0-9]+ ' \
        "${runtime_log}" || true)"
    if [[ "${exit_code}" -eq 0 && "${completed_cycles}" -eq "${cycles}" && \
          "${warning_count}" -eq 0 ]]; then
        status="PASS"
    else
        status="FAIL"
        if [[ -z "${failure_reason}" && "${completed_cycles}" -ne "${cycles}" ]]; then
            failure_reason="completed cycle record mismatch"
        fi
        failure_reason="${failure_reason:-runtime command failed with exit ${exit_code}}"
        exit_code=1
    fi

    finished_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    write_summary "${finished_utc}" || true
    echo "${status} stability: completed=${completed_cycles}/${cycles} " \
        "kernel_warnings=${warning_count} summary=${summary_path}"
    exit "${exit_code}"
}

trap finalize EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

sudo "${unload_path}" >/dev/null
"${setup_path}"

before_lines="$(sudo dmesg | wc -l)"

VDEVLAB_SMOKE_CYCLES="${cycles}" \
VDEVLAB_RUN_ID="${run_id}" \
VDEVLAB_LOG_DIR="${log_dir}" \
    bash "${smoke_path}"

new_kernel_log="$(sudo dmesg | tail -n "+$((before_lines + 1))")"
printf '%s\n' "${new_kernel_log}"
warning_count="$(printf '%s\n' "${new_kernel_log}" | grep -Ec \
    'BUG:|Oops:|WARNING:|kernel panic|general protection fault|lockdep' || true)"
if [[ "${warning_count}" -ne 0 ]]; then
    failure_reason="kernel warning/oops pattern detected"
    exit 1
fi

if grep -q '^vdevlab_core ' /proc/modules || [[ -e /dev/vdevlab0 ]] || \
   (command -v pgrep >/dev/null 2>&1 && pgrep -x vtemp-monitor >/dev/null); then
    failure_reason="residual module, device, or monitor state detected"
    exit 1
fi
