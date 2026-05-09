#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"

if CH_BIN_RESOLVED="$(resolve_clickhouse_bin)"; then
    echo "[clickhouse] install done (${CH_BIN_RESOLVED})"
    exit 0
fi

mkdir -p "${CH_LOCAL_DIR}"
tmp_tar="${CH_LOCAL_DIR}/${CH_PACKAGE_NAME}.tgz.part"
tmp_dir="${CH_LOCAL_DIR}/${CH_PACKAGE_NAME}.tmp"

if [ ! -s "${tmp_tar}" ]; then
    curl -fL -C - --retry 5 --retry-delay 2 "${CH_PACKAGE_URL}" -o "${tmp_tar}"
fi

rm -rf "${tmp_dir}"
mkdir -p "${tmp_dir}"
tar -xzf "${tmp_tar}" -C "${tmp_dir}"

extracted_root="$(find "${tmp_dir}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "${extracted_root}" ]; then
    echo "Unable to determine extracted ClickHouse directory under ${tmp_dir}" >&2
    exit 1
fi

rm -rf "${CH_HOME_DEFAULT}"
mv "${extracted_root}" "${CH_HOME_DEFAULT}"
rm -rf "${tmp_dir}"

CH_BIN_RESOLVED="$(resolve_clickhouse_bin)"
echo "[clickhouse] install done (${CH_BIN_RESOLVED})"
