#!/usr/bin/env python3
from __future__ import annotations

import os

from agentlogsbench.elastic import query_runner as elastic_query_runner
from agentlogsbench.elastic.query_runner import q05_body, q08_body, q11_body

__all__ = ["main", "q05_body", "q08_body", "q11_body"]


def main() -> int:
    previous = os.environ.get("AIBENCH_SEARCH_ENGINE")
    os.environ["AIBENCH_SEARCH_ENGINE"] = "opensearch"
    try:
        return elastic_query_runner.main()
    finally:
        if previous is None:
            os.environ.pop("AIBENCH_SEARCH_ENGINE", None)
        else:
            os.environ["AIBENCH_SEARCH_ENGINE"] = previous


if __name__ == "__main__":
    raise SystemExit(main())
