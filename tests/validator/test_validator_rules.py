import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validator"))
import validate  # noqa: E402


class ValidatorUnitTest(unittest.TestCase):
    def test_yolo_to_pixels_and_iou(self):
        box = validate.yolo_to_pixels([0.5, 0.5, 0.4, 0.2], 100, 200)
        self.assertAlmostEqual(box[0], 30.0)
        self.assertAlmostEqual(box[1], 80.0)
        self.assertAlmostEqual(box[2], 70.0)
        self.assertAlmostEqual(box[3], 120.0)
        self.assertAlmostEqual(validate.iou(box, box), 1.0)
        self.assertAlmostEqual(validate.iou(box, (0.0, 0.0, 10.0, 10.0)), 0.0)

    def test_read_yolo_valid_and_corrupt_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            lbl = Path(tmp) / "sample.txt"
            lbl.write_text("0 0.5 0.5 0.2 0.2\nbad line\n1 0.1 0.2 0.3\n", encoding="utf-8")
            rows = validate.read_yolo(lbl)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0][0], 0)
            self.assertEqual(rows[1], (None, None))
            self.assertEqual(rows[2], (None, None))


if __name__ == "__main__":
    unittest.main()
