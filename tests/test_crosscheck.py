"""Isolated M3 geometry, matching, coverage and candidate tests with temporary fixtures."""

import json
import math
import random
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validator.crosscheck import (  # noqa: E402
    CandidateConfig, candidates_from_matches, generate_candidates,
    PixelBox, box_iou, load_class_maps, load_delivery_boxes, match_delivery_boxes,
    match_image_boxes, measure_mask_pixels, panoptic_to_pixel, yolo_to_pixel,
)
from scripts.pngutil import segment_rgb, write_rgb


class PixelConversionTest(unittest.TestCase):
    def test_rectangular_image_uses_distinct_width_and_height(self):
        box = yolo_to_pixel((0.5, 0.25, 0.4, 0.2), 640, 480)
        for actual, expected in zip(box, (192, 72, 448, 168)):
            self.assertAlmostEqual(actual, expected)

    def test_fractional_edges_and_out_of_bounds_are_preserved(self):
        fractional = yolo_to_pixel((0.5, 0.5, 0.5, 0.5), 101, 51)
        self.assertEqual(fractional, PixelBox(25.25, 12.75, 75.75, 38.25))
        crossing = yolo_to_pixel((0.0, 1.0, 0.2, 0.2), 100, 200)
        self.assertAlmostEqual(crossing.left, -10)
        self.assertAlmostEqual(crossing.bottom, 220)

    def test_panoptic_and_mask_pixels_use_the_same_edge_convention(self):
        box = panoptic_to_pixel((10, 20, 3, 2))
        self.assertEqual(box, PixelBox(10, 20, 13, 22))
        self.assertTrue(box.contains_pixel(10, 20))
        self.assertTrue(box.contains_pixel(12, 21))
        self.assertFalse(box.contains_pixel(13, 21))
        self.assertFalse(box.contains_pixel(12, 22))
        self.assertFalse(PixelBox(0.75, 0, 2, 1).contains_pixel(0, 0))

    def test_invalid_geometry_is_rejected(self):
        for box in ((0.5, 0.5, 0, 0.2), (0, 0, -1, 1),
                    (math.nan, 0, 1, 1), (0, 0, math.inf, 1), (1, 2, 3)):
            with self.subTest(box=box):
                with self.assertRaises((TypeError, ValueError)):
                    yolo_to_pixel(box, 100, 200)
                with self.assertRaises((TypeError, ValueError)):
                    panoptic_to_pixel(box)
        for dimensions in ((0, 200), (100, -1), (10.5, 20), (True, 20), (math.inf, 20)):
            with self.subTest(dimensions=dimensions):
                with self.assertRaises((TypeError, ValueError)):
                    yolo_to_pixel((0.5, 0.5, 1, 1), *dimensions)


class DeliveryConversionTest(unittest.TestCase):
    def make_delivery(self, root):
        delivery = Path(root) / "delivery"
        (delivery / "labels").mkdir(parents=True)
        images = [
            {"id": 1, "file_name": "wide.jpg", "width": 640, "height": 480},
            {"id": 2, "file_name": "small.jpg", "width": 100, "height": 200},
            {"id": 3, "file_name": "missing.jpg", "width": 50, "height": 50},
            {"id": 4, "file_name": "bad_size.jpg", "width": 0, "height": 50},
        ]
        annotations = [{"image_id": 1, "segments_info": [
            {"id": 99, "category_id": 7, "iscrowd": 0, "bbox": [10, 20, 30, 40]},
            {"id": 100, "category_id": 7, "bbox": [10, 20, -1, 40]},
        ]}]
        (delivery / "panoptic.json").write_text(
            json.dumps({"images": images, "annotations": annotations}), encoding="utf-8"
        )
        (delivery / "labels" / "wide.txt").write_text(
            "7 0.5 0.5 0.5 0.5\n\nmalformed\n7 nan 0.5 0.5 0.5\n7 0.2 0.3 0.1 0.1\n",
            encoding="utf-8",
        )
        (delivery / "labels" / "small.txt").write_text(
            "999 0.5 0.5 0.5 0.5\n", encoding="utf-8"
        )
        return delivery

    def test_loader_keeps_valid_data_and_reports_bad_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            result = load_delivery_boxes(self.make_delivery(temp))
        by_name = {image["image"]: image for image in result["images"]}
        self.assertEqual(set(by_name), {"wide", "small", "missing"})
        self.assertEqual(by_name["wide"]["detection_boxes"][0]["bbox"],
                         PixelBox(160, 120, 480, 360))
        self.assertEqual(by_name["small"]["detection_boxes"][0]["bbox"],
                         PixelBox(25, 50, 75, 150))
        # Class-rule decisions belong to M2; conversion preserves integer IDs.
        self.assertEqual(by_name["small"]["detection_boxes"][0]["class_id"], 999)
        self.assertEqual([box["line_number"] for box in by_name["wide"]["detection_boxes"]], [1, 5])
        self.assertEqual(by_name["wide"]["panoptic_boxes"][0]["bbox"], PixelBox(10, 20, 40, 60))
        self.assertEqual(len(result["issues"]), 5)

    def test_missing_and_malformed_panoptic_json_report_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for content in (None, "not JSON", "[]", '{"images": null}'):
                with self.subTest(content=content):
                    if content is not None:
                        (root / "panoptic.json").write_text(content, encoding="utf-8")
                    result = load_delivery_boxes(root)
                    self.assertEqual(result["images"], [])
                    self.assertEqual(len(result["issues"]), 1)

    def test_cli_outputs_json_without_modifying_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            delivery = self.make_delivery(temp)
            before = {p.relative_to(delivery): p.read_bytes() for p in delivery.rglob("*") if p.is_file()}
            output = Path(temp) / "boxes_pixel.json"
            process = subprocess.run(
                [sys.executable, "-B", str(ROOT / "validator" / "crosscheck.py"),
                 str(delivery), "--out", str(output)], capture_output=True, text=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["coordinate_format"],
                             "left,top,right,bottom")
            after = {p.relative_to(delivery): p.read_bytes() for p in delivery.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            blocked = subprocess.run(
                [sys.executable, "-B", str(ROOT / "validator" / "crosscheck.py"),
                 str(delivery), "--out", str(delivery / "panoptic.json")],
                capture_output=True, text=True,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertEqual((delivery / "panoptic.json").read_bytes(), before[Path("panoptic.json")])


class BoxMatchingTest(unittest.TestCase):
    def setUp(self):
        self.names = {0: "person", 2: "car"}
        self.categories = {
            1: {"name": "person", "isthing": 1},
            3: {"name": "car", "isthing": 1},
            100: {"name": "road", "isthing": 0},
        }

    def image(self, detections, segments):
        return {
            "image": "sample",
            "detection_boxes": [
                {"class_id": cls, "line_number": i + 1, "bbox": box}
                for i, (cls, box) in enumerate(detections)
            ],
            "panoptic_boxes": [
                {"segment_id": i + 10, "category_id": cls, "iscrowd": crowd, "bbox": box}
                for i, (cls, crowd, box) in enumerate(segments)
            ],
        }

    def test_iou_uses_continuous_edges_and_handles_nonoverlap(self):
        self.assertAlmostEqual(box_iou((0, 0, 10, 10), (5, 0, 15, 10)), 1 / 3)
        self.assertEqual(box_iou((0, 0, 10, 10), (10, 0, 20, 10)), 0)
        self.assertEqual(box_iou((0, 0, 0, 0), (0, 0, 0, 0)), 0)
        self.assertEqual(box_iou((0.25, 0.25, 0.75, 0.75), (0.25, 0.25, 0.75, 0.75)), 1)
        with self.assertRaises(ValueError):
            box_iou((10, 0, 0, 10), (0, 0, 10, 10))

    def test_class_names_match_even_when_numeric_ids_differ(self):
        image = self.image([(0, (0, 0, 10, 10))], [(1, 0, (0, 0, 10, 10))])
        match = match_image_boxes(image, self.names, self.categories)["matches"][0]
        self.assertNotEqual(match["class_id"], match["category_id"])
        self.assertTrue(match["same_class"])
        self.assertEqual(match["detection_class_name"], "person")

    def test_position_wins_before_class_comparison(self):
        image = self.image([(2, (0, 0, 10, 10))], [
            (1, 0, (0, 0, 10, 10)), (3, 0, (8, 0, 18, 10)),
        ])
        result = match_image_boxes(image, self.names, self.categories)
        self.assertEqual(result["matches"][0]["segment_index"], 0)
        self.assertFalse(result["matches"][0]["same_class"])
        self.assertEqual(result["unmatched_segments"], [1])

    def test_stuff_and_crowd_cannot_hide_a_thing_match(self):
        image = self.image([(0, (0, 0, 10, 10))], [
            (100, 0, (0, 0, 10, 10)), (1, 1, (0, 0, 10, 10)),
            (1, 0, (0, 0, 9, 10)), (3, 0, (20, 20, 30, 30)),
        ])
        result = match_image_boxes(image, self.names, self.categories)
        self.assertEqual(result["matches"][0]["segment_index"], 2)
        self.assertEqual([item["reason"] for item in result["excluded_segments"]], ["stuff", "crowd"])
        self.assertEqual(result["unmatched_segments"], [3])

    def test_many_boxes_can_match_one_segment_for_later_merge_checks(self):
        image = self.image(
            [(0, (0, 0, 10, 10)), (0, (10, 0, 20, 10))],
            [(1, 0, (0, 0, 20, 10))],
        )
        result = match_image_boxes(image, self.names, self.categories)
        self.assertEqual([m["segment_index"] for m in result["matches"]], [0, 0])
        self.assertEqual(result["unmatched_detections"], [])
        self.assertEqual(result["unmatched_segments"], [])

    def test_threshold_unmatched_items_and_ties_are_deterministic(self):
        image = self.image(
            [(0, (0, 0, 10, 10)), (0, (50, 50, 60, 60))],
            [(1, 0, (0, 0, 5, 10)), (3, 0, (0, 0, 5, 10))],
        )
        result = match_image_boxes(image, self.names, self.categories, min_iou=0.5)
        self.assertEqual(result["matches"][0]["segment_index"], 0)
        self.assertEqual(result["unmatched_detections"], [1])
        strict = match_image_boxes(image, self.names, self.categories, min_iou=0.6)
        self.assertEqual(strict["matches"], [])
        self.assertEqual(strict["unmatched_detections"], [0, 1])
        self.assertEqual(strict["unmatched_segments"], [0, 1])
        for threshold in (-0.1, 1.1, math.nan, math.inf):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                match_image_boxes(image, self.names, self.categories, threshold)

    def test_unknown_class_and_category_do_not_stop_valid_matches(self):
        image = self.image(
            [(999, (0, 0, 10, 10)), (0, (0, 0, 10, 10))],
            [(999, 0, (0, 0, 10, 10)), (1, 0, (0, 0, 10, 10))],
        )
        result = match_image_boxes(image, self.names, self.categories)
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["detection_index"], 1)
        self.assertEqual(len(result["issues"]), 2)
        self.assertEqual(result["unmatched_detections"], [])

    def test_class_map_loader_preserves_names_with_spaces_and_reports_bad_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "classes.txt").write_text(
                "0 person\n9 traffic light\nbroken\n0 duplicate\n", encoding="utf-8"
            )
            (root / "panoptic.json").write_text(json.dumps({"categories": [
                {"id": 1, "name": "person", "isthing": 1},
                {"id": 10, "name": "traffic light", "isthing": 1},
                {"id": 100, "name": "road", "isthing": 0},
                {"id": 101, "name": "unknown flag"},
            ]}), encoding="utf-8")
            names, categories, issues = load_class_maps(root)
        self.assertEqual(names[9], "traffic light")
        self.assertEqual(names[0], "person")
        self.assertEqual(categories[10]["name"], "traffic light")
        self.assertEqual(categories[100]["isthing"], 0)
        self.assertEqual(len(issues), 3)

    def test_delivery_matching_and_cli_use_only_the_supplied_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "delivery"
            (root / "labels").mkdir(parents=True)
            (root / "classes.txt").write_text("0 person\n", encoding="utf-8")
            (root / "labels" / "img_0001.txt").write_text("0 0.5 0.5 0.5 0.5\n", encoding="utf-8")
            (root / "panoptic.json").write_text(json.dumps({
                "categories": [{"id": 1, "name": "person", "isthing": 1}],
                "images": [{"id": 987, "file_name": "img_0001.jpg", "width": 200, "height": 100}],
                "annotations": [{"image_id": 987, "segments_info": [
                    {"id": 555, "category_id": 1, "bbox": [50, 25, 100, 50]},
                ]}],
            }), encoding="utf-8")
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            result = match_delivery_boxes(root)
            self.assertEqual(result["issues"], [])
            self.assertEqual(result["images"][0]["matching"]["matches"][0]["iou"], 1)
            output = Path(temp) / "matches.json"
            process = subprocess.run(
                [sys.executable, "-B", str(ROOT / "validator" / "crosscheck.py"),
                 str(root), "--match", "--out", str(output)], capture_output=True, text=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), json.loads(json.dumps(result)))
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)


class MaskCoverageTest(unittest.TestCase):
    def rgb(self, ids):
        return bytes(channel for sid in ids for channel in segment_rgb(sid))

    def make_delivery(self, temp):
        root = Path(temp) / "delivery"
        (root / "labels").mkdir(parents=True)
        (root / "masks").mkdir()
        (root / "classes.txt").write_text("0 person\n2 car\n", encoding="utf-8")
        (root / "labels" / "opaque_image.txt").write_text(
            "0 0.166666666667 0.5 0.333333333333 1\n"
            "0 0.833333333333 0.5 0.333333333333 1\n"
            "0 0.5 0.25 0.333333333333 0.5\n", encoding="utf-8",
        )
        data = {
            "images": [{"id": 888, "file_name": "opaque_image.jpg", "width": 6, "height": 2}],
            "categories": [{"id": 1, "name": "person", "isthing": 1},
                           {"id": 100, "name": "road", "isthing": 0}],
            "annotations": [{"image_id": 888, "file_name": "opaque_mask.png", "segments_info": [
                {"id": 70000, "category_id": 1, "bbox": [0, 0, 6, 2], "area": 999},
                {"id": 131329, "category_id": 100, "bbox": [2, 1, 2, 1], "area": 2},
            ]}],
        }
        (root / "panoptic.json").write_text(json.dumps(data), encoding="utf-8")
        write_rgb(root / "masks" / "opaque_mask.png", 6, 2, self.rgb([
            70000, 70000, 0, 0, 70000, 70000,
            70000, 70000, 131329, 131329, 70000, 70000,
        ]))
        return root

    def test_actual_pixels_multichannel_ids_and_fractional_edges(self):
        ids = [0, 70000, 70000, 0, 70000, 70000, 131329, 131329, 0, 70000, 131329, 0]
        counts = measure_mask_pixels(4, 3, self.rgb(ids), [
            (1, 0, 3, 3), (-5, 1, 1, 4), (1.5, 0, 2.5, 1), (0, 0, 4, 3),
        ])
        self.assertEqual(counts["segment_pixels"], {70000: 5, 131329: 3})
        self.assertEqual(counts["background_pixels"], 4)
        self.assertEqual(counts["inside_pixels_by_box"], [
            {70000: 4, 131329: 2}, {70000: 1}, {70000: 1}, {70000: 5, 131329: 3},
        ])

    def test_run_accumulation_matches_independent_pixel_center_enumeration(self):
        rng = random.Random(42)
        for case in range(12):
            width, height = rng.randint(1, 8), rng.randint(1, 6)
            ids = [rng.choice([0, 70000, 131329]) for _ in range(width * height)]
            boxes = []
            for _ in range(5):
                x1, x2 = sorted([rng.uniform(-1, width + 1), rng.uniform(-1, width + 1)])
                y1, y2 = sorted([rng.uniform(-1, height + 1), rng.uniform(-1, height + 1)])
                boxes.append(PixelBox(x1, y1, x2, y2))
            counts = measure_mask_pixels(width, height, self.rgb(ids), boxes)
            expected_totals, expected_inside = {}, [{} for _ in boxes]
            for y in range(height):
                for x in range(width):
                    sid = ids[y * width + x]
                    if not sid:
                        continue
                    expected_totals[sid] = expected_totals.get(sid, 0) + 1
                    for index, box in enumerate(boxes):
                        if box.contains_pixel(x, y):
                            expected_inside[index][sid] = expected_inside[index].get(sid, 0) + 1
            with self.subTest(case=case):
                self.assertEqual(counts["segment_pixels"], expected_totals)
                self.assertEqual(counts["inside_pixels_by_box"], expected_inside)

    def test_coverage_uses_actual_mask_not_declared_area_or_bbox_area(self):
        with tempfile.TemporaryDirectory() as temp:
            result = match_delivery_boxes(self.make_delivery(temp), include_coverage=True)
        image = result["images"][0]
        self.assertEqual(result["issues"], [])
        self.assertEqual(image["mask_file"], "opaque_mask.png")
        self.assertEqual(image["mask_coverage"]["background_pixels"], 2)
        self.assertEqual(len(image["mask_coverage"]["segments"]), 1)  # Stuff is excluded.
        segment = image["mask_coverage"]["segments"][0]
        self.assertEqual(segment["actual_pixels"], 8)  # Declared area is 999; bbox area is 12.
        self.assertEqual(segment["same_class_box_indices"], [0, 1])
        pairs = image["matching"]["matches"]
        self.assertEqual([p["inside_pixels"] for p in pairs], [4, 4, 0])
        self.assertEqual([p["outside_pixels"] for p in pairs], [4, 4, 8])
        self.assertEqual([p["coverage"] for p in pairs], [0.5, 0.5, 0.0])
        self.assertEqual([p["coverage_percent"] for p in pairs], [50.0, 50.0, 0.0])

    def test_nonprimary_box_overlap_is_preserved_for_merge_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp)
            data = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
            data["categories"][1] = {"id": 100, "name": "car", "isthing": 1}
            # Deliberately make this bbox win the spatial match for the left box.
            data["annotations"][0]["segments_info"][1]["bbox"] = [0, 0, 2, 2]
            (root / "panoptic.json").write_text(json.dumps(data), encoding="utf-8")
            result = match_delivery_boxes(root, include_coverage=True)
        image = result["images"][0]
        self.assertEqual(image["matching"]["matches"][0]["segment_index"], 1)
        person = image["mask_coverage"]["segments"][0]
        left = next(box for box in person["box_coverages"] if box["detection_index"] == 0)
        self.assertFalse(left["matched"])
        self.assertTrue(left["same_class"])
        self.assertEqual(left["coverage_percent"], 50.0)

    def test_empty_segment_reports_null_coverage_without_dividing_by_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp)
            write_rgb(root / "masks" / "opaque_mask.png", 6, 2, bytes(6 * 2 * 3))
            result = match_delivery_boxes(root, include_coverage=True)
        image = result["images"][0]
        self.assertEqual(image["mask_coverage"]["status"], "partial")
        self.assertEqual(image["mask_coverage"]["segments"][0]["actual_pixels"], 0)
        self.assertEqual(len(result["issues"]), 1)
        for pair in image["matching"]["matches"]:
            self.assertIsNone(pair["coverage"])
            self.assertEqual(pair["segment_pixels"], 0)

    def test_unreadable_or_misaligned_masks_have_unavailable_coverage(self):
        for failure in ("missing", "corrupt", "dimensions", "no_filename", "outside_path"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = self.make_delivery(temp)
                mask = root / "masks" / "opaque_mask.png"
                if failure == "missing":
                    mask.unlink()
                elif failure == "corrupt":
                    mask.write_bytes(b"not a PNG")
                elif failure == "dimensions":
                    write_rgb(mask, 1, 1, bytes(3))
                else:
                    data = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
                    if failure == "no_filename":
                        del data["annotations"][0]["file_name"]
                    else:
                        data["annotations"][0]["file_name"] = "../../outside.png"
                    (root / "panoptic.json").write_text(json.dumps(data), encoding="utf-8")
                result = match_delivery_boxes(root, include_coverage=True)
                image = result["images"][0]
                self.assertEqual(image["mask_coverage"]["status"], "unavailable")
                self.assertEqual(len(result["issues"]), 1)
                for pair in image["matching"]["matches"]:
                    self.assertIsNone(pair["coverage"])
                    self.assertIsNone(pair["segment_pixels"])

    def test_pixel_buffer_validation_and_masks_without_detections(self):
        with self.assertRaises(ValueError):
            measure_mask_pixels(2, 2, bytes(3), [])
        counts = measure_mask_pixels(2, 1, self.rgb([0, 70000]), [])
        self.assertEqual(counts["segment_pixels"], {70000: 1})
        self.assertEqual(counts["inside_pixels_by_box"], [])

    def test_coverage_cli_implies_matching_and_preserves_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            output = Path(temp) / "coverage.json"
            process = subprocess.run(
                [sys.executable, "-B", str(ROOT / "validator" / "crosscheck.py"),
                 str(root), "--coverage", "--out", str(output)], capture_output=True, text=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["images"][0]["matching"]["matches"][0]["coverage_percent"], 50.0)
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)


class CandidateGenerationTest(unittest.TestCase):
    def setUp(self):
        self.config = CandidateConfig(min_segment_pixels=1, min_segment_fraction=0.0)

    def make_delivery(self, temp, cases):
        root = Path(temp) / "delivery"
        (root / "labels").mkdir(parents=True)
        (root / "masks").mkdir()
        (root / "classes.txt").write_text("0 person\n2 car\n", encoding="utf-8")
        data = {
            "images": [], "annotations": [],
            "categories": [{"id": 1, "name": "person", "isthing": 1},
                           {"id": 3, "name": "car", "isthing": 1},
                           {"id": 100, "name": "road", "isthing": 0}],
        }
        for index, case in enumerate(cases):
            name = case.get("name", f"img_case_{index}")
            width, height = case.get("width", 10), case.get("height", 2)
            segments = case.get("segments", [
                {"id": 11, "category_id": 1, "bbox": [0, 0, width, height], "area": 99999},
            ])
            data["images"].append({"id": index + 888, "file_name": f"{name}.jpg",
                                   "width": width, "height": height})
            data["annotations"].append({"image_id": index + 888, "file_name": f"{name}.png",
                                        "segments_info": segments})
            lines = []
            for class_id, (left, top, right, bottom) in case.get("detections", [(0, (0, 0, width, height))]):
                values = ((left + right) / (2 * width), (top + bottom) / (2 * height),
                          (right - left) / width, (bottom - top) / height)
                lines.extend([str(class_id) + " " + " ".join(f"{value:.17g}" for value in values), ""])
            if not case.get("missing_labels"):
                (root / "labels" / f"{name}.txt").write_text("\n".join(lines), encoding="utf-8")
            ids = case.get("pixels", [segments[0]["id"]] * (width * height))
            pixels = bytes(channel for sid in ids for channel in segment_rgb(sid))
            write_rgb(root / "masks" / f"{name}.png", width, height, pixels)
        (root / "panoptic.json").write_text(json.dumps(data), encoding="utf-8")
        return root

    def drift_case(self, **extra):
        return {"pixels": [11, *([0] * 8), 11] * 2,
                "detections": [(0, (2, 0, 10, 2))], **extra}

    def test_class_disagreement_keeps_both_pending_alternatives(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp, [{"name": "opaque_name", "detections": [(2, (0, 0, 10, 2))]}])
            result = generate_candidates(root, self.config)
        self.assertEqual({entry["type"] for entry in result["candidates"]}, {"class_swap", "category_swap"})
        self.assertEqual(result["summary"]["candidate_count"], 2)
        self.assertEqual(result["summary"]["review_group_count"], 1)
        self.assertTrue(result["review_required"])
        for entry in result["candidates"]:
            self.assertEqual(entry["target"], "opaque_name")
            self.assertEqual(entry["image"], entry["target"])
            self.assertEqual(entry["status"], "pending_review")
            self.assertEqual(entry["alternative_types"], ["class_swap", "category_swap"])
            self.assertEqual(entry["review_group"], "opaque_name:class_disagreement")
            self.assertNotIn("verdict", entry)
            evidence = entry["evidence"][0]
            self.assertEqual(evidence["detection_class_name"], "car")
            self.assertEqual(evidence["segment_class_name"], "person")
            self.assertEqual((evidence["detection_line"], evidence["segment_id"]), (1, 11))
            self.assertEqual(evidence["iou"], 1.0)
        self.assertNotIn("errors", result)

    def test_deduplication_retains_multiple_object_evidence(self):
        case = {"detections": [(2, (0, 0, 5, 2)), (2, (5, 0, 10, 2))],
                "segments": [{"id": 11, "category_id": 1, "bbox": [0, 0, 5, 2]},
                             {"id": 12, "category_id": 1, "bbox": [5, 0, 5, 2]}],
                "pixels": ([11] * 5 + [12] * 5) * 2}
        with tempfile.TemporaryDirectory() as temp:
            result = generate_candidates(self.make_delivery(temp, [case]), self.config)
        self.assertEqual(len(result["candidates"]), 2)
        keys = {(entry["type"], entry["target"]) for entry in result["candidates"]}
        self.assertEqual(len(keys), 2)
        for entry in result["candidates"]:
            self.assertEqual([e["segment_id"] for e in entry["evidence"]], [11, 12])
            self.assertEqual([e["detection_line"] for e in entry["evidence"]], [1, 3])

    def test_disagreement_requires_position_and_compares_names(self):
        cases = [{"detections": [(2, (0, 0, 5, 2))]}, {}]
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp, cases)
            strict = generate_candidates(root, CandidateConfig(class_min_iou=0.6, min_segment_pixels=1,
                                                               min_segment_fraction=0.0))
            initial = generate_candidates(root, self.config)
        self.assertEqual(strict["candidates"], [])
        self.assertEqual(initial["summary"]["by_type"]["class_swap"], 1)  # IoU exactly 0.5 passes.
        self.assertEqual({entry["target"] for entry in initial["candidates"]}, {"img_case_0"})

    def test_drift_uses_mask_pixels_despite_high_bbox_iou_and_false_declared_area(self):
        with tempfile.TemporaryDirectory() as temp:
            result = generate_candidates(self.make_delivery(temp, [self.drift_case()]), self.config)
        self.assertEqual([entry["type"] for entry in result["candidates"]], ["bbox_drift"])
        evidence = result["candidates"][0]["evidence"][0]
        self.assertAlmostEqual(evidence["iou"], 0.8)
        self.assertEqual(evidence["segment_pixels"], 4)
        self.assertEqual(evidence["inside_pixels"], 2)
        self.assertEqual(evidence["coverage_percent"], 50.0)
        for actual, expected in zip(evidence["detection_bbox"], [2.0, 0.0, 10.0, 2.0]):
            self.assertAlmostEqual(actual, expected)

    def test_missing_requires_actual_significant_non_crowd_thing_pixels(self):
        pixels = []
        for y in range(4):
            pixels.extend([11] * 5 + [12, 13, 14, 15 if y == 0 else 0, 0])
        case = {"height": 4, "detections": [], "pixels": pixels,
                "segments": [{"id": 11, "category_id": 1, "bbox": [0, 0, 5, 4]},
                             {"id": 12, "category_id": 1, "bbox": [5, 0, 1, 4], "area": 99999},
                             {"id": 13, "category_id": 100, "bbox": [6, 0, 1, 4]},
                             {"id": 14, "category_id": 1, "bbox": [7, 0, 1, 4], "iscrowd": 1},
                             {"id": 15, "category_id": 1, "bbox": [8, 0, 1, 1], "area": 99999}]}
        config = CandidateConfig(min_segment_pixels=3, min_segment_fraction=0.25)
        with tempfile.TemporaryDirectory() as temp:
            result = generate_candidates(self.make_delivery(temp, [case]), config)
        self.assertEqual(result["issues"], [])
        self.assertEqual([entry["type"] for entry in result["candidates"]], ["missing_box"])
        evidence = result["candidates"][0]["evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["segment_id"], 11)
        self.assertEqual(evidence[0]["segment_pixels"], 20)
        self.assertEqual(evidence[0]["segment_fraction"], 0.5)
        self.assertEqual(evidence[0]["nearby_detections"], [])

    def test_nonprimary_covering_box_prevents_spurious_missing_candidate(self):
        case = {"segments": [{"id": 11, "category_id": 1, "bbox": [0, 0, 10, 2]},
                             {"id": 12, "category_id": 3, "bbox": [0, 0, 5, 2]}],
                "pixels": ([12] * 5 + [11] * 5) * 2}
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp, [case])
            measured = match_delivery_boxes(root, include_coverage=True)
            self.assertEqual(measured["images"][0]["matching"]["unmatched_segments"], [1])
            result = candidates_from_matches(measured, self.config)
        self.assertEqual(result["candidates"], [])

    def test_merge_retains_two_distinct_boxes_without_redundant_drift(self):
        case = {"detections": [(0, (0, 0, 5, 2)), (0, (5, 0, 10, 2))]}
        with tempfile.TemporaryDirectory() as temp:
            result = generate_candidates(self.make_delivery(temp, [case]), self.config)
        self.assertEqual([entry["type"] for entry in result["candidates"]], ["instance_merge"])
        evidence = result["candidates"][0]["evidence"][0]
        self.assertEqual(evidence["same_class_box_count"], 2)
        self.assertEqual([box["coverage_percent"] for box in evidence["detections"]], [50.0, 50.0])
        self.assertEqual([box["detection_line"] for box in evidence["detections"]], [1, 3])
        self.assertEqual(evidence["distinct_box_pairs"], [{"detection_indices": [0, 1], "box_iou": 0.0}])

    def test_duplicate_nested_incidental_or_other_class_boxes_do_not_imply_merge(self):
        cases = [
            {"detections": [(0, (0, 0, 5, 2)), (0, (0, 0, 5, 2))]},
            {"detections": [(0, (0, 0, 10, 2)), (0, (2, 0, 4, 2))]},
            {"detections": [(0, (0, 0, 9, 2)), (0, (9, 0, 10, 2))]},
            {"detections": [(0, (0, 0, 5, 2)), (2, (5, 0, 10, 2))]},
        ]
        with tempfile.TemporaryDirectory() as temp:
            result = generate_candidates(self.make_delivery(temp, cases), self.config)
        self.assertEqual(result["summary"]["by_type"]["instance_merge"], 0)

    def test_merge_uses_nonprimary_pixel_overlap(self):
        case = {"width": 6, "detections": [(0, (0, 0, 2, 2)), (0, (4, 0, 6, 2))],
                "segments": [{"id": 70000, "category_id": 1, "bbox": [0, 0, 6, 2]},
                             {"id": 131329, "category_id": 3, "bbox": [0, 0, 2, 2]}],
                "pixels": [70000, 70000, 0, 0, 70000, 70000,
                           70000, 70000, 131329, 131329, 70000, 70000]}
        with tempfile.TemporaryDirectory() as temp:
            result = generate_candidates(self.make_delivery(temp, [case]), self.config)
        entry = next(entry for entry in result["candidates"] if entry["type"] == "instance_merge")
        boxes = entry["evidence"][0]["detections"]
        self.assertEqual([box["detection_index"] for box in boxes], [0, 1])
        self.assertEqual([box["primary_match"] for box in boxes], [False, True])

    def test_missing_corrupt_misaligned_or_empty_masks_do_not_invent_pixel_candidates(self):
        for failure in ("missing", "corrupt", "dimensions", "empty"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = self.make_delivery(temp, [self.drift_case()])
                mask = root / "masks" / "img_case_0.png"
                if failure == "missing":
                    mask.unlink()
                elif failure == "corrupt":
                    mask.write_bytes(b"bad PNG")
                elif failure == "dimensions":
                    write_rgb(mask, 1, 1, bytes(3))
                else:
                    write_rgb(mask, 10, 2, bytes(60))
                result = generate_candidates(root, self.config)
                self.assertEqual(result["candidates"], [])
                self.assertGreater(len(result["issues"]), 0)

    def test_class_alternatives_still_work_when_mask_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp, [{"detections": [(2, (0, 0, 10, 2))]}])
            (root / "masks" / "img_case_0.png").unlink()
            result = generate_candidates(root, self.config)
        self.assertEqual({entry["type"] for entry in result["candidates"]}, {"class_swap", "category_swap"})
        self.assertTrue(all(entry["evidence"][0]["coverage"] is None for entry in result["candidates"]))

    def test_invalid_detection_input_or_background_id_does_not_create_semantic_candidates(self):
        cases = [{"detections": [(999, (0, 0, 10, 2))]}, {"missing_labels": True},
                 {"detections": [(2, (0, 0, 10, 2))],
                  "segments": [{"id": 0, "category_id": 1, "bbox": [0, 0, 10, 2]}]}]
        with tempfile.TemporaryDirectory() as temp:
            result = generate_candidates(self.make_delivery(temp, cases), self.config)
        self.assertEqual(result["candidates"], [])
        self.assertGreaterEqual(len(result["issues"]), 3)

    def test_threshold_validation_and_measurement_api_requirements(self):
        for field in ("min_iou", "class_min_iou", "drift_max_coverage", "min_segment_fraction",
                      "missing_min_coverage", "merge_min_coverage", "merge_max_box_iou"):
            for value in (-0.1, 1.1, math.nan, math.inf, True):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    CandidateConfig(**{field: value})
            CandidateConfig(**{field: 0.0})
            CandidateConfig(**{field: 1.0})
        for value in (0, -1, 1.5, True):
            with self.subTest(pixels=value), self.assertRaises(ValueError):
                CandidateConfig(min_segment_pixels=value)
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp, [{}])
            with self.assertRaises(ValueError):
                candidates_from_matches(match_delivery_boxes(root), self.config)
            with self.assertRaises(ValueError):
                candidates_from_matches(match_delivery_boxes(root, include_coverage=True),
                                        CandidateConfig(min_iou=0.1))

    def test_cli_covers_all_signs_reuses_api_and_preserves_delivery(self):
        cases = [{"name": "img_class", "detections": [(2, (0, 0, 10, 2))]},
                 self.drift_case(name="img_drift"), {"name": "img_missing", "detections": []},
                 {"name": "img_merge", "detections": [(0, (0, 0, 5, 2)), (0, (5, 0, 10, 2))]}]
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_delivery(temp, cases)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            output = Path(temp) / "candidates.json"
            command = [sys.executable, "-B", str(ROOT / "validator" / "crosscheck.py"), str(root),
                       "--candidates", "--min-segment-pixels", "1", "--min-segment-fraction", "0", "--out"]
            process = subprocess.run([*command, str(output)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            actual = json.loads(output.read_text(encoding="utf-8"))
            expected = generate_candidates(root, self.config)
            self.assertEqual(actual, expected)
            self.assertEqual(actual["summary"]["candidate_count"], 5)
            self.assertEqual(actual["summary"]["candidate_image_count"], 4)
            self.assertEqual(actual["summary"]["review_group_count"], 4)
            self.assertEqual(set(actual["summary"]["by_type"].values()), {1})
            self.assertEqual(set(actual["summary"]["by_sign"].values()), {1})
            self.assertEqual(expected, candidates_from_matches(match_delivery_boxes(root, include_coverage=True), self.config))
            blocked = subprocess.run([*command, str(root / "panoptic.json")], capture_output=True, text=True)
            self.assertNotEqual(blocked.returncode, 0)
            invalid_output = Path(temp) / "invalid.json"
            invalid = subprocess.run([*command, str(invalid_output), "--drift-max-coverage", "nan"],
                                     capture_output=True, text=True)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertFalse(invalid_output.exists())
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
