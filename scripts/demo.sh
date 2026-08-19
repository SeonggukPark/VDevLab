#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
setup_path="${project_root}/scripts/setup.sh"
load_path="${project_root}/scripts/load.sh"
unload_path="${project_root}/scripts/unload.sh"
control_path="${project_root}/tools/vdevlab-ctl"
vdevlab_path="${project_root}/.venv/bin/vdevlab"
python_path="${project_root}/.venv/bin/python"
report_dir="${VDEVLAB_REPORT_DIR:-${project_root}/reports}"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
recovery_report="${report_dir}/recovery-${run_id}.json"
disconnect_report="${report_dir}/disconnect-${run_id}.json"
prepared=0
module_loaded=0

if [[ "${1:-}" == "--prepared" ]]; then
    prepared=1
    shift
fi
if [[ "$#" -ne 0 ]]; then
    echo "Usage: $0" >&2
    exit 2
fi

cleanup() {
    local status=$?

    trap - EXIT INT TERM
    if [[ -x "${control_path}" && -e /dev/vdevlab0 ]]; then
        "${control_path}" reset >/dev/null 2>&1 || true
    fi
    if [[ "${module_loaded}" -eq 1 ]] || grep -q '^vdevlab_core ' /proc/modules; then
        "${unload_path}" >/dev/null 2>&1 || true
    fi
    if [[ -n "${SUDO_UID:-}" && -n "${SUDO_GID:-}" ]]; then
        [[ ! -e "${recovery_report}" ]] || \
            chown "${SUDO_UID}:${SUDO_GID}" "${recovery_report}" || true
        [[ ! -e "${disconnect_report}" ]] || \
            chown "${SUDO_UID}:${SUDO_GID}" "${disconnect_report}" || true
    fi
    exit "${status}"
}

trap cleanup EXIT INT TERM

if [[ "${EUID}" -ne 0 ]]; then
    "${setup_path}"
    exec sudo env VDEVLAB_REPORT_DIR="${report_dir}" \
        "${BASH_SOURCE[0]}" --prepared
fi

if [[ "${prepared}" -eq 0 ]]; then
    if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
        sudo -H -u "${SUDO_USER}" "${setup_path}"
    else
        "${setup_path}"
    fi
fi

if grep -q '^vdevlab_core ' /proc/modules; then
    echo "error: vdevlab_core is already loaded; unload it before the demo" >&2
    exit 1
fi

mkdir -p "${report_dir}"
"${load_path}"
module_loaded=1

"${vdevlab_path}" run "${project_root}/examples/scenarios/recovery.yaml" \
    --cwd "${project_root}" --report "${recovery_report}"
"${vdevlab_path}" run "${project_root}/examples/scenarios/disconnect.yaml" \
    --cwd "${project_root}" --report "${disconnect_report}"

"${python_path}" - "${recovery_report}" "${disconnect_report}" <<'PY'
import json
from pathlib import Path
import sys

required = {
    "recovery": {"event_count", "stdout", "kernel_warnings", "recovery_latency"},
    "disconnect": {"event_count", "stdout", "disconnect", "kernel_warnings"},
}
for name, raw_path in zip(required, sys.argv[1:], strict=True):
    document = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or document.get("status") != "PASS":
        raise SystemExit(f"FAIL report: {name} did not produce schema v1 PASS")
    passed_types = {
        assertion.get("type")
        for assertion in document.get("assertions", [])
        if assertion.get("passed") is True
    }
    missing = required[name] - passed_types
    if missing:
        raise SystemExit(
            f"FAIL report: {name} missing passing assertions: {sorted(missing)}"
        )
    kernel_log = document.get("observations", {}).get("kernel_log", {})
    if not kernel_log.get("available") or kernel_log.get("warning_count") != 0:
        raise SystemExit(f"FAIL report: {name} kernel warning check failed")
    print(f"PASS report: {name} schema v1 assertions and kernel log")
PY

if [[ "$("${control_path}" get)" != "fault=none" ]]; then
    echo "FAIL cleanup: active fault remains after scenarios" >&2
    exit 1
fi
if pgrep -x vtemp-monitor >/dev/null; then
    echo "FAIL cleanup: vtemp-monitor process remains" >&2
    exit 1
fi

"${unload_path}"
module_loaded=0
if [[ -e /dev/vdevlab0 ]]; then
    echo "FAIL cleanup: /dev/vdevlab0 remains" >&2
    exit 1
fi

if [[ -n "${SUDO_UID:-}" && -n "${SUDO_GID:-}" ]]; then
    chown "${SUDO_UID}:${SUDO_GID}" "${recovery_report}" "${disconnect_report}"
fi

echo "PASS demo: recovery and disconnect scenarios"
echo "Recovery report: ${recovery_report}"
echo "Disconnect report: ${disconnect_report}"
