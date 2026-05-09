#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
CH_PATH="${CH_PATH:-${RUNTIME_DIR}/ch_data}"

CH_PATH="${CH_PATH}" RUNTIME_DIR="${RUNTIME_DIR}" RESULT_DIR="${RESULT_DIR}" bash "${SCRIPT_DIR}/cleanup.sh"
