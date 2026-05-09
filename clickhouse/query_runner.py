#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def env_flag(name: str) -> bool:
    return os.environ.get(name, "0").lower() in {"1", "true", "yes"}


def storage_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for sub in path.rglob("*"):
        if sub.is_file():
            total += sub.stat().st_size
    return total


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def resolve_clickhouse_bin(root: Path) -> str:
    env_bin = os.environ.get("CH_BIN")
    if env_bin:
        return env_bin

    local_root = root / "agentlogsbench" / "clickhouse" / ".local"
    candidates = sorted(local_root.glob("clickhouse-common-static-*/usr/bin/clickhouse"))
    if candidates:
        return str(candidates[-1])

    system_bin = shutil.which("clickhouse")
    if system_bin:
        return system_bin

    return str(local_root / "clickhouse-common-static" / "usr" / "bin" / "clickhouse")


def bind_clickhouse_context(query_sql: str, params: Dict[str, str]) -> str:
    sql = query_sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    return (
        "WITH "
        f"{sql_quote(params['tenant'])} AS tenant_param, "
        f"{sql_quote(params['app'])} AS app_param, "
        f"{sql_quote(params['trace_id'])} AS trace_id_param, "
        f"{sql_quote(params['release_ring'])} AS release_ring_param, "
        f"{sql_quote(params['customer_tier'])} AS customer_tier_param, "
        f"{sql_quote(params['traffic_cluster'])} AS traffic_cluster_param, "
        f"{sql_quote(params['request_key'])} AS request_key_param, "
        f"{sql_quote(params['workflow_variant'])} AS workflow_variant_param, "
        f"toDate({sql_quote(params['start_date'])}) AS start_date_param, "
        f"toDate({sql_quote(params['end_date'])}) AS end_date_param\n"
        f"{sql}"
    )


def run_clickhouse_query(ch_bin: str, ch_path: str, sql: str, timeout_seconds: int) -> Tuple[Dict[str, Any], int]:
    started = time.perf_counter()
    proc = subprocess.run(
        [ch_bin, "local", "--path", ch_path, "-q", f"{sql}\nFORMAT JSON"],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"query failed with code {proc.returncode}")
    return json.loads(proc.stdout), elapsed_ms


def load_query_definitions(agentlogsbench_root: Path) -> List[Dict[str, str]]:
    suite = json.loads(query_suite_path(agentlogsbench_root).read_text(encoding="utf-8"))
    return list(suite["queries"])


def verify_contract(
    contract: Dict[str, Any],
    result_payload: Dict[str, Any],
    skip_expected_row_count: bool = False,
) -> Tuple[List[str], int, List[str], List[str], str]:
    observed_fields = [entry["name"] for entry in result_payload.get("meta", [])]
    normalized_rows = normalize_query_rows(result_payload.get("data", []))
    row_count = len(normalized_rows)
    required_fields = contract["assertions"].get("must_include_fields", [])
    missing_fields = [field for field in required_fields if field not in observed_fields]
    row_count_errors: List[str] = []
    minimum_row_count = contract.get("minimum_row_count")
    if isinstance(minimum_row_count, int) and row_count < minimum_row_count:
        row_count_errors.append(f"row_count {row_count} < minimum_row_count {minimum_row_count}")
    expected_row_count = contract.get("expected_row_count")
    if (
        not skip_expected_row_count
        and isinstance(expected_row_count, int)
        and row_count != expected_row_count
    ):
        row_count_errors.append(f"row_count {row_count} != expected_row_count {expected_row_count}")
    if contract.get("result_kind") == "sample_rows" and "payload" not in contract["assertions"].get("must_include_fields", []):
        result_fingerprint = fingerprint_query_rows_excluding_fields(normalized_rows, ["payload"])
    else:
        result_fingerprint = fingerprint_query_rows(normalized_rows)
    return observed_fields, row_count, missing_fields, row_count_errors, result_fingerprint


def render_query_log(query_id: str, sql: str, result_payload: Dict[str, Any], runs: List[int]) -> str:
    return (
        f"{query_id}\n"
        f"{sql}\n"
        f"{json.dumps(result_payload, ensure_ascii=False, indent=2)}\n"
        f"latency_ms_runs={runs}\n\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run observation-first ClickHouse benchmark queries.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
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
    adapter = json.loads(adapter_manifest_path(agentlogsbench_root, "clickhouse").read_text(encoding="utf-8"))
    query_map = json.loads(adapter_query_map_path(agentlogsbench_root, "clickhouse").read_text(encoding="utf-8"))
    timeout_seconds = int(edition["execution_protocol"]["timeout_seconds"])

    ch_bin = resolve_clickhouse_bin(root)
    ch_path = os.environ.get("CH_PATH", str(agentlogsbench_root / "clickhouse" / "runtime" / "ch_data"))

    args.result_dir.mkdir(parents=True, exist_ok=True)
    args.out_file.parent.mkdir(parents=True, exist_ok=True)
    result_file = args.result_file or (args.result_dir / "result.json")
    result_file.parent.mkdir(parents=True, exist_ok=True)

    version_proc = subprocess.run([ch_bin, "local", "--version"], check=False, capture_output=True, text=True)
    engine_version = (version_proc.stdout or version_proc.stderr or "clickhouse-local-unknown").strip()

    params = load_context_from_paths(manifest_observation_paths(manifest_path, manifest), manifest["replay_trace_id"])
    query_results: List[Dict[str, Any]] = []
    log_lines: List[str] = []

    for query in load_query_definitions(agentlogsbench_root):
        query_id = query["id"]
        query_sql_path = engine_queries_file(agentlogsbench_root, "clickhouse")
        query_sql = load_query_sql(query_sql_path, query["canonical_sql_section"])
        actual_sql = bind_clickhouse_context(query_sql, params)
        contract = contracts[query_id]
        assertion_keys = sorted(contract["assertions"].keys())
        try:
            warmup_payload, _ = run_clickhouse_query(ch_bin, ch_path, actual_sql, timeout_seconds)
            runs: List[int] = []
            last_payload = warmup_payload
            for _ in range(5):
                payload, elapsed_ms = run_clickhouse_query(ch_bin, ch_path, actual_sql, timeout_seconds)
                runs.append(elapsed_ms)
                last_payload = payload

            observed_fields, row_count, missing_fields, row_count_errors, result_fingerprint = verify_contract(
                contract,
                last_payload,
                skip_expected_row_count=skip_contract_verification,
            )
            fingerprint_errors: List[str] = []
            expected_result_fingerprint = contract.get("expected_result_fingerprints", {}).get("clickhouse")
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
            last_payload = {"meta": [], "data": [], "error": f"timeout after {timeout_seconds}s"}
            observed_fields = []
            row_count = 0
            missing_fields = []
            row_count_errors = []
            result_fingerprint = ""
            fingerprint_errors = []
            error_text = str(exc)
        except Exception as exc:  # noqa: BLE001 - benchmark skeleton should emit a result payload even on failure
            runs = [1, 1, 1, 1, 1]
            status = "unsupported"
            last_payload = {"meta": [], "data": [], "error": str(exc)}
            observed_fields = []
            row_count = 0
            missing_fields = []
            row_count_errors = []
            result_fingerprint = ""
            fingerprint_errors = []
            error_text = str(exc)

        log_lines.append(render_query_log(query_id, actual_sql, last_payload, runs))
        if error_text:
            log_lines.append(f"ERROR: {error_text}\n\n")

        verification: Dict[str, Any] = {
            "contract_id": query_id,
            "fixture_dataset": contract["fixture_dataset"],
            "assertion_keys_checked": assertion_keys,
            "verification_mode": "benchmark_only" if skip_contract_verification else "fixture_contract",
            "observed_fields": observed_fields,
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
        "engine": "clickhouse",
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
            "storage_bytes": storage_bytes(Path(ch_path)),
        },
        "query_results": query_results,
    }
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
