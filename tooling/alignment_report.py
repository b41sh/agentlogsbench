from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from agentlogsbench.tooling.paths import data_generation_path
from agentlogsbench.tooling.smoke_summary import build_smoke_summary


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_alignment_report(root: Path, generated_dir: Path) -> Dict[str, Any]:
    config = load_json(data_generation_path(root))
    manifest = load_json(generated_dir / "manifest.json")
    summary = load_json(generated_dir / "summary.json")
    labels = load_json(generated_dir / "accuracy_labels.json")
    smoke = build_smoke_summary(root)

    generation_rows = summary["generation_rows"]
    request_path_counts = summary["request_path_counts"]
    count_tokens_ratio = request_path_counts.get("/v1/messages/count_tokens", 0) / max(1, generation_rows)

    report = {
        "edition": manifest["edition"],
        "generated_at": manifest["generated_at"],
        "seed_files": manifest["seed_files"],
        "targets": {
            "trace_target": manifest["trace_target"],
            "generation_target": manifest["generation_target"],
            "strong_injection_rate": config["keyword_injection"]["strong_injection_rate"],
            "preserve_flags": config["preserve"],
        },
        "actual": {
            "trace_count": summary["trace_count"],
            "generation_rows": generation_rows,
            "observation_rows": summary["observation_rows"],
            "tenant_count": summary["tenant_count"],
            "app_count": summary["app_count"],
            "request_path_counts": request_path_counts,
            "count_tokens_ratio": count_tokens_ratio,
            "trace_archetype_counts": summary["trace_archetype_counts"],
            "trace_generation_distribution": summary["trace_generation_distribution"],
            "messages_body_size_buckets": summary["messages_body_size_buckets"],
            "count_tokens_body_size_buckets": summary["count_tokens_body_size_buckets"],
            "keyword_injection": summary["keyword_injection"],
            "payload_coverage": summary["payload_coverage"],
            "top_models": labels["top_models"],
            "replay_observation_id": labels["replay_observation_id"],
        },
        "systems": smoke["systems"],
        "notes": {
            "generator_scope": "doc-aligned small calibrated generator",
            "remaining_small_scale_simplifications": [
                "seed-derived envelopes still synthesize internal text/content instead of doing full template rewriting",
                "observation compiler is smoke-grade and intentionally simpler than a production-grade observation compiler",
                "Elastic remains blocked by environment download speed, not query-shape logic",
            ],
        },
    }
    return report


def build_markdown(report: Dict[str, Any]) -> str:
    actual = report["actual"]
    systems = report["systems"]
    lines: List[str] = [
        "# Generator Alignment Report",
        "",
        f"- edition: `{report['edition']}`",
        f"- generated_at: `{report['generated_at']}`",
        f"- seed_files: `{', '.join(report['seed_files'])}`",
        "",
        "## Core Alignment",
        "",
        f"- trace_target vs actual: `{report['targets']['trace_target']}` vs `{actual['trace_count']}`",
        f"- generation_target vs actual: `{report['targets']['generation_target']}` vs `{actual['generation_rows']}`",
        f"- observation_rows: `{actual['observation_rows']}`",
        f"- tenant_count/app_count: `{actual['tenant_count']}` / `{actual['app_count']}`",
        f"- /count_tokens ratio: `{pct(actual['count_tokens_ratio'])}`",
        "",
        "## Distribution Snapshot",
        "",
        f"- trace_archetype_counts: `{actual['trace_archetype_counts']}`",
        f"- trace_generation_distribution: `{actual['trace_generation_distribution']}`",
        f"- messages_body_size_buckets: `{actual['messages_body_size_buckets']}`",
        f"- count_tokens_body_size_buckets: `{actual['count_tokens_body_size_buckets']}`",
        "",
        "## Search and Attr Coverage",
        "",
        f"- keyword_injection: `{actual['keyword_injection']}`",
        f"- generation payload: `{actual['payload_coverage']['generation']}`",
        f"- tool payload: `{actual['payload_coverage']['tool']}`",
        f"- top_models: `{actual['top_models']}`",
        f"- replay_observation_id: `{actual['replay_observation_id']}`",
        "",
        "## Small Run Status",
        "",
    ]
    for engine, payload in systems.items():
        if payload["status"] == "ok":
            lines.append(f"- `{engine}`: ok, queries={list(payload['queries'].keys())}")
        else:
            lines.append(f"- `{engine}`: {payload['status']} ({payload.get('reason', 'n/a')})")
    lines.extend([
        "",
        "## Notes",
        "",
        f"- generator_scope: `{report['notes']['generator_scope']}`",
    ])
    for note in report["notes"]["remaining_small_scale_simplifications"]:
        lines.append(f"- {note}")
    return "\n".join(lines)


def write_alignment_report(root: Path, generated_dir: Path) -> Dict[str, Path]:
    report = build_alignment_report(root, generated_dir)
    json_path = generated_dir / "alignment-report.json"
    md_path = generated_dir / "alignment-report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(build_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
