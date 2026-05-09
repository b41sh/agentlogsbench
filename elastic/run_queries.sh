#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <INDEX_NAME> [QUERIES_FILE]" >&2
    exit 1
fi

INDEX_NAME="$1"
QUERIES_FILE="${2:-${SCRIPT_DIR}/queries.json}"
TRIES="${TRIES:-3}"
ES_ENDPOINT="${ES_ENDPOINT:-http://127.0.0.1:9200}"
QUERY_RESULTS_FILE="${QUERY_RESULTS_FILE:-}"
QUERY_CONTEXT_FILE="${QUERY_CONTEXT_FILE:-}"

if [ -n "${QUERY_CONTEXT_FILE}" ] && [ -f "${QUERY_CONTEXT_FILE}" ]; then
context_b64="$(python3 - "${QUERY_CONTEXT_FILE}" <<'PY'
import base64
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
context = {
    "tenant": payload.get("tenant", ""),
    "app": payload.get("app", ""),
    "trace_id": payload.get("trace_id", ""),
    "release_ring": payload.get("release_ring", ""),
    "customer_tier": payload.get("customer_tier", ""),
    "traffic_cluster": payload.get("traffic_cluster", ""),
    "request_key": payload.get("request_key", ""),
    "workflow_variant": payload.get("workflow_variant", ""),
    "start_date": payload.get("start_date", ""),
    "end_date": payload.get("end_date", ""),
}
if not all(context.values()):
    raise SystemExit(f"Could not resolve Elasticsearch query context from {sys.argv[1]}: {context}")
print(base64.b64encode(json.dumps(context, ensure_ascii=False).encode("utf-8")).decode("ascii"))
PY
)"
else
context_b64="$(python3 - "${ES_ENDPOINT}" "${INDEX_NAME}" <<'PY'
import base64
import json
import sys
from urllib import request

endpoint, index_name = sys.argv[1:3]


def json_post(path, payload):
    req = request.Request(
        f"{endpoint}/{index_name}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


identity_payload = json_post(
    "/_search",
    {
        "size": 1,
        "_source": ["tenant", "app", "trace_id", "payload"],
        "query": {
            "bool": {
                "filter": [
                    {"exists": {"field": "tenant"}},
                    {"exists": {"field": "app"}},
                    {"exists": {"field": "trace_id"}},
                    {"exists": {"field": "payload.attr.release_ring"}},
                    {"exists": {"field": "payload.attr.customer_tier"}},
                    {"exists": {"field": "payload.attr.traffic_cluster"}},
                    {"exists": {"field": "payload.attr.request_key"}},
                    {"exists": {"field": "payload.attr.workflow_variant"}},
                ]
            }
        },
        "sort": [
            {"biz_date": {"order": "asc"}},
            {"trace_id": {"order": "asc"}},
            {"seq_no": {"order": "asc"}},
            {"observation_id": {"order": "asc"}},
        ],
    },
)
hits = identity_payload.get("hits", {}).get("hits", [])
if not hits:
    raise SystemExit("No documents found in Elasticsearch benchmark index")
source = hits[0].get("_source", {})
attr = source.get("payload", {}).get("attr", {})

min_payload = json_post(
    "/_search",
    {"size": 1, "_source": ["biz_date"], "sort": [{"biz_date": {"order": "asc"}}]},
)
max_payload = json_post(
    "/_search",
    {"size": 1, "_source": ["biz_date"], "sort": [{"biz_date": {"order": "desc"}}]},
)

context = {
    "tenant": source.get("tenant", ""),
    "app": source.get("app", ""),
    "trace_id": source.get("trace_id", ""),
    "release_ring": attr.get("release_ring", ""),
    "customer_tier": attr.get("customer_tier", ""),
    "traffic_cluster": attr.get("traffic_cluster", ""),
    "request_key": attr.get("request_key", ""),
    "workflow_variant": attr.get("workflow_variant", ""),
    "start_date": min_payload["hits"]["hits"][0]["_source"].get("biz_date", ""),
    "end_date": max_payload["hits"]["hits"][0]["_source"].get("biz_date", ""),
}

if not all(context.values()):
    raise SystemExit(f"Could not resolve Elasticsearch query context: {context}")

print(base64.b64encode(json.dumps(context, ensure_ascii=False).encode("utf-8")).decode("ascii"))
PY
)"
fi

if [ -n "${QUERY_RESULTS_FILE}" ]; then
    mkdir -p "$(dirname "${QUERY_RESULTS_FILE}")"
    : > "${QUERY_RESULTS_FILE}"
fi

python3 - "${QUERIES_FILE}" "${context_b64}" <<'PY' | while IFS= read -r item_b64; do
import base64
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
context = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8"))


def replace_placeholders(value):
    if isinstance(value, dict):
        return {key: replace_placeholders(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [replace_placeholders(inner) for inner in value]
    if isinstance(value, str):
        return (
            value.replace("__TENANT__", context["tenant"])
            .replace("__APP__", context["app"])
            .replace("__TRACE_ID__", context["trace_id"])
            .replace("__RELEASE_RING__", context["release_ring"])
            .replace("__CUSTOMER_TIER__", context["customer_tier"])
            .replace("__TRAFFIC_CLUSTER__", context["traffic_cluster"])
            .replace("__REQUEST_KEY__", context["request_key"])
            .replace("__WORKFLOW_VARIANT__", context["workflow_variant"])
            .replace("__START_DATE__", context["start_date"])
            .replace("__END_DATE__", context["end_date"])
        )
    return value

queries = payload["queries"]
total_queries = len(queries)

for query_no, item in enumerate(queries, start=1):
    print(
        base64.b64encode(
            json.dumps(
                {
                    "query_no": query_no,
                    "total_queries": total_queries,
                    "item": replace_placeholders(item),
                },
                ensure_ascii=False,
            ).encode("utf-8")
        ).decode("ascii")
    )
PY
    [ -z "${item_b64}" ] && continue

    query_no="$(python3 -c 'import base64,json,sys; print(json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))["query_no"])' "${item_b64}")"
    total_queries="$(python3 -c 'import base64,json,sys; print(json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))["total_queries"])' "${item_b64}")"
    query_id="$(python3 -c 'import base64,json,sys; print(json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))["item"]["id"])' "${item_b64}")"

    if [ "${query_no}" = "1" ]; then
        benchmark_log "elastic" "Resolved ${total_queries} queries from ${QUERIES_FILE} with ${TRIES} tries each"
    fi

    benchmark_log "elastic" "Query ${query_no}/${total_queries} (${query_id}): executing timed runs"

    for try_index in $(seq 1 "${TRIES}"); do
        benchmark_log "elastic" "Query ${query_no}/${total_queries} (${query_id}): try ${try_index}/${TRIES} clearing file system cache"
        clear_os_cache
        benchmark_log "elastic" "Query ${query_no}/${total_queries} (${query_id}): try ${try_index}/${TRIES} clearing Elasticsearch caches"
        curl -fsS -X POST "${ES_ENDPOINT}/${INDEX_NAME}/_cache/clear?fielddata=true&query=true&request=true" >/dev/null || true
        benchmark_log "elastic" "Query ${query_no}/${total_queries} (${query_id}): try ${try_index}/${TRIES}"
        python3 "${SCRIPT_DIR}/execute_query.py" \
            --endpoint "${ES_ENDPOINT}" \
            --index "${INDEX_NAME}" \
            --item-b64 "${item_b64}" \
            --mode timed
    done

    if [ -n "${QUERY_RESULTS_FILE}" ]; then
        benchmark_log "elastic" "Query ${query_no}/${total_queries} (${query_id}): writing result snapshot"
        python3 "${SCRIPT_DIR}/execute_query.py" \
            --endpoint "${ES_ENDPOINT}" \
            --index "${INDEX_NAME}" \
            --item-b64 "${item_b64}" \
            --mode render >> "${QUERY_RESULTS_FILE}"
    fi
done

benchmark_log "elastic" "All query runs completed"
