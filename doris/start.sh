#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"

bash "${SCRIPT_DIR}/install.sh"
RUNTIME_DIR="${RUNTIME_DIR}" bash "${SCRIPT_DIR}/deploy.sh"
