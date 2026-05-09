from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.tooling.paths import query_contracts_path
from agentlogsbench.tooling.run_artifacts import validate_run_artifacts


class ValidateRunArtifactsTest(unittest.TestCase):
    def test_fixture_results_have_required_metadata(self) -> None:
        results_dir = Path(__file__).resolve().parent / "fixtures" / "results"
        result = validate_run_artifacts(results_dir)
        self.assertTrue(result["ok"], msg=result)
        self.assertEqual(result["errors"], [])

    def test_runnable_results_have_required_contract_checks(self) -> None:
        fixture_dir = Path(__file__).resolve().parent / "fixtures" / "results"
        contracts = json.loads(query_contracts_path(ROOT / "agentlogsbench").read_text(encoding="utf-8"))["contracts"]
        payload = json.loads((fixture_dir / "clickhouse.json").read_text(encoding="utf-8"))
        payload["dataset_tier"] = "S"
        payload["run_metadata"]["execution_mode"] = "runnable"
        for item in payload["query_results"]:
            verification = item["contract_verification"]
            contract = contracts[item["query_id"]]
            verification["observed_fields"] = contract["assertions"]["must_include_fields"]
            verification["row_count"] = contract.get("expected_row_count", contract.get("minimum_row_count", 0))
            verification["result_fingerprint"] = contract.get("expected_result_fingerprints", {}).get(
                "clickhouse",
                "pending-fixture-baseline",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            (results_dir / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            result = validate_run_artifacts(results_dir)
            self.assertTrue(result["ok"], msg=result)
            self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
