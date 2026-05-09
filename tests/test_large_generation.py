from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class LargeGenerationTest(unittest.TestCase):
    def test_sharded_generation_and_validation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "medium"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "120",
                    "--traces",
                    "50",
                    "--chunk-generations",
                    "30",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "validate_large_generated_data.py"),
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
            )

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

            self.assertGreaterEqual(len(manifest["observation_files"]), 2)
            self.assertEqual(summary["generation_rows"], 120)
            self.assertEqual(summary["shard_count"], len(manifest["observation_files"]))

    def test_parallel_generation_and_validation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "parallel"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data_parallel.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "120",
                    "--traces",
                    "50",
                    "--chunk-generations",
                    "20",
                    "--workers",
                    "2",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "validate_large_generated_data.py"),
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
            )
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["generation_rows"], 120)
            self.assertEqual(summary["worker_count"], 2)
            self.assertEqual(manifest["worker_count"], 2)

    def test_parallel_generation_with_compressed_shards_and_validation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "parallel-gz"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data_parallel.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "120",
                    "--traces",
                    "50",
                    "--chunk-generations",
                    "20",
                    "--workers",
                    "2",
                    "--compress-shards",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "validate_large_generated_data.py"),
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
            )
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["compression"], "gzip")
            self.assertEqual(manifest["compression"], "gzip")
            self.assertTrue(all(item["path"].endswith(".ndjson.gz") for item in manifest["observation_files"]))
            self.assertTrue(all((output_dir / item["path"]).exists() for item in manifest["observation_files"]))

    def test_large_validator_rejects_cross_shard_duplicate_observation_id(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "parallel"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data_parallel.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "120",
                    "--traces",
                    "50",
                    "--chunk-generations",
                    "20",
                    "--workers",
                    "2",
                ],
                check=True,
            )
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            first_shard = output_dir / manifest["observation_files"][0]["path"]
            later_shard = output_dir / manifest["observation_files"][-1]["path"]
            first_row = json.loads(first_shard.read_text(encoding="utf-8").splitlines()[0])
            lines = later_shard.read_text(encoding="utf-8").splitlines()
            later_row = json.loads(lines[0])
            later_row["observation_id"] = first_row["observation_id"]
            later_row["trace_id"] = first_row["trace_id"]
            lines[0] = json.dumps(later_row, ensure_ascii=False)
            later_shard.write_text("\n".join(lines) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(root / "common" / "validate_large_generated_data.py"),
                    "--output-dir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0, msg=result.stdout)
            self.assertIn("duplicate observation_id", result.stdout)

    def test_large_validator_rejects_missing_parent_and_cross_trace_parent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "parallel"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data_parallel.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "120",
                    "--traces",
                    "50",
                    "--chunk-generations",
                    "20",
                    "--workers",
                    "2",
                ],
                check=True,
            )
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            first_shard = output_dir / manifest["observation_files"][0]["path"]
            later_shard = output_dir / manifest["observation_files"][-1]["path"]
            parent_row = json.loads(first_shard.read_text(encoding="utf-8").splitlines()[0])
            lines = later_shard.read_text(encoding="utf-8").splitlines()
            changed = False
            for index, raw_line in enumerate(lines):
                row = json.loads(raw_line)
                if row.get("parent_observation_id"):
                    row["parent_observation_id"] = parent_row["observation_id"]
                    lines[index] = json.dumps(row, ensure_ascii=False)
                    changed = True
                    break
            self.assertTrue(changed)
            later_shard.write_text("\n".join(lines) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(root / "common" / "validate_large_generated_data.py"),
                    "--output-dir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0, msg=result.stdout)
            self.assertIn("parent/child trace mismatch", result.stdout)

    def test_large_validator_rejects_missing_parent_reference(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "parallel"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data_parallel.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "120",
                    "--traces",
                    "50",
                    "--chunk-generations",
                    "20",
                    "--workers",
                    "2",
                ],
                check=True,
            )
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            later_shard = output_dir / manifest["observation_files"][-1]["path"]
            lines = later_shard.read_text(encoding="utf-8").splitlines()
            changed = False
            for index, raw_line in enumerate(lines):
                row = json.loads(raw_line)
                if row.get("parent_observation_id"):
                    row["parent_observation_id"] = "obs-nonexistent-parent"
                    lines[index] = json.dumps(row, ensure_ascii=False)
                    changed = True
                    break
            self.assertTrue(changed)
            later_shard.write_text("\n".join(lines) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(root / "common" / "validate_large_generated_data.py"),
                    "--output-dir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0, msg=result.stdout)
            self.assertIn("missing parent_observation_id", result.stdout)

    def test_large_generation_honors_trace_target_under_small_trace_budget(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "medium"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "12",
                    "--traces",
                    "2",
                    "--chunk-generations",
                    "3",
                ],
                check=True,
            )
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["trace_target"], 2)
            self.assertEqual(summary["trace_count"], 2)

    def test_large_generation_handles_large_trace_start_without_datetime_overflow(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "large-trace-offset"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "12",
                    "--traces",
                    "4",
                    "--chunk-generations",
                    "3",
                    "--trace-idx-start",
                    "416666660",
                ],
                check=True,
            )
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["trace_count"], 4)

    def test_parallel_generation_is_retry_safe_on_same_output_dir(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "parallel"
            cmd = [
                "python3",
                str(root / "common" / "generate_large_data_parallel.py"),
                "--output-dir",
                str(output_dir),
                "--seed-dir",
                str(root / "common" / "seeds"),
                "--generations",
                "120",
                "--traces",
                "50",
                "--chunk-generations",
                "20",
                "--workers",
                "2",
            ]
            subprocess.run(cmd, check=True)
            subprocess.run(cmd, check=True)

    def test_parallel_generation_preserves_requested_total_shard_count(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "parallel-shards"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "generate_large_data_parallel.py"),
                    "--output-dir",
                    str(output_dir),
                    "--seed-dir",
                    str(root / "common" / "seeds"),
                    "--generations",
                    "100",
                    "--traces",
                    "40",
                    "--chunk-generations",
                    "10",
                    "--workers",
                    "6",
                ],
                check=True,
            )
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["shard_count"], 10)
            self.assertEqual(len(manifest["observation_files"]), 10)


if __name__ == "__main__":
    unittest.main()
