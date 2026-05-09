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
CH_PATH="${CH_PATH:-${SCRIPT_DIR}/runtime/ch_data}"
QUERY_RESULTS_FILE="${QUERY_RESULTS_FILE:-}"
QUERY_CONTEXT_FILE="${QUERY_CONTEXT_FILE:-}"

if [ -n "${CH_BIN:-}" ] && [ -x "${CH_BIN}" ]; then
    CH_BIN_RESOLVED="${CH_BIN}"
else
    CH_BIN_RESOLVED="$(resolve_clickhouse_bin)"
fi

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
else
    context_row="$("${CH_BIN_RESOLVED}" local --path "${CH_PATH}" --database "${DB_NAME}" -q "SELECT any(tenant), any(app), any(trace_id), any(payload.attr.release_ring::String), any(payload.attr.customer_tier::String), any(payload.attr.traffic_cluster::String), any(payload.attr.request_key::String), any(payload.attr.workflow_variant::String), toString(min(biz_date)), toString(max(biz_date)) FROM agent_observations FORMAT TabSeparatedRaw")"
fi
IFS=$'\t' read -r TENANT_PARAM APP_PARAM TRACE_ID_PARAM RELEASE_RING_PARAM CUSTOMER_TIER_PARAM TRAFFIC_CLUSTER_PARAM REQUEST_KEY_PARAM WORKFLOW_VARIANT_PARAM START_DATE_PARAM END_DATE_PARAM <<< "${context_row}"

if [ -z "${TENANT_PARAM}" ] || [ -z "${APP_PARAM}" ] || [ -z "${TRACE_ID_PARAM}" ] || [ -z "${RELEASE_RING_PARAM}" ] || [ -z "${CUSTOMER_TIER_PARAM}" ] || [ -z "${TRAFFIC_CLUSTER_PARAM}" ] || [ -z "${REQUEST_KEY_PARAM}" ] || [ -z "${WORKFLOW_VARIANT_PARAM}" ] || [ -z "${START_DATE_PARAM}" ] || [ -z "${END_DATE_PARAM}" ]; then
    echo "Could not resolve ClickHouse query context from ${DB_NAME}.agent_observations" >&2
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
    bound = (
        "WITH "
        f"{sql_quote(tenant)} AS tenant_param, "
        f"{sql_quote(app)} AS app_param, "
        f"{sql_quote(trace_id)} AS trace_id_param, "
        f"{sql_quote(release_ring)} AS release_ring_param, "
        f"{sql_quote(customer_tier)} AS customer_tier_param, "
        f"{sql_quote(traffic_cluster)} AS traffic_cluster_param, "
        f"{sql_quote(request_key)} AS request_key_param, "
        f"{sql_quote(workflow_variant)} AS workflow_variant_param, "
        f"toDate({sql_quote(start_date)}) AS start_date_param, "
        f"toDate({sql_quote(end_date)}) AS end_date_param\n"
        f"{sql}"
    )
    print(
        base64.b64encode(
            json.dumps(
                {
                    "query_no": query_no,
                    "total_queries": total_queries,
                    "query_id": query_id,
                    "query": bound,
                    "capture_query": build_sql_capture_query(query_id, bound),
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
        benchmark_log "clickhouse" "Resolved ${total_queries} SQL queries from ${QUERIES_FILE} with ${TRIES} tries each"
    fi

    benchmark_log "clickhouse" "Query ${query_no}/${total_queries} (${query_id}): clearing file system cache"
    clear_os_cache
    benchmark_log "clickhouse" "Query ${query_no}/${total_queries} (${query_id}): executing timed runs"

    for try_index in $(seq 1 "${TRIES}"); do
        benchmark_log "clickhouse" "Query ${query_no}/${total_queries} (${query_id}): try ${try_index}/${TRIES}"
        start_ns="$(date +%s%N)"
        "${CH_BIN_RESOLVED}" local --path "${CH_PATH}" --database "${DB_NAME}" -q "${query}" >/dev/null
        end_ns="$(date +%s%N)"
        elapsed="$(awk "BEGIN { printf \"%.3f\", (${end_ns} - ${start_ns}) / 1000000000 }")"
        echo "Response time: ${elapsed} s"
    done

    if [ -n "${QUERY_RESULTS_FILE}" ]; then
        benchmark_log "clickhouse" "Query ${query_no}/${total_queries} (${query_id}): writing result snapshot"
        "${CH_BIN_RESOLVED}" local --path "${CH_PATH}" --database "${DB_NAME}" --format TSVWithNames -q "${capture_query}" \
            | python3 "${ROOT_DIR}/agentlogsbench/common/write_query_result_section.py" --engine sql --query-id "${query_id}" --with-header \
            >> "${QUERY_RESULTS_FILE}"
    fi
done

benchmark_log "clickhouse" "All query runs completed"
