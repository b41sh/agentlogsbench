from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSONBENCH_DATABEND = ROOT / "JSONBench" / "databend"
if str(JSONBENCH_DATABEND) not in sys.path:
    sys.path.insert(0, str(JSONBENCH_DATABEND))

import load_data
import build_result
import run_queries
import stats


class JsonbenchDatabendTest(unittest.TestCase):
    def test_promoted_row_extracts_benchmark_paths_and_keeps_data(self) -> None:
        raw = {
            "kind": "commit",
            "commit": {
                "operation": "create",
                "collection": "app.bsky.feed.post",
            },
            "did": "did:plc:test",
            "time_us": 1700000000123456,
            "extra": {"nested": True},
        }

        row = load_data.promoted_row(raw)

        self.assertEqual(row["kind"], "commit")
        self.assertEqual(row["operation"], "create")
        self.assertEqual(row["collection"], "app.bsky.feed.post")
        self.assertEqual(row["did"], "did:plc:test")
        self.assertEqual(row["time_us"], 1700000000123456)
        self.assertEqual(row["data"], raw)

    def test_write_load_file_handles_gzip_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            source = temp_dir / "file_0001.json.gz"
            target = temp_dir / "prepared.ndjson"
            rows = [
                {"kind": "commit", "commit": {"operation": "create", "collection": "app.bsky.feed.post"}, "did": "u1", "time_us": 1},
                {"kind": "identity", "did": "u2", "time_us": 2},
            ]
            with gzip.open(source, "wt", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            stats = load_data.write_load_file(source, target)
            loaded = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(stats.accepted_rows, 2)
            self.assertEqual(stats.rejected_rows, 0)
            self.assertEqual(loaded[0]["collection"], "app.bsky.feed.post")
            self.assertIsNone(loaded[1]["operation"])
            self.assertEqual(loaded[1]["data"], rows[1])

    def test_write_load_file_skips_invalid_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            source = temp_dir / "file_0001.json"
            target = temp_dir / "prepared.ndjson"
            error_log = temp_dir / "error.log"
            source.write_text(
                json.dumps({"kind": "commit", "did": "u1", "time_us": 1}) + "\n"
                '{"kind":"commit","text":"unterminated}\n'
                + json.dumps({"kind": "identity", "did": "u2", "time_us": 2}) + "\n",
                encoding="utf-8",
            )

            prepare_stats = load_data.write_load_file(source, target, error_log)
            loaded = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(prepare_stats.accepted_rows, 2)
            self.assertEqual(prepare_stats.rejected_rows, 1)
            self.assertEqual(len(loaded), 2)
            self.assertIn("Skipped invalid JSON row", error_log.read_text(encoding="utf-8"))

    def test_storage_stats_do_not_double_count_index_breakdown(self) -> None:
        values = (199, 1116, 4221, 894, None, 2779, None, 548)

        data_size, index_size = stats.compute_storage_sizes(values)

        self.assertEqual(data_size, 1116)
        self.assertEqual(index_size, 4221)

    def test_load_queries_reads_one_statement_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            path = Path(temp_dir_raw) / "queries.sql"
            path.write_text(
                "-- comment\n"
                "\n"
                "SELECT 1;\n"
                "SELECT 2\n",
                encoding="utf-8",
            )

            self.assertEqual(run_queries.load_queries(path), ["SELECT 1", "SELECT 2"])

    def test_parse_runtime_matrix_reads_jsonbench_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            path = Path(temp_dir_raw) / "runtime"
            path.write_text(
                "[0.1,0.2,0.3],\n"
                "[1,2,3],\n"
                "[4.5,5.5,6.5],\n"
                "[7,8,9],\n"
                "[10,11,12],\n",
                encoding="utf-8",
            )

            matrix = build_result.parse_runtime_matrix(path)

            self.assertEqual(len(matrix), 5)
            self.assertEqual(matrix[0], [0.1, 0.2, 0.3])
            self.assertEqual(matrix[-1], [10.0, 11.0, 12.0])

    def test_output_prefix_name_removes_legacy_leading_underscore(self) -> None:
        self.assertEqual(build_result.output_prefix_name("_m6i.8xlarge"), "m6i.8xlarge")
        self.assertEqual(build_result.output_prefix_name("local"), "local")

    def test_build_result_main_writes_jsonbench_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            runtime = temp_dir / "runtime"
            runtime.write_text(
                "[0.1,0.2,0.3],\n"
                "[1,2,3],\n"
                "[4,5,6],\n"
                "[7,8,9],\n"
                "[10,11,12],\n",
                encoding="utf-8",
            )
            count = temp_dir / "count"
            total_size = temp_dir / "total_size"
            data_size = temp_dir / "data_size"
            index_size = temp_dir / "index_size"
            count.write_text("1000000\n", encoding="utf-8")
            total_size.write_text("2048\n", encoding="utf-8")
            data_size.write_text("1536\n", encoding="utf-8")
            index_size.write_text("512\n", encoding="utf-8")
            results = temp_dir / "results"

            old_argv = sys.argv
            try:
                sys.argv = [
                    "build_result.py",
                    "--size",
                    "1",
                    "--output-prefix",
                    "_machine",
                    "--count-file",
                    str(count),
                    "--total-size-file",
                    str(total_size),
                    "--data-size-file",
                    str(data_size),
                    "--index-size-file",
                    str(index_size),
                    "--runtime-file",
                    str(runtime),
                    "--results-dir",
                    str(results),
                    "--version",
                    "test-version",
                    "--machine",
                    "test-machine",
                    "--os",
                    "test-os",
                    "--date",
                    "2026-07-02",
                ]
                self.assertEqual(build_result.main(), 0)
            finally:
                sys.argv = old_argv

            payload = json.loads((results / "machine_bluesky_1m.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["system"], "Databend")
            self.assertEqual(payload["version"], "test-version")
            self.assertEqual(payload["dataset_size"], 1_000_000)
            self.assertEqual(payload["num_loaded_documents"], 1_000_000)
            self.assertEqual(payload["total_size"], 2048)
            self.assertEqual(payload["result"][0], [0.1, 0.2, 0.3])


if __name__ == "__main__":
    unittest.main()
