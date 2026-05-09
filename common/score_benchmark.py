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
from agentlogsbench.tooling.score import load_and_score


def main() -> int:
    parser = argparse.ArgumentParser(description="Score benchmark result JSON files.")
    parser.add_argument("--root", type=Path, default=None, help="Benchmark root, defaults to agentlogsbench/")
    parser.add_argument("--results-dir", type=Path, required=True, help="Directory containing per-engine result JSON files")
    args = parser.parse_args()

    root = args.root or benchmark_root(Path(__file__).resolve())
    query_ids = load_main_track_query_ids(root)
    scored = load_and_score(args.results_dir, query_ids)
    print(json.dumps(scored, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
