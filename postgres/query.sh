#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
OUT_FILE="${OUT_FILE:-${RESULT_DIR}/query.out}"
RESULT_FILE="${RESULT_FILE:-${RESULT_DIR}/result.json}"

mkdir -p "${RESULT_DIR}"

PG_CLIENT_DIR="${PG_CLIENT_DIR:-$(resolve_pg_client_dir || true)}"
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-55432}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-agentlogsbench_pg}"
PG_TABLE="${PG_TABLE:-agent_observations}"

run_python_with_pgclient "${ROOT_DIR}/agentlogsbench/postgres/query_runner.py" \
    --root "${ROOT_DIR}" \
    --result-dir "${RESULT_DIR}" \
    --out-file "${OUT_FILE}" \
    --result-file "${RESULT_FILE}" \
    --host "${PG_HOST}" \
    --port "${PG_PORT}" \
    --user "${PG_USER}" \
    --db "${PG_DB}" \
    --table "${PG_TABLE}"
