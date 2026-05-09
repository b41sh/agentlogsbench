#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
OUT_FILE="${OUT_FILE:-${RESULT_DIR}/query.out}"
RESULT_FILE="${RESULT_FILE:-${RESULT_DIR}/result.json}"
mkdir -p "$(dirname "${OUT_FILE}")"

ES_ENDPOINT="${ES_ENDPOINT:-http://127.0.0.1:9200}"
ES_INDEX="${ES_INDEX:-agentlogsbench_agent_observations}"
ES_STORAGE_PATH="${ES_STORAGE_PATH:-${SCRIPT_DIR}/runtime/data}"

mkdir -p "${RESULT_DIR}"

python3 "${ROOT_DIR}/agentlogsbench/elastic/query_runner.py" \
  --root "${ROOT_DIR}" \
  --result-dir "${RESULT_DIR}" \
  --out-file "${OUT_FILE}" \
  --result-file "${RESULT_FILE}" \
  --endpoint "${ES_ENDPOINT}" \
  --index "${ES_INDEX}" \
  --storage-path "${ES_STORAGE_PATH}"
