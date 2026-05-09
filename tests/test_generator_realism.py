from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.tooling.generator import generate_small_dataset, write_dataset
from agentlogsbench.tooling.validate_generated import validate_generated_dataset


class GeneratorRealismTest(unittest.TestCase):
    def test_checked_in_fixture_passes_current_validator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        validation = validate_generated_dataset(root / "common" / "generated" / "small")
        self.assertTrue(validation["ok"], msg=validation)

    def test_repo_seed_generation_passes_realism_validator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        seed_dir = root / "common" / "seeds"

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            dataset = generate_small_dataset(
                output_dir=output_dir,
                seed_dir=seed_dir,
                generation_target=48,
                trace_target=20,
                seed=20260411,
            )
            write_dataset(dataset, output_dir)

            validation = validate_generated_dataset(output_dir)
            self.assertTrue(validation["ok"], msg=validation)

    def test_repo_seed_generation_limits_text_reuse_and_keeps_replay_consistent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        seed_dir = root / "common" / "seeds"

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            dataset = generate_small_dataset(
                output_dir=output_dir,
                seed_dir=seed_dir,
                generation_target=48,
                trace_target=20,
                seed=20260411,
            )

            summary = dataset.summary
            self.assertLessEqual(summary["text_reuse"]["duplicate_ratio"], 0.18, msg=summary["text_reuse"])
            self.assertLessEqual(summary["text_reuse"]["max_reuse_count"], 3, msg=summary["text_reuse"])
            self.assertLessEqual(summary["text_reuse"]["max_line_reuse_count"], 32, msg=summary["text_reuse"])
            self.assertLessEqual(summary["text_reuse"]["reused_line_count"], 12, msg=summary["text_reuse"])
            self.assertGreaterEqual(len(summary["tool_name_distribution"]), 8, msg=summary["tool_name_distribution"])
            self.assertGreaterEqual(len(summary["source_distribution"]), 3, msg=summary["source_distribution"])

            count_token_requests = [
                row for row in dataset.requests if row["request_path"] == "/v1/messages/count_tokens"
            ]
            self.assertTrue(count_token_requests)
            self.assertTrue(
                all(not row["v"]["request"]["body"].get("tools") for row in count_token_requests),
                msg=count_token_requests[0]["v"]["request"]["body"],
            )

            self.assertEqual(
                dataset.accuracy_labels["replay_observation_id"],
                dataset.manifest["replay_observation_id"],
            )
            self.assertTrue(dataset.summary["keyword_injection"]["positive_observation_ids"])
            self.assertEqual(
                dataset.manifest["seed_files"],
                sorted(str(path.relative_to(seed_dir)) for path in seed_dir.rglob("*.json")),
            )


if __name__ == "__main__":
    unittest.main()
