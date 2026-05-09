#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <DB_PATH> [QUERIES_FILE]" >&2
    exit 1
fi

DB_PATH="$1"
QUERIES_FILE="${2:-${SCRIPT_DIR}/queries.sql}"
TRIES="${TRIES:-3}"
QUERY_RESULTS_FILE="${QUERY_RESULTS_FILE:-}"
QUERY_CONTEXT_FILE="${QUERY_CONTEXT_FILE:-}"
DUCKDB_TABLE="${DUCKDB_TABLE:-agent_observations}"

python3 - "${ROOT_DIR}" "${DB_PATH}" "${QUERIES_FILE}" "${DUCKDB_TABLE}" "${QUERY_RESULTS_FILE}" "${TRIES}" "${QUERY_CONTEXT_FILE}" <<'PY'
from __future__ import annotations

import csv
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

import duckdb

root = Path(sys.argv[1])
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from agentlogsbench.tooling.query_loader import load_query_sections
from agentlogsbench.tooling.query_results import render_sql_result_section


def resolve_context(conn: duckdb.DuckDBPyConnection, table_name: str, context_path: Path | None) -> dict[str, str]:
    if context_path and context_path.exists():
        payload = json.loads(context_path.read_text(encoding="utf-8"))
        return {
            key: str(payload[key])
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
        }

    row = conn.execute(
        f"""
        SELECT
            tenant,
            app,
            trace_id,
            payload.attr.release_ring,
            payload.attr.customer_tier,
            payload.attr.traffic_cluster,
            payload.attr.request_key,
            payload.attr.workflow_variant
        FROM {table_name}
        WHERE payload.attr.release_ring IS NOT NULL
          AND payload.attr.customer_tier IS NOT NULL
          AND payload.attr.traffic_cluster IS NOT NULL
          AND payload.attr.request_key IS NOT NULL
          AND payload.attr.workflow_variant IS NOT NULL
        ORDER BY biz_date ASC, trace_id ASC, seq_no ASC, observation_id ASC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise SystemExit(f"Could not resolve deterministic DuckDB query context from {table_name}")
    tenant, app, trace_id, release_ring, customer_tier, traffic_cluster, request_key, workflow_variant = row
    start_date, end_date = conn.execute(
        f"SELECT CAST(MIN(biz_date) AS VARCHAR), CAST(MAX(biz_date) AS VARCHAR) FROM {table_name}"
    ).fetchone()
    return {
        "tenant": str(tenant),
        "app": str(app),
        "trace_id": str(trace_id),
        "release_ring": str(release_ring),
        "customer_tier": str(customer_tier),
        "traffic_cluster": str(traffic_cluster),
        "request_key": str(request_key),
        "workflow_variant": str(workflow_variant),
        "start_date": str(start_date),
        "end_date": str(end_date),
    }


def substitute(sql: str, params: dict[str, str], table_name: str) -> str:
    rendered = sql.replace("agent_observations", table_name)
    markers = {
        "__TENANT__": params["tenant"],
        "__APP__": params["app"],
        "__TRACE_ID__": params["trace_id"],
        "__RELEASE_RING__": params["release_ring"],
        "__CUSTOMER_TIER__": params["customer_tier"],
        "__TRAFFIC_CLUSTER__": params["traffic_cluster"],
        "__REQUEST_KEY__": params["request_key"],
        "__WORKFLOW_VARIANT__": params["workflow_variant"],
        "__START_DATE__": params["start_date"],
        "__END_DATE__": params["end_date"],
    }
    for marker, value in markers.items():
        rendered = rendered.replace(marker, value.replace("'", "''"))
    return rendered


def tsv_text(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        rendered = []
        for value in row:
            if value is None:
                rendered.append("null")
            elif isinstance(value, bool):
                rendered.append("true" if value else "false")
            else:
                rendered.append(str(value))
        writer.writerow(rendered)
    return buffer.getvalue()


db_path = Path(sys.argv[2])
queries_file = Path(sys.argv[3])
table_name = sys.argv[4]
query_results_file = Path(sys.argv[5]) if sys.argv[5] else None
tries = int(sys.argv[6])
context_path = Path(sys.argv[7]) if sys.argv[7] else None

con = duckdb.connect(str(db_path), read_only=True)
con.execute("PRAGMA threads=4")
params = resolve_context(con, table_name, context_path)
queries = list(load_query_sections(queries_file).items())
sections: list[str] = []

for query_no, (query_id, raw_sql) in enumerate(queries, start=1):
    sql = substitute(raw_sql.strip().rstrip(";"), params, table_name)
    print(
        f"[{time.strftime('%F %T')}] [duckdb] Query {query_no}/{len(queries)} ({query_id}): executing timed runs",
        file=sys.stderr,
        flush=True,
    )
    for try_index in range(1, tries + 1):
        print(
            f"[{time.strftime('%F %T')}] [duckdb] Query {query_no}/{len(queries)} ({query_id}): try {try_index}/{tries}",
            file=sys.stderr,
            flush=True,
        )
        started = time.perf_counter()
        con.execute(sql).fetchall()
        elapsed = time.perf_counter() - started
        print(f"Response time: {elapsed:.3f} s")

    if query_results_file is not None:
        rows = con.execute(sql).fetchall()
        columns = [desc[0] for desc in con.description or []]
        sections.append(render_sql_result_section(query_id, tsv_text(columns, rows), with_header=True))

if query_results_file is not None:
    query_results_file.parent.mkdir(parents=True, exist_ok=True)
    query_results_file.write_text("".join(sections), encoding="utf-8")

con.close()
PY
