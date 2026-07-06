#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTLOGSBENCH_ROOT = REPO_ROOT / "agentlogsbench"
DEFAULT_DRIVER_PATH = AGENTLOGSBENCH_ROOT / "bendsql" / "bindings" / "python" / "package"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.query_loader import load_query_sections
from agentlogsbench.tooling.query_results import render_sql_result_section


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [databend] {message}", file=sys.stderr, flush=True)


def add_driver_path(driver_path: Path, explicit: bool) -> None:
    has_extension = any((driver_path / "databend_driver").glob("_databend_driver*.so"))
    if (explicit or has_extension) and str(driver_path) not in sys.path:
        sys.path.insert(0, str(driver_path))


def resolve_context(conn: object, table: str, context_path: Path | None) -> dict[str, str]:
    if context_path and context_path.exists():
        payload = json.loads(context_path.read_text(encoding="utf-8"))
        return {key: str(payload[key]) for key in CONTEXT_KEYS}

    row = conn.query_row(  # type: ignore[attr-defined]
        f"""
        SELECT
            tenant,
            app,
            trace_id,
            payload #>> '{{attr,release_ring}}',
            payload #>> '{{attr,customer_tier}}',
            payload #>> '{{attr,traffic_cluster}}',
            payload #>> '{{attr,request_key}}',
            payload #>> '{{attr,workflow_variant}}',
            CAST(MIN(biz_date) OVER () AS STRING),
            CAST(MAX(biz_date) OVER () AS STRING)
        FROM {table}
        ORDER BY biz_date ASC, trace_id ASC, seq_no ASC, observation_id ASC
        LIMIT 1
        """
    )
    if row is None:
        raise SystemExit(f"Could not resolve Databend query context from {table}")
    return dict(zip(CONTEXT_KEYS, (str(value) for value in row.values())))


def bind_sql(sql: str, params: dict[str, str], table: str) -> tuple[str, dict[str, str]]:
    rendered = sql.strip().rstrip(";").replace("agent_observations", table)
    return rendered, {
        "tenant_param": params["tenant"],
        "app_param": params["app"],
        "trace_id_param": params["trace_id"],
        "release_ring_param": params["release_ring"],
        "customer_tier_param": params["customer_tier"],
        "traffic_cluster_param": params["traffic_cluster"],
        "request_key_param": params["request_key"],
        "workflow_variant_param": params["workflow_variant"],
        "start_date_param": params["start_date"],
        "end_date_param": params["end_date"],
    }


def iterator_columns(iterator: Any) -> list[str]:
    return [field.name for field in iterator.schema().fields()]


def fetch_rows(conn: object, sql: str, params: dict[str, str]) -> tuple[list[str], list[dict[str, Any]]]:
    iterator = conn.query_iter(sql, params)  # type: ignore[attr-defined]
    try:
        columns = iterator_columns(iterator)
        rows = [row.__dict__() for row in iterator]
        return columns, rows
    finally:
        iterator.close()


def execute_query(conn: object, sql: str, params: dict[str, str]) -> float:
    started = time.perf_counter()
    iterator = conn.query_iter(sql, params)  # type: ignore[attr-defined]
    try:
        for _ in iterator:
            pass
    finally:
        iterator.close()
    return time.perf_counter() - started


def configure_session(conn: object) -> None:
    conn.exec("SET enable_experimental_virtual_column=1")  # type: ignore[attr-defined]


def tsv_text(columns: list[str], rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        rendered = []
        for column in columns:
            value = row.get(column)
            if value is None:
                rendered.append("null")
            elif isinstance(value, bool):
                rendered.append("true" if value else "false")
            else:
                rendered.append(str(value))
        writer.writerow(rendered)
    return buffer.getvalue()


CONTEXT_KEYS = (
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Databend benchmark queries.")
    parser.add_argument("database")
    parser.add_argument("queries_file", type=Path)
    parser.add_argument("--dsn", default=os.environ.get("DATABEND_DSN", "databend://root:@127.0.0.1:8000/?sslmode=disable"))
    explicit_driver_path = "DATABEND_DRIVER_PYTHONPATH" in os.environ
    parser.add_argument("--driver-path", type=Path, default=Path(os.environ.get("DATABEND_DRIVER_PYTHONPATH", DEFAULT_DRIVER_PATH)))
    parser.add_argument("--table", default=os.environ.get("DATABEND_TABLE", "agent_observations"))
    parser.add_argument("--tries", type=int, default=int(os.environ.get("TRIES", "3")))
    parser.add_argument("--warmup-runs", type=int, default=int(os.environ.get("WARMUP_RUNS", "1")))
    parser.add_argument("--query-results-file", type=Path, default=Path(os.environ["QUERY_RESULTS_FILE"]) if os.environ.get("QUERY_RESULTS_FILE") else None)
    parser.add_argument("--query-context-file", type=Path, default=Path(os.environ["QUERY_CONTEXT_FILE"]) if os.environ.get("QUERY_CONTEXT_FILE") else None)
    args = parser.parse_args()

    add_driver_path(args.driver_path, explicit_driver_path)
    try:
        import databend_driver
    except ImportError as exc:
        raise SystemExit(f"Could not import databend_driver from {args.driver_path}: {exc}") from exc

    client = databend_driver.BlockingDatabendClient(args.dsn)
    conn = client.get_conn()
    sections: list[str] = []
    try:
        conn.exec(f"USE {args.database}")
        configure_session(conn)
        params = resolve_context(conn, args.table, args.query_context_file)
        queries = list(load_query_sections(args.queries_file).items())
        log(f"Resolved {len(queries)} SQL queries from {args.queries_file} with warmup_runs={args.warmup_runs} measured_runs={args.tries}")

        for query_no, (query_id, raw_sql) in enumerate(queries, start=1):
            sql, sql_params = bind_sql(raw_sql, params, args.table)
            if args.warmup_runs > 0:
                log(f"Query {query_no}/{len(queries)} ({query_id}): executing warmup runs")
                for warmup_index in range(1, args.warmup_runs + 1):
                    log(f"Query {query_no}/{len(queries)} ({query_id}): warmup {warmup_index}/{args.warmup_runs}")
                    execute_query(conn, sql, sql_params)

            log(f"Query {query_no}/{len(queries)} ({query_id}): executing measured runs")
            for try_index in range(1, args.tries + 1):
                log(f"Query {query_no}/{len(queries)} ({query_id}): try {try_index}/{args.tries}")
                elapsed = execute_query(conn, sql, sql_params)
                print(f"Response time: {elapsed:.3f} s")

            if args.query_results_file is not None:
                columns, dict_rows = fetch_rows(conn, sql, sql_params)
                sections.append(render_sql_result_section(query_id, tsv_text(columns, dict_rows), with_header=True))

        if args.query_results_file is not None:
            args.query_results_file.parent.mkdir(parents=True, exist_ok=True)
            args.query_results_file.write_text("".join(sections), encoding="utf-8")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
