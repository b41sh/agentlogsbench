#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"

RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
PGDATA="${PGDATA:-${RUNTIME_DIR}/pgdata}"
PG_LOG="${PG_LOG:-${RUNTIME_DIR}/postgres.log}"

PGDATA="${PGDATA}" PG_LOG="${PG_LOG}" RUNTIME_DIR="${RUNTIME_DIR}" RESULT_DIR="${RESULT_DIR}" bash "${SCRIPT_DIR}/cleanup.sh"
