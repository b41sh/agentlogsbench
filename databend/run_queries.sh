#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <DB_NAME> [QUERIES_FILE]" >&2
    exit 1
fi

DB_NAME="$1"
QUERIES_FILE="${2:-${SCRIPT_DIR}/queries.sql}"

python3 "${SCRIPT_DIR}/run_queries.py" "${DB_NAME}" "${QUERIES_FILE}"
