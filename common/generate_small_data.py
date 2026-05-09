#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.generator import generate_small_dataset, write_dataset
from agentlogsbench.tooling.paths import seed_dir as default_seed_dir_for_root


def main() -> int:
    default_seed_dir = Path("/mnt/disk1/claude-max/doris-wt-feat-nested-ee-codex/agent_logs/minimax")
    if not default_seed_dir.exists():
        default_seed_dir = default_seed_dir_for_root(REPO_ROOT / "agentlogsbench")
    parser = argparse.ArgumentParser(description="Generate small AI agent observability benchmark data.")
    parser.add_argument("--output-dir", type=Path, default=Path("common/generated/small"))
    parser.add_argument("--seed-dir", type=Path, default=default_seed_dir)
    parser.add_argument("--generations", type=int, default=48)
    parser.add_argument("--traces", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260411)
    args = parser.parse_args()

    dataset = generate_small_dataset(
        args.output_dir,
        args.seed_dir,
        generation_target=args.generations,
        trace_target=args.traces,
        seed=args.seed,
    )
    write_dataset(dataset, args.output_dir)
    print(
        json.dumps(
            {
                "ok": True,
                "output_dir": str(args.output_dir),
                "generation_rows": len(dataset.requests),
                "observation_rows": len(dataset.observations),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
