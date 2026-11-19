"""Unit tests for P3 Release Gate and Lineage tracking.

Author: Đỗ Anh Hoàng (2A202604061 · @AnhHoangDepTrai)
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from release.gate import RELEASE_THRESHOLD, evaluate_release_gate


class TestReleaseGate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_gate_"))
        self.run_dir = self.temp_dir / "r_test"
        self.delivery_dir = self.run_dir / "delivery"
        self.delivery_dir.mkdir(parents=True)

        # Release info
        (self.delivery_dir / "release.json").write_text(
            json.dumps({"release_id": "lab250_test123", "version": "v1"}),
            encoding="utf-8",
        )

        # Manifest with 100 items for easy math
        items = {f"{i:06d}": {"image": f"images/{i:06d}.jpg"} for i in range(100)}
        (self.delivery_dir / "manifest.json").write_text(
            json.dumps({"items": items}),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_evaluate_release_gate_hold_when_exceeding_threshold(self):
        # 3 errors out of 100 images = 3.0% > 2.0% -> HOLD
        errors = [
            {"type": "class_swap", "target": "000001"},
            {"type": "bbox_drift", "target": "000002"},
            {"type": "invalid_class", "target": "000003"},
        ]
        (self.run_dir / "errors.json").write_text(
            json.dumps({"errors": errors}),
            encoding="utf-8",
        )

        result = evaluate_release_gate(self.run_dir, record=True)
        self.assertEqual(result["decision"], "HOLD")
        self.assertAlmostEqual(result["error_rate"], 0.03)
        self.assertEqual(result["error_count"], 3)
        self.assertEqual(result["total_images"], 100)

        # Check lineage recording
        lineage_file = self.temp_dir / "lineage.jsonl"
        self.assertTrue(lineage_file.is_file())
        lines = [json.loads(line) for line in lineage_file.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["event"], "decision")
        self.assertEqual(lines[0]["decision"], "HOLD")
        self.assertEqual(lines[0]["release_id"], "lab250_test123")

    def test_evaluate_release_gate_release_when_under_threshold(self):
        # 1 error out of 100 images = 1.0% <= 2.0% -> RELEASE
        errors = [
            {"type": "missing_image", "target": "000001"},
        ]
        (self.run_dir / "errors.json").write_text(
            json.dumps({"errors": errors}),
            encoding="utf-8",
        )

        result = evaluate_release_gate(self.run_dir, record=True)
        self.assertEqual(result["decision"], "RELEASE")
        self.assertAlmostEqual(result["error_rate"], 0.01)
        self.assertEqual(result["error_count"], 1)

    def test_blast_radius_impact(self):
        errors = [{"type": "wrong_hash", "target": f"{i:06d}"} for i in range(1, 6)]
        (self.run_dir / "errors.json").write_text(
            json.dumps({"errors": errors}),
            encoding="utf-8",
        )

        # Pre-populate lineage with a training run
        lineage_file = self.temp_dir / "lineage.jsonl"
        lineage_file.write_text(
            json.dumps({"event": "train", "release_id": "lab250_test123", "run_id": "R-021"}) + "\n",
            encoding="utf-8",
        )

        result = evaluate_release_gate(self.run_dir, record=True)
        self.assertEqual(result["decision"], "HOLD")
        impacts = result["impacted_runs"]
        self.assertEqual(len(impacts), 1)
        self.assertEqual(impacts[0]["run_id"], "R-021")
        self.assertTrue(impacts[0]["affected"])
        self.assertEqual(impacts[0]["action"], "review_or_retrain")


if __name__ == "__main__":
    unittest.main()
