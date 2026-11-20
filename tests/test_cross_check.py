"""Kiểm thử đơn vị trên dữ liệu tổng hợp (synthetic fixture) cho Phần 2.

Không phụ thuộc data_source/, không đọc _private/, không dùng mạng.
Kiểm tra:
- REV-01..REV-06 trong validator/cross_check.py (kể cả tên ảnh đề ẩn img_0001).
- Chống báo giả với iscrowd=1, isthing=0, duplicate_box, ảnh thiếu file, lỗi class_id/category_id.
- Công cụ xem ảnh và kiểm tra H3 trong tools/review_viewer.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "validator"))

import cross_check  # noqa: E402
import pngutil  # noqa: E402


def _paint_rect(pixels: bytearray, width: int, rect: tuple[int, int, int, int], seg_id: int) -> int:
    """Tô hình chữ nhật [x1, y1, x2, y2) bằng màu RGB của seg_id; trả về số pixel đã tô."""
    r, g, b = pngutil.segment_rgb(seg_id)
    x1, y1, x2, y2 = rect
    count = 0
    for y in range(y1, y2):
        for x in range(x1, x2):
            off = (y * width + x) * 3
            pixels[off] = r
            pixels[off + 1] = g
            pixels[off + 2] = b
            count += 1
    return count


def _yolo_line(cls_id: int, rect: tuple[int, int, int, int], width: int, height: int) -> str:
    x1, y1, x2, y2 = rect
    xc = ((x1 + x2) / 2.0) / width
    yc = ((y1 + y2) / 2.0) / height
    bw = (x2 - x1) / width
    bh = (y2 - y1) / height
    return f"{cls_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}"


def _build_synthetic_delivery(root: Path) -> Path:
    """Tạo một thư mục delivery/ nhỏ hoàn toàn tổng hợp với các tình huống chuẩn và lỗi."""
    d = root / "delivery"
    for sub in ("images", "labels", "masks"):
        (d / sub).mkdir(parents=True)

    # Cố tình dùng ID panoptic KHÁC ID YOLO (REV-02: phải ghép theo tên lớp)
    # YOLO: 0=person, 2=car, 7=truck
    # Panoptic COCO-style: 1=person, 3=car, 8=truck, 187=sky (stuff: isthing=0)
    classes = [f"{i} cls_{i}" for i in range(80)]
    classes[0] = "0 person"
    classes[2] = "2 car"
    classes[7] = "7 truck"
    (d / "classes.txt").write_text("\n".join(classes) + "\n", encoding="utf-8")

    categories = [
        {"id": 1, "name": "person", "isthing": 1},
        {"id": 3, "name": "car", "isthing": 1},
        {"id": 8, "name": "truck", "isthing": 1},
        {"id": 187, "name": "sky", "isthing": 0},
    ]

    W, H = 300, 200
    manifest_items = {}
    pan_images = []
    pan_anns = []

    def add_image(
        idx: int,
        stem: str,
        yolo_rows: list[str],
        segs: list[tuple[int, int, tuple[int, int, int, int], int]],
        create_jpg: bool = True,
    ) -> None:
        # segs: list of (seg_id, category_id, rect, iscrowd)
        jpg_path = d / "images" / f"{stem}.jpg"
        if create_jpg:
            Image.new("RGB", (W, H), (120, 140, 160)).save(jpg_path, format="JPEG")
        (d / "labels" / f"{stem}.txt").write_text("\n".join(yolo_rows) + ("\n" if yolo_rows else ""), encoding="utf-8")

        pixels = bytearray(W * H * 3)
        seg_infos = []
        for sid, cat_id, rect, iscrowd in segs:
            area = _paint_rect(pixels, W, rect, sid)
            x1, y1, x2, y2 = rect
            seg_infos.append(
                {
                    "id": sid,
                    "category_id": cat_id,
                    "area": area,
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "iscrowd": iscrowd,
                }
            )
        pngutil.write_rgb(d / "masks" / f"{stem}.png", W, H, bytes(pixels))

        manifest_items[stem] = {
            "image": f"images/{stem}.jpg",
            "label": f"labels/{stem}.txt",
            "mask": f"masks/{stem}.png",
            "image_sha256": "0" * 64,
            "label_sha256": "0" * 64,
            "mask_sha256": "0" * 64,
        }
        pan_images.append({"id": idx, "file_name": f"{stem}.jpg", "width": W, "height": H})
        pan_anns.append({"image_id": idx, "file_name": f"{stem}.png", "segments_info": seg_infos})

    # 1. Ảnh sạch + stuff + crowd -> phải ra 0 ứng viên
    add_image(
        1,
        "img_0001",
        [_yolo_line(2, (20, 20, 100, 100), W, H)],
        [
            (101, 3, (20, 20, 100, 100), 0),      # car khớp hoàn toàn
            (102, 187, (0, 0, 300, 20), 0),       # sky (stuff, isthing=0) -> bỏ qua
            (103, 1, (180, 50, 260, 140), 1),     # person crowd (iscrowd=1) -> bỏ qua
        ],
    )

    # 2. Khác tên lớp tại cùng vị trí -> class_swap / category_swap
    add_image(
        2,
        "img_0002",
        [_yolo_line(2, (40, 30, 140, 130), W, H)],  # YOLO: car
        [(201, 8, (40, 30, 140, 130), 0)],          # Panoptic: truck
    )

    # 3. Box lệch khỏi mask cùng lớp -> bbox_drift
    add_image(
        3,
        "img_0003",
        [_yolo_line(2, (70, 50, 170, 130), W, H)],  # dịch phải 30px, xuống 20px
        [(301, 3, (40, 30, 140, 110), 0)],
    )

    # 4. Segment đáng kể không có box -> missing_box
    add_image(
        4,
        "img_0004",
        [_yolo_line(0, (10, 10, 70, 90), W, H)],    # chỉ có box cho person
        [
            (401, 1, (10, 10, 70, 90), 0),          # person khớp
            (402, 3, (150, 60, 250, 150), 0),       # car 9000 px bị thiếu box
        ],
    )

    # 5. Hai vật cùng lớp bị gộp thành 1 segment -> instance_merge
    # Tạo 1 segment id=501 phủ cả 2 hình chữ nhật tách biệt
    jpg5 = d / "images" / "img_0005.jpg"
    Image.new("RGB", (W, H), (100, 120, 140)).save(jpg5, format="JPEG")
    (d / "labels" / "img_0005.txt").write_text(
        _yolo_line(2, (20, 40, 100, 120), W, H) + "\n" + _yolo_line(2, (160, 40, 240, 120), W, H) + "\n",
        encoding="utf-8",
    )
    px5 = bytearray(W * H * 3)
    a1 = _paint_rect(px5, W, (20, 40, 100, 120), 501)
    a2 = _paint_rect(px5, W, (160, 40, 240, 120), 501)
    pngutil.write_rgb(d / "masks" / "img_0005.png", W, H, bytes(px5))
    manifest_items["img_0005"] = {
        "image": "images/img_0005.jpg",
        "label": "labels/img_0005.txt",
        "mask": "masks/img_0005.png",
        "image_sha256": "0" * 64,
        "label_sha256": "0" * 64,
        "mask_sha256": "0" * 64,
    }
    pan_images.append({"id": 5, "file_name": "img_0005.jpg", "width": W, "height": H})
    pan_anns.append(
        {
            "image_id": 5,
            "file_name": "img_0005.png",
            "segments_info": [
                {"id": 501, "category_id": 3, "area": a1 + a2, "bbox": [20, 40, 220, 80], "iscrowd": 0}
            ],
        }
    )

    # 6. Ảnh có lỗi luật duplicate_box (lệch 2px, cùng cỡ) -> KHÔNG được báo nhầm instance_merge
    add_image(
        6,
        "img_0006",
        [
            _yolo_line(2, (50, 50, 150, 130), W, H),
            _yolo_line(2, (52, 51, 152, 131), W, H),
        ],
        [(601, 3, (50, 50, 150, 130), 0)],
    )

    # 7. Ảnh lỗi luật: thiếu file ảnh + class_id=80 + category_id không tồn tại -> không crash
    add_image(
        7,
        "img_0007",
        [_yolo_line(80, (10, 10, 80, 80), W, H)],
        [(701, 999, (10, 10, 80, 80), 0)],
        create_jpg=False,
    )

    (d / "manifest.json").write_text(
        json.dumps({"dataset": "synthetic", "num_classes": 80, "items": manifest_items}, indent=2) + "\n",
        encoding="utf-8",
    )
    (d / "panoptic.json").write_text(
        json.dumps({"categories": categories, "images": pan_images, "annotations": pan_anns}) + "\n",
        encoding="utf-8",
    )
    return d


class CrossCheckAndViewerTest(unittest.TestCase):
    def test_cross_check_detects_all_four_patterns_and_ignores_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            delivery = _build_synthetic_delivery(Path(tmp))
            result = cross_check.find_candidates(delivery)

            by_img: dict[str, list[dict]] = {}
            for cand in result["candidates"]:
                by_img.setdefault(cand["image"], []).append(cand)

            # Ảnh sạch + stuff + crowd -> không có ứng viên
            self.assertNotIn("img_0001", by_img)
            # Duplicate box -> không báo nhầm instance_merge hay lỗi gán nhãn khác
            self.assertNotIn("img_0006", by_img)
            # Ảnh thiếu file -> bỏ qua an toàn, không crash
            self.assertNotIn("img_0007", by_img)
            self.assertEqual(result["summary"]["skipped_missing_images"], 1)

            # REV-03: class_swap / category_swap
            self.assertEqual(len(by_img.get("img_0002", [])), 1)
            self.assertEqual(by_img["img_0002"][0]["suggested_types"], ["class_swap", "category_swap"])
            self.assertEqual(by_img["img_0002"][0]["det_class"], "car")
            self.assertEqual(by_img["img_0002"][0]["pan_class"], "truck")

            # REV-04: bbox_drift
            self.assertEqual(len(by_img.get("img_0003", [])), 1)
            self.assertEqual(by_img["img_0003"][0]["suggested_types"], ["bbox_drift"])

            # REV-05: missing_box
            self.assertEqual(len(by_img.get("img_0004", [])), 1)
            self.assertEqual(by_img["img_0004"][0]["suggested_types"], ["missing_box"])
            self.assertEqual(by_img["img_0004"][0]["pan_class"], "car")

            # REV-06: instance_merge
            self.assertEqual(len(by_img.get("img_0005", [])), 1)
            self.assertEqual(by_img["img_0005"][0]["suggested_types"], ["instance_merge"])
            self.assertEqual(len(by_img["img_0005"][0]["det_boxes_px"]), 2)

    def test_viewer_build_and_merge_h3_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            delivery = _build_synthetic_delivery(root)
            cands_path = root / "candidates.json"
            cross_check.write_candidates(delivery, cands_path)

            viz_dir = root / "review_viz"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "review_viewer.py"),
                    "build",
                    "--delivery",
                    str(delivery),
                    "--candidates",
                    str(cands_path),
                    "--out",
                    str(viz_dir),
                    "--members",
                    "4",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            self.assertIn("4 thẻ review", proc.stdout)
            self.assertTrue((viz_dir / "index.html").is_file())
            self.assertEqual(len(list((viz_dir / "imgs").glob("*.png"))), 12)  # 4 ứng viên x 3 ảnh

            # Kiểm tra lệnh merge bắt lỗi ghi chú ngắn (< 20 ký tự)
            bad_csv = root / "bad.csv"
            bad_csv.write_text(
                "image,type,verdict,note\nimg_0002,class_swap,confirmed,qua ngan\n",
                encoding="utf-8",
            )
            bad_run = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "review_viewer.py"), "merge", str(bad_csv), "--out", str(root / "out_bad.csv")],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(bad_run.returncode, 0)
            self.assertIn("LỖI H3", bad_run.stdout)

            # Kiểm tra lệnh merge đạt chuẩn H3 khi gộp 2 phần hợp lệ
            p1 = root / "p1.csv"
            p2 = root / "p2.csv"
            p1.write_text(
                'image,type,verdict,note\nimg_0002,class_swap,confirmed,"HaKhanh xem: xe tai thung kin, detection ghi car sai con panoptic ghi truck dung"\n',
                encoding="utf-8",
            )
            p2.write_text(
                'image,type,verdict,note\nimg_0003,bbox_drift,rejected,"TV2 xem: vat bi che mot phan o mep nen mask nho hon box, nhan van hop ly"\n',
                encoding="utf-8",
            )
            good_out = root / "review_log.csv"
            good_run = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "review_viewer.py"), "merge", str(p1), str(p2), "--out", str(good_out)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            self.assertIn("Đạt kiểm tra H3", good_run.stdout)
            self.assertTrue(good_out.is_file())

    def test_cross_check_cli_and_threshold_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            delivery = _build_synthetic_delivery(root)
            out_json = root / "candidates.json"
            overrides = root / "thresh.json"
            overrides.write_text(json.dumps({"missing_min_seg_px": 1000}), encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "validator" / "cross_check.py"),
                    str(delivery),
                    "--out",
                    str(out_json),
                    "--thresholds-json",
                    str(overrides),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            self.assertIn("4 ứng viên", proc.stdout)
            doc = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(doc["thresholds"]["missing_min_seg_px"], 1000)
            self.assertEqual(doc["summary"]["total_candidates"], 4)

    def test_overlapping_three_same_class_objects_not_false_merge(self):
        """3 vật cùng lớp chồng lấn trước/sau (mỗi vật đều có box + mask khớp 1-1) -> không báo nhầm instance_merge."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "delivery"
            for sub in ("images", "labels", "masks"):
                (d / sub).mkdir(parents=True)
            W, H = 300, 200
            (d / "classes.txt").write_text("0 person\n", encoding="utf-8")
            Image.new("RGB", (W, H), (100, 120, 100)).save(d / "images" / "img_0001.jpg", format="JPEG")

            # Người 1 (phía sau trái): [40, 60, 130, 180]
            # Người 2 (phía sau phải): [130, 40, 210, 170]
            # Người 3 (phía trước giữa, che đè cả 2 khung phía sau): [80, 70, 200, 185]
            b1 = (40, 60, 130, 180)
            b2 = (130, 40, 210, 170)
            b3 = (80, 70, 200, 185)
            (d / "labels" / "img_0001.txt").write_text(
                "\n".join(_yolo_line(0, b, W, H) for b in (b1, b2, b3)) + "\n",
                encoding="utf-8",
            )
            pixels = bytearray(W * H * 3)
            # Tô 2 người phía sau trước, rồi người phía trước đè lên đúng như occlusion thực tế
            _paint_rect(pixels, W, b1, 10)
            _paint_rect(pixels, W, b2, 20)
            _paint_rect(pixels, W, b3, 30)
            pngutil.write_rgb(d / "masks" / "img_0001.png", W, H, bytes(pixels))

            # Đếm lại diện tích thực từng segment sau khi bị đè
            r_c, g_c, b_c = pixels[0::3], pixels[1::3], pixels[2::3]
            from collections import Counter
            cnt = Counter(zip(r_c, g_c, b_c))
            seg_infos = []
            for sid, rect in ((10, b1), (20, b2), (30, b3)):
                x1, y1, x2, y2 = rect
                seg_infos.append(
                    {
                        "id": sid,
                        "category_id": 1,
                        "area": cnt[pngutil.segment_rgb(sid)],
                        "bbox": [x1, y1, x2 - x1, y2 - y1],
                        "iscrowd": 0,
                    }
                )
            (d / "manifest.json").write_text(
                json.dumps(
                    {
                        "dataset": "synthetic",
                        "num_classes": 1,
                        "items": {
                            "img_0001": {
                                "image": "images/img_0001.jpg",
                                "label": "labels/img_0001.txt",
                                "mask": "masks/img_0001.png",
                                "image_sha256": "0" * 64,
                                "label_sha256": "0" * 64,
                                "mask_sha256": "0" * 64,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (d / "panoptic.json").write_text(
                json.dumps(
                    {
                        "categories": [{"id": 1, "name": "person", "isthing": 1}],
                        "images": [{"id": 1, "file_name": "img_0001.jpg", "width": W, "height": H}],
                        "annotations": [{"image_id": 1, "file_name": "img_0001.png", "segments_info": seg_infos}],
                    }
                ),
                encoding="utf-8",
            )

            res = cross_check.find_candidates(d)
            merge_cands = [c for c in res["candidates"] if "instance_merge" in c["suggested_types"]]
            self.assertEqual(merge_cands, [])

    def test_validate_cli_rules_and_candidates_integration(self):
        """Kiểm tra tích hợp CLI chung validator/validate.py xuất cả --out và --candidates."""
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            delivery = _build_synthetic_delivery(root)
            # Bổ sung metadata.json, jobs.csv và sha256 thật cho fixture để validate_rules chạy trọn vẹn
            man_path = delivery / "manifest.json"
            man_doc = json.loads(man_path.read_text(encoding="utf-8"))
            meta_items = []
            for stem, it in man_doc["items"].items():
                for kind in ("image", "label", "mask"):
                    p = delivery / it[kind]
                    if p.is_file():
                        it[f"{kind}_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
                meta_items.append(
                    {"image": stem, "scene_id": "scene_1", "split": "train", "job_id": "J01", "guideline_version": "v1.2"}
                )
            man_path.write_text(json.dumps(man_doc, indent=2), encoding="utf-8")
            (delivery / "metadata.json").write_text(json.dumps({"items": meta_items}, indent=2), encoding="utf-8")
            (delivery / "jobs.csv").write_text("job_id,annotator,reviewer,guideline\nJ01,A01,Q01,v1.2\n", encoding="utf-8")

            rules_out = root / "rules.json"
            cands_out = root / "candidates.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "validator" / "validate.py"),
                    str(delivery),
                    "--out",
                    str(rules_out),
                    "--candidates",
                    str(cands_out),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            self.assertIn("Rules:", proc.stdout)
            self.assertIn("Candidates:", proc.stdout)
            rules_doc = json.loads(rules_out.read_text(encoding="utf-8"))
            cands_doc = json.loads(cands_out.read_text(encoding="utf-8"))
            # --out chỉ chứa lỗi luật (img_0006 duplicate_box, img_0007 missing_image/invalid_class/invalid_category_id)
            rule_types = {e["type"] for e in rules_doc["errors"]}
            self.assertIn("duplicate_box", rule_types)
            self.assertIn("missing_image", rule_types)
            self.assertNotIn("class_swap", rule_types)
            self.assertNotIn("missing_box", rule_types)
            # --candidates chứa đủ 4 ứng viên lỗi gán nhãn
            self.assertEqual(cands_doc["summary"]["total_candidates"], 4)

            # Kiểm tra chặn ghi --candidates vào trong thư mục delivery/
            bad_proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "validator" / "validate.py"),
                    str(delivery),
                    "--out",
                    str(rules_out),
                    "--candidates",
                    str(delivery / "candidates.json"),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(bad_proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
