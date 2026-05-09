#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

CWD = str(Path.cwd().resolve())
sys.path = [entry for entry in sys.path if entry not in ("", CWD)]

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.engines import engine_queries_file
from agentlogsbench.tooling.paths import (
    adapter_manifest_path,
    adapter_query_map_path,
    bundled_small_data_dir,
    edition_path,
    query_contracts_path,
    query_suite_path,
)
from agentlogsbench.tooling.query_context import load_context_from_paths, load_manifest, manifest_observation_paths
from agentlogsbench.tooling.query_loader import load_query_sql
from agentlogsbench.tooling.query_results import (
    fingerprint_query_rows,
    fingerprint_query_rows_excluding_fields,
    normalize_query_rows,
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def env_flag(name: str) -> bool:
    return os.environ.get(name, "0").lower() in {"1", "true", "yes"}


def load_query_definitions(agentlogsbench_root: Path) -> List[Dict[str, Any]]:
    suite = json.loads(query_suite_path(agentlogsbench_root).read_text(encoding="utf-8"))
    return list(suite["queries"])


def normalize_query_sql(query_sql: str) -> str:
    sql = query_sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    return sql


def render_query_log(query_id: str, sql: str, rows: List[Dict[str, Any]], runs: List[int]) -> str:
    return (
        f"{query_id}\n"
        f"{sql}\n"
        f"{json.dumps(rows, ensure_ascii=False, indent=2)}\n"
        f"latency_ms_runs={runs}\n\n"
    )


def verify_contract(
    contract: Dict[str, Any],
    field_names: List[str],
    row_count: int,
    skip_expected_row_count: bool = False,
) -> List[str]:
    required_fields = contract["assertions"].get("must_include_fields", [])
    errors = [field for field in required_fields if field not in field_names]
    minimum_row_count = contract.get("minimum_row_count")
    if isinstance(minimum_row_count, int) and row_count < minimum_row_count:
        errors.append(f"row_count {row_count} < minimum_row_count {minimum_row_count}")
    expected_row_count = contract.get("expected_row_count")
    if (
        not skip_expected_row_count
        and isinstance(expected_row_count, int)
        and row_count != expected_row_count
    ):
        errors.append(f"row_count {row_count} != expected_row_count {expected_row_count}")
    return errors


def stable_numeric(value: Any) -> float:
    return float(value) if value is not None else 0.0


def stable_text(value: Any) -> str:
    return str(value) if value is not None else ""


def stabilize_rows(query_id: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = list(rows)
    if query_id in {"Q05", "Q08"}:
        if query_id == "Q05":
            return sorted(
                ordered,
                key=lambda row: (
                    stable_numeric(row.get("text_score")),
                    stable_numeric(row.get("latency_ms")),
                    stable_text(row.get("event_time")),
                    stable_text(row.get("trace_id")),
                    stable_text(row.get("observation_id")),
                ),
                reverse=True,
            )
        for row in ordered:
            if isinstance(row.get("phrase_match"), bool):
                row["phrase_match"] = 1 if row["phrase_match"] else 0
        return sorted(
            ordered,
            key=lambda row: (
                stable_numeric(row.get("phrase_match")),
                stable_numeric(row.get("text_score")),
                stable_text(row.get("event_time")),
                stable_text(row.get("trace_id")),
                stable_text(row.get("observation_id")),
            ),
            reverse=True,
        )
    if query_id == "Q06":
        ordered.sort(key=lambda row: stable_text(row.get("model")))
        ordered.sort(key=lambda row: stable_text(row.get("type")))
        ordered.sort(key=lambda row: stable_numeric(row.get("output_tokens")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("input_tokens")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("observations")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("avg_latency_ms")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("total_cost")), reverse=True)
        return ordered
    if query_id == "Q02":
        ordered.sort(key=lambda row: stable_text(row.get("trace_id")))
        ordered.sort(key=lambda row: stable_numeric(row.get("total_latency_ms")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("total_cost")), reverse=True)
        return ordered
    if query_id == "Q07":
        return sorted(
            ordered,
            key=lambda row: (
                stable_text(row.get("event_time")),
                stable_text(row.get("trace_id")),
                stable_text(row.get("observation_id")),
            ),
            reverse=True,
        )
    if query_id == "Q11":
        for row in ordered:
            if isinstance(row.get("phrase_match"), bool):
                row["phrase_match"] = 1 if row["phrase_match"] else 0
        return sorted(
            ordered,
            key=lambda row: (
                stable_numeric(row.get("phrase_match")),
                stable_numeric(row.get("text_score")),
                stable_numeric(row.get("latency_ms")),
                stable_text(row.get("event_time")),
                stable_text(row.get("trace_id")),
                stable_text(row.get("observation_id")),
            ),
            reverse=True,
        )
    if query_id == "Q09":
        ordered.sort(key=lambda row: stable_text(row.get("status")))
        ordered.sort(key=lambda row: stable_text(row.get("tool_name")))
        ordered.sort(key=lambda row: stable_numeric(row.get("avg_latency_ms")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("observations")), reverse=True)
        return ordered
    if query_id == "Q10":
        for row in ordered:
            cache_hit = row.get("cache_hit")
            if cache_hit in (True, False):
                row["cache_hit"] = "true" if cache_hit else "false"
        ordered.sort(key=lambda row: stable_text(row.get("cache_hit")))
        ordered.sort(key=lambda row: stable_text(row.get("stop_reason")))
        ordered.sort(key=lambda row: stable_numeric(row.get("avg_latency_ms")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("observations")), reverse=True)
        return ordered
    if query_id == "Q12":
        ordered.sort(key=lambda row: stable_text(row.get("retrieval_strategy")))
        ordered.sort(key=lambda row: stable_text(row.get("customer_tier")))
        ordered.sort(key=lambda row: stable_text(row.get("release_ring")))
        ordered.sort(key=lambda row: stable_numeric(row.get("total_cost")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("observations")), reverse=True)
        return ordered
    return ordered


def substitute_context(sql: str, params: Dict[str, str], table_name: str) -> str:
    rendered = sql.replace("agent_observations", table_name)
    markers = {
        "__TENANT__": params["tenant"],
        "__APP__": params["app"],
        "__TRACE_ID__": params["trace_id"],
        "__START_DATE__": params["start_date"],
        "__END_DATE__": params["end_date"],
    }
    for marker, value in markers.items():
        rendered = rendered.replace(marker, value.replace("'", "''"))
    return rendered


def fetch_engine_version(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("SELECT version()").fetchone()
    return row[0] if row else "duckdb-unknown"


def fetch_storage_bytes(db_path: Path) -> int:
    return db_path.stat().st_size if db_path.exists() else 0


def run_duckdb_query(conn: duckdb.DuckDBPyConnection, sql: str) -> Tuple[List[str], List[Dict[str, Any]], int]:
    started = time.perf_counter()
    rows = conn.execute(sql).fetchall()
    field_names = [desc[0] for desc in conn.description or []]
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    return field_names, [dict(zip(field_names, row)) for row in rows], elapsed_ms


def main() -> int:
    parser = argparse.ArgumentParser(description="Run observation-first DuckDB benchmark queries.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--table", default="agent_observations")
    parser.add_argument("--result-file", type=Path, default=None)
    args = parser.parse_args()

    root = args.root
    agentlogsbench_root = root / "agentlogsbench"
    manifest_path = Path(
        os.environ.get("AIBENCH_MANIFEST_PATH", str(bundled_small_data_dir(agentlogsbench_root) / "manifest.json"))
    )
    manifest = load_manifest(manifest_path)
    skip_contract_verification = env_flag("AIBENCH_SKIP_CONTRACT_VERIFICATION")
    dataset_tier = os.environ.get("AIBENCH_DATASET_TIER", "S")
    dataset_version = os.environ.get("AIBENCH_DATASET_VERSION", manifest["edition"])
    contracts = json.loads(query_contracts_path(agentlogsbench_root).read_text(encoding="utf-8"))["contracts"]
    edition_text = edition_path(agentlogsbench_root).read_text(encoding="utf-8")
    edition = json.loads(edition_text)
    adapter = json.loads(adapter_manifest_path(agentlogsbench_root, "duckdb").read_text(encoding="utf-8"))
    query_map = json.loads(adapter_query_map_path(agentlogsbench_root, "duckdb").read_text(encoding="utf-8"))

    args.result_dir.mkdir(parents=True, exist_ok=True)
    args.out_file.parent.mkdir(parents=True, exist_ok=True)
    result_file = args.result_file or (args.result_dir / "result.json")
    result_file.parent.mkdir(parents=True, exist_ok=True)

    params = load_context_from_paths(manifest_observation_paths(manifest_path, manifest), manifest["replay_trace_id"])
    conn = duckdb.connect(str(args.db_path), read_only=True)
    conn.execute("PRAGMA threads=4")
    engine_version = fetch_engine_version(conn)

    query_results: List[Dict[str, Any]] = []
    log_lines: List[str] = []

    for query in load_query_definitions(agentlogsbench_root):
        query_id = query["id"]
        query_sql_path = engine_queries_file(agentlogsbench_root, "duckdb")
        query_sql = load_query_sql(query_sql_path, query["canonical_sql_section"])
        actual_sql = substitute_context(normalize_query_sql(query_sql), params, args.table)
        contract = contracts[query_id]
        assertion_keys = sorted(contract["assertions"].keys())
        try:
            _, _, _ = run_duckdb_query(conn, actual_sql)
            runs: List[int] = []
            field_names: List[str] = []
            rows: List[Dict[str, Any]] = []
            for _ in range(5):
                field_names, rows, elapsed_ms = run_duckdb_query(conn, actual_sql)
                runs.append(elapsed_ms)

            rows = stabilize_rows(query_id, normalize_query_rows(rows))
            row_count = len(rows)
            missing_fields = verify_contract(
                contract,
                field_names,
                row_count,
                skip_expected_row_count=skip_contract_verification,
            )
            if contract.get("result_kind") == "sample_rows" and "payload" not in contract["assertions"].get("must_include_fields", []):
                result_fingerprint = fingerprint_query_rows_excluding_fields(rows, ["payload"])
            else:
                result_fingerprint = fingerprint_query_rows(rows)
            fingerprint_errors: List[str] = []
            expected_result_fingerprint = contract.get("expected_result_fingerprints", {}).get("duckdb")
            if (
                not skip_contract_verification
                and isinstance(expected_result_fingerprint, str)
                and result_fingerprint != expected_result_fingerprint
            ):
                fingerprint_errors.append(
                    f"result_fingerprint {result_fingerprint} != expected_result_fingerprint {expected_result_fingerprint}"
                )
            status = "incorrect" if missing_fields or fingerprint_errors else "ok"
            error_text = ""
        except Exception as exc:  # noqa: BLE001
            runs = [1, 1, 1, 1, 1]
            status = "unsupported"
            field_names = []
            rows = []
            row_count = 0
            missing_fields = []
            result_fingerprint = ""
            fingerprint_errors = []
            error_text = str(exc)

        log_lines.append(render_query_log(query_id, actual_sql, rows, runs))
        if error_text:
            log_lines.append(f"ERROR: {error_text}\n\n")

        verification: Dict[str, Any] = {
            "contract_id": query_id,
            "fixture_dataset": contract["fixture_dataset"],
            "assertion_keys_checked": assertion_keys,
            "verification_mode": "benchmark_only" if skip_contract_verification else "fixture_contract",
            "observed_fields": field_names,
            "row_count": row_count,
            "result_fingerprint": result_fingerprint,
            "canonical_sql_file": query["canonical_sql_file"],
            "engine_queries_file": str(query_sql_path.relative_to(root)),
            "canonical_sql_section": query["canonical_sql_section"],
            "compiled_sql_fingerprint": sha256_text(actual_sql),
        }
        if missing_fields:
            verification["missing_fields"] = missing_fields
        if fingerprint_errors:
            verification["fingerprint_errors"] = fingerprint_errors

        query_results.append(
            {
                "query_id": query_id,
                "status": status,
                "latency_ms_runs": runs,
                "contract_verification": verification,
            }
        )

    args.out_file.write_text("".join(log_lines), encoding="utf-8")
    result = {
        "engine": "duckdb",
        "edition": "2026.04-observability-v1",
        "dataset_tier": dataset_tier,
        "run_protocol": {
            "warmup_runs": 1,
            "measured_runs": 5,
            "timeout_seconds": 900,
            "cache_policy": "disable_where_supported",
        },
        "run_metadata": {
            "dataset_version": dataset_version,
            "engine_version": engine_version,
            "config_fingerprint": sha256_text(edition_text),
            "index_config_fingerprint": sha256_text(json.dumps(adapter["declared_indexes"], sort_keys=True)),
            "query_adapter_version": str(query_map["adapter_version"]),
            "execution_mode": "runnable",
            "run_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "secondary_metrics": {
            "ingest_ms": 0,
            "index_build_ms": 0,
            "storage_bytes": fetch_storage_bytes(args.db_path),
        },
        "query_results": query_results,
    }
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
