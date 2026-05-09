#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.run_artifacts import validate_run_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate benchmark run artifacts.")
    parser.add_argument("--results-dir", type=Path, required=True, help="Directory containing result JSON files")
    args = parser.parse_args()

    result = validate_run_artifacts(args.results_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
