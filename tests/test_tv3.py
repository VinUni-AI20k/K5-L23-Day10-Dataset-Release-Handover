"""Synthetic tests: no COCO annotations, no private truth, no network."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validator"))

from metadata import validate_metadata  # noqa: E402
from panoptic import validate_panoptic  # noqa: E402
from pngutil import segment_rgb, write_rgb  # noqa: E402


class TV3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.delivery = Path(self.temp.name) / "delivery"
        (self.delivery / "masks").mkdir(parents=True)
        self.thing_id = 0x010203  # Requires decoding all RGB channels.
        self.stuff_id = 0x040506
        ids = [self.thing_id] * 3 + [self.stuff_id, 0, 0]
        pixels = bytes(channel for sid in ids for channel in segment_rgb(sid))
        write_rgb(self.delivery / "masks" / "mask_alpha.png", 3, 2, pixels)
        self.panoptic = {
            "categories": [
                {"id": 7, "name": "test_object", "isthing": 1},
                {"id": 99, "name": "test_ground", "isthing": 0},
            ],
            "images": [{"id": 42, "file_name": "img_alpha.jpg"}],
            "annotations": [{
                "image_id": 42,
                "file_name": "mask_alpha.png",
                "segments_info": [
                    {"id": self.thing_id, "category_id": 7, "area": 3, "iscrowd": 0},
                    {"id": self.stuff_id, "category_id": 99, "area": 1, "iscrowd": 0},
                ],
            }],
        }
        self.metadata = {"items": [
            {"image": "img_alpha", "scene_id": "scene_A", "split": "train", "job_id": "J-old", "guideline_version": "v1.2"},
            {"image": "img_beta", "scene_id": "scene_A", "split": "train", "job_id": "J-old", "guideline_version": "v1.2"},
            {"image": "img_gamma", "scene_id": "scene_B", "split": "val", "job_id": "J-new", "guideline_version": "v1.3"},
        ]}
        with (self.delivery / "jobs.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["job_id", "annotator", "reviewer", "guideline"])
            writer.writeheader()
            writer.writerows([
                {"job_id": "J-old", "annotator": "A01", "reviewer": "Q01", "guideline": "v1.2"},
                {"job_id": "J-new", "annotator": "A02", "reviewer": "Q02", "guideline": "v1.3"},
            ])
        self.save()

    def save(self):
        for name, doc in [("panoptic.json", self.panoptic), ("metadata.json", self.metadata)]:
            (self.delivery / name).write_text(json.dumps(doc), encoding="utf-8")

    def test_clean_fixture_has_no_findings(self):
        self.assertEqual(validate_metadata(self.delivery), [])
        self.assertEqual(validate_panoptic(self.delivery), [])

    def test_invalid_category_is_image_target_not_mask_or_numeric_id(self):
        self.panoptic["annotations"][0]["segments_info"][0]["category_id"] = 123456
        self.save()
        self.assertEqual(validate_panoptic(self.delivery), [
            {"type": "invalid_category_id", "target": "img_alpha"}
        ])

    def test_one_pixel_area_deficit_is_overlap(self):
        self.panoptic["annotations"][0]["segments_info"][0]["area"] = 4
        self.save()
        self.assertEqual(validate_panoptic(self.delivery), [
            {"type": "thing_overlap", "target": "img_alpha"}
        ])

    def test_smaller_declared_area_is_not_this_directional_rule(self):
        self.panoptic["annotations"][0]["segments_info"][0]["area"] = 2
        self.save()
        self.assertEqual(validate_panoptic(self.delivery), [])

    def test_stuff_area_is_not_thing_overlap(self):
        self.panoptic["annotations"][0]["segments_info"][1]["area"] = 100
        self.save()
        self.assertEqual(validate_panoptic(self.delivery), [])

    def test_crowd_does_not_disable_an_exact_thing_area_rule(self):
        segment = self.panoptic["annotations"][0]["segments_info"][0]
        segment["iscrowd"] = 1
        segment["area"] = 4
        self.save()
        self.assertEqual(validate_panoptic(self.delivery), [
            {"type": "thing_overlap", "target": "img_alpha"}
        ])

    def test_multiple_bad_segments_deduplicate_to_one_image_type(self):
        for segment in self.panoptic["annotations"][0]["segments_info"]:
            segment["category_id"] = -999
        self.save()
        self.assertEqual(validate_panoptic(self.delivery), [
            {"type": "invalid_category_id", "target": "img_alpha"}
        ])

    def test_scene_leak_targets_scene_once(self):
        self.metadata["items"][1]["split"] = "val"
        self.save()
        self.assertEqual(validate_metadata(self.delivery), [
            {"type": "scene_leak", "target": "scene_A"}
        ])

    def test_guideline_is_compared_with_own_job(self):
        self.metadata["items"][0]["guideline_version"] = "v1.3"
        self.save()
        self.assertEqual(validate_metadata(self.delivery), [
            {"type": "guideline_mismatch", "target": "img_alpha"}
        ])

    def test_different_jobs_can_use_different_valid_guidelines(self):
        self.assertEqual(validate_metadata(self.delivery), [])

    def test_unknown_job_is_diagnostic_not_a_fabricated_finding(self):
        self.metadata["items"][0]["job_id"] = "not-a-job"
        self.save()
        with self.assertRaisesRegex(ValueError, "Unknown job"):
            validate_metadata(self.delivery)

    def test_missing_mask_is_not_silently_treated_as_clean(self):
        (self.delivery / "masks" / "mask_alpha.png").unlink()
        with self.assertRaises(FileNotFoundError):
            validate_panoptic(self.delivery)

    def test_mask_cannot_escape_delivery(self):
        self.panoptic["annotations"][0]["file_name"] = "../../outside.png"
        self.save()
        with self.assertRaisesRegex(ValueError, "outside delivery"):
            validate_panoptic(self.delivery)

    def test_validators_leave_all_input_bytes_unchanged(self):
        before = {p.relative_to(self.delivery): p.read_bytes() for p in self.delivery.rglob("*") if p.is_file()}
        validate_metadata(self.delivery)
        validate_panoptic(self.delivery)
        after = {p.relative_to(self.delivery): p.read_bytes() for p in self.delivery.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
