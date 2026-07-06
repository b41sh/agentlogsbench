from __future__ import annotations

import sys
import unittest
from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.databend.collect_stats import compute_storage_sizes


IMPORT_SPEC = util.spec_from_file_location("agentlogsbench_databend_import", Path(__file__).resolve().parents[1] / "databend" / "import.py")
assert IMPORT_SPEC is not None
databend_import = util.module_from_spec(IMPORT_SPEC)
assert IMPORT_SPEC.loader is not None
IMPORT_SPEC.loader.exec_module(databend_import)

RUN_QUERIES_SPEC = util.spec_from_file_location("agentlogsbench_databend_run_queries", Path(__file__).resolve().parents[1] / "databend" / "run_queries.py")
assert RUN_QUERIES_SPEC is not None
databend_run_queries = util.module_from_spec(RUN_QUERIES_SPEC)
assert RUN_QUERIES_SPEC.loader is not None
RUN_QUERIES_SPEC.loader.exec_module(databend_run_queries)


class FakeConn:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def exec(self, statement: str) -> None:
        self.statements.append(statement)


class DatabendStatsTest(unittest.TestCase):
    def test_storage_stats_do_not_double_count_index_breakdown(self) -> None:
        values = (
            2,
            199,
            1116,
            4221,
            894,
            None,
            2779,
            None,
            548,
        )

        data_size, index_size = compute_storage_sizes(values)

        self.assertEqual(data_size, 1116)
        self.assertEqual(index_size, 4221)

    def test_storage_stats_falls_back_to_component_sum_when_total_index_missing(self) -> None:
        values = (
            2,
            199,
            None,
            None,
            894,
            None,
            2779,
            None,
            548,
        )

        data_size, index_size = compute_storage_sizes(values)

        self.assertEqual(data_size, 199)
        self.assertEqual(index_size, 4221)

    def test_recluster_table_runs_final_recluster(self) -> None:
        conn = FakeConn()

        databend_import.recluster_table(conn, "agent_observations")

        self.assertEqual(conn.statements, ["ALTER TABLE agent_observations RECLUSTER FINAL"])

    def test_query_session_enables_virtual_columns(self) -> None:
        conn = FakeConn()

        databend_run_queries.configure_session(conn)

        self.assertEqual(conn.statements, ["SET enable_experimental_virtual_column=1"])


if __name__ == "__main__":
    unittest.main()
