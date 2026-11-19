#!/usr/bin/env python3
"""Validator của nhóm 07 cho Lab 10.

Giao diện CLI chuẩn:
  python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

Phân công module:
  - Khung CLI & Rule File/Metadata: Văn (Team Lead)
  - Rule YOLO & Panoptic: Minh (rules_yolo_panoptic.py)
  - Cross-check Candidates: Vũ
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

# Import module kiểm tra lỗi YOLO & Panoptic của Minh
try:
    from validator.rules_yolo_panoptic import check_yolo_label, check_panoptic_ann
except ImportError:
    from rules_yolo_panoptic import check_yolo_label, check_panoptic_ann

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

try:
    import pngutil
except ImportError:
    pngutil = None


def sha256_file(path: Path) -> str:
    """Tính mã băm SHA256 trên bytes thực tế của file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def check_file_and_metadata_rules(delivery_dir: Path) -> list[tuple[str, str]]:
    """Kiểm tra các lỗi luật mức File và Metadata (Phụ trách: Văn).
    
    1. missing_image: manifest có nhưng thiếu file ảnh
    2. wrong_hash: sha256 thật khác sha256 trong manifest
    3. scene_leak: cùng 1 cảnh nhưng có ảnh ở cả train và val
    4. guideline_mismatch: guideline của ảnh khác guideline của job trong jobs.csv
    """
    errors: list[tuple[str, str]] = []
    
    manifest_path = delivery_dir / "manifest.json"
    metadata_path = delivery_dir / "metadata.json"
    jobs_path = delivery_dir / "jobs.csv"

    if not manifest_path.is_file() or not metadata_path.is_file() or not jobs_path.is_file():
        return errors

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["items"]
    metadata = {m["image"]: m for m in json.loads(metadata_path.read_text(encoding="utf-8"))["items"]}
    jobs = {row["job_id"]: row for row in read_csv(jobs_path)}

    scene_splits: dict[str, set[str]] = {}

    for stem, it in manifest.items():
        m = metadata.get(stem, {})
        scene_id = m.get("scene_id")
        split = m.get("split")
        job_id = m.get("job_id")
        img_guideline = m.get("guideline_version")

        # Gom split theo scene để kiểm tra scene_leak
        if scene_id and split:
            scene_splits.setdefault(scene_id, set()).add(split)

        # 1. missing_image
        img_file = delivery_dir / it["image"]
        if not img_file.is_file():
            errors.append(("missing_image", stem))
            continue

        # 2. wrong_hash (đọc chế độ byte 'rb')
        if sha256_file(img_file) != it["image_sha256"]:
            errors.append(("wrong_hash", stem))
            continue

        # 4. guideline_mismatch (so với guideline ghi ở job trong jobs.csv)
        job = jobs.get(job_id)
        if job and img_guideline != job.get("guideline"):
            errors.append(("guideline_mismatch", stem))

    # 3. scene_leak (target là scene_id, ví dụ 'scene_557')
    for scene_id, splits in scene_splits.items():
        if len(splits) > 1:
            errors.append(("scene_leak", scene_id))

    return errors


def generate_candidates(delivery_dir: Path) -> list[dict]:
    """Đối chiếu Detection ↔ Panoptic để tìm ứng viên lỗi gán nhãn (Phụ trách: Vũ)."""
    candidates = []
    manifest_path = delivery_dir / "manifest.json"
    panoptic_path = delivery_dir / "panoptic.json"
    classes_path = delivery_dir / "classes.txt"

    if not manifest_path.is_file() or not panoptic_path.is_file() or not classes_path.is_file():
        return candidates

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["items"]
    pan = json.loads(panoptic_path.read_text(encoding="utf-8"))
    
    # Map class index sang tên lớp YOLO
    yolo_classes = [ln.split(" ", 1)[1].strip() for ln in classes_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    cat_by_id = {c["id"]: c for c in pan["categories"]}
    things_cats = {c["id"] for c in pan["categories"] if c.get("isthing")}
    anns = {a["image_id"]: a for a in pan["annotations"]}
    imgs = {im["file_name"]: im for im in pan["images"]}

    for stem, it in manifest.items():
        im_info = imgs.get(it["image"].split("/")[-1])
        if not im_info:
            continue
        W, H = im_info["width"], im_info["height"]
        ann = anns.get(im_info["id"], {})
        segments = [s for s in ann.get("segments_info", []) if s["category_id"] in things_cats and not s.get("iscrowd")]

        # Đọc nhãn YOLO
        lbl_file = delivery_dir / it["label"]
        yolo_boxes = []
        if lbl_file.is_file():
            for ln in lbl_file.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    parts = ln.split()
                    c = int(float(parts[0]))
                    if 0 <= c < len(yolo_classes):
                        x, y, w, h = map(float, parts[1:5])
                        # Chuyển sang pixel [x1, y1, x2, y2]
                        x1 = (x - w / 2) * W
                        y1 = (y - h / 2) * H
                        x2 = (x + w / 2) * W
                        y2 = (y + h / 2) * H
                        yolo_boxes.append({"cls": yolo_classes[c], "bbox": [x1, y1, x2, y2], "area": w * h * W * H})

        # Hàm tính IoU giữa 2 box pixel
        def calc_iou(b1, b2):
            ix = max(0.0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
            iy = max(0.0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
            inter = ix * iy
            a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
            a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
            return inter / (a1 + a2 - inter + 1e-12)

        # 1. Kiểm tra class_swap hoặc category_swap hoặc bbox_drift
        for yb in yolo_boxes:
            best_iou = 0.0
            best_seg = None
            for seg in segments:
                # panoptic bbox: [x, y, w, h]
                sb = [seg["bbox"][0], seg["bbox"][1], seg["bbox"][0] + seg["bbox"][2], seg["bbox"][1] + seg["bbox"][3]]
                iou = calc_iou(yb["bbox"], sb)
                if iou > best_iou:
                    best_iou = iou
                    best_seg = seg

            if best_seg:
                seg_cls = cat_by_id[best_seg["category_id"]]["name"]
                # Cùng vị trí (IoU >= 0.45) nhưng khác lớp -> Nghi vấn đổi lớp
                if best_iou >= 0.45 and yb["cls"] != seg_cls:
                    candidates.append({
                        "image": stem,
                        "type": "class_swap",
                        "note": f"Detection: {yb['cls']} vs Panoptic: {seg_cls} (IoU={best_iou:.2f})"
                    })
                # Cùng lớp nhưng box bị trôi (IoU từ 0.2 đến 0.55 và diện tích tương đối)
                elif yb["cls"] == seg_cls and 0.15 <= best_iou < 0.60:
                    candidates.append({
                        "image": stem,
                        "type": "bbox_drift",
                        "note": f"Lớp {yb['cls']} có IoU thấp ({best_iou:.2f}), nghi vấn trôi box"
                    })

        # 2. Kiểm tra missing_box: segment lớn mà không có box detection nào khớp
        for seg in segments:
            if seg.get("area", 0) >= 3000:
                sb = [seg["bbox"][0], seg["bbox"][1], seg["bbox"][0] + seg["bbox"][2], seg["bbox"][1] + seg["bbox"][3]]
                max_iou = max([calc_iou(yb["bbox"], sb) for yb in yolo_boxes], default=0.0)
                if max_iou < 0.15:
                    seg_cls = cat_by_id[seg["category_id"]]["name"]
                    candidates.append({
                        "image": stem,
                        "type": "missing_box",
                        "note": f"Segment {seg_cls} diện tích {seg['area']}px nhưng không có box tương ứng"
                    })

        # 3. Kiểm tra instance_merge: 1 segment phủ 2 box cùng lớp
        for seg in segments:
            seg_cls = cat_by_id[seg["category_id"]]["name"]
            sb = [seg["bbox"][0], seg["bbox"][1], seg["bbox"][0] + seg["bbox"][2], seg["bbox"][1] + seg["bbox"][3]]
            matched_boxes = [yb for yb in yolo_boxes if yb["cls"] == seg_cls and calc_iou(yb["bbox"], sb) > 0.25]
            if len(matched_boxes) >= 2:
                candidates.append({
                    "image": stem,
                    "type": "instance_merge",
                    "note": f"Segment {seg_cls} bao trùm {len(matched_boxes)} box detection cùng lớp"
                })

    # Khử trùng candidate cùng ảnh + cùng loại
    unique_candidates = []
    seen = set()
    for c in candidates:
        key = (c["image"], c["type"])
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    return unique_candidates


def main():
    parser = argparse.ArgumentParser(description="Day 10 Lab Validator — Nhóm 07")
    parser.add_argument("delivery", type=str, help="Đường dẫn thư mục delivery cần kiểm tra")
    parser.add_argument("--out", type=str, required=True, help="Đường dẫn file errors.json xuất ra")
    parser.add_argument("--candidates", type=str, default=None, help="Đường dẫn file candidates.json xuất ra (tùy chọn)")
    args = parser.parse_args()

    delivery_dir = Path(args.delivery).resolve()
    if not delivery_dir.is_dir():
        print(f"Lỗi: Thư mục {delivery_dir} không tồn tại!", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Bắt đầu kiểm tra dữ liệu tại: {delivery_dir.name}")
    all_errors: list[dict] = []
    seen_errors: set[tuple[str, str]] = set()

    def add_err(etype: str, target: str):
        if (etype, target) not in seen_errors:
            seen_errors.add((etype, target))
            all_errors.append({"type": etype, "target": target})

    # --- 1. Luật File & Metadata (Văn) ---
    file_errors = check_file_and_metadata_rules(delivery_dir)
    for etype, target in file_errors:
        add_err(etype, target)

    # --- 2. Luật YOLO & Panoptic (Minh) ---
    manifest_path = delivery_dir / "manifest.json"
    panoptic_path = delivery_dir / "panoptic.json"

    if manifest_path.is_file() and panoptic_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["items"]
        pan = json.loads(panoptic_path.read_text(encoding="utf-8"))
        valid_cats = {c["id"] for c in pan.get("categories", [])}
        anns = {a["image_id"]: a for a in pan.get("annotations", [])}
        imgs = {im["file_name"]: im for im in pan.get("images", [])}

        for stem, it in manifest.items():
            im_file_name = it["image"].split("/")[-1]
            im_info = imgs.get(im_file_name)
            w, h = (im_info["width"], im_info["height"]) if im_info else (640, 480)

            # Kiểm tra YOLO label
            lbl_path = delivery_dir / it["label"]
            yolo_errs = check_yolo_label(lbl_path, stem, w, h)
            for etype, target in yolo_errs:
                add_err(etype, target)

            # Kiểm tra Panoptic mask & annotations
            if im_info and im_info["id"] in anns:
                mask_path = delivery_dir / it["mask"]
                pan_errs = check_panoptic_ann(mask_path, stem, anns[im_info["id"]], valid_cats)
                for etype, target in pan_errs:
                    add_err(etype, target)

    # Xuất errors.json
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_data = {"errors": all_errors}
    out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] Đã phát hiện {len(all_errors)} lỗi luật. Ghi vào: {out_path}")

    # --- 3. Sinh Candidates (Vũ) nếu được yêu cầu ---
    if args.candidates:
        cand_path = Path(args.candidates).resolve()
        cand_path.parent.mkdir(parents=True, exist_ok=True)
        candidates = generate_candidates(delivery_dir)
        cand_path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[+] Đã sinh {len(candidates)} ứng viên đối chiếu. Ghi vào: {cand_path}")


if __name__ == "__main__":
    main()
