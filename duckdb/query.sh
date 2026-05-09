#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
OUT_FILE="${OUT_FILE:-${RESULT_DIR}/result.log}"
RESULT_FILE="${RESULT_FILE:-${RESULT_DIR}/result.json}"
DB_PATH="${DB_PATH:-${SCRIPT_DIR}/runtime/query.duckdb}"
DUCKDB_TABLE="${DUCKDB_TABLE:-agent_observations}"

mkdir -p "${RESULT_DIR}"

python3 "${ROOT_DIR}/agentlogsbench/duckdb/query_runner.py" \
  --root "${ROOT_DIR}" \
  --result-dir "${RESULT_DIR}" \
  --out-file "${OUT_FILE}" \
  --db-path "${DB_PATH}" \
  --table "${DUCKDB_TABLE}" \
  --result-file "${RESULT_FILE}"
