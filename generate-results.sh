#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_PATH="${SCRIPT_DIR}/data.generated.js"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --output)
            OUTPUT_PATH="$2"
            shift
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

TMP_OUTPUT="${OUTPUT_PATH}.new"

python3 "${SCRIPT_DIR}/common/render_dashboard.py" \
    --root "${SCRIPT_DIR}" \
    --output "${TMP_OUTPUT}" >/dev/null

if [ -f "${OUTPUT_PATH}" ]; then
    mv "${OUTPUT_PATH}" "${OUTPUT_PATH}.bak"
fi
mv "${TMP_OUTPUT}" "${OUTPUT_PATH}"

echo "Generated ${OUTPUT_PATH}"
