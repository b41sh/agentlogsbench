#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
OS_CONF_DIR="${OS_CONF_DIR:-${RUNTIME_DIR}/conf}"
OS_STORAGE_PATH="${OS_STORAGE_PATH:-${RUNTIME_DIR}/data}"

bash "${SCRIPT_DIR}/install.sh"
RUNTIME_DIR="${RUNTIME_DIR}" OS_CONF_DIR="${OS_CONF_DIR}" OS_STORAGE_PATH="${OS_STORAGE_PATH}" bash "${SCRIPT_DIR}/deploy.sh"
