"""Synthetic rule tests: no source annotations, private truth or network."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validator"))
import common
import rules_detection
import rules_file
import rules_meta
import validate


class ValidatorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.delivery = self.base / "delivery"
        self.delivery.mkdir()
        (self.delivery / "images").mkdir()
        (self.delivery / "labels").mkdir()
        items, meta, images, annotations = {}, [], [], []
        for i, name in enumerate(("img_0001", "sample-B")):
            content = b"synthetic image bytes"
            (self.delivery / "images" / f"{name}.jpg").write_bytes(content)
            (self.delivery / "labels" / f"{name}.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
            items[name] = {"image": f"images/{name}.jpg", "label": f"labels/{name}.txt",
                           "mask": f"masks/{name}.png", "image_sha256": hashlib.sha256(content).hexdigest()}
            meta.append({"image": name, "scene_id": "scene-test", "split": "train",
                         "job_id": "J01", "guideline_version": "v1.2"})
            images.append({"id": 10 + i, "file_name": f"{name}.jpg", "width": 640, "height": 480})
            annotations.append({"image_id": 10 + i, "segments_info": []})
        for filename, doc in (("manifest.json", {"items": items}), ("metadata.json", {"items": meta}),
                              ("panoptic.json", {"images": images, "annotations": annotations, "categories": []})):
            (self.delivery / filename).write_text(json.dumps(doc), encoding="utf-8")
        (self.delivery / "jobs.csv").write_text("job_id,annotator,reviewer,guideline\nJ01,A01,Q01,v1.2\n", encoding="utf-8")
        (self.delivery / "classes.txt").write_text("\n".join(f"{i} class-{i}" for i in range(80)), encoding="utf-8")

    def boxes(self, lines):
        (self.delivery / "labels/img_0001.txt").write_text(lines, encoding="utf-8")
        return common.load(self.delivery)

    def test_clean_and_opaque_names(self):
        ctx = common.load(self.delivery)
        self.assertEqual(validate.collect_errors(ctx), ([], set()))
        self.assertEqual(ctx["images"]["sample-B"]["id"], 11)
        self.assertEqual(common.yolo_to_pixel(.5, .5, .2, .2, 640, 480), (256, 192, 384, 288))

    def test_missing_image_is_not_wrong_hash(self):
        (self.delivery / "images/img_0001.jpg").unlink()
        self.assertEqual(rules_file.check(common.load(self.delivery)), [{"type": "missing_image", "target": "img_0001"}])

    def test_hash_uses_content(self):
        (self.delivery / "images/img_0001.jpg").write_bytes(b"changed")
        self.assertEqual(rules_file.check(common.load(self.delivery)), [{"type": "wrong_hash", "target": "img_0001"}])

    def test_job_guideline_scene_and_priority(self):
        ctx = common.load(self.delivery)
        ctx["meta"]["img_0001"]["guideline_version"] = "v1.3"
        ctx["meta"]["sample-B"]["split"] = "val"
        (self.delivery / "images/img_0001.jpg").unlink()
        findings, skip = validate.collect_errors(ctx)
        self.assertEqual(findings, [{"type": "missing_image", "target": "img_0001"},
                                    {"type": "scene_leak", "target": "scene-test"}])
        self.assertEqual(skip, {"img_0001"})
        self.assertIn({"type": "guideline_mismatch", "target": "img_0001"}, rules_meta.check(ctx))

    def test_invalid_class(self):
        for value in ("-1", "80", "1.5"):
            with self.subTest(value=value):
                errors = rules_detection.check(self.boxes(f"{value} 0.5 0.5 0.2 0.2\n"))
                self.assertEqual(errors, [{"type": "invalid_class", "target": "img_0001"}])

    def test_bounds_checks_edges_and_tolerance(self):
        for x, expected in (("0.08", True), ("0.095", False), ("0.92", True)):
            with self.subTest(x=x):
                errors = rules_detection.check(self.boxes(f"0 {x} 0.5 0.2 0.2\n"))
                self.assertEqual(bool(errors), expected)
                if errors:
                    self.assertEqual(errors[0]["type"], "bbox_out_of_bounds")

    def test_duplicate_vs_overlapping_objects(self):
        first = "0 0.5 0.5 0.2 0.2\n"
        for second, duplicate in (("0 0.5 0.5 0.2 0.2", True),
                                  ("0 0.503125 0.504166667 0.2 0.2", True),
                                  ("0 0.5 0.5 0.25 0.24", False),
                                  ("1 0.5 0.5 0.2 0.2", False),
                                  ("0 0.52 0.5 0.2 0.2", False)):
            with self.subTest(second=second):
                errors = rules_detection.check(self.boxes(first + second + "\n"))
                self.assertEqual(bool(errors), duplicate)
                if errors:
                    self.assertEqual(errors[0]["type"], "duplicate_box")

    def test_bad_labels_fail_explicitly(self):
        for line in ("0 nan 0.5 0.2 0.2", "0 0.5 0.5"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                self.boxes(line)

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            common.delivery_path(self.delivery, "../outside.txt")

    def test_cli_output_and_read_only_delivery(self):
        before = {p.relative_to(self.delivery): p.read_bytes() for p in self.delivery.rglob("*") if p.is_file()}
        out, candidates = self.base / "output/rules.json", self.base / "output/candidates.json"
        result = subprocess.run([sys.executable, str(ROOT / "validator/validate.py"), str(self.delivery),
                                 "--out", str(out), "--candidates", str(candidates)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(out.read_text()), {"errors": []})
        self.assertEqual(json.loads(candidates.read_text()), [])
        self.assertIn("stub", result.stderr)
        self.assertEqual(before, {p.relative_to(self.delivery): p.read_bytes() for p in self.delivery.rglob("*") if p.is_file()})
        self.assertEqual(validate.main([str(self.delivery), "--out", str(self.delivery / "rules.json")]), 2)


if __name__ == "__main__":
    unittest.main()
