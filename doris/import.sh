#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
METRICS_FILE="${METRICS_FILE:-${RUNTIME_DIR}/metrics.json}"

if [ -f "${RUNTIME_DIR}/deploy.env" ]; then
    # shellcheck disable=SC1090
    source "${RUNTIME_DIR}/deploy.env"
fi

DORIS_FE_HOST="${DORIS_FE_HOST:-127.0.0.1}"
DORIS_QUERY_PORT="${DORIS_QUERY_PORT:-19030}"
DORIS_HTTP_PORT="${DORIS_HTTP_PORT:-18030}"
DORIS_USER="${DORIS_USER:-root}"
DORIS_PASSWORD="${DORIS_PASSWORD:-}"
DORIS_DB="${DORIS_DB:-agentlogsbench_bench}"
DORIS_TABLE="${DORIS_TABLE:-agent_observations}"
DATA_GLOB="${DATA_GLOB:-${ROOT_DIR}/agentlogsbench/common/generated/small/agent_observations_s.ndjson}"
CREATE_SQL="${CREATE_SQL:-${SCRIPT_DIR}/create.sql}"

tmp_dir="${SCRIPT_DIR}/.tmp_import"
rm -rf "${tmp_dir}"
mkdir -p "${tmp_dir}"
trap 'rm -rf "${tmp_dir}"' EXIT

python3 - "${CREATE_SQL}" "${DORIS_DB}" "${DORIS_TABLE}" > "${tmp_dir}/create.sql" <<'PY'
from pathlib import Path
import sys

create_sql, db_name, table_name = sys.argv[1:4]
text = Path(create_sql).read_text(encoding="utf-8")
text = text.replace("__DORIS_DB__", db_name).replace("__DORIS_TABLE__", table_name)
print(text)
PY

mysql_env=()
if [ -n "${DORIS_PASSWORD}" ]; then
    mysql_env=("MYSQL_PWD=${DORIS_PASSWORD}")
fi

started_at="$(date +%s)"
benchmark_log "doris" "Preparing schema ${DORIS_DB}.${DORIS_TABLE}"
env "${mysql_env[@]}" mysql -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" < "${tmp_dir}/create.sql"

shopt -s nullglob
files=( ${DATA_GLOB} )
shopt -u nullglob
if [ "${#files[@]}" -eq 0 ]; then
    echo "No files matched DATA_GLOB=${DATA_GLOB}" >&2
    exit 1
fi

benchmark_log "doris" "Importing ${#files[@]} files into ${DORIS_DB}.${DORIS_TABLE}"
file_index=0
for file in "${files[@]}"; do
    file_index=$((file_index + 1))
    benchmark_log "doris" "Import file ${file_index}/${#files[@]}: $(basename "${file}")"
    if [ "${file##*.}" = "gz" ]; then
        response="$(
            gzip -dc "${file}" | curl -sS --fail --location-trusted \
                -u "${DORIS_USER}:${DORIS_PASSWORD}" \
                -H "Expect:100-continue" \
                -H "format: json" \
                -H "read_json_by_line: true" \
                -H "load_to_single_tablet: true" \
                -H "columns: event_time,biz_date,trace_id,session_id,observation_id,parent_observation_id,seq_no,type,status,tenant,app,environment,task_category,trace_archetype,model,tool_name,input,output,input_tokens,output_tokens,total_cost,latency_ms,payload" \
                -T - \
                "http://${DORIS_FE_HOST}:${DORIS_HTTP_PORT}/api/${DORIS_DB}/${DORIS_TABLE}/_stream_load"
        )"
    else
        response="$(
            curl -sS --fail --location-trusted \
                -u "${DORIS_USER}:${DORIS_PASSWORD}" \
                -H "Expect:100-continue" \
                -H "format: json" \
                -H "read_json_by_line: true" \
                -H "load_to_single_tablet: true" \
                -H "columns: event_time,biz_date,trace_id,session_id,observation_id,parent_observation_id,seq_no,type,status,tenant,app,environment,task_category,trace_archetype,model,tool_name,input,output,input_tokens,output_tokens,total_cost,latency_ms,payload" \
                -T "${file}" \
                "http://${DORIS_FE_HOST}:${DORIS_HTTP_PORT}/api/${DORIS_DB}/${DORIS_TABLE}/_stream_load"
        )"
    fi
    if ! printf '%s' "${response}" | python3 -c 'import json,sys; o=json.loads(sys.stdin.read()); sys.exit(0 if o.get("Status") in {"Success","Publish Timeout"} else 1)'; then
        echo "${response}" >&2
        exit 1
    fi
    benchmark_log "doris" "Import file ${file_index}/${#files[@]} complete"
done

ingest_ms="$(( ($(date +%s) - started_at) * 1000 ))"
mkdir -p "$(dirname "${METRICS_FILE}")"
python3 - "${METRICS_FILE}" "${ingest_ms}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
ingest_ms = int(sys.argv[2])
payload = {"ingest_ms": ingest_ms, "index_build_ms": 0}
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY

benchmark_log "doris" "Import complete files=${#files[@]}"
