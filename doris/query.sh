#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
OUT_FILE="${OUT_FILE:-${RESULT_DIR}/query.out}"
RESULT_FILE="${RESULT_FILE:-${RESULT_DIR}/result.json}"

if [ -f "${RUNTIME_DIR}/deploy.env" ]; then
    # shellcheck disable=SC1090
    source "${RUNTIME_DIR}/deploy.env"
fi

mkdir -p "${RESULT_DIR}"

DORIS_FE_HOST="${DORIS_FE_HOST:-127.0.0.1}"
DORIS_QUERY_PORT="${DORIS_QUERY_PORT:-19030}"
DORIS_USER="${DORIS_USER:-root}"
DORIS_PASSWORD="${DORIS_PASSWORD:-}"
DORIS_DB="${DORIS_DB:-agentlogsbench_bench}"
DORIS_TABLE="${DORIS_TABLE:-agent_observations}"

python3 "${ROOT_DIR}/agentlogsbench/doris/query_runner.py" \
  --root "${ROOT_DIR}" \
  --result-dir "${RESULT_DIR}" \
  --out-file "${OUT_FILE}" \
  --result-file "${RESULT_FILE}" \
  --host "${DORIS_FE_HOST}" \
  --port "${DORIS_QUERY_PORT}" \
  --user "${DORIS_USER}" \
  --password "${DORIS_PASSWORD}" \
  --db "${DORIS_DB}" \
  --table "${DORIS_TABLE}" \
  --storage-path "${RUNTIME_DIR}/be-storage" \
  --metrics-file "${RUNTIME_DIR}/metrics.json"
