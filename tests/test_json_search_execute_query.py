from __future__ import annotations

import base64
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.elastic import execute_query as elastic_execute_query
from agentlogsbench.opensearch import execute_query as opensearch_execute_query


def _encode_item(query_id: str) -> str:
    payload = {
        "item": {
            "id": query_id,
            "body": {
                "query": {"match_all": {}},
                "aggs": {},
            },
        }
    }
    return base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")


class JsonSearchExecuteQueryTest(unittest.TestCase):
    def _run_main(self, module: object, *, query_id: str, mode: str) -> tuple[int, str]:
        argv = [
            "execute_query.py",
            "--endpoint",
            "http://127.0.0.1:9200",
            "--index",
            "agentlogsbench_agent_observations",
            "--item-b64",
            _encode_item(query_id),
            "--mode",
            mode,
        ]
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout):
            result = module.main()
        return result, stdout.getvalue()

    def test_timed_mode_skips_exact_render_path(self) -> None:
        for module in (elastic_execute_query, opensearch_execute_query):
            with self.subTest(module=module.__name__):
                with mock.patch.object(module, "json_post", return_value=({"hits": {"hits": []}}, 123)) as json_post:
                    with mock.patch.object(module, "exact_payload", side_effect=AssertionError("exact path should not run in timed mode")):
                        result, stdout = self._run_main(module, query_id="Q02", mode="timed")

                self.assertEqual(result, 0)
                self.assertEqual(stdout, "Response time: 0.123 s\n")
                json_post.assert_called_once_with(
                    "http://127.0.0.1:9200",
                    "agentlogsbench_agent_observations",
                    {"query": {"match_all": {}}, "aggs": {}},
                )

    def test_q02_render_mode_uses_raw_search(self) -> None:
        for module in (elastic_execute_query, opensearch_execute_query):
            with self.subTest(module=module.__name__):
                payload = {"aggregations": {"trace_id": {"buckets": []}}}
                with mock.patch.object(module, "json_post", return_value=(payload, 123)) as json_post:
                    with mock.patch.object(module, "exact_payload", side_effect=AssertionError("Q02 render should use the raw search path")):
                        with mock.patch.object(module, "render_elasticsearch_result_section", return_value="rendered\n") as renderer:
                            result, stdout = self._run_main(module, query_id="Q02", mode="render")

                self.assertEqual(result, 0)
                self.assertEqual(stdout, "rendered\n")
                json_post.assert_called_once_with(
                    "http://127.0.0.1:9200",
                    "agentlogsbench_agent_observations",
                    {"query": {"match_all": {}}, "aggs": {}},
                )
                renderer.assert_called_once_with("Q02", payload)

    def test_q13_render_mode_keeps_exact_render_path(self) -> None:
        for module in (elastic_execute_query, opensearch_execute_query):
            with self.subTest(module=module.__name__):
                payload = {
                    "hits": {"total": {"value": 1}},
                    "aggregations": {
                        "traces": {"value": 1},
                        "last_event_time": {"value_as_string": "2026-04-15 12:00:00"},
                    },
                }
                with mock.patch.object(module, "exact_payload", return_value=(payload, 987)) as exact_payload:
                    with mock.patch.object(module, "json_post", side_effect=AssertionError("Q13 render should keep the exact path")):
                        with mock.patch.object(module, "render_elasticsearch_result_section", return_value="rendered\n") as renderer:
                            result, stdout = self._run_main(module, query_id="Q13", mode="render")

                self.assertEqual(result, 0)
                self.assertEqual(stdout, "rendered\n")
                exact_payload.assert_called_once_with(
                    "Q13",
                    "http://127.0.0.1:9200",
                    "agentlogsbench_agent_observations",
                    {"query": {"match_all": {}}, "aggs": {}},
                )
                renderer.assert_called_once_with("Q13", payload)
