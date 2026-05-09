from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.tooling.query_results import (
    extract_elasticsearch_result,
    render_sql_result_section,
)


class QueryResultsTest(unittest.TestCase):
    def test_render_sql_result_section_projects_common_columns(self) -> None:
        text = "\t".join(
            [
                "event_time",
                "trace_id",
                "observation_id",
                "tool_name",
                "latency_ms",
                "text_score",
                "payload",
            ]
        ) + "\n" + "\t".join(
            [
                "2026-04-01 10:00:00",
                "trace-1",
                "obs-1",
                "tool-a",
                "123",
                "2",
                "{\"k\":1}",
            ]
        ) + "\n"

        rendered = render_sql_result_section("Q05", text, with_header=True)

        self.assertIn("Result for query Q05:", rendered)
        self.assertIn("event_time", rendered)
        self.assertIn("trace_id", rendered)
        self.assertNotIn("payload", rendered)
        self.assertNotIn("text_score", rendered)
        self.assertIn("obs-1", rendered)

    def test_extract_elasticsearch_result_sorts_and_limits_rows(self) -> None:
        payload = {
            "aggregations": {
                "tool_name": {
                    "buckets": [
                        {
                            "key": "tool-b",
                            "status": {
                                "buckets": [
                                    {"key": "error", "doc_count": 10, "avg_latency_ms": {"value": 30.0}},
                                    {"key": "ok", "doc_count": 10, "avg_latency_ms": {"value": 20.0}},
                                ]
                            },
                        },
                        {
                            "key": "tool-a",
                            "status": {
                                "buckets": [
                                    {"key": "ok", "doc_count": 12, "avg_latency_ms": {"value": 10.0}},
                                ]
                            },
                        },
                    ]
                }
            }
        }

        columns, rows = extract_elasticsearch_result("Q09", payload)

        self.assertEqual(columns, ["tool_name", "status", "observations", "avg_latency_ms"])
        self.assertEqual(rows[0], ["tool-a", "ok", "12", "10"])
        self.assertEqual(rows[1], ["tool-b", "error", "10", "30"])
        self.assertEqual(rows[2], ["tool-b", "ok", "10", "20"])


if __name__ == "__main__":
    unittest.main()

