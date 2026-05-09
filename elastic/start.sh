#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
ES_CONF_DIR="${ES_CONF_DIR:-${RUNTIME_DIR}/conf}"
ES_STORAGE_PATH="${ES_STORAGE_PATH:-${RUNTIME_DIR}/data}"

bash "${SCRIPT_DIR}/install.sh"
RUNTIME_DIR="${RUNTIME_DIR}" ES_CONF_DIR="${ES_CONF_DIR}" ES_STORAGE_PATH="${ES_STORAGE_PATH}" bash "${SCRIPT_DIR}/deploy.sh"
