#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.validate_large_generated import validate_large_generated_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a sharded large generated benchmark dataset.")
    parser.add_argument("--output-dir", type=Path, default=Path("generated/medium"))
    args = parser.parse_args()
    result = validate_large_generated_dataset(args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
