#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
rm -rf "${RUNTIME_DIR}"
rm -rf "${SCRIPT_DIR}/result"
mkdir -p "${RESULT_DIR}"
echo "[clickhouse] cleanup done"
