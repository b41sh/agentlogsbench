from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.tooling.edition import validate_edition


class ValidateEditionTest(unittest.TestCase):
    def test_current_edition_validates(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = validate_edition(root)
        self.assertTrue(result["ok"], msg=result)
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
