#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${RUNTIME_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runtime}"
bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install.sh"
mkdir -p "${RUNTIME_DIR}"
