#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"

RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"

benchmark_log "databend" "Databend service is external; stop.sh does not stop DATABEND_DSN"

if [ -d "${RUNTIME_DIR}" ]; then
    find "${RUNTIME_DIR}" -mindepth 1 -maxdepth 1 -type d -empty -delete
fi
