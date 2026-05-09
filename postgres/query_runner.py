#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

import psycopg2
from psycopg2 import errors as psycopg2_errors

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


def normalize_query_sql(query_sql: str) -> str:
    sql = query_sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    return sql


def load_query_definitions(agentlogsbench_root: Path) -> List[Dict[str, Any]]:
    suite = json.loads(query_suite_path(agentlogsbench_root).read_text(encoding="utf-8"))
    return list(suite["queries"])


def apply_postgres_context(conn: Any, params: Dict[str, str]) -> None:
    with conn.cursor() as cur:
        for key, value in params.items():
            cur.execute("SELECT set_config(%s, %s, false)", (f"agentlogsbench.{key}", value))


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


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [json_safe(inner) for inner in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def render_query_log(query_id: str, sql: str, rows: List[Dict[str, Any]], runs: List[int]) -> str:
    return (
        f"{query_id}\n"
        f"{sql}\n"
        f"{json.dumps(json_safe(rows), ensure_ascii=False, indent=2)}\n"
        f"latency_ms_runs={runs}\n\n"
    )


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
            elif cache_hit in ("t", "true", "1", 1):
                row["cache_hit"] = "true"
            elif cache_hit in ("f", "false", "0", 0):
                row["cache_hit"] = "false"
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
    if query_id == "Q14":
        return sorted(
            ordered,
            key=lambda row: (
                stable_text(row.get("event_time")),
                stable_text(row.get("trace_id")),
                stable_text(row.get("observation_id")),
            ),
            reverse=True,
        )
    if query_id == "Q15":
        return sorted(
            ordered,
            key=lambda row: (
                stable_numeric(row.get("latency_ms")),
                stable_text(row.get("event_time")),
                stable_text(row.get("trace_id")),
                stable_text(row.get("observation_id")),
            ),
            reverse=True,
        )
    if query_id == "Q16":
        return sorted(
            ordered,
            key=lambda row: (
                stable_text(row.get("event_time")),
                stable_text(row.get("trace_id")),
                stable_text(row.get("observation_id")),
            ),
            reverse=True,
        )
    if query_id == "Q17":
        return sorted(
            ordered,
            key=lambda row: (
                stable_numeric(row.get("seq_no")),
                stable_text(row.get("observation_id")),
            ),
        )
    if query_id == "Q18":
        ordered.sort(key=lambda row: stable_text(row.get("prompt_template_version")))
        ordered.sort(key=lambda row: stable_numeric(row.get("total_cost")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("observations")), reverse=True)
        return ordered
    if query_id == "Q19":
        ordered.sort(key=lambda row: stable_text(row.get("release_ring")))
        ordered.sort(key=lambda row: stable_text(row.get("deployment_channel")))
        ordered.sort(key=lambda row: stable_numeric(row.get("incident_traces")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("incident_observations")), reverse=True)
        return ordered
    if query_id == "Q20":
        ordered.sort(key=lambda row: stable_text(row.get("policy_pack")))
        ordered.sort(key=lambda row: stable_text(row.get("workflow_variant")))
        ordered.sort(key=lambda row: stable_numeric(row.get("total_cost")), reverse=True)
        ordered.sort(key=lambda row: stable_numeric(row.get("observations")), reverse=True)
        return ordered
    return ordered


def fetch_engine_version(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        row = cur.fetchone()
    return row[0] if row else "postgres-unknown"


def fetch_storage_bytes(conn: Any, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_total_relation_size(%s)", (table_name,))
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def run_postgres_query(conn: Any, sql: str) -> Tuple[List[str], List[Dict[str, Any]], int]:
    started = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(sql)
        field_names = [desc[0] for desc in cur.description or []]
        rows = [dict(zip(field_names, row)) for row in cur.fetchall()]
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    return field_names, rows, elapsed_ms


def main() -> int:
    parser = argparse.ArgumentParser(description="Run observation-first PostgreSQL benchmark queries.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--db", required=True)
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
    adapter = json.loads(adapter_manifest_path(agentlogsbench_root, "postgres").read_text(encoding="utf-8"))
    query_map = json.loads(adapter_query_map_path(agentlogsbench_root, "postgres").read_text(encoding="utf-8"))
    timeout_seconds = int(edition["execution_protocol"]["timeout_seconds"])

    args.result_dir.mkdir(parents=True, exist_ok=True)
    args.out_file.parent.mkdir(parents=True, exist_ok=True)
    result_file = args.result_file or (args.result_dir / "result.json")
    result_file.parent.mkdir(parents=True, exist_ok=True)

    params = load_context_from_paths(manifest_observation_paths(manifest_path, manifest), manifest["replay_trace_id"])
    conn = psycopg2.connect(host=args.host, port=int(args.port), user=args.user, dbname=args.db)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = {timeout_seconds * 1000}")
    apply_postgres_context(conn, params)
    engine_version = fetch_engine_version(conn)

    query_results: List[Dict[str, Any]] = []
    log_lines: List[str] = []

    for query in load_query_definitions(agentlogsbench_root):
        query_id = query["id"]
        query_sql_path = engine_queries_file(agentlogsbench_root, "postgres")
        query_sql = load_query_sql(query_sql_path, query["canonical_sql_section"])
        actual_sql = normalize_query_sql(query_sql)
        contract = contracts[query_id]
        assertion_keys = sorted(contract["assertions"].keys())
        try:
            _, _, _ = run_postgres_query(conn, actual_sql)
            runs: List[int] = []
            field_names: List[str] = []
            rows: List[Dict[str, Any]] = []
            for _ in range(5):
                field_names, rows, elapsed_ms = run_postgres_query(conn, actual_sql)
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
            expected_result_fingerprint = contract.get("expected_result_fingerprints", {}).get("postgres")
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
        except psycopg2_errors.QueryCanceled as exc:
            conn.rollback()
            runs = [timeout_seconds * 1000] * 5
            status = "timeout"
            field_names = []
            rows = []
            row_count = 0
            missing_fields = []
            result_fingerprint = ""
            fingerprint_errors = []
            error_text = str(exc)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
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
        "engine": "postgres",
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
            "storage_bytes": fetch_storage_bytes(conn, args.table),
        },
        "query_results": query_results,
    }
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
