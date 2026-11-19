"""Small synthetic fixtures, never ground truth or private lab data."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validator.rules import box_outside, delivery_path, duplicate_boxes, validate_rules
from scripts.pngutil import write_rgb


class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "delivery"
        self.root.mkdir()
        for directory in ("images", "labels", "masks"):
            (self.root / directory).mkdir()
        self.items = {}
        self.meta = []
        self.pano = {"categories": [{"id": 1, "isthing": 1}], "images": [], "annotations": []}
        for i, name in enumerate(("img_0001", "other_name")):
            (self.root / f"images/{name}.jpg").write_bytes(b"hash fixture")
            (self.root / f"labels/{name}.txt").write_text("0 0.5 0.5 0.2 0.2\n")
            write_rgb(self.root / f"masks/{name}.png", 10, 10, bytes([1, 0, 0]) * 100)
            self.items[name] = {kind: f"{folder}/{name}.{ext}" for kind, folder, ext in
                                (("image", "images", "jpg"), ("label", "labels", "txt"), ("mask", "masks", "png"))}
            self.meta.append(dict(image=name, scene_id="scene_a", split="train", job_id="J1", guideline_version="v1"))
            self.pano["images"].append(dict(id=i, file_name=f"{name}.jpg", width=10, height=10))
            self.pano["annotations"].append(dict(image_id=i, segments_info=[dict(id=1, category_id=1, area=100)]))
        (self.root / "classes.txt").write_text("0 person\n")
        (self.root / "jobs.csv").write_text("job_id,guideline\nJ1,v1\n")
        self.save()

    def save(self):
        for item in self.items.values():
            for kind in ("image", "label", "mask"):
                path = self.root / item[kind]
                if path.exists():
                    item[f"{kind}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        for name, value in (("manifest.json", {"items": self.items}), ("metadata.json", {"items": self.meta}), ("panoptic.json", self.pano)):
            (self.root / name).write_text(json.dumps(value), encoding="utf-8")

    def check(self, kind=None, target="img_0001"):
        expected = [] if kind is None else [{"type": kind, "target": target}]
        self.assertEqual(validate_rules(self.root), {"errors": expected})

    def test_clean_and_opaque_names(self):
        self.check()

    def test_missing_image_not_wrong_hash(self):
        (self.root / "images/img_0001.jpg").unlink()
        self.check("missing_image")

    def test_hash_each_file_kind(self):
        for kind in ("image", "label", "mask"):
            with self.subTest(kind=kind):
                self.save()
                self.items["img_0001"][f"{kind}_sha256"] = "0" * 64
                (self.root / "manifest.json").write_text(json.dumps({"items": self.items}))
                self.check("wrong_hash")

    def test_invalid_class(self):
        (self.root / "labels/img_0001.txt").write_text("80 0.5 0.5 0.2 0.2\n")
        self.save()
        self.check("invalid_class")

    def test_bounds(self):
        (self.root / "labels/img_0001.txt").write_text("0 0.99 0.5 0.1 0.2\n")
        self.save()
        self.check("bbox_out_of_bounds")

    def test_duplicate(self):
        (self.root / "labels/img_0001.txt").write_text("0 0.5 0.5 0.2 0.2\n0 0.6 0.5 0.2 0.2\n")
        self.save()
        self.check("duplicate_box")

    def test_scene(self):
        self.meta[1]["split"] = "val"
        self.save()
        self.check("scene_leak", "scene_a")

    def test_guideline_uses_job(self):
        self.meta[0]["guideline_version"] = "v2"
        self.save()
        self.check("guideline_mismatch")

    def test_category(self):
        self.pano["annotations"][0]["segments_info"][0]["category_id"] = 999
        self.save()
        self.check("invalid_category_id")

    def test_overlap(self):
        self.pano["annotations"][0]["segments_info"][0]["area"] = 101
        self.save()
        self.check("thing_overlap")

    def test_edges_rounding_and_nonfinite(self):
        self.assertFalse(box_outside((0, 0.05, 0.5, 0.100001, 0.2)))
        self.assertTrue(box_outside((0, float("nan"), 0.5, 0.1, 0.2)))
        self.assertTrue(box_outside((0, 0.5, 0.5, 0, 0.2)))

    def test_natural_overlap_different_size_or_class(self):
        a = (0, 0.5, 0.5, 0.2, 0.2)
        self.assertFalse(duplicate_boxes(a, (0, 0.5, 0.5, 0.21, 0.2), 640, 480))
        self.assertFalse(duplicate_boxes(a, (1, 0.5, 0.5, 0.2, 0.2), 640, 480))
        self.assertTrue(duplicate_boxes(a, (0, 0.5 + 2/640, 0.5, 0.2, 0.2), 640, 480))

    def test_reject_external_path(self):
        with self.assertRaises(ValueError):
            delivery_path(self.root, "../secret.txt")


if __name__ == "__main__":
    unittest.main()
