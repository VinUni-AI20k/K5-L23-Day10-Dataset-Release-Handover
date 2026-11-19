import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import qc.crosscheck  # noqa: F401


class CrosscheckStubTest(unittest.TestCase):
    def test_crosscheck_package_importable(self):
        self.assertTrue((ROOT / "qc" / "crosscheck" / "__init__.py").is_file())


if __name__ == "__main__":
    unittest.main()
