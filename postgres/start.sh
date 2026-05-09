#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"

RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
PGDATA="${PGDATA:-${RUNTIME_DIR}/pgdata}"
PG_LOG="${PG_LOG:-${RUNTIME_DIR}/postgres.log}"
PG_PORT="$(resolve_pg_port "${PG_PORT:-}")"

bash "${SCRIPT_DIR}/install.sh"
PGDATA="${PGDATA}" PG_LOG="${PG_LOG}" PG_PORT="${PG_PORT}" RUNTIME_DIR="${RUNTIME_DIR}" bash "${SCRIPT_DIR}/deploy.sh"
