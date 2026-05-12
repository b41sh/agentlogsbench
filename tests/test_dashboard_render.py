from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


class DashboardRenderTest(unittest.TestCase):
    def test_render_dashboard_writes_clickbench_style_js_payload(self) -> None:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            queries_dir = temp_root / "common" / "queries"
            clickhouse_results_dir = temp_root / "clickhouse" / "results"
            clickhouse_query_results_dir = clickhouse_results_dir / "_query_results"
            postgres_results_dir = temp_root / "postgres" / "results"
            queries_dir.mkdir(parents=True, exist_ok=True)
            clickhouse_results_dir.mkdir(parents=True, exist_ok=True)
            clickhouse_query_results_dir.mkdir(parents=True, exist_ok=True)
            postgres_results_dir.mkdir(parents=True, exist_ok=True)

            (queries_dir / "query-suite.json").write_text(
                json.dumps(
                    {
                        "queries": [
                            {
                                "id": "Q01",
                                "title": "First query",
                                "category": "retrieval",
                                "contract": "First contract",
                                "main_track": True,
                            },
                            {
                                "id": "Q02",
                                "title": "Second query",
                                "category": "analytics",
                                "contract": "Second contract",
                                "main_track": True,
                            },
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (queries_dir / "queries.sql").write_text(
                "-- Q01\nSELECT 1;\n\n-- Q02\nSELECT 2;\n",
                encoding="utf-8",
            )

            (clickhouse_results_dir / "demo.json").write_text(
                json.dumps(
                    {
                        "system": "ClickHouse",
                        "version": "25.1",
                        "os": "Ubuntu",
                        "date": "2026-04-15",
                        "machine": "m6i.8xlarge",
                        "retains_structure": "yes",
                        "tags": ["baseline"],
                        "dataset_size": 1_000_000,
                        "num_loaded_documents": 998_799,
                        "total_size": 2_048,
                        "data_size": 1_536,
                        "index_size": 512,
                        "load_time": 12.345,
                        "result": [
                            [0.1, 0.08, 0.07],
                            [0.2, 0.16, 0.15],
                        ],
                        "artifact_manifest": {
                            "query_results": {
                                "path": "_query_results/_demo.query_results",
                            }
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (clickhouse_query_results_dir / "_demo.query_results").write_text("ok\n", encoding="utf-8")
            (postgres_results_dir / "stale.json").write_text(
                json.dumps(
                    {
                        "system": "PostgreSQL",
                        "machine": "legacy",
                        "dataset_size": 998_799,
                        "result": [[1, 2, 3], [4, 5, 6]],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            output_path = temp_root / "data.generated.js"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "render_dashboard.py"),
                    "--root",
                    str(temp_root),
                    "--output",
                    str(output_path),
                ],
                check=True,
            )

            rendered = output_path.read_text(encoding="utf-8")
            self.assertIn("const queryCatalog =", rendered)
            self.assertIn("const data = [", rendered)
            self.assertIn("ClickHouse", rendered)
            self.assertNotIn("stale.json", rendered)

            query_catalog = json.loads(re.search(r"const queryCatalog = (.*?);\n", rendered, re.S).group(1))
            dataset_sizes = json.loads(re.search(r"const datasetSizes = (.*?);\n", rendered, re.S).group(1))
            results = json.loads(re.search(r"const data = (\[.*?\]);", rendered, re.S).group(1))

            self.assertEqual(len(query_catalog), 2)
            self.assertEqual(dataset_sizes, [{"value": 1_000_000, "label": "1M"}])
            self.assertEqual(len(results), 1)
            self.assertEqual(
                results[0]["source"],
                "https://github.com/velodb/agentlogsbench/blob/main/clickhouse/results/demo.json",
            )
            self.assertEqual(
                results[0]["query_results_source"],
                "https://github.com/velodb/agentlogsbench/blob/main/clickhouse/results/_query_results/_demo.query_results",
            )
            self.assertEqual(results[0]["cluster_size"], 1)
            self.assertEqual(results[0]["proprietary"], "no")
            self.assertEqual(results[0]["hardware"], "cpu")
            self.assertEqual(results[0]["tuned"], "no")
            self.assertEqual(results[0]["tags"], ["baseline"])
            self.assertEqual(query_catalog[0]["sql"], "SELECT 1;")

    def test_render_dashboard_omits_missing_query_results_source(self) -> None:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            queries_dir = temp_root / "common" / "queries"
            postgres_results_dir = temp_root / "postgres" / "results"
            queries_dir.mkdir(parents=True, exist_ok=True)
            postgres_results_dir.mkdir(parents=True, exist_ok=True)

            (queries_dir / "query-suite.json").write_text(
                json.dumps(
                    {
                        "queries": [
                            {
                                "id": "Q01",
                                "title": "First query",
                                "category": "retrieval",
                                "contract": "First contract",
                                "main_track": True,
                            }
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (queries_dir / "queries.sql").write_text("-- Q01\nSELECT 1;\n", encoding="utf-8")

            (postgres_results_dir / "demo.json").write_text(
                json.dumps(
                    {
                        "system": "PostgreSQL",
                        "version": "16",
                        "os": "Ubuntu",
                        "date": "2026-04-15",
                        "machine": "m6i.8xlarge",
                        "dataset_size": 10_000_000,
                        "total_size": 1024,
                        "result": [[0.1, 0.09, 0.08]],
                        "artifact_manifest": {
                            "query_results": {
                                "path": "_query_results/missing.query_results",
                            }
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            output_path = temp_root / "data.generated.js"
            subprocess.run(
                [
                    "python3",
                    str(root / "common" / "render_dashboard.py"),
                    "--root",
                    str(temp_root),
                    "--output",
                    str(output_path),
                ],
                check=True,
            )

            rendered = output_path.read_text(encoding="utf-8")
            results = json.loads(re.search(r"const data = (\[.*?\]);", rendered, re.S).group(1))
            self.assertIsNone(results[0]["query_results_source"])


if __name__ == "__main__":
    unittest.main()
