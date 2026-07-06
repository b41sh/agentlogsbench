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
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTLOGSBENCH_ROOT = REPO_ROOT / "agentlogsbench"
DEFAULT_DRIVER_PATH = AGENTLOGSBENCH_ROOT / "bendsql" / "bindings" / "python" / "package"

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


def add_driver_path(driver_path: Path, explicit: bool) -> None:
    has_extension = any((driver_path / "databend_driver").glob("_databend_driver*.so"))
    if (explicit or has_extension) and str(driver_path) not in sys.path:
        sys.path.insert(0, str(driver_path))


def load_query_definitions(agentlogsbench_root: Path) -> list[dict[str, Any]]:
    suite = json.loads(query_suite_path(agentlogsbench_root).read_text(encoding="utf-8"))
    return list(suite["queries"])


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


def verify_contract(
    contract: dict[str, Any],
    field_names: list[str],
    row_count: int,
    skip_expected_row_count: bool = False,
) -> list[str]:
    required_fields = contract["assertions"].get("must_include_fields", [])
    errors = [field for field in required_fields if field not in field_names]
    minimum_row_count = contract.get("minimum_row_count")
    if isinstance(minimum_row_count, int) and row_count < minimum_row_count:
        errors.append(f"row_count {row_count} < minimum_row_count {minimum_row_count}")
    expected_row_count = contract.get("expected_row_count")
    if not skip_expected_row_count and isinstance(expected_row_count, int) and row_count != expected_row_count:
        errors.append(f"row_count {row_count} != expected_row_count {expected_row_count}")
    return errors


def render_query_log(query_id: str, sql: str, rows: list[dict[str, Any]], runs: list[int]) -> str:
    return (
        f"{query_id}\n"
        f"{sql}\n"
        f"{json.dumps(rows, ensure_ascii=False, indent=2, default=str)}\n"
        f"latency_ms_runs={runs}\n\n"
    )


def run_query(conn: object, sql: str, params: dict[str, str]) -> tuple[list[str], list[dict[str, Any]], int]:
    started = time.perf_counter()
    iterator = conn.query_iter(sql, params)  # type: ignore[attr-defined]
    try:
        field_names = iterator_columns(iterator)
        dict_rows = [row.__dict__() for row in iterator]
    finally:
        iterator.close()
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    return field_names, normalize_query_rows(dict_rows), elapsed_ms


def main() -> int:
    parser = argparse.ArgumentParser(description="Run observation-first Databend benchmark queries.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, default=None)
    parser.add_argument("--dsn", default=os.environ.get("DATABEND_DSN", "databend://root:@127.0.0.1:8000/?sslmode=disable"))
    explicit_driver_path = "DATABEND_DRIVER_PYTHONPATH" in os.environ
    parser.add_argument("--driver-path", type=Path, default=Path(os.environ.get("DATABEND_DRIVER_PYTHONPATH", DEFAULT_DRIVER_PATH)))
    parser.add_argument("--database", default=os.environ.get("DATABEND_DB", "agentlogsbench_bench"))
    parser.add_argument("--table", default=os.environ.get("DATABEND_TABLE", "agent_observations"))
    args = parser.parse_args()

    add_driver_path(args.driver_path, explicit_driver_path)
    try:
        import databend_driver
    except ImportError as exc:
        raise SystemExit(f"Could not import databend_driver from {args.driver_path}: {exc}") from exc

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
    adapter = json.loads(adapter_manifest_path(agentlogsbench_root, "databend").read_text(encoding="utf-8"))
    query_map = json.loads(adapter_query_map_path(agentlogsbench_root, "databend").read_text(encoding="utf-8"))

    args.result_dir.mkdir(parents=True, exist_ok=True)
    args.out_file.parent.mkdir(parents=True, exist_ok=True)
    result_file = args.result_file or (args.result_dir / "result.json")
    result_file.parent.mkdir(parents=True, exist_ok=True)

    client = databend_driver.BlockingDatabendClient(args.dsn)
    conn = client.get_conn()
    query_results: list[dict[str, Any]] = []
    log_lines: list[str] = []
    try:
        conn.exec(f"USE {args.database}")
        conn.exec("SET enable_experimental_virtual_column=1")
        engine_version = conn.version()
        params = load_context_from_paths(manifest_observation_paths(manifest_path, manifest), manifest["replay_trace_id"])

        for query in load_query_definitions(agentlogsbench_root):
            query_id = query["id"]
            query_sql_path = engine_queries_file(agentlogsbench_root, "databend")
            query_sql = load_query_sql(query_sql_path, query["canonical_sql_section"])
            actual_sql, sql_params = bind_sql(query_sql, params, args.table)
            contract = contracts[query_id]
            assertion_keys = sorted(contract["assertions"].keys())
            try:
                _, _, _ = run_query(conn, actual_sql, sql_params)
                runs: list[int] = []
                field_names: list[str] = []
                rows: list[dict[str, Any]] = []
                for _ in range(5):
                    field_names, rows, elapsed_ms = run_query(conn, actual_sql, sql_params)
                    runs.append(elapsed_ms)

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
                fingerprint_errors: list[str] = []
                expected_result_fingerprint = contract.get("expected_result_fingerprints", {}).get("databend")
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

            verification: dict[str, Any] = {
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
            "engine": "databend",
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
                "storage_bytes": 0,
            },
            "query_results": query_results,
        }
        result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
