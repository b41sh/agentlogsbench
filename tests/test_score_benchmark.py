from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.tooling.edition import load_json
from agentlogsbench.tooling.score import load_and_score, score_results


class ScoreBenchmarkTest(unittest.TestCase):
    def test_fixture_results_are_not_eligible_for_main_leaderboard(self) -> None:
        root = Path(__file__).resolve().parents[1]
        edition = load_json(root / "common" / "config" / "edition.json")
        query_ids = edition["main_track"]["query_ids"]
        scored = load_and_score(root / "tests" / "fixtures" / "results", query_ids)

        self.assertEqual(scored["main_leaderboard"], [])
        self.assertEqual(
            sorted(item["engine"] for item in scored["appendix"]),
            ["clickhouse", "doris", "elastic", "opensearch", "postgres"],
        )
        for item in scored["appendix"]:
            self.assertEqual(item["status"], "non_runnable")

    def test_supporting_tier_does_not_affect_fastest_by_query(self) -> None:
        query_ids = ["Q01"]
        m_result = {
            "engine": "m_engine",
            "edition": "2026.04-observability-v1",
            "dataset_tier": "M",
            "run_protocol": {"warmup_runs": 1, "measured_runs": 5, "timeout_seconds": 900},
            "run_metadata": {"execution_mode": "runnable"},
            "query_results": [{"query_id": "Q01", "status": "ok", "latency_ms_runs": [100, 100, 100, 100, 100]}],
            "secondary_metrics": {}
        }
        s_result = {
            "engine": "s_engine",
            "edition": "2026.04-observability-v1",
            "dataset_tier": "S",
            "run_protocol": {"warmup_runs": 1, "measured_runs": 5, "timeout_seconds": 900},
            "run_metadata": {"execution_mode": "runnable"},
            "query_results": [{"query_id": "Q01", "status": "ok", "latency_ms_runs": [10, 10, 10, 10, 10]}],
            "secondary_metrics": {}
        }

        scored = score_results([m_result, s_result], query_ids)
        self.assertEqual(scored["fastest_by_query"]["Q01"], 100.0)
        self.assertEqual(scored["main_leaderboard"][0]["engine"], "m_engine")
        self.assertEqual(scored["appendix"][0]["engine"], "s_engine")

    def test_runnable_m_results_can_reach_main_leaderboard(self) -> None:
        query_ids = ["Q01"]
        runnable = {
            "engine": "runnable_engine",
            "edition": "2026.04-observability-v1",
            "dataset_tier": "M",
            "run_protocol": {"warmup_runs": 1, "measured_runs": 5, "timeout_seconds": 900},
            "run_metadata": {"execution_mode": "runnable"},
            "query_results": [{"query_id": "Q01", "status": "ok", "latency_ms_runs": [42, 42, 42, 42, 42]}],
            "secondary_metrics": {},
        }

        scored = score_results([runnable], query_ids)
        self.assertEqual([item["engine"] for item in scored["main_leaderboard"]], ["runnable_engine"])
        self.assertEqual(scored["appendix"], [])


if __name__ == "__main__":
    unittest.main()
