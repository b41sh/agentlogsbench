#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
OUT_FILE="${OUT_FILE:-${RESULT_DIR}/query.out}"
RESULT_FILE="${RESULT_FILE:-${RESULT_DIR}/result.json}"
DATABEND_DB="${DATABEND_DB:-agentlogsbench_bench}"
DATABEND_TABLE="${DATABEND_TABLE:-agent_observations}"

mkdir -p "${RESULT_DIR}"

python3 "${ROOT_DIR}/agentlogsbench/databend/query_runner.py" \
  --root "${ROOT_DIR}" \
  --result-dir "${RESULT_DIR}" \
  --out-file "${OUT_FILE}" \
  --result-file "${RESULT_FILE}" \
  --database "${DATABEND_DB}" \
  --table "${DATABEND_TABLE}"
