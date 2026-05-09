from __future__ import annotations

import json
import unittest
from pathlib import Path


class ObservationOnlyContractTest(unittest.TestCase):
    def test_generated_artifacts_do_not_export_raw_call_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        generated_dir = root / "common" / "generated" / "small"

        self.assertFalse((generated_dir / "raw_agent_calls_s.ndjson").exists())

        manifest = json.loads((generated_dir / "manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((generated_dir / "summary.json").read_text(encoding="utf-8"))

        forbidden_manifest_keys = {"raw_call_target", "raw_call_file", "replay_request_id"}
        forbidden_summary_keys = {
            "raw_call_rows",
            "trace_raw_call_distribution",
            "trace_archetype_raw_call_counts",
            "raw_call_type_counts",
        }

        self.assertTrue(forbidden_manifest_keys.isdisjoint(manifest.keys()), msg=manifest)
        self.assertTrue(forbidden_summary_keys.isdisjoint(summary.keys()), msg=summary)

    def test_generated_observations_do_not_expose_raw_call_type(self) -> None:
        root = Path(__file__).resolve().parents[1]
        observation_path = root / "common" / "generated" / "small" / "agent_observations_s.ndjson"

        with observation_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                context = row["payload"].get("context", {})
                self.assertNotIn("raw_call_type", context, msg=row["observation_id"])

    def test_engine_scripts_do_not_default_back_to_raw_call_assets(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script_paths = (
            root / "doris" / "benchmark.sh",
            root / "doris" / "import.sh",
            root / "doris" / "query.sh",
            root / "doris" / "cleanup.sh",
            root / "elastic" / "benchmark.sh",
            root / "elastic" / "import.sh",
            root / "elastic" / "query.sh",
            root / "elastic" / "cleanup.sh",
            root / "opensearch" / "benchmark.sh",
            root / "opensearch" / "import.sh",
            root / "opensearch" / "query.sh",
            root / "opensearch" / "cleanup.sh",
        )
        forbidden_strings = (
            "raw_agent_calls_s.ndjson",
            "agent_call_logs_raw",
            "replay_request_id",
        )

        for path in script_paths:
            content = path.read_text(encoding="utf-8")
            for forbidden in forbidden_strings:
                self.assertNotIn(forbidden, content, msg=f"{path} still contains {forbidden}")


if __name__ == "__main__":
    unittest.main()
