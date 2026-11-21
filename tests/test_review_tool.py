import csv
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import review_tool  # noqa: E402


class ReviewCliTest(unittest.TestCase):
    def test_review_records_actual_reviewer_and_note(self):
        candidate = {
            "image": "image_01",
            "type": "bbox_drift",
            "suggested_note": "machine-generated suggestion must not become the review note",
        }
        inputs = [
            "c",
            "Trinh Xuan Toan",
            "The detection box extends beyond the visible bus body.",
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "review_log.csv"
            with patch("builtins.input", side_effect=inputs), redirect_stdout(StringIO()):
                review_tool.run_cli_review([candidate], output)

            with output.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

        self.assertEqual(row["verdict"], "confirmed")
        self.assertIn("Người review: Trinh Xuan Toan.", row["note"])
        self.assertIn("visible bus body", row["note"])
        self.assertNotIn("machine-generated suggestion", row["note"])


if __name__ == "__main__":
    unittest.main()
