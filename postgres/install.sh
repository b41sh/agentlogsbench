#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"

if PG_BIN_DIR_RESOLVED="$(resolve_pg_bin_dir)" && python_can_import_psycopg2; then
    echo "[postgres] install done (${PG_BIN_DIR_RESOLVED})"
    exit 0
fi

apt_install_postgres_runtime

PG_BIN_DIR_RESOLVED="$(resolve_pg_bin_dir)"
if ! python_can_import_psycopg2; then
    echo "python3-psycopg2 is still unavailable after installation." >&2
    exit 1
fi

echo "[postgres] install done (${PG_BIN_DIR_RESOLVED})"
