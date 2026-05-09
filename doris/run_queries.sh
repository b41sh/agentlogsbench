#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <DB_NAME> <QUERIES_FILE>" >&2
    exit 1
fi

DB_NAME="$1"
QUERIES_FILE="${2:-${SCRIPT_DIR}/queries.sql}"
TRIES="${TRIES:-3}"
DORIS_FE_HOST="${DORIS_FE_HOST:-127.0.0.1}"
DORIS_QUERY_PORT="${DORIS_QUERY_PORT:-19030}"
DORIS_USER="${DORIS_USER:-root}"
DORIS_PASSWORD="${DORIS_PASSWORD:-}"
QUERY_RESULTS_FILE="${QUERY_RESULTS_FILE:-}"
QUERY_CONTEXT_FILE="${QUERY_CONTEXT_FILE:-}"

mysql_env=()
if [ -n "${DORIS_PASSWORD}" ]; then
    mysql_env=("MYSQL_PWD=${DORIS_PASSWORD}")
fi

env "${mysql_env[@]}" mysql -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" "${DB_NAME}" -e "SET GLOBAL parallel_pipeline_task_num=32; SET GLOBAL enable_sql_cache=false;" >/dev/null

if [ -n "${QUERY_CONTEXT_FILE}" ] && [ -f "${QUERY_CONTEXT_FILE}" ]; then
    context_row="$(python3 - "${QUERY_CONTEXT_FILE}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(
    "\t".join(
        str(payload.get(key, ""))
        for key in (
            "tenant",
            "app",
            "trace_id",
            "release_ring",
            "customer_tier",
            "traffic_cluster",
            "request_key",
            "workflow_variant",
            "start_date",
            "end_date",
        )
    )
)
PY
)"
    IFS=$'\t' read -r TENANT_PARAM APP_PARAM TRACE_ID_PARAM RELEASE_RING_PARAM CUSTOMER_TIER_PARAM TRAFFIC_CLUSTER_PARAM REQUEST_KEY_PARAM WORKFLOW_VARIANT_PARAM START_DATE_PARAM END_DATE_PARAM <<< "${context_row}"
else
    identity_row="$(env "${mysql_env[@]}" mysql -N -B -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" "${DB_NAME}" -e "SELECT tenant, app, trace_id, CAST(payload['attr']['release_ring'] AS STRING), CAST(payload['attr']['customer_tier'] AS STRING), CAST(payload['attr']['traffic_cluster'] AS STRING), CAST(payload['attr']['request_key'] AS STRING), CAST(payload['attr']['workflow_variant'] AS STRING) FROM agent_observations LIMIT 1")"
    date_row="$(env "${mysql_env[@]}" mysql -N -B -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" "${DB_NAME}" -e "SELECT CAST(MIN(biz_date) AS STRING), CAST(MAX(biz_date) AS STRING) FROM agent_observations")"
    IFS=$'\t' read -r TENANT_PARAM APP_PARAM TRACE_ID_PARAM RELEASE_RING_PARAM CUSTOMER_TIER_PARAM TRAFFIC_CLUSTER_PARAM REQUEST_KEY_PARAM WORKFLOW_VARIANT_PARAM <<< "${identity_row}"
    IFS=$'\t' read -r START_DATE_PARAM END_DATE_PARAM <<< "${date_row}"
fi

if [ -z "${TENANT_PARAM}" ] || [ -z "${APP_PARAM}" ] || [ -z "${TRACE_ID_PARAM}" ] || [ -z "${RELEASE_RING_PARAM}" ] || [ -z "${CUSTOMER_TIER_PARAM}" ] || [ -z "${TRAFFIC_CLUSTER_PARAM}" ] || [ -z "${REQUEST_KEY_PARAM}" ] || [ -z "${WORKFLOW_VARIANT_PARAM}" ] || [ -z "${START_DATE_PARAM}" ] || [ -z "${END_DATE_PARAM}" ]; then
    echo "Could not resolve Doris query context from ${DB_NAME}.agent_observations" >&2
    exit 1
fi

if [ -n "${QUERY_RESULTS_FILE}" ]; then
    mkdir -p "$(dirname "${QUERY_RESULTS_FILE}")"
    : > "${QUERY_RESULTS_FILE}"
fi

python3 - "${ROOT_DIR}" "${QUERIES_FILE}" "${TENANT_PARAM}" "${APP_PARAM}" "${TRACE_ID_PARAM}" "${RELEASE_RING_PARAM}" "${CUSTOMER_TIER_PARAM}" "${TRAFFIC_CLUSTER_PARAM}" "${REQUEST_KEY_PARAM}" "${WORKFLOW_VARIANT_PARAM}" "${START_DATE_PARAM}" "${END_DATE_PARAM}" <<'PY' | while IFS= read -r query_b64; do
import base64
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from agentlogsbench.tooling.query_loader import load_query_sections
from agentlogsbench.tooling.query_results import build_sql_capture_query


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


queries_path = Path(sys.argv[2])
tenant, app, trace_id, release_ring, customer_tier, traffic_cluster, request_key, workflow_variant, start_date, end_date = sys.argv[3:13]

queries = list(load_query_sections(queries_path).items())
total_queries = len(queries)

for query_no, (query_id, query_sql) in enumerate(queries, start=1):
    sql = query_sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    init_command = "\n".join(
        [
            "SET parallel_pipeline_task_num=32;",
            "SET enable_sql_cache=false;",
            f"SET @tenant_param = {sql_quote(tenant)};",
            f"SET @app_param = {sql_quote(app)};",
            f"SET @trace_id_param = {sql_quote(trace_id)};",
            f"SET @release_ring_param = {sql_quote(release_ring)};",
            f"SET @customer_tier_param = {sql_quote(customer_tier)};",
            f"SET @traffic_cluster_param = {sql_quote(traffic_cluster)};",
            f"SET @request_key_param = {sql_quote(request_key)};",
            f"SET @workflow_variant_param = {sql_quote(workflow_variant)};",
            f"SET @start_date_param = {sql_quote(start_date)};",
            f"SET @end_date_param = {sql_quote(end_date)};",
        ]
    )
    print(
        base64.b64encode(
            json.dumps(
                {
                    "query_no": query_no,
                    "total_queries": total_queries,
                    "query_id": query_id,
                    "query": sql,
                    "capture_query": build_sql_capture_query(query_id, sql),
                    "init_command": init_command,
                }
            ).encode("utf-8")
        ).decode("ascii")
    )
PY
    [ -z "${query_b64}" ] && continue

    query_item="$(python3 - "${query_b64}" <<'PY'
import base64
import sys

print(base64.b64decode(sys.argv[1]).decode("utf-8"))
PY
    )"
    query_no="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["query_no"])' <<< "${query_item}")"
    total_queries="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["total_queries"])' <<< "${query_item}")"
    query_id="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["query_id"])' <<< "${query_item}")"
    query="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["query"])' <<< "${query_item}")"
    capture_query="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["capture_query"])' <<< "${query_item}")"
    init_command="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["init_command"])' <<< "${query_item}")"

    if [ "${query_no}" = "1" ]; then
        benchmark_log "doris" "Resolved ${total_queries} SQL queries from ${QUERIES_FILE} with ${TRIES} tries each"
    fi

    benchmark_log "doris" "Query ${query_no}/${total_queries} (${query_id}): clearing file system cache"
    clear_os_cache
    benchmark_log "doris" "Query ${query_no}/${total_queries} (${query_id}): executing timed runs"

    for try_index in $(seq 1 "${TRIES}"); do
        benchmark_log "doris" "Query ${query_no}/${total_queries} (${query_id}): try ${try_index}/${TRIES}"
        start_ns="$(date +%s%N)"
        env "${mysql_env[@]}" mysql -N -B -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" "${DB_NAME}" \
            --init-command="${init_command}" \
            -e "${query}" >/dev/null
        end_ns="$(date +%s%N)"
        elapsed="$(awk "BEGIN { printf \"%.3f\", (${end_ns} - ${start_ns}) / 1000000000 }")"
        echo "Response time: ${elapsed} s"
    done

    if [ -n "${QUERY_RESULTS_FILE}" ]; then
        benchmark_log "doris" "Query ${query_no}/${total_queries} (${query_id}): writing result snapshot"
        env "${mysql_env[@]}" mysql -B --raw -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" "${DB_NAME}" \
            --init-command="${init_command}" \
            -e "${capture_query}" \
            | python3 "${ROOT_DIR}/agentlogsbench/common/write_query_result_section.py" --engine sql --query-id "${query_id}" --with-header \
            >> "${QUERY_RESULTS_FILE}"
    fi
done

benchmark_log "doris" "All query runs completed"
