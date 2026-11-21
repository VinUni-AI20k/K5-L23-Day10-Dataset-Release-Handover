import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validator"))
import cross_check  # noqa: E402


class GreedyMatchTest(unittest.TestCase):
    def test_disjoint_segment_is_not_consumed_by_zero_iou_pair(self):
        boxes = [{"bbox": (0, 0, 10, 10)}]
        segments = [
            {"bbox": (0, 0, 10, 10)},
            {"bbox": (100, 100, 10, 10)},
        ]

        matches = cross_check.greedy_match_boxes(boxes, segments)

        self.assertEqual(matches, [(1.0, 0, 0)])

    def test_each_box_and_segment_is_matched_at_most_once(self):
        boxes = [
            {"bbox": (0, 0, 10, 10)},
            {"bbox": (5, 0, 10, 10)},
        ]
        segments = [
            {"bbox": (0, 0, 10, 10)},
            {"bbox": (5, 0, 10, 10)},
        ]

        matches = cross_check.greedy_match_boxes(boxes, segments)

        self.assertEqual(len(matches), 2)
        self.assertEqual(len({segment_index for _, segment_index, _ in matches}), 2)
        self.assertEqual(len({box_index for _, _, box_index in matches}), 2)

    def test_instance_merge_checks_all_box_pairs(self):
        boxes = [
            {"bbox": (0, 0, 10, 10)},
            {"bbox": (1, 0, 10, 10)},
            {"bbox": (30, 0, 10, 10)},
        ]

        self.assertTrue(cross_check.has_distinct_box_pair(boxes))


if __name__ == "__main__":
    unittest.main()
