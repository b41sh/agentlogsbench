#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <DB_NAME> [QUERIES_FILE]" >&2
    exit 1
fi

DB_NAME="$1"
QUERIES_FILE="${2:-${SCRIPT_DIR}/queries.sql}"
TRIES="${TRIES:-3}"
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-55432}"
PG_USER="${PG_USER:-postgres}"
QUERY_RESULTS_FILE="${QUERY_RESULTS_FILE:-}"
QUERY_CONTEXT_FILE="${QUERY_CONTEXT_FILE:-}"

PG_BIN_DIR_RESOLVED="${PG_BIN_DIR:-$(resolve_pg_bin_dir)}"
PSQL_BIN="${PG_BIN_DIR_RESOLVED}/psql"

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
    identity_row="$("${PSQL_BIN}" -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${DB_NAME}" -At -F $'\t' -c "SELECT tenant, app, trace_id, payload #>> '{attr,release_ring}', payload #>> '{attr,customer_tier}', payload #>> '{attr,traffic_cluster}', payload #>> '{attr,request_key}', payload #>> '{attr,workflow_variant}' FROM agent_observations WHERE COALESCE(payload #>> '{attr,release_ring}', '') <> '' AND COALESCE(payload #>> '{attr,customer_tier}', '') <> '' AND COALESCE(payload #>> '{attr,traffic_cluster}', '') <> '' AND COALESCE(payload #>> '{attr,request_key}', '') <> '' AND COALESCE(payload #>> '{attr,workflow_variant}', '') <> '' ORDER BY biz_date ASC, trace_id ASC, seq_no ASC, observation_id ASC LIMIT 1")"
    date_row="$("${PSQL_BIN}" -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${DB_NAME}" -At -F $'\t' -c "SELECT to_char(MIN(biz_date), 'YYYY-MM-DD'), to_char(MAX(biz_date), 'YYYY-MM-DD') FROM agent_observations")"
    IFS=$'\t' read -r TENANT_PARAM APP_PARAM TRACE_ID_PARAM RELEASE_RING_PARAM CUSTOMER_TIER_PARAM TRAFFIC_CLUSTER_PARAM REQUEST_KEY_PARAM WORKFLOW_VARIANT_PARAM <<< "${identity_row}"
    IFS=$'\t' read -r START_DATE_PARAM END_DATE_PARAM <<< "${date_row}"
fi

if [ -z "${TENANT_PARAM}" ] || [ -z "${APP_PARAM}" ] || [ -z "${TRACE_ID_PARAM}" ] || [ -z "${RELEASE_RING_PARAM}" ] || [ -z "${CUSTOMER_TIER_PARAM}" ] || [ -z "${TRAFFIC_CLUSTER_PARAM}" ] || [ -z "${REQUEST_KEY_PARAM}" ] || [ -z "${WORKFLOW_VARIANT_PARAM}" ] || [ -z "${START_DATE_PARAM}" ] || [ -z "${END_DATE_PARAM}" ]; then
    echo "Could not resolve PostgreSQL query context from ${DB_NAME}.agent_observations" >&2
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
    capture_sql = build_sql_capture_query(query_id, sql)
    prefix = "\n".join(
        [
            "BEGIN;",
            f"SET LOCAL agentlogsbench.tenant = {sql_quote(tenant)};",
            f"SET LOCAL agentlogsbench.app = {sql_quote(app)};",
            f"SET LOCAL agentlogsbench.trace_id = {sql_quote(trace_id)};",
            f"SET LOCAL agentlogsbench.release_ring = {sql_quote(release_ring)};",
            f"SET LOCAL agentlogsbench.customer_tier = {sql_quote(customer_tier)};",
            f"SET LOCAL agentlogsbench.traffic_cluster = {sql_quote(traffic_cluster)};",
            f"SET LOCAL agentlogsbench.request_key = {sql_quote(request_key)};",
            f"SET LOCAL agentlogsbench.workflow_variant = {sql_quote(workflow_variant)};",
            f"SET LOCAL agentlogsbench.start_date = {sql_quote(start_date)};",
            f"SET LOCAL agentlogsbench.end_date = {sql_quote(end_date)};",
        ]
    )
    query_text = f"{prefix}\n{sql};\nROLLBACK;"
    capture_query_text = f"{prefix}\n{capture_sql};\nROLLBACK;"
    print(
        base64.b64encode(
            json.dumps(
                {
                    "query_no": query_no,
                    "total_queries": total_queries,
                    "query_id": query_id,
                    "query": query_text,
                    "capture_query": capture_query_text,
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

    if [ "${query_no}" = "1" ]; then
        benchmark_log "postgres" "Resolved ${total_queries} SQL queries from ${QUERIES_FILE} with ${TRIES} tries each"
    fi

    benchmark_log "postgres" "Query ${query_no}/${total_queries} (${query_id}): clearing file system cache"
    clear_os_cache
    benchmark_log "postgres" "Query ${query_no}/${total_queries} (${query_id}): executing timed runs"

    for try_index in $(seq 1 "${TRIES}"); do
        benchmark_log "postgres" "Query ${query_no}/${total_queries} (${query_id}): try ${try_index}/${TRIES}"
        start_ns="$(date +%s%N)"
        "${PSQL_BIN}" -q -X -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${DB_NAME}" -At -v ON_ERROR_STOP=1 -c "${query}" >/dev/null
        end_ns="$(date +%s%N)"
        elapsed="$(awk "BEGIN { printf \"%.3f\", (${end_ns} - ${start_ns}) / 1000000000 }")"
        echo "Response time: ${elapsed} s"
    done

    if [ -n "${QUERY_RESULTS_FILE}" ]; then
        benchmark_log "postgres" "Query ${query_no}/${total_queries} (${query_id}): writing result snapshot"
        "${PSQL_BIN}" -q -X -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${DB_NAME}" -A -F $'\t' -P footer=off -P null='null' -v ON_ERROR_STOP=1 -c "${capture_query}" \
            | python3 "${ROOT_DIR}/agentlogsbench/common/write_query_result_section.py" --engine sql --query-id "${query_id}" --with-header \
            >> "${QUERY_RESULTS_FILE}"
    fi
done

benchmark_log "postgres" "All query runs completed"
