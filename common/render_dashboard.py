#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.dashboard import build_dashboard_payload, render_dashboard_js


def main() -> int:
    parser = argparse.ArgumentParser(description="Render ClickBench-style dashboard data for agentlogsbench.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Benchmark root")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data.generated.js",
        help="Output JavaScript payload consumed by index.html",
    )
    args = parser.parse_args()

    payload = build_dashboard_payload(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_dashboard_js(payload), encoding="utf-8")
    print(
        f"Rendered dashboard data for {len(payload['results'])} runs across "
        f"{len(payload['dataset_sizes'])} dataset sizes -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
