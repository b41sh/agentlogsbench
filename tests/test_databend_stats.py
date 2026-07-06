from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.databend.collect_stats import compute_storage_sizes


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


if __name__ == "__main__":
    unittest.main()
