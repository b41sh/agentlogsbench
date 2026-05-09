from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

from agentlogsbench.tooling.engines import CLICKBENCH_RESULTS_DIRNAME, LEGACY_RESULTS_DIRNAME
from agentlogsbench.tooling.paths import bundled_small_data_dir


TIME_PATTERN = re.compile(r"^Time:\s+([0-9.]+)\s+ms$")


def parse_query_out(path: Path) -> Dict[str, float]:
    current = None
    timings: Dict[str, float] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("Q"):
            current = line.split(":", 1)[0]
            continue
        match = TIME_PATTERN.match(line)
        if match and current:
            timings[current] = float(match.group(1))
    return timings


def build_smoke_summary(root: Path) -> Dict[str, object]:
    systems = {}
    for engine in ("clickhouse", "postgres", "doris"):
        path = root / engine / CLICKBENCH_RESULTS_DIRNAME / "query.out"
        if not path.exists():
            path = root / engine / LEGACY_RESULTS_DIRNAME / "query.out"
        if path.exists():
            systems[engine] = {
                "status": "ok",
                "queries": parse_query_out(path),
            }
        else:
            systems[engine] = {"status": "missing"}

    for engine in ("elastic", "opensearch"):
        systems[engine] = {
            "status": "blocked",
            "reason": "official tarball download is too slow / unstable in current environment",
        }

    return {
        "generated_data_dir": str(bundled_small_data_dir(root)),
        "systems": systems,
    }


def write_smoke_summary(root: Path, output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_smoke_summary(root)
    json_path = output_dir / "smoke-summary.json"
    md_path = output_dir / "smoke-summary.md"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    lines: List[str] = ["# Small Run Summary", ""]
    for engine, payload in summary["systems"].items():
        lines.append(f"## {engine}")
        if payload["status"] != "ok":
            lines.append(f"- status: {payload['status']}")
            if "reason" in payload:
                lines.append(f"- reason: {payload['reason']}")
            lines.append("")
            continue
        lines.append("| Query | Time (ms) |")
        lines.append("| --- | --- |")
        for query_id, ms in sorted(payload["queries"].items()):
            lines.append(f"| {query_id} | {ms:.3f} |")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
