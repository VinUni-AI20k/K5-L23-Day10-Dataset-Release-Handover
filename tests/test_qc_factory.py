import csv
import hashlib
import json
import struct
import sys
import tempfile
import threading
import unittest
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "validator") not in sys.path:
    sys.path.insert(0, str(ROOT / "validator"))

import validate  # noqa: E402
from qc_factory_day10.adapters.delivery_reader import run_preflight  # noqa: E402
from qc_factory_day10.orchestration.pipeline import finalize_challenge, run_challenge_pipeline  # noqa: E402
from qc_factory_day10.review.review_store import ReviewStore  # noqa: E402
from qc_factory_day10.review.server import create_review_server  # noqa: E402
from qc_factory_day10.adapters.delivery_reader import load_delivery  # noqa: E402


def _write_rgb_png(path: Path, width: int, height: int, rgb_rows: list[bytes]) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rgb_rows)
    idat = zlib.compress(raw)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_synthetic_delivery(root: Path) -> Path:
    delivery = root / "delivery"
    (delivery / "images").mkdir(parents=True)
    (delivery / "labels").mkdir(parents=True)
    (delivery / "masks").mkdir(parents=True)
    (delivery / "incoming").mkdir(parents=True)
    (delivery / "guideline").mkdir(parents=True)

    # img_0001: class_swap candidate (det=bicycle, panoptic=person)
    img1 = delivery / "images" / "img_0001.jpg"
    img1.write_bytes(b"fake-jpg-1")
    lbl1 = delivery / "labels" / "img_0001.txt"
    lbl1.write_text("1 0.5 0.5 0.5 0.5\n", encoding="utf-8")
    mask1 = delivery / "masks" / "img_0001.png"
    row_seg1 = bytes([0, 0, 0] * 1 + [1, 0, 0] * 2 + [0, 0, 0] * 1)
    row_bg = bytes([0, 0, 0] * 4)
    _write_rgb_png(mask1, 4, 4, [row_bg, row_seg1, row_seg1, row_bg])

    # img_0002: instance_merge candidate (2 distinct person boxes inside 1 person segment on 20x20 image)
    img2 = delivery / "images" / "img_0002.jpg"
    img2.write_bytes(b"fake-jpg-2")
    lbl2 = delivery / "labels" / "img_0002.txt"
    lbl2.write_text("0 0.25 0.5 0.45 0.8\n0 0.75 0.5 0.45 0.8\n", encoding="utf-8")
    mask2 = delivery / "masks" / "img_0002.png"
    row_seg2 = bytes([2, 0, 0] * 20)
    _write_rgb_png(mask2, 20, 20, [row_seg2] * 20)

    manifest = {
        "items": {
            "img_0001": {
                "image": "images/img_0001.jpg", "image_sha256": _sha256(img1),
                "label": "labels/img_0001.txt", "label_sha256": _sha256(lbl1),
                "mask": "masks/img_0001.png", "mask_sha256": _sha256(mask1),
            },
            "img_0002": {
                "image": "images/img_0002.jpg", "image_sha256": _sha256(img2),
                "label": "labels/img_0002.txt", "label_sha256": _sha256(lbl2),
                "mask": "masks/img_0002.png", "mask_sha256": _sha256(mask2),
            },
        }
    }
    (delivery / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (delivery / "metadata.json").write_text(
        json.dumps({"items": [
            {"image": "img_0001", "scene_id": "scene_10", "split": "train", "job_id": "j1", "guideline_version": "v1.2"},
            {"image": "img_0002", "scene_id": "scene_20", "split": "train", "job_id": "j1", "guideline_version": "v1.2"},
        ]}),
        encoding="utf-8",
    )
    (delivery / "jobs.csv").write_text("job_id,annotator,reviewer,guideline\nj1,ann_A,rev_B,v1.2\n", encoding="utf-8")
    (delivery / "classes.txt").write_text("0 person\n1 bicycle\n", encoding="utf-8")
    (delivery / "release.json").write_text(json.dumps({"release_id": "lab250_test"}), encoding="utf-8")
    (delivery / "guideline" / "changelog.md").write_text("v1.2 -> v1.3: bicycle rule updated\n", encoding="utf-8")
    (delivery / "incoming" / "ticket.md").write_text("Issue on scene_10 with bicycle\n", encoding="utf-8")
    panoptic = {
        "categories": [
            {"id": 1, "name": "person", "isthing": 1},
            {"id": 2, "name": "bicycle", "isthing": 1},
        ],
        "images": [
            {"id": 1, "file_name": "img_0001.jpg", "width": 4, "height": 4},
            {"id": 2, "file_name": "img_0002.jpg", "width": 20, "height": 20},
        ],
        "annotations": [
            {"image_id": 1, "file_name": "img_0001.png", "segments_info": [{"id": 1, "category_id": 1, "area": 4, "bbox": [1, 1, 2, 2]}]},
            {"image_id": 2, "file_name": "img_0002.png", "segments_info": [{"id": 2, "category_id": 1, "area": 400, "bbox": [0, 0, 20, 20]}]},
        ],
    }
    (delivery / "panoptic.json").write_text(json.dumps(panoptic), encoding="utf-8")
    return delivery


class QCFactoryTest(unittest.TestCase):
    def test_validator_detects_instance_merge_and_class_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            delivery = _make_synthetic_delivery(Path(tmp))
            self.assertEqual(validate.check_rules(delivery), [])
            cands = validate.cross_check_candidates(delivery)
            types = {(c["type"], c["target"]) for c in cands}
            self.assertIn(("class_swap", "img_0001"), types)
            self.assertIn(("instance_merge", "img_0002"), types)

    def test_preflight_and_challenge_pipeline_and_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            delivery = _make_synthetic_delivery(tmp_p)
            out_dir = tmp_p / "out"

            pf = run_preflight(delivery, out_path=out_dir / "preflight_report.json")
            self.assertTrue(pf["ready_for_qc"])

            res = run_challenge_pipeline(delivery, out_dir, serve=False)
            self.assertTrue(res["ok"])
            self.assertTrue((out_dir / "triage.csv").is_file())
            self.assertTrue((out_dir / "difficulty_summary.json").is_file())
            self.assertTrue((out_dir / "trace.json").is_file())

            trace = json.loads((out_dir / "trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace["tier_a"], ["img_0001"])
            self.assertEqual(trace["notify"], ["ann_A", "rev_B"])

            # Simulate human review via ReviewStore
            store = ReviewStore(out_dir / "review_state.db")
            cands = store.list_candidates()
            self.assertGreaterEqual(len(cands), 2)
            with self.assertRaises(ValueError):
                store.record_decision(cands[0]["candidate_id"], "confirmed", "category_swap", "too short", "@hung")
            store.record_decision(
                cands[0]["candidate_id"],
                "confirmed",
                "category_swap",
                "Trong ảnh thấy xe đạp nhưng mask panoptic gán thành person.",
                "@hung",
            )
            fin = finalize_challenge(out_dir)
            self.assertTrue(fin["ok"])
            self.assertEqual(fin["review_rows_exported"], 1)
            errs = json.loads((out_dir / "errors.json").read_text(encoding="utf-8"))["errors"]
            self.assertIn({"type": "category_swap", "target": cands[0]["image_id"]}, errs)

    def test_review_http_server_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            delivery = _make_synthetic_delivery(tmp_p)
            out_dir = tmp_p / "out"
            run_challenge_pipeline(delivery, out_dir, serve=False)
            ctx = load_delivery(delivery)
            store = ReviewStore(out_dir / "review_state.db")
            srv = create_review_server(ctx, store, out_dir, ["@hung"], port=0)
            port = srv.server_address[1]
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                html_body = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
                self.assertIn("QC Intelligence Review", html_body)
                state = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state").read().decode("utf-8"))
                self.assertGreaterEqual(len(state["candidates"]), 2)
            finally:
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
