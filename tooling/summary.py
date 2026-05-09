from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def build_markdown_summary(scored: Dict[str, Any]) -> str:
    lines = ["# Benchmark Summary", ""]
    metadata = scored.get("run_metadata", {})
    if metadata:
        lines.append("## Run Metadata")
        lines.append("")
        for key, value in metadata.items():
            if key == "engine_runs":
                continue
            lines.append(f"- `{key}`: {value}")
        lines.append("")
        engine_runs = metadata.get("engine_runs", [])
        if engine_runs:
            lines.append("### Engine Runs")
            lines.append("")
            for item in engine_runs:
                lines.append(
                    f"- `{item['engine']}`: edition={item['edition']}, "
                    f"dataset_tier={item['dataset_tier']}, "
                    f"engine_version={item['engine_version']}, "
                    f"dataset_version={item['dataset_version']}, "
                    f"config_fingerprint={item['config_fingerprint']}, "
                    f"index_config_fingerprint={item['index_config_fingerprint']}, "
                    f"query_adapter_version={item['query_adapter_version']}, "
                    f"execution_mode={item['execution_mode']}, "
                    f"run_timestamp={item['run_timestamp']}"
                )
            lines.append("")
    lines.append("## Main Leaderboard")
    lines.append("")
    lines.append("| Rank | Engine | Composite Ratio |")
    lines.append("| --- | --- | --- |")
    for idx, item in enumerate(scored["main_leaderboard"], start=1):
        lines.append(f"| {idx} | {item['engine']} | {item['composite_ratio']:.6f} |")
    lines.append("")

    if scored["appendix"]:
        lines.append("## Incomplete Engines")
        lines.append("")
        for item in scored["appendix"]:
            lines.append(f"- `{item['engine']}`: {item['reason']}")
        lines.append("")

    return "\n".join(lines)


def write_summary(scored: Dict[str, Any], output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "benchmark-summary.json"
    md_path = output_dir / "benchmark-summary.md"
    json_path.write_text(json.dumps(scored, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(build_markdown_summary(scored), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
