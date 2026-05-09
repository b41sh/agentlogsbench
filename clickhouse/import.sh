#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"

if [ -n "${CH_BIN:-}" ] && [ -x "${CH_BIN}" ]; then
    CH_BIN_RESOLVED="${CH_BIN}"
else
    CH_BIN_RESOLVED="$(resolve_clickhouse_bin)"
fi
CH_PATH="${CH_PATH:-${SCRIPT_DIR}/runtime/ch_data}"
CH_DB="${CH_DB:-bench}"
CH_TABLE="${CH_TABLE:-agent_observations}"
DATA_GLOB="${DATA_GLOB:-${ROOT_DIR}/agentlogsbench/common/generated/small/agent_observations_s.ndjson}"
CREATE_SQL="${CREATE_SQL:-${SCRIPT_DIR}/create.sql}"

mkdir -p "${CH_PATH}"

benchmark_log "clickhouse" "Preparing schema ${CH_DB}.${CH_TABLE}"
schema_sql="$(sed -e "s/__CH_DB__/${CH_DB}/g" -e "s/__CH_TABLE__/${CH_TABLE}/g" "${CREATE_SQL}")"
"${CH_BIN_RESOLVED}" local --path "${CH_PATH}" -q "${schema_sql}"

shopt -s nullglob
files=( ${DATA_GLOB} )
shopt -u nullglob

if [ "${#files[@]}" -eq 0 ]; then
    echo "No files matched DATA_GLOB=${DATA_GLOB}" >&2
    exit 1
fi

benchmark_log "clickhouse" "Importing ${#files[@]} files into ${CH_DB}.${CH_TABLE}"
file_index=0
for file in "${files[@]}"; do
    file_index=$((file_index + 1))
    benchmark_log "clickhouse" "Import file ${file_index}/${#files[@]}: $(basename "${file}")"
    if [ "${file##*.}" = "gz" ]; then
        gzip -dc "${file}" | "${CH_BIN_RESOLVED}" local --path "${CH_PATH}" --query "INSERT INTO ${CH_DB}.${CH_TABLE} FORMAT JSONEachRow"
    else
        "${CH_BIN_RESOLVED}" local --path "${CH_PATH}" --query "INSERT INTO ${CH_DB}.${CH_TABLE} FORMAT JSONEachRow" < "${file}"
    fi
done

benchmark_log "clickhouse" "Import complete files=${#files[@]}"
