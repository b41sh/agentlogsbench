#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.edition import benchmark_root, load_main_track_query_ids
from agentlogsbench.tooling.score import iter_result_files, load_and_score, load_result
from agentlogsbench.tooling.summary import write_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize benchmark results.")
    parser.add_argument("--root", type=Path, default=None, help="Benchmark root, defaults to agentlogsbench/")
    parser.add_argument("--results-dir", type=Path, required=True, help="Directory containing per-engine result JSON files")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for summary artifacts")
    args = parser.parse_args()

    root = args.root or benchmark_root(Path(__file__).resolve())
    query_ids = load_main_track_query_ids(root)
    scored = load_and_score(args.results_dir, query_ids)
    engine_runs = []
    editions = set()
    dataset_tiers = set()
    for path in iter_result_files(args.results_dir):
        payload = load_result(path)
        if "query_results" not in payload:
            continue
        metadata = payload.get("run_metadata", {})
        edition = payload.get("edition")
        if edition:
            editions.add(edition)
        dataset_tier = payload.get("dataset_tier")
        if dataset_tier:
            dataset_tiers.add(dataset_tier)
        engine_runs.append({
            "engine": payload["engine"],
            "edition": edition,
            "dataset_tier": dataset_tier,
            "dataset_version": metadata.get("dataset_version"),
            "engine_version": metadata.get("engine_version"),
            "config_fingerprint": metadata.get("config_fingerprint"),
            "index_config_fingerprint": metadata.get("index_config_fingerprint"),
            "query_adapter_version": metadata.get("query_adapter_version"),
            "execution_mode": metadata.get("execution_mode"),
            "run_timestamp": metadata.get("run_timestamp")
        })
    if len(dataset_tiers) == 1:
        summary_tier = next(iter(dataset_tiers))
    elif dataset_tiers:
        summary_tier = "mixed"
    else:
        summary_tier = None
    if len(editions) == 1:
        summary_edition = next(iter(editions))
    elif editions:
        summary_edition = "mixed"
    else:
        summary_edition = None
    scored["run_metadata"] = {
        "edition": summary_edition,
        "dataset_tier": summary_tier,
        "results_dir": str(args.results_dir),
        "engine_runs": engine_runs
    }
    paths = write_summary(scored, args.output_dir)
    print(json.dumps({"ok": True, "outputs": {key: str(value) for key, value in paths.items()}}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
