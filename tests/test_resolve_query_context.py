from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.common.resolve_query_context import context_is_complete, resolve_context


class ResolveQueryContextTest(unittest.TestCase):
    def test_context_is_complete_requires_all_fields(self) -> None:
        payload = {
            "tenant": "tenant-a",
            "app": "app-a",
            "trace_id": "trace-a",
            "release_ring": "stable",
            "customer_tier": "pro",
            "traffic_cluster": "cluster-a",
            "request_key": "req-a",
            "workflow_variant": "tool_first",
            "start_date": "2026-04-01",
            "end_date": "2026-04-03",
        }

        self.assertTrue(context_is_complete(payload))
        payload["workflow_variant"] = ""
        self.assertFalse(context_is_complete(payload))

    def test_resolve_context_from_rows(self) -> None:
        rows = [
            {
                "tenant": "tenant-b",
                "app": "app-b",
                "trace_id": "trace-z",
                "biz_date": "2026-04-02",
                "type": "TOOL",
                "status": "error",
                "input": "Unable to open the file",
                "output": "",
                "payload": {
                    "attr": {
                        "release_ring": "canary",
                        "customer_tier": "enterprise",
                        "traffic_cluster": "cluster-b",
                        "request_key": "req-z",
                        "workflow_variant": "fallback_recovery",
                    }
                },
            },
            {
                "tenant": "tenant-a",
                "app": "app-a",
                "trace_id": "trace-a",
                "biz_date": "2026-04-01",
                "type": "TOOL",
                "status": "error",
                "input": "unable to open index",
                "output": "",
                "payload": {
                    "attr": {
                        "release_ring": "stable",
                        "customer_tier": "pro",
                        "traffic_cluster": "cluster-a",
                        "request_key": "req-a",
                        "workflow_variant": "tool_first",
                    }
                },
            },
            {
                "tenant": "tenant-a",
                "app": "app-a",
                "trace_id": "trace-a",
                "biz_date": "2026-04-03",
                "type": "GENERATION",
                "status": "ok",
                "input": "",
                "output": "",
                "payload": {
                    "attr": {
                        "release_ring": "stable",
                        "customer_tier": "pro",
                        "traffic_cluster": "cluster-a",
                        "request_key": "req-a",
                        "workflow_variant": "tool_first",
                    }
                },
            },
        ]

        # Reuse the core reducer without touching the filesystem.
        from agentlogsbench.common.resolve_query_context import iter_rows as original_iter_rows
        from agentlogsbench.common import resolve_query_context as module

        def fake_iter_rows(_files):
            for row in rows:
                yield row

        module.iter_rows = fake_iter_rows
        try:
            context = resolve_context([Path("unused")])
        finally:
            module.iter_rows = original_iter_rows

        self.assertEqual(
            context,
            {
                "tenant": "tenant-a",
                "app": "app-a",
                "trace_id": "trace-a",
                "release_ring": "stable",
                "customer_tier": "pro",
                "traffic_cluster": "cluster-a",
                "request_key": "req-a",
                "workflow_variant": "tool_first",
                "start_date": "2026-04-01",
                "end_date": "2026-04-03",
            },
        )

    def test_resolve_context_rejects_incomplete_context_rows(self) -> None:
        rows = [
            {
                "tenant": "tenant-a",
                "app": "app-a",
                "trace_id": "trace-a",
                "biz_date": "2026-04-01",
                "type": "TOOL",
                "status": "error",
                "input": "unable to open index",
                "output": "",
                "payload": {
                    "attr": {
                        "release_ring": "",
                        "customer_tier": "",
                        "traffic_cluster": "",
                        "request_key": "",
                        "workflow_variant": "",
                    }
                },
            },
            {
                "tenant": "tenant-a",
                "app": "app-a",
                "trace_id": "trace-a",
                "biz_date": "2026-04-03",
                "type": "GENERATION",
                "status": "ok",
                "input": "",
                "output": "",
                "payload": {"attr": {}},
            },
        ]

        from agentlogsbench.common.resolve_query_context import iter_rows as original_iter_rows
        from agentlogsbench.common import resolve_query_context as module

        def fake_iter_rows(_files):
            for row in rows:
                yield row

        module.iter_rows = fake_iter_rows
        try:
            with self.assertRaisesRegex(ValueError, "complete query context"):
                resolve_context([Path("unused")])
        finally:
            module.iter_rows = original_iter_rows

    def test_resolve_context_keeps_phrase_selected_pair_when_error_row_is_incomplete(self) -> None:
        rows = [
            {
                "tenant": "tenant-b",
                "app": "app-b",
                "trace_id": "trace-b1",
                "biz_date": "2026-04-01",
                "type": "GENERATION",
                "status": "ok",
                "input": "",
                "output": "",
                "payload": {
                    "attr": {
                        "release_ring": "stable",
                        "customer_tier": "pro",
                        "traffic_cluster": "cluster-b",
                        "request_key": "req-b",
                        "workflow_variant": "wf-b",
                    }
                },
            },
            {
                "tenant": "tenant-a",
                "app": "app-a",
                "trace_id": "trace-a1",
                "biz_date": "2026-04-02",
                "type": "TOOL",
                "status": "error",
                "input": "unable to open index",
                "output": "",
                "payload": {
                    "attr": {
                        "release_ring": "",
                        "customer_tier": "",
                        "traffic_cluster": "",
                        "request_key": "",
                        "workflow_variant": "",
                    }
                },
            },
            {
                "tenant": "tenant-a",
                "app": "app-a",
                "trace_id": "trace-a1",
                "biz_date": "2026-04-03",
                "type": "GENERATION",
                "status": "ok",
                "input": "",
                "output": "",
                "payload": {
                    "attr": {
                        "release_ring": "canary",
                        "customer_tier": "enterprise",
                        "traffic_cluster": "cluster-a",
                        "request_key": "req-a",
                        "workflow_variant": "wf-a",
                    }
                },
            },
        ]

        from agentlogsbench.common.resolve_query_context import iter_rows as original_iter_rows
        from agentlogsbench.common import resolve_query_context as module

        def fake_iter_rows(_files):
            for row in rows:
                yield row

        module.iter_rows = fake_iter_rows
        try:
            context = resolve_context([Path("unused")])
        finally:
            module.iter_rows = original_iter_rows

        self.assertEqual(
            context,
            {
                "tenant": "tenant-a",
                "app": "app-a",
                "trace_id": "trace-a1",
                "release_ring": "canary",
                "customer_tier": "enterprise",
                "traffic_cluster": "cluster-a",
                "request_key": "req-a",
                "workflow_variant": "wf-a",
                "start_date": "2026-04-01",
                "end_date": "2026-04-03",
            },
        )


if __name__ == "__main__":
    unittest.main()
