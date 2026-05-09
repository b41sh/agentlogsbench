#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
INT_PATTERN = re.compile(r"^-?[0-9]+$")
FLOAT_PATTERN = re.compile(r"^-?[0-9]+\.[0-9]+$")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def bind_doris_context(query_sql: str, params: Dict[str, str]) -> str:
    sql = query_sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    prefix = "\n".join(
        [
            f"SET @tenant_param = {sql_quote(params['tenant'])};",
            f"SET @app_param = {sql_quote(params['app'])};",
            f"SET @trace_id_param = {sql_quote(params['trace_id'])};",
            f"SET @release_ring_param = {sql_quote(params['release_ring'])};",
            f"SET @customer_tier_param = {sql_quote(params['customer_tier'])};",
            f"SET @traffic_cluster_param = {sql_quote(params['traffic_cluster'])};",
            f"SET @request_key_param = {sql_quote(params['request_key'])};",
            f"SET @workflow_variant_param = {sql_quote(params['workflow_variant'])};",
            f"SET @start_date_param = {sql_quote(params['start_date'])};",
            f"SET @end_date_param = {sql_quote(params['end_date'])};",
        ]
    )
    return f"{prefix}\n{sql}"


def load_query_definitions(agentlogsbench_root: Path) -> List[Dict[str, Any]]:
    suite = json.loads(query_suite_path(agentlogsbench_root).read_text(encoding="utf-8"))
    return list(suite["queries"])


def decode_mysql_batch_value(value: str) -> str:
    return (
        value.replace("\\\\", "\\")
        .replace("\\t", "\t")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\0", "\0")
    )


def strip_string_edges(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_string_edges(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [strip_string_edges(inner) for inner in value]
    if isinstance(value, str):
        return value.strip()
    return value


def coerce_field(field_name: str, value: str) -> Any:
    decoded = decode_mysql_batch_value(value)
    if decoded == "NULL":
        return None
    decoded = decoded.strip()
    if field_name == "payload" and (decoded.startswith("{") or decoded.startswith("[")):
        try:
            return strip_string_edges(json.loads(decoded))
        except json.JSONDecodeError:
            pass
    if INT_PATTERN.match(decoded):
        try:
            return int(decoded)
        except ValueError:
            return decoded
    if FLOAT_PATTERN.match(decoded):
        try:
            return float(decoded)
        except ValueError:
            return decoded
    return decoded


def mysql_command(
    host: str,
    port: str,
    user: str,
    password: str,
    db: str,
    sql: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    proc = subprocess.run(
        [
            "mysql",
            "--batch",
            "--default-character-set=utf8mb4",
            "-h",
            host,
            "-P",
            port,
            "-u",
            user,
            db,
            "-e",
            sql,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"query failed with code {proc.returncode}")

    output = proc.stdout.strip()
    if not output:
        return [], []

    reader = csv.reader(output.splitlines(), delimiter="\t")
    rows = list(reader)
    field_names = rows[0]
    payload_rows: List[Dict[str, Any]] = []
    for raw_row in rows[1:]:
        payload_rows.append(
            {
                field_names[idx]: coerce_field(field_names[idx], raw_row[idx]) if idx < len(raw_row) else None
                for idx in range(len(field_names))
            }
        )
    return field_names, payload_rows


def run_doris_query(
    host: str,
    port: str,
    user: str,
    password: str,
    db: str,
    sql: str,
    timeout_seconds: int,
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    started = time.perf_counter()
    proc = subprocess.Popen(
        [
            "mysql",
            "--batch",
            "--default-character-set=utf8mb4",
            "-h",
            host,
            "-P",
            port,
            "-u",
            user,
            db,
            "-e",
            sql,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, **({"MYSQL_PWD": password} if password else {})},
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.communicate()
        raise exc

    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    if proc.returncode != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or f"query failed with code {proc.returncode}")

    output = stdout.strip()
    if not output:
        return [], [], elapsed_ms

    reader = csv.reader(output.splitlines(), delimiter="\t")
    rows = list(reader)
    field_names = rows[0]
    payload_rows: List[Dict[str, Any]] = []
    for raw_row in rows[1:]:
        payload_rows.append(
            {
                field_names[idx]: coerce_field(field_names[idx], raw_row[idx]) if idx < len(raw_row) else None
                for idx in range(len(field_names))
            }
        )
    return field_names, payload_rows, elapsed_ms


def verify_contract(
    contract: Dict[str, Any],
    field_names: List[str],
    rows: List[Dict[str, Any]],
    skip_expected_row_count: bool = False,
) -> Tuple[int, List[str], List[str], str]:
    normalized_rows = normalize_query_rows(rows)
    row_count = len(normalized_rows)
    required_fields = contract["assertions"].get("must_include_fields", [])
    missing_fields = [field for field in required_fields if field not in field_names]
    row_count_errors: List[str] = []
    minimum_row_count = contract.get("minimum_row_count")
    if isinstance(minimum_row_count, int) and row_count < minimum_row_count:
        row_count_errors.append(f"row_count {row_count} < minimum_row_count {minimum_row_count}")
    expected_row_count = contract.get("expected_row_count")
    if not skip_expected_row_count and isinstance(expected_row_count, int) and row_count != expected_row_count:
        row_count_errors.append(f"row_count {row_count} != expected_row_count {expected_row_count}")
    if contract.get("result_kind") == "sample_rows" and "payload" not in contract["assertions"].get("must_include_fields", []):
        result_fingerprint = fingerprint_query_rows_excluding_fields(normalized_rows, ["payload"])
    else:
        result_fingerprint = fingerprint_query_rows(normalized_rows)
    return row_count, missing_fields, row_count_errors, result_fingerprint


def render_query_log(query_id: str, sql: str, rows: List[Dict[str, Any]], runs: List[int]) -> str:
    return (
        f"{query_id}\n"
        f"{sql}\n"
        f"{json.dumps(normalize_query_rows(rows), ensure_ascii=False, indent=2)}\n"
        f"latency_ms_runs={runs}\n\n"
    )


def fetch_engine_version(host: str, port: str, user: str, password: str, db: str) -> str:
    _, rows = mysql_command(host, port, user, password, db, "SELECT version() AS version")
    if not rows:
        return "doris-unknown"
    version = rows[0].get("version")
    return str(version) if version else "doris-unknown"


def storage_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for sub in path.rglob("*"):
        if sub.is_file():
            total += sub.stat().st_size
    return total


def load_metrics(metrics_file: Path) -> Dict[str, int]:
    if not metrics_file.exists():
        return {"ingest_ms": 0, "index_build_ms": 0}
    payload = json.loads(metrics_file.read_text(encoding="utf-8"))
    return {
        "ingest_ms": int(payload.get("ingest_ms", 0)),
        "index_build_ms": int(payload.get("index_build_ms", 0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run observation-first Doris benchmark queries.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default="")
    parser.add_argument("--db", required=True)
    parser.add_argument("--table", default="agent_observations")
    parser.add_argument("--storage-path", type=Path, required=True)
    parser.add_argument("--metrics-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, default=None)
    args = parser.parse_args()

    root = args.root
    agentlogsbench_root = root / "agentlogsbench"
    manifest_path = Path(
        os.environ.get("AIBENCH_MANIFEST_PATH", str(bundled_small_data_dir(agentlogsbench_root) / "manifest.json"))
    )
    manifest = load_manifest(manifest_path)
    skip_contract_verification = os.environ.get("AIBENCH_SKIP_CONTRACT_VERIFICATION", "0").lower() in {"1", "true", "yes"}
    dataset_tier = os.environ.get("AIBENCH_DATASET_TIER", "S")
    dataset_version = os.environ.get("AIBENCH_DATASET_VERSION", manifest["edition"])
    contracts = json.loads(query_contracts_path(agentlogsbench_root).read_text(encoding="utf-8"))["contracts"]
    edition_text = edition_path(agentlogsbench_root).read_text(encoding="utf-8")
    edition = json.loads(edition_text)
    adapter = json.loads(adapter_manifest_path(agentlogsbench_root, "doris").read_text(encoding="utf-8"))
    query_map = json.loads(adapter_query_map_path(agentlogsbench_root, "doris").read_text(encoding="utf-8"))
    timeout_seconds = int(edition["execution_protocol"]["timeout_seconds"])

    args.result_dir.mkdir(parents=True, exist_ok=True)
    args.out_file.parent.mkdir(parents=True, exist_ok=True)
    result_file = args.result_file or (args.result_dir / "result.json")
    result_file.parent.mkdir(parents=True, exist_ok=True)

    params = load_context_from_paths(manifest_observation_paths(manifest_path, manifest), manifest["replay_trace_id"])
    engine_version = fetch_engine_version(args.host, args.port, args.user, args.password, args.db)
    metrics = load_metrics(args.metrics_file)
    query_results: List[Dict[str, Any]] = []
    log_lines: List[str] = []

    for query in load_query_definitions(agentlogsbench_root):
        query_id = query["id"]
        query_sql_path = engine_queries_file(agentlogsbench_root, "doris")
        query_sql = load_query_sql(query_sql_path, query["canonical_sql_section"])
        actual_sql = bind_doris_context(query_sql, params)
        contract = contracts[query_id]
        assertion_keys = sorted(contract["assertions"].keys())
        try:
            _, _, _ = run_doris_query(args.host, args.port, args.user, args.password, args.db, actual_sql, timeout_seconds)
            runs: List[int] = []
            field_names: List[str] = []
            rows: List[Dict[str, Any]] = []
            for _ in range(5):
                field_names, rows, elapsed_ms = run_doris_query(
                    args.host,
                    args.port,
                    args.user,
                    args.password,
                    args.db,
                    actual_sql,
                    timeout_seconds,
                )
                runs.append(elapsed_ms)

            rows = normalize_query_rows(rows)
            row_count, missing_fields, row_count_errors, result_fingerprint = verify_contract(
                contract,
                field_names,
                rows,
                skip_expected_row_count=skip_contract_verification,
            )
            fingerprint_errors: List[str] = []
            expected_result_fingerprint = contract.get("expected_result_fingerprints", {}).get("doris")
            if (
                not skip_contract_verification
                and isinstance(expected_result_fingerprint, str)
                and result_fingerprint != expected_result_fingerprint
            ):
                fingerprint_errors.append(
                    f"result_fingerprint {result_fingerprint} != expected_result_fingerprint {expected_result_fingerprint}"
                )
            status = "incorrect" if missing_fields or row_count_errors or fingerprint_errors else "ok"
            error_text = ""
        except subprocess.TimeoutExpired as exc:
            runs = [timeout_seconds * 1000] * 5
            status = "timeout"
            field_names = []
            rows = []
            row_count = 0
            missing_fields = []
            row_count_errors = []
            result_fingerprint = ""
            fingerprint_errors = []
            error_text = str(exc)
        except Exception as exc:  # noqa: BLE001
            runs = [1, 1, 1, 1, 1]
            status = "unsupported"
            field_names = []
            rows = []
            row_count = 0
            missing_fields = []
            row_count_errors = []
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
        if row_count_errors:
            verification["row_count_errors"] = row_count_errors
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
        "engine": "doris",
        "edition": "2026.04-observability-v1",
        "dataset_tier": dataset_tier,
        "run_protocol": {
            "warmup_runs": 1,
            "measured_runs": 5,
            "timeout_seconds": timeout_seconds,
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
            "ingest_ms": metrics["ingest_ms"],
            "index_build_ms": metrics["index_build_ms"],
            "storage_bytes": storage_bytes(args.storage_path),
        },
        "query_results": query_results,
    }
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
