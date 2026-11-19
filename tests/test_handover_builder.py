"""Unit tests for P4 Handover Builder.

Author: Đỗ Anh Hoàng (2A202604061 · @AnhHoangDepTrai)
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from handover.builder import build_handover_v2


class TestHandoverBuilder(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_handover_"))
        self.run_dir = self.temp_dir / "r_test"
        self.delivery_dir = self.run_dir / "delivery"
        self.delivery_dir.mkdir(parents=True)
        (self.delivery_dir / "images").mkdir()
        (self.delivery_dir / "labels").mkdir()

        # release.json
        (self.delivery_dir / "release.json").write_text(
            json.dumps({"release_id": "lab250_mocked", "version": "v1"}),
            encoding="utf-8",
        )

        # classes.txt
        (self.delivery_dir / "classes.txt").write_text(
            "0 person\n1 car\n2 dog\n",
            encoding="utf-8",
        )

        # jobs.csv
        (self.delivery_dir / "jobs.csv").write_text(
            "job_id,annotator,reviewer,guideline\nJ01,A01,Q01,v1.2\n",
            encoding="utf-8",
        )

        # Create 3 images and labels
        items = {}
        metadata_items = []
        for i in range(1, 4):
            stem = f"{i:06d}"
            img_p = self.delivery_dir / "images" / f"{stem}.jpg"
            img_p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            lbl_p = self.delivery_dir / "labels" / f"{stem}.txt"
            lbl_p.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

            items[stem] = {
                "image": f"images/{stem}.jpg",
                "label": f"labels/{stem}.txt",
                "image_sha256": hashlib.sha256(img_p.read_bytes()).hexdigest(),
                "label_sha256": hashlib.sha256(lbl_p.read_bytes()).hexdigest(),
            }
            metadata_items.append({
                "image": stem,
                "scene_id": "scene_001",
                "split": "train",
                "job_id": "J01",
                "guideline_version": "v1.2",
            })

        (self.delivery_dir / "manifest.json").write_text(json.dumps({"items": items}), encoding="utf-8")
        (self.delivery_dir / "metadata.json").write_text(json.dumps({"items": metadata_items}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_handover_rework_partitioning(self):
        # Image 000001 has class_swap error -> must go to rework_queue and not in v2 images
        errors = [
            {"type": "class_swap", "target": "000001"},
        ]
        (self.run_dir / "errors.json").write_text(json.dumps({"errors": errors}), encoding="utf-8")

        v2_dir = build_handover_v2(self.run_dir)
        self.assertTrue(v2_dir.is_dir())

        # Check images in v2
        v2_stems = [p.stem for p in (v2_dir / "images").glob("*.jpg")]
        self.assertNotIn("000001", v2_stems)
        self.assertIn("000002", v2_stems)
        self.assertIn("000003", v2_stems)

        # Check rework_queue.csv
        rework_path = v2_dir / "rework_queue.csv"
        self.assertTrue(rework_path.is_file())
        with rework_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["image"], "000001")
        self.assertEqual(rows[0]["type"], "class_swap")
        self.assertEqual(rows[0]["annotator"], "A01")
        self.assertEqual(rows[0]["reviewer"], "Q01")

        # Check README.txt
        readme_text = (v2_dir / "README.txt").read_text(encoding="utf-8")
        self.assertIn("Release: lab250_mocked_v2", readme_text)
        self.assertIn("Parent: lab250_mocked", readme_text)
        self.assertIn("Số ảnh: 2", readme_text)
        self.assertIn("Số nhãn: 2", readme_text)

        # Check .sha256 file
        sha256_file = v2_dir.with_suffix(".sha256")
        self.assertTrue(sha256_file.is_file())


if __name__ == "__main__":
    unittest.main()
