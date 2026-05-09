from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from agentlogsbench.tooling.generator import POSITIVE_PHRASES


REQUIRED_OBSERVATION_FIELDS = {
    "event_time",
    "biz_date",
    "trace_id",
    "session_id",
    "observation_id",
    "parent_observation_id",
    "seq_no",
    "type",
    "status",
    "tenant",
    "app",
    "environment",
    "task_category",
    "trace_archetype",
    "model",
    "tool_name",
    "input",
    "output",
    "input_tokens",
    "output_tokens",
    "total_cost",
    "latency_ms",
    "payload",
}

REQUIRED_SUMMARY_KEYS = (
    "generation_rows",
    "observation_rows",
    "trace_count",
    "tenant_count",
    "app_count",
    "observation_type_counts",
    "observation_status_counts",
    "keyword_injection",
    "payload_coverage",
    "telemetry_coverage",
    "text_reuse",
    "source_distribution",
    "tool_name_distribution",
)


def _load_ndjson(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def validate_generated_dataset(output_dir: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    obs_path = output_dir / "agent_observations_s.ndjson"
    summary_path = output_dir / "summary.json"
    labels_path = output_dir / "accuracy_labels.json"
    manifest_path = output_dir / "manifest.json"

    for path in (obs_path, summary_path, labels_path, manifest_path):
        if not path.exists():
            errors.append(f"missing file: {path}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    obs_rows = _load_ndjson(obs_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if not obs_rows:
        errors.append("observation dataset is empty")

    for key in REQUIRED_SUMMARY_KEYS:
        if key not in summary:
            errors.append(f"summary missing key: {key}")

    observation_ids = set()
    trace_ids = set()
    parent_ids = set()
    for row in obs_rows:
        missing = REQUIRED_OBSERVATION_FIELDS - set(row.keys())
        if missing:
            errors.append(f"observation row missing fields: {sorted(missing)}")
            continue
        observation_ids.add(row["observation_id"])
        trace_ids.add(row["trace_id"])
        if row["parent_observation_id"]:
            parent_ids.add(row["parent_observation_id"])
        if not isinstance(row["payload"], dict):
            errors.append(f"payload must be an object for observation {row['observation_id']}")
        if "raw_call_type" in row["payload"].get("context", {}):
            errors.append(f"observation payload.context must not expose raw_call_type: {row['observation_id']}")

    if len(observation_ids) != len(obs_rows):
        errors.append("observation_id values must be globally unique")

    if not parent_ids.issubset(observation_ids):
        errors.append("some parent_observation_id values do not point to an observation row")

    if manifest.get("replay_trace_id") not in trace_ids:
        errors.append("manifest replay_trace_id not found in observation dataset")
    if manifest.get("replay_observation_id") not in observation_ids:
        errors.append("manifest replay_observation_id not found in observation dataset")

    if labels.get("replay_observation_id") not in observation_ids:
        errors.append("accuracy_labels replay_observation_id not found in observation dataset")
    if labels.get("replay_observation_id") != manifest.get("replay_observation_id"):
        errors.append("accuracy_labels replay_observation_id must match manifest replay_observation_id")
    if manifest.get("trace_target") != summary.get("trace_count"):
        errors.append(
            f"trace_count mismatch: expected {manifest.get('trace_target')} got {summary.get('trace_count')}"
        )
    if manifest.get("generation_target") != summary.get("generation_rows"):
        errors.append(
            f"generation_rows mismatch: expected {manifest.get('generation_target')} got {summary.get('generation_rows')}"
        )

    obs_types = set(summary["observation_type_counts"].keys())
    if not {"GENERATION", "TOOL"}.issubset(obs_types):
        errors.append("observation dataset must contain GENERATION and TOOL rows")
    if summary["observation_type_counts"].get("EVENT", 0) == 0:
        warnings.append("observation dataset does not include EVENT rows")

    top_level_rows = sum(1 for row in obs_rows if row["parent_observation_id"] is None)
    if summary.get("generation_rows") != top_level_rows:
        errors.append("summary.generation_rows must match top-level request observation count")
    if summary.get("observation_rows") != len(obs_rows):
        errors.append("summary.observation_rows mismatch")

    if summary.get("tenant_count", 0) < 10:
        errors.append("tenant_count too small for long-tail small dataset")
    if summary.get("app_count", 0) < 12:
        errors.append("app_count too small for long-tail small dataset")

    if len(summary.get("trace_archetype_counts", {})) < 4:
        errors.append("expected at least four trace archetypes in small data")

    failure_rates = summary.get("failure_rates", {})
    if failure_rates.get("tool_failure_rate", 0) <= 0:
        warnings.append("tool_failure_rate is zero; failure-triage realism is weak")

    strong_rate = summary["keyword_injection"]["strong_rate"]
    hard_negative_rate = summary["keyword_injection"]["hard_negative_rate"]
    if not 0.10 <= strong_rate <= 0.30:
        errors.append(f"strong keyword injection rate out of expected small-scale range: {strong_rate}")
    if not 0.08 <= hard_negative_rate <= 0.35:
        errors.append(f"hard negative injection rate out of expected small-scale range: {hard_negative_rate}")
    positive_hit_ids = summary["keyword_injection"].get("positive_observation_ids", [])
    if not positive_hit_ids:
        errors.append("keyword_injection must record positive_observation_ids from actual text matches")
    else:
        observation_by_id = {row["observation_id"]: row for row in obs_rows}
        phrases = POSITIVE_PHRASES["error"] + POSITIVE_PHRASES["business"] + POSITIVE_PHRASES["safety"]
        for observation_id in positive_hit_ids[:10]:
            row = observation_by_id.get(observation_id)
            if row is None:
                errors.append(f"keyword_injection positive observation missing from dataset: {observation_id}")
                continue
            serialized = json.dumps(
                {"input": row.get("input"), "output": row.get("output"), "payload": row.get("payload", {})},
                ensure_ascii=False,
            )
            if not any(phrase in serialized for phrase in phrases):
                errors.append(f"keyword_injection observation does not contain a configured positive phrase: {observation_id}")

    gen_cov = summary["payload_coverage"]["generation"]
    tool_cov = summary["payload_coverage"]["tool"]
    dynamic_cov = summary["payload_coverage"]["attr"]
    telemetry_cov = summary["telemetry_coverage"]
    text_reuse = summary["text_reuse"]
    if gen_cov["temperature_ratio"] < 0.50:
        errors.append("temperature coverage too low")
    if gen_cov["provider_stop_reason_ratio"] < 1.0:
        errors.append("provider stop_reason coverage must be 1.0")
    if tool_cov["cwd_ratio"] < 0.20:
        errors.append("tool cwd coverage too low")
    if tool_cov["stderr_ratio"] < 0.05:
        warnings.append("tool stderr coverage is low; tool failure triage may be weak")
    if dynamic_cov["unique_key_count"] < 120:
        errors.append(f"dynamic field catalog too small: {dynamic_cov['unique_key_count']}")
    if dynamic_cov["p50_keys_per_observation"] < 18:
        errors.append(
            f"dynamic fields are too sparse for production-like faceting: {dynamic_cov['p50_keys_per_observation']}"
        )
    for key in ("release_ring", "customer_tier", "region", "workflow_variant", "retrieval_strategy"):
        if dynamic_cov["core_field_presence_ratio"].get(key, 0) < 0.95:
            errors.append(f"dynamic field core coverage too low for {key}")

    if len(summary.get("language_distribution", {})) < 3:
        errors.append("expected at least three language profiles in small data")
    for key in ("resource", "scope", "otel", "langfuse", "mlflow"):
        if telemetry_cov.get(key, 0) < 0.95:
            errors.append(f"telemetry coverage too low for {key}")
    if text_reuse.get("duplicate_ratio", 1.0) > 0.18:
        errors.append(f"text reuse ratio is too high: {text_reuse.get('duplicate_ratio')}")
    if text_reuse.get("max_reuse_count", 99) > 3:
        errors.append(f"text reuse max count is too high: {text_reuse.get('max_reuse_count')}")
    if text_reuse.get("max_line_reuse_count", 999) > 32:
        errors.append(f"text line reuse max count is too high: {text_reuse.get('max_line_reuse_count')}")
    if text_reuse.get("reused_line_count", 999) > 12:
        errors.append(f"too many heavily reused text lines: {text_reuse.get('reused_line_count')}")
    if len(summary.get("tool_name_distribution", {})) < 8:
        errors.append("tool_name_distribution is too narrow for production-like agent traces")
    if len(summary.get("source_distribution", {})) < 3:
        errors.append("source_distribution is too narrow for a provider-agnostic benchmark")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
