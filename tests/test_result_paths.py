from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.tooling.score import iter_result_files


class ResultPathTest(unittest.TestCase):
    def test_iter_result_files_supports_legacy_and_clickbench_style_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            direct = root / "result.json"
            legacy_nested = root / "clickhouse" / "result.json"
            clickbench_default = root / "postgres" / "results" / "result.json"
            clickbench_named = root / "doris" / "results" / "single-file.json"

            direct.write_text("{}", encoding="utf-8")
            legacy_nested.parent.mkdir(parents=True, exist_ok=True)
            legacy_nested.write_text("{}", encoding="utf-8")
            clickbench_default.parent.mkdir(parents=True, exist_ok=True)
            clickbench_default.write_text("{}", encoding="utf-8")
            clickbench_named.parent.mkdir(parents=True, exist_ok=True)
            clickbench_named.write_text("{}", encoding="utf-8")

            discovered = list(iter_result_files(root))

        self.assertEqual(discovered, [direct, legacy_nested, clickbench_named, clickbench_default])


if __name__ == "__main__":
    unittest.main()
