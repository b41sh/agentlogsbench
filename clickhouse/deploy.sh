#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"

CH_PATH="${CH_PATH:-${SCRIPT_DIR}/runtime/ch_data}"

if ! CH_BIN_RESOLVED="$(resolve_clickhouse_bin)"; then
    bash "${SCRIPT_DIR}/install.sh"
    CH_BIN_RESOLVED="$(resolve_clickhouse_bin)"
fi

mkdir -p "${CH_PATH}"
echo "[clickhouse] deploy done (${CH_BIN_RESOLVED})"
