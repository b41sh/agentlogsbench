#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.edition import benchmark_root, validate_edition


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate benchmark edition config and manifests.")
    parser.add_argument("--root", type=Path, default=None, help="Benchmark root, defaults to agentlogsbench/")
    args = parser.parse_args()

    root = args.root or benchmark_root(Path(__file__).resolve())
    result = validate_edition(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
