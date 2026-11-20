"""Synthetic Detection tests. Never read the real delivery or private data.

Run from repository root:
    py -B -X utf8 -m unittest discover -s tests -p test_detection.py -v
"""

import hashlib
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validator.detection import validate_detection


class DetectionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.delivery = Path(self.temporary.name) / "arbitrary_delivery"
        self.delivery.mkdir()
        (self.delivery / "images").mkdir()
        (self.delivery / "labels").mkdir()
        (self.delivery / "classes.txt").write_text("0 person\n7 example class\n", encoding="utf-8")
        self.items = {}
        self.images = []

    def add_image(self, target="000001", label="0 0.5 0.5 0.2 0.2\n", *, width=100, height=100):
        # Raw bytes suffice: this module hashes images, not JPEG decoding.
        content = b"synthetic-image-bytes\x00\xff"
        (self.delivery / "images" / f"{target}.jpg").write_bytes(content)
        (self.delivery / "labels" / f"{target}.txt").write_text(label, encoding="utf-8")
        self.items[target] = {
            "image": f"images/{target}.jpg",
            "label": f"labels/{target}.txt",
            "image_sha256": hashlib.sha256(content).hexdigest(),
        }
        self.images.append({"file_name": f"{target}.jpg", "width": width, "height": height})

    def run_rules(self):
        (self.delivery / "manifest.json").write_text(json.dumps({"items": self.items}), encoding="utf-8")
        (self.delivery / "panoptic.json").write_text(json.dumps({"images": self.images}), encoding="utf-8")
        return validate_detection(self.delivery)

    def expected(self, kind, target="000001"):
        return [{"type": kind, "target": target}]

    def test_valid_existing_image_and_correct_hash(self):
        self.add_image()
        self.assertEqual(self.run_rules(), [])

    def test_missing_image_does_not_stop_other_images(self):
        self.add_image()
        self.add_image("000002", "99 0.5 0.5 0.2 0.2\n")
        (self.delivery / "images/000001.jpg").unlink()
        self.assertEqual(self.run_rules(), [
            {"type": "invalid_class", "target": "000002"},
            {"type": "missing_image", "target": "000001"},
        ])

    def test_wrong_image_hash(self):
        self.add_image()
        (self.delivery / "images/000001.jpg").write_bytes(b"changed")
        self.assertEqual(self.run_rules(), self.expected("wrong_hash"))

    def test_label_hash_is_outside_image_hash_scope(self):
        self.add_image()
        self.items["000001"]["label_sha256"] = "0" * 64
        self.items["000001"]["mask_sha256"] = "0" * 64
        self.assertEqual(self.run_rules(), [])

    def test_classes_are_read_from_file(self):
        self.add_image(label="7 0.5 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_invalid_class(self):
        self.add_image(label="1 0.5 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("invalid_class"))

    def test_negative_class(self):
        self.add_image(label="-1 0.5 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("invalid_class"))

    def test_fractional_class_is_not_truncated(self):
        self.add_image(label="0.5 0.5 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("invalid_class"))

    def test_integral_decimal_class(self):
        self.add_image(label="7.0 0.5 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_bbox_exceeds_left(self):
        self.add_image(label="0 0.05 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("bbox_out_of_bounds"))

    def test_bbox_exceeds_right(self):
        self.add_image(label="0 0.98 0.5 0.1 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("bbox_out_of_bounds"))

    def test_bbox_exceeds_top(self):
        self.add_image(label="0 0.5 0.05 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("bbox_out_of_bounds"))

    def test_bbox_exceeds_bottom(self):
        self.add_image(label="0 0.5 0.95 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("bbox_out_of_bounds"))

    def test_bbox_touching_all_edges(self):
        self.add_image(label="0 0.5 0.5 1 1\n")
        self.assertEqual(self.run_rules(), [])

    def test_bbox_floating_point_noise(self):
        self.add_image(label="0 0.0999999999 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_bbox_small_real_overflow(self):
        # Keep the original small-overflow check above the new 1e-6 tolerance.
        self.add_image(label="0 0.099998 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("bbox_out_of_bounds"))

    def test_bbox_rounding_below_tolerance_on_each_edge(self):
        for x, y in ((0.0999995, 0.5), (0.9000005, 0.5), (0.5, 0.0999995), (0.5, 0.9000005)):
            with self.subTest(x=x, y=y):
                self.add_image(label=f"0 {x} {y} 0.2 0.2\n")
                self.assertEqual(self.run_rules(), [])

    def test_bbox_rounding_equal_to_tolerance_on_each_edge(self):
        for x, y in ((0.099999, 0.5), (0.900001, 0.5), (0.5, 0.099999), (0.5, 0.900001)):
            with self.subTest(x=x, y=y):
                self.add_image(label=f"0 {x} {y} 0.2 0.2\n")
                self.assertEqual(self.run_rules(), [])

    def test_bbox_just_above_tolerance_on_each_edge(self):
        for x, y in ((0.0999989999, 0.5), (0.9000010001, 0.5), (0.5, 0.0999989999), (0.5, 0.9000010001)):
            with self.subTest(x=x, y=y):
                self.add_image(label=f"0 {x} {y} 0.2 0.2\n")
                self.assertEqual(self.run_rules(), self.expected("bbox_out_of_bounds"))

    def test_nonfinite_or_nonpositive_bbox(self):
        for row in ("0 nan 0.5 0.2 0.2", "0 0.5 inf 0.2 0.2", "0 0.5 0.5 0 0.2", "0 0.5 0.5 -0.2 0.2"):
            with self.subTest(row=row):
                self.add_image(label=row + "\n")
                self.assertEqual(self.run_rules(), self.expected("bbox_out_of_bounds"))

    def test_duplicate_identical(self):
        self.add_image(label="0 0.5 0.5 0.2 0.2\n" * 2)
        self.assertEqual(self.run_rules(), self.expected("duplicate_box"))

    def test_duplicate_one_pixel(self):
        self.add_image(label="0 0.5 0.5 0.2 0.2\n0 0.51 0.51 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("duplicate_box"))

    def test_duplicate_two_pixels_inclusive_per_axis(self):
        self.add_image(label="0 0.5 0.5 0.2 0.2\n0 0.52 0.52 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("duplicate_box"))

    def test_duplicate_real_rounding_near_left_edge(self):
        # Regression fixture copied from observed delivery labels; no real data read.
        with (self.delivery / "classes.txt").open("a", encoding="utf-8") as classes:
            classes.write("21 example animal\n")
        self.add_image(
            "000000020247",
            "21 0.068203 0.306050 0.133187 0.546061\n"
            "21 0.066593 0.308238 0.133187 0.546061\n",
            width=640, height=457,
        )
        self.assertEqual(self.run_rules(), self.expected("duplicate_box", "000000020247"))

    def test_duplicate_at_bbox_tolerance_limit(self):
        self.add_image(label="0 0.099999 0.5 0.2 0.2\n0 0.109999 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("duplicate_box"))

    def test_near_edge_different_classes_are_not_duplicates(self):
        self.add_image(label="0 0.0999995 0.5 0.2 0.2\n7 0.1099995 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_near_edge_different_sizes_are_not_duplicates(self):
        self.add_image(label="0 0.0999995 0.5 0.2 0.2\n0 0.1099995 0.5 0.18 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_near_edge_above_two_pixels_is_not_duplicate(self):
        self.add_image(label="0 0.0999995 0.5 0.2 0.2\n0 0.1200005 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_out_of_bounds_boxes_still_excluded_from_duplicates(self):
        self.add_image(label="0 0.099998 0.5 0.2 0.2\n" * 2)
        self.assertEqual(self.run_rules(), self.expected("bbox_out_of_bounds"))

    def test_duplicate_above_two_pixels_is_rejected(self):
        self.add_image(label="0 0.5 0.5 0.2 0.2\n0 0.52001 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_dimensions_scale_both_axes(self):
        self.add_image(width=1000, height=200, label="0 0.5 0.5 0.2 0.2\n0 0.502 0.51 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("duplicate_box"))

    def test_same_normalized_offset_is_farther_on_large_image(self):
        self.add_image(width=1000, label="0 0.5 0.5 0.2 0.2\n0 0.51 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_same_box_different_class(self):
        self.add_image(label="0 0.5 0.5 0.2 0.2\n7 0.5 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_same_center_different_size(self):
        self.add_image(label="0 0.5 0.5 0.2 0.2\n0 0.5 0.5 0.21 0.2\n")
        self.assertEqual(self.run_rules(), [])

    def test_overlapping_distinct_objects(self):
        self.add_image(label="0 0.5 0.5 0.4 0.4\n0 0.55 0.5 0.4 0.4\n")
        self.assertEqual(self.run_rules(), [])

    def test_target_preserves_leading_zeros(self):
        self.add_image("000000000007", "99 0.5 0.5 0.2 0.2\n")
        self.assertEqual(self.run_rules(), self.expected("invalid_class", "000000000007"))

    def test_results_are_unique_and_stable(self):
        self.add_image("000002", "99 0.5 0.5 0.2 0.2\n" * 3)
        self.add_image("000001", "0 0.5 0.5 0.2 0.2\n" * 3)
        first = self.run_rules()
        self.assertEqual(first, self.run_rules())
        self.assertEqual(len(first), 2)
        self.assertEqual(first, sorted(first, key=lambda e: (e["type"], e["target"])))

    def test_empty_labels_and_blank_lines(self):
        self.add_image(label="\n  \n")
        self.assertEqual(self.run_rules(), [])

    def test_missing_label_warns_and_continues(self):
        self.add_image()
        self.add_image("000002", "99 0.5 0.5 0.2 0.2\n")
        (self.delivery / "labels/000001.txt").unlink()
        with self.assertWarnsRegex(RuntimeWarning, "cannot read label"):
            self.assertEqual(self.run_rules(), self.expected("invalid_class", "000002"))

    def test_malformed_row_warns_and_continues(self):
        self.add_image(label="0 broken\n0 x 0.5 0.2 0.2\n99 0.5 0.5 0.2 0.2\n")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertEqual(self.run_rules(), self.expected("invalid_class"))
        self.assertEqual(len(caught), 2)

    def test_missing_dimensions_warns_without_inventing_errors(self):
        self.add_image(label="0 0.5 0.5 0.2 0.2\n" * 2)
        self.images = []
        with self.assertWarnsRegex(RuntimeWarning, "no image dimensions"):
            self.assertEqual(self.run_rules(), [])

    def test_manifest_path_outside_delivery_is_not_read(self):
        self.add_image()
        self.items["000001"]["image"] = "../outside.jpg"
        with self.assertWarnsRegex(RuntimeWarning, "Path escapes delivery"):
            self.assertEqual(self.run_rules(), [])

    def test_input_files_unchanged(self):
        self.add_image(label="0 0.5 0.5 0.2 0.2\n" * 2)
        self.run_rules()
        before = {p.relative_to(self.delivery): p.read_bytes() for p in self.delivery.rglob("*") if p.is_file()}
        validate_detection(self.delivery)
        after = {p.relative_to(self.delivery): p.read_bytes() for p in self.delivery.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
