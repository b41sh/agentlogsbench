#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
CH_PATH="${CH_PATH:-${RUNTIME_DIR}/ch_data}"

bash "${SCRIPT_DIR}/install.sh"
CH_PATH="${CH_PATH}" bash "${SCRIPT_DIR}/deploy.sh"
