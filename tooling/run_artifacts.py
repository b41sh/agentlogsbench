from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agentlogsbench.tooling.edition import (
    benchmark_root,
    load_adapter_query_map,
    load_contracts,
    load_json,
    load_main_track_query_ids,
)
from agentlogsbench.tooling.paths import adapters_dir, edition_path
from agentlogsbench.tooling.score import RESULT_STATUSES, iter_result_files, load_result


REQUIRED_RUN_METADATA_FIELDS = (
    "dataset_version",
    "engine_version",
    "config_fingerprint",
    "index_config_fingerprint",
    "query_adapter_version",
    "execution_mode",
    "run_timestamp",
)
REQUIRED_SECONDARY_METRICS = ("ingest_ms", "index_build_ms", "storage_bytes")
EXPECTED_EDITION = "2026.04-observability-v1"
EXPECTED_DATASET_TIERS = {"S", "M", "L"}
EXPECTED_CACHE_POLICY = "disable_where_supported"
EXPECTED_EXECUTION_MODES = {"runnable", "fixture"}
CONTRACT_FLAG_FIELDS = (
    "same_element_required",
    "portable_boolean_term_phrase_only",
    "must_reject_analyzer_specific_false_positives",
    "explode_required",
    "double_explode_required",
)


def _validate_contract_verification(
    errors: List[str],
    path: Path,
    query_id: str,
    query_result: Dict[str, Any],
    contract: Dict[str, Any],
    require_observed_shape: bool,
    skip_fixture_contract_checks: bool,
    engine: str,
) -> None:
    verification = query_result.get("contract_verification")
    if not isinstance(verification, dict):
        errors.append(f"{path}: {query_id} missing contract_verification")
        return

    if verification.get("contract_id") != query_id:
        errors.append(f"{path}: {query_id} contract_verification.contract_id must equal query_id")
    if verification.get("fixture_dataset") != contract.get("fixture_dataset"):
        errors.append(f"{path}: {query_id} contract_verification.fixture_dataset mismatch")

    checked_keys = verification.get("assertion_keys_checked")
    expected_keys = sorted(contract.get("assertions", {}).keys())
    if checked_keys != expected_keys:
        errors.append(
            f"{path}: {query_id} assertion_keys_checked must match contract assertions {expected_keys}"
        )

    if require_observed_shape:
        observed_fields = verification.get("observed_fields")
        required_fields = contract.get("assertions", {}).get("must_include_fields", [])
        if not isinstance(observed_fields, list):
            errors.append(f"{path}: {query_id} contract_verification.observed_fields must be a list")
        else:
            missing_fields = [field for field in required_fields if field not in observed_fields]
            if missing_fields:
                errors.append(
                    f"{path}: {query_id} contract_verification.observed_fields missing {missing_fields}"
                )

        row_count = verification.get("row_count")
        if not isinstance(row_count, int) or row_count < 0:
            errors.append(
                f"{path}: {query_id} contract_verification.row_count must be a non-negative integer"
            )
        else:
            minimum_row_count = contract.get("minimum_row_count")
            if isinstance(minimum_row_count, int) and row_count < minimum_row_count:
                errors.append(
                    f"{path}: {query_id} row_count {row_count} < minimum_row_count {minimum_row_count}"
                )
            expected_row_count = contract.get("expected_row_count")
            if (
                not skip_fixture_contract_checks
                and isinstance(expected_row_count, int)
                and row_count != expected_row_count
            ):
                errors.append(
                    f"{path}: {query_id} row_count {row_count} != expected_row_count {expected_row_count}"
                )

        expected_result_fingerprint = contract.get("expected_result_fingerprints", {}).get(engine)
        actual_result_fingerprint = verification.get("result_fingerprint")
        if not isinstance(actual_result_fingerprint, str):
            errors.append(f"{path}: {query_id} contract_verification.result_fingerprint must be a string")
        elif (
            not skip_fixture_contract_checks
            and
            isinstance(expected_result_fingerprint, str)
            and actual_result_fingerprint != expected_result_fingerprint
        ):
            errors.append(
                f"{path}: {query_id} result_fingerprint {actual_result_fingerprint} "
                f"!= expected_result_fingerprint {expected_result_fingerprint}"
            )

    for field in CONTRACT_FLAG_FIELDS:
        expected_flag = contract.get(field)
        actual_flag = verification.get(field)
        if expected_flag is True and actual_flag is not True:
            errors.append(f"{path}: {query_id} contract_verification.{field} must be true")
        if expected_flag is None and actual_flag not in (None, False):
            errors.append(f"{path}: {query_id} contract_verification.{field} must be omitted or false")


def validate_run_artifacts(results_dir: Path, root: Path | None = None) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    found_results = 0
    root = root or benchmark_root(Path(__file__).resolve())
    edition = load_json(edition_path(root))
    query_ids = load_main_track_query_ids(root)
    query_id_set = set(query_ids)
    execution_protocol = edition.get("execution_protocol", {})
    contracts = load_contracts(root).get("contracts", {})
    manifests = {
        manifest_path.parent.name: load_json(manifest_path)
        for manifest_path in adapters_dir(root).glob("*/manifest.json")
    }

    for path in iter_result_files(results_dir):
        payload = load_result(path)
        if "query_results" not in payload:
            continue
        found_results += 1
        engine = payload.get("engine")
        if not engine:
            errors.append(f"{path}: missing engine")
            continue
        manifest = manifests.get(engine)
        if manifest is None:
            errors.append(f"{path}: unknown engine {engine}")
            continue
        query_map = load_adapter_query_map(root, manifest)
        adapter_version = str(query_map["adapter_version"])

        if payload.get("edition") != EXPECTED_EDITION:
            errors.append(f"{path}: edition must be {EXPECTED_EDITION}")
        if payload.get("dataset_tier") not in EXPECTED_DATASET_TIERS:
            errors.append(f"{path}: dataset_tier must be one of {sorted(EXPECTED_DATASET_TIERS)}")

        run_protocol = payload.get("run_protocol", {})
        for field in ("warmup_runs", "measured_runs", "timeout_seconds"):
            if run_protocol.get(field) != execution_protocol.get(field):
                errors.append(
                    f"{path}: run_protocol.{field} must be {execution_protocol.get(field)}"
                )
        if run_protocol.get("cache_policy") != EXPECTED_CACHE_POLICY:
            errors.append(f"{path}: run_protocol.cache_policy must be {EXPECTED_CACHE_POLICY}")

        metadata = payload.get("run_metadata", {})
        for field in REQUIRED_RUN_METADATA_FIELDS:
            if field not in metadata:
                errors.append(f"{path}: missing run_metadata.{field}")
        if metadata.get("query_adapter_version") != adapter_version:
            errors.append(
                f"{path}: run_metadata.query_adapter_version must match adapter_version {adapter_version}"
            )
        if metadata.get("execution_mode") not in EXPECTED_EXECUTION_MODES:
            errors.append(
                f"{path}: run_metadata.execution_mode must be one of {sorted(EXPECTED_EXECUTION_MODES)}"
            )
        require_observed_shape = metadata.get("execution_mode") == "runnable"

        secondary = payload.get("secondary_metrics", {})
        for field in REQUIRED_SECONDARY_METRICS:
            value = secondary.get(field)
            if not isinstance(value, (int, float)):
                errors.append(f"{path}: secondary_metrics.{field} must be numeric")

        query_results = payload.get("query_results")
        if not isinstance(query_results, list):
            errors.append(f"{path}: query_results must be a list")
            continue

        seen_ids = set()
        for query_result in query_results:
            query_id = query_result.get("query_id")
            if query_id not in query_id_set:
                errors.append(f"{path}: unexpected query_id {query_id}")
                continue
            if query_id in seen_ids:
                errors.append(f"{path}: duplicate query_id {query_id}")
                continue
            seen_ids.add(query_id)

            status = query_result.get("status")
            if status not in RESULT_STATUSES:
                errors.append(f"{path}: {query_id} invalid status {status}")

            runs = query_result.get("latency_ms_runs")
            if not isinstance(runs, list) or len(runs) != execution_protocol.get("measured_runs"):
                errors.append(
                    f"{path}: {query_id} latency_ms_runs must have exactly "
                    f"{execution_protocol.get('measured_runs')} entries"
                )
            elif not all(isinstance(value, (int, float)) and value > 0 for value in runs):
                errors.append(f"{path}: {query_id} latency_ms_runs must be positive numeric values")

            contract = contracts.get(query_id)
            if not isinstance(contract, dict):
                errors.append(f"{path}: missing contract definition for {query_id}")
            else:
                verification_mode = query_result.get("contract_verification", {}).get("verification_mode")
                _validate_contract_verification(
                    errors,
                    path,
                    query_id,
                    query_result,
                    contract,
                    require_observed_shape,
                    verification_mode == "benchmark_only",
                    engine,
                )

        if seen_ids != query_id_set:
            missing_ids = sorted(query_id_set - seen_ids)
            errors.append(f"{path}: missing query_ids {missing_ids}")

    if found_results == 0:
        errors.append(f"no result payloads found under {results_dir}")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
