#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export OS_INDEX="${OS_INDEX:-agentlogsbench_agent_observations}"
export RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
export OS_PID_FILE="${OS_PID_FILE:-${RUNTIME_DIR}/opensearch.pid}"
export OS_ENDPOINT="${OS_ENDPOINT:-http://127.0.0.1:9200}"
export RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"

curl -sS -X DELETE "${OS_ENDPOINT}/${OS_INDEX}" >/dev/null 2>&1 || true

if [ -f "${OS_PID_FILE}" ]; then
    pid="$(cat "${OS_PID_FILE}")"
    kill "${pid}" >/dev/null 2>&1 || true
    rm -f "${OS_PID_FILE}"
fi

rm -rf "${RUNTIME_DIR}"
rm -rf "${SCRIPT_DIR}/result"
mkdir -p "${RESULT_DIR}"
echo "[opensearch] cleanup done"
