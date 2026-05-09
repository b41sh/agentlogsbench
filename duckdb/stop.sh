#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${RUNTIME_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runtime}"
if [ -d "${RUNTIME_DIR}" ]; then
    find "${RUNTIME_DIR}" -mindepth 1 -maxdepth 1 -type d -empty -delete
fi
