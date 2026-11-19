"""Kiểm luật B trên delivery tự tạo, không cần dữ liệu hay đáp án riêng."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validator"))
import validate


class MetadataPanopticTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.delivery = Path(self.tmp.name) / "delivery"
        self.delivery.mkdir()
        # Id dùng cả ba kênh RGB; hai segment có bbox giao nhau nhưng mask rời.
        self.ids = [66051, 66051, 300, 300]
        pixels = bytes(v for sid in self.ids for v in validate.pngutil.segment_rgb(sid))
        validate.pngutil.write_rgb(self.delivery / "mask.png", 2, 2, pixels)
        (self.delivery / "image.jpg").write_bytes(b"fixture image")
        (self.delivery / "label.txt").write_text("0 0.5 0.5 1 1\n", encoding="utf-8")
        self.item = {"image": "image.jpg", "label": "label.txt", "mask": "mask.png"}
        for kind in ("image", "label", "mask"):
            self.item[kind + "_sha256"] = validate.sha256(self.delivery / self.item[kind])
        self.pan = {
            "categories": [{"id": 1, "isthing": 1}, {"id": 2, "isthing": 0}],
            "images": [{"id": 17, "file_name": "opaque_name.jpg", "width": 2, "height": 2}],
            "annotations": [{"image_id": 17, "file_name": "mask.png", "segments_info": [
                {"id": sid, "category_id": 1, "area": 2, "bbox": [0, 0, 2, 2], "iscrowd": 0}
                for sid in (66051, 300)]}],
        }
        self.meta = {"image": "opaque_name", "scene_id": "scene_x", "split": "train",
                     "job_id": "J1", "guideline_version": "v1.2"}
        self.write_json("manifest.json", {"items": {"opaque_name": self.item}})
        self.write_json("panoptic.json", self.pan)
        self.write_json("metadata.json", {"items": [self.meta]})
        (self.delivery / "classes.txt").write_text("0 person\n", encoding="utf-8")
        (self.delivery / "jobs.csv").write_text(
            "job_id,annotator,reviewer,guideline\nJ1,A01,Q01,v1.2\nJ2,A02,Q02,v1.3\n", encoding="utf-8")
        self.ctx = validate.load_delivery(self.delivery)

    def write_json(self, name, value):
        (self.delivery / name).write_text(json.dumps(value), encoding="utf-8")

    def test_clean_cli_and_intersecting_boxes(self):
        out = Path(self.tmp.name) / "rules.json"
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "validator" / "validate.py"),
                        str(self.delivery), "--out", str(out)], check=True, capture_output=True)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"errors": []})

    def test_guideline_uses_own_job(self):
        self.assertFalse(validate.check_guideline_mismatch(self.ctx, "opaque_name", self.item))
        self.ctx["metadata"]["opaque_name"]["job_id"] = "J2"
        self.assertTrue(validate.check_guideline_mismatch(self.ctx, "opaque_name", self.item))

    def test_scene_leak_deduplicated_and_target_is_scene(self):
        for index in range(3):
            self.ctx["metadata"][str(index)] = dict(self.meta, split="val")
        self.assertEqual(validate.check_scene_leak(self.ctx), [{"type": "scene_leak", "target": "scene_x"}])
        self.ctx["metadata"] = {"x": dict(self.meta, split="test"), "y": self.meta}
        self.assertEqual(validate.check_scene_leak(self.ctx), [])

    def test_unknown_category_has_priority_over_overlap(self):
        seg = self.ctx["annotations"]["opaque_name"]["segments_info"][0]
        seg.update(category_id=999, area=4)
        self.assertEqual(validate.rule_errors(self.ctx)[0],
                         [{"type": "invalid_category_id", "target": "opaque_name"}])

    def test_pixel_deficit_one_pixel_and_absent_segment(self):
        seg = self.ctx["annotations"]["opaque_name"]["segments_info"][0]
        seg["area"] = 3
        self.assertEqual(validate.rule_errors(self.ctx)[0],
                         [{"type": "thing_overlap", "target": "opaque_name"}])
        seg.update(id=99999, area=1)
        self.assertTrue(validate.check_thing_overlap(self.ctx, "opaque_name", self.item))

    def test_stuff_ignored_and_crowd_checked(self):
        seg = self.ctx["annotations"]["opaque_name"]["segments_info"][0]
        seg.update(category_id=2, area=100)
        self.assertFalse(validate.check_thing_overlap(self.ctx, "opaque_name", self.item))
        seg.update(category_id=1, iscrowd=1)
        self.assertTrue(validate.check_thing_overlap(self.ctx, "opaque_name", self.item))

    def test_file_error_precedes_panoptic_and_scene_is_independent(self):
        self.ctx["metadata"]["other"] = dict(self.meta, split="val")
        self.ctx["annotations"]["opaque_name"]["segments_info"][0]["area"] = 3
        (self.delivery / "image.jpg").unlink()
        self.assertEqual(validate.rule_errors(self.ctx)[0], [
            {"type": "missing_image", "target": "opaque_name"},
            {"type": "scene_leak", "target": "scene_x"}])


if __name__ == "__main__":
    unittest.main()
