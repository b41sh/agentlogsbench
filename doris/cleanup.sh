#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"

if [ -f "${RUNTIME_DIR}/deploy.env" ]; then
    # shellcheck disable=SC1090
    source "${RUNTIME_DIR}/deploy.env"
fi

DORIS_FE_HOST="${DORIS_FE_HOST:-127.0.0.1}"
DORIS_QUERY_PORT="${DORIS_QUERY_PORT:-19030}"
DORIS_USER="${DORIS_USER:-root}"
DORIS_PASSWORD="${DORIS_PASSWORD:-}"
DORIS_DB="${DORIS_DB:-agentlogsbench_bench}"
DORIS_TABLE="${DORIS_TABLE:-agent_observations}"

mysql_env=()
if [ -n "${DORIS_PASSWORD}" ]; then
    mysql_env=("MYSQL_PWD=${DORIS_PASSWORD}")
fi

env "${mysql_env[@]}" mysql -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" "${DORIS_DB}" \
    -e "TRUNCATE TABLE ${DORIS_TABLE};" >/dev/null 2>&1 || true

if [ "${DORIS_LOCAL:-0}" = "1" ] && [ -n "${DORIS_HOME:-}" ]; then
    JAVA_HOME="${JAVA_HOME:-}" "${DORIS_HOME}/be/bin/stop_be.sh" >/dev/null 2>&1 || true
    JAVA_HOME="${JAVA_HOME:-}" "${DORIS_HOME}/fe/bin/stop_fe.sh" >/dev/null 2>&1 || true
fi

rm -rf "${RUNTIME_DIR}"
rm -rf "${SCRIPT_DIR}/result"
mkdir -p "${RESULT_DIR}"
echo "[doris] cleanup done"
