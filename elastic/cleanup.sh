#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export ES_INDEX="${ES_INDEX:-agentlogsbench_agent_observations}"
export RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
export ES_PID_FILE="${ES_PID_FILE:-${RUNTIME_DIR}/elasticsearch.pid}"
export ES_ENDPOINT="${ES_ENDPOINT:-http://127.0.0.1:9200}"
export RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"

curl -sS -X DELETE "${ES_ENDPOINT}/${ES_INDEX}" >/dev/null 2>&1 || true

if [ -f "${ES_PID_FILE}" ]; then
    pid="$(cat "${ES_PID_FILE}")"
    kill "${pid}" >/dev/null 2>&1 || true
    rm -f "${ES_PID_FILE}"
fi

rm -rf "${RUNTIME_DIR}"
rm -rf "${SCRIPT_DIR}/result"
mkdir -p "${RESULT_DIR}"
echo "[elastic] cleanup done"
