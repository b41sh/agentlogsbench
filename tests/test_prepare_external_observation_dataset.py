from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.common.prepare_external_observation_dataset import build_dataset


class PrepareExternalObservationDatasetTest(unittest.TestCase):
    def test_build_dataset_writes_metadata_only_manifest_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "agent_observations_0001.ndjson.gz"
            input_path.write_bytes(b"compressed-data-placeholder")

            output_dir = tmp_path / "bundle"
            result = build_dataset(
                [input_path],
                output_dir,
                "public-agentlogs-1m",
                target_rows=1000000,
                input_glob=str(tmp_path / "agent_observations_*.ndjson.gz"),
            )

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertEqual(result["source_file_count"], 1)
            self.assertEqual([Path(item).resolve() for item in manifest["source_files"]], [input_path.resolve()])
            self.assertEqual(manifest["observation_rows"], 1000000)
            self.assertEqual(summary["source_file_count"], 1)
            self.assertEqual(summary["observation_rows"], 1000000)
            self.assertFalse((output_dir / "agent_observations_1m.ndjson").exists())


if __name__ == "__main__":
    unittest.main()
