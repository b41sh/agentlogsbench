from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class SummarizeResultsTest(unittest.TestCase):
    def _fixture_payload(self, engine: str) -> dict:
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "tests" / "fixtures" / "results" / f"{engine}.json").read_text(encoding="utf-8")
        )
        payload["dataset_tier"] = "S"
        payload.setdefault("run_metadata", {})
        payload["run_metadata"]["execution_mode"] = "runnable"
        payload["run_metadata"].setdefault("dataset_version", "2026.04-observability-v1-small")
        payload["run_metadata"].setdefault("engine_version", f"{engine}-test")
        payload["run_metadata"].setdefault("config_fingerprint", "cfg-test")
        payload["run_metadata"].setdefault("index_config_fingerprint", "idx-test")
        payload["run_metadata"].setdefault("query_adapter_version", "2")
        payload["run_metadata"].setdefault("run_timestamp", "2026-04-12T00:00:00Z")
        return payload

    def test_summary_preserves_supporting_tier_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            results_dir = temp_root / "results"
            output_dir = temp_root / "summary"
            results_dir.mkdir(parents=True, exist_ok=True)
            (results_dir / "clickhouse.json").write_text(
                json.dumps(self._fixture_payload("clickhouse"), indent=2),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "python3",
                    str(Path(__file__).resolve().parents[1] / "common" / "summarize_results.py"),
                    "--results-dir",
                    str(results_dir),
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
            )

            summary = json.loads((output_dir / "benchmark-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["run_metadata"]["dataset_tier"], "S")
            self.assertEqual(summary["run_metadata"]["engine_runs"][0]["dataset_tier"], "S")
            self.assertEqual(summary["run_metadata"]["engine_runs"][0]["execution_mode"], "runnable")

    def test_summary_preserves_input_edition(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir) / "results"
            output_dir = Path(temp_dir) / "summary"
            results_dir.mkdir(parents=True, exist_ok=True)

            payload = self._fixture_payload("clickhouse")
            payload["edition"] = "wrong-edition"
            (results_dir / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "summarize_results.py"),
                    "--results-dir",
                    str(results_dir),
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
            )

            summary = json.loads((output_dir / "benchmark-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["run_metadata"]["edition"], "wrong-edition")
            self.assertEqual(summary["run_metadata"]["engine_runs"][0]["edition"], "wrong-edition")


if __name__ == "__main__":
    unittest.main()
