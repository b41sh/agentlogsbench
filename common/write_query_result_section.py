#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.query_results import render_elasticsearch_result_section, render_sql_result_section


def main() -> int:
    parser = argparse.ArgumentParser(description="Render one query result section in JSONBench text format.")
    parser.add_argument("--engine", choices=("sql", "elastic"), required=True)
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--with-header", action="store_true", help="Treat SQL stdin as tab-separated with a header row")
    args = parser.parse_args()

    text = sys.stdin.read()
    if args.engine == "sql":
        sys.stdout.write(render_sql_result_section(args.query_id, text, with_header=args.with_header))
        return 0

    payload = json.loads(text)
    sys.stdout.write(render_elasticsearch_result_section(args.query_id, payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

