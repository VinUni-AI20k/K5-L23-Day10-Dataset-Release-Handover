#!/usr/bin/env python3
"""Validator kiểm tra chất lượng bàn giao dữ liệu (Detection & Panoptic).

Sử dụng:
  python validator/validate.py <delivery_dir> --out <errors.json> [--candidates <candidates.json>]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

# Thư viện chuẩn được phép nạp pngutil từ scripts/
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import pngutil
except ImportError:
    pngutil = None


def calc_sha256(path: Path) -> str:
    """Tính mã băm SHA-256 trên byte nhị phân của file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def bbox_iou(b1: tuple[float, float, float, float], b2: tuple[float, float, float, float]) -> float:
    """Tính IoU giữa 2 box [x1, y1, x2, y2]."""
    ix1 = max(b1[0], b2[0])
    iy1 = max(b1[1], b2[1])
    ix2 = min(b1[2], b2[2])
    iy2 = min(b1[3], b2[3])
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    a1 = max(0.0, b1[2] - b1[0]) * max(0.0, b1[3] - b1[1])
    a2 = max(0.0, b2[2] - b2[0]) * max(0.0, b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def validate_delivery(delivery_dir: Path, out_path: Path, candidates_path: Path | None = None):
    delivery_dir = delivery_dir.resolve()
    manifest_path = delivery_dir / "manifest.json"
    metadata_path = delivery_dir / "metadata.json"
    panoptic_path = delivery_dir / "panoptic.json"
    classes_path = delivery_dir / "classes.txt"
    jobs_path = delivery_dir / "jobs.csv"

    errors: list[dict[str, str]] = []
    candidates: list[dict] = []

    # 1. Đọc classes.txt (80 lớp detection)
    classes80: list[str] = []
    if classes_path.is_file():
        for line in classes_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                parts = line.split(" ", 1)
                classes80.append(parts[1].strip() if len(parts) > 1 else parts[0].strip())

    # 2. Đọc jobs.csv
    jobs_info: dict[str, dict[str, str]] = {}
    if jobs_path.is_file():
        with jobs_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                jobs_info[row["job_id"]] = row

    # 3. Đọc manifest.json & metadata.json
    manifest_items = {}
    if manifest_path.is_file():
        manifest_items = json.loads(manifest_path.read_text(encoding="utf-8")).get("items", {})

    metadata_items = {}
    if metadata_path.is_file():
        for m in json.loads(metadata_path.read_text(encoding="utf-8")).get("items", []):
            metadata_items[m["image"]] = m

    # 4. Đọc panoptic.json
    panoptic_doc = {}
    cat_by_id = {}
    cat_name_to_id = {}
    thing_cat_ids = set()
    pan_annotations = {}
    if panoptic_path.is_file():
        panoptic_doc = json.loads(panoptic_path.read_text(encoding="utf-8"))
        for c in panoptic_doc.get("categories", []):
            cat_by_id[c["id"]] = c
            cat_name_to_id[c["name"]] = c["id"]
            if c.get("isthing"):
                thing_cat_ids.add(c["id"])
        for ann in panoptic_doc.get("annotations", []):
            pan_annotations[ann["image_id"]] = ann

    # =========================================================================
    # KIỂM TRA LỖI LUẬT MỨC METADATA: scene_leak & guideline_mismatch
    # =========================================================================
    scenes: dict[str, set[str]] = {}
    for img_name, meta in metadata_items.items():
        scenes.setdefault(meta["scene_id"], set()).add(meta["split"])
        # guideline_mismatch
        job_id = meta.get("job_id")
        if job_id in jobs_info:
            expected_guideline = jobs_info[job_id]["guideline"]
            if meta.get("guideline_version") != expected_guideline:
                errors.append({"type": "guideline_mismatch", "target": img_name})

    for sc_id, splits in scenes.items():
        if len(splits) > 1:
            errors.append({"type": "scene_leak", "target": sc_id})

    # =========================================================================
    # KIỂM TRA TỪNG ẢNH TRONG MANIFEST
    # =========================================================================
    for img_name, item in manifest_items.items():
        img_rel = item.get("image")
        label_rel = item.get("label")
        mask_rel = item.get("mask")

        img_file = delivery_dir / img_rel
        label_file = delivery_dir / label_rel
        mask_file = delivery_dir / mask_rel

        # Lỗi 1: missing_image
        if not img_file.is_file():
            errors.append({"type": "missing_image", "target": img_name})
            continue

        # Lỗi 2: wrong_hash
        if calc_sha256(img_file) != item.get("image_sha256"):
            errors.append({"type": "wrong_hash", "target": img_name})

        # Lỗi Detection: invalid_class, bbox_out_of_bounds, duplicate_box
        boxes: list[tuple[int, float, float, float, float]] = []
        if label_file.is_file():
            has_invalid_class = False
            has_oob = False
            lines = label_file.read_text(encoding="utf-8").splitlines()
            for ln in lines:
                ln = ln.strip()
                if not ln:
                    continue
                parts = ln.split()
                if len(parts) < 5:
                    continue
                c, x, y, w, h = int(float(parts[0])), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                if not (0 <= c < 80):
                    has_invalid_class = True
                if x - w / 2 < -0.01 or y - h / 2 < -0.01 or x + w / 2 > 1.01 or y + h / 2 > 1.01:
                    has_oob = True
                boxes.append((c, x, y, w, h))

            if has_invalid_class:
                errors.append({"type": "invalid_class", "target": img_name})
            if has_oob:
                errors.append({"type": "bbox_out_of_bounds", "target": img_name})

            # duplicate_box: lặp cùng lớp, cùng kích thước chính xác, chỉ lệch tâm 1-2px
            has_duplicate = False
            n_boxes = len(boxes)
            for i in range(n_boxes):
                ci, xi, yi, wi, hi = boxes[i]
                for j in range(i + 1, n_boxes):
                    cj, xj, yj, wj, hj = boxes[j]
                    if ci == cj:
                        # Cùng kích thước chính xác (lỗi gài giữ nguyên width và height)
                        if abs(wi - wj) < 1e-4 and abs(hi - hj) < 1e-4:
                            dist = math.hypot(xi - xj, yi - yj)
                            # Độ lệch tâm 1-2px (< 0.015 trên ảnh chuẩn hoá)
                            if 0 < dist < 0.015:
                                has_duplicate = True
                                break
                if has_duplicate:
                    break
            if has_duplicate:
                errors.append({"type": "duplicate_box", "target": img_name})

    # =========================================================================
    # KIỂM TRA LỖI PANOPTIC (invalid_category_id & thing_overlap)
    # =========================================================================
    # Để đối chiếu panoptic annotation với từng ảnh:
    # panoptic.json["images"] chứa mapping file_name / id
    pan_images = {im["file_name"]: im for im in panoptic_doc.get("images", [])}
    pan_images_by_id = {im["id"]: im for im in panoptic_doc.get("images", [])}
    # annotation by image_id
    pan_ann_by_img_id = {a["image_id"]: a for a in panoptic_doc.get("annotations", [])}
    # Hoặc annotation by file_name
    pan_ann_by_file = {Path(a["file_name"]).stem: a for a in panoptic_doc.get("annotations", [])}

    for img_name, item in manifest_items.items():
        mask_rel = item.get("mask")
        mask_file = delivery_dir / mask_rel if mask_rel else None
        # Tìm annotation tương ứng
        ann = pan_ann_by_file.get(img_name)
        if not ann:
            # Tìm theo id số
            try:
                numeric_id = int(img_name.lstrip("0") or "0")
                ann = pan_ann_by_img_id.get(numeric_id)
            except ValueError:
                ann = None

        if not ann:
            continue

        segs = ann.get("segments_info", [])
        # invalid_category_id
        for s in segs:
            cid = s.get("category_id")
            if cid not in cat_by_id:
                errors.append({"type": "invalid_category_id", "target": img_name})
                break

        # thing_overlap: đếm số pixel thật của segment trong mask RGB rồi so với s["area"]
        t_segs = [s for s in segs if s.get("category_id") in thing_cat_ids and not s.get("iscrowd")]
        if len(t_segs) >= 2 and mask_file and mask_file.is_file() and pngutil is not None:
            try:
                w_px, h_px, raw_pixels = pngutil.read_rgb(mask_file)
                stride = w_px * 3
                pixel_counts: dict[int, int] = {}
                for s in t_segs:
                    sid = s["id"]
                    bx, by, bw, bh = s.get("bbox", [0, 0, w_px, h_px])
                    c = 0
                    for y in range(max(0, by), min(h_px, by + bh)):
                        row_start = y * stride
                        for x in range(max(0, bx), min(w_px, bx + bw)):
                            idx = row_start + x * 3
                            seg_val = raw_pixels[idx] | (raw_pixels[idx + 1] << 8) | (raw_pixels[idx + 2] << 16)
                            if seg_val == sid:
                                c += 1
                    pixel_counts[sid] = c

                for s in t_segs:
                    sid = s.get("id")
                    declared_area = s.get("area", 0)
                    actual_px = pixel_counts.get(sid, 0)
                    if declared_area > 0 and actual_px < declared_area:
                        diff = declared_area - actual_px
                        if diff >= 10 and (actual_px / declared_area) < 0.90:
                            errors.append({"type": "thing_overlap", "target": img_name})
                            break
            except Exception:
                pass

    # =========================================================================
    # ĐỐI CHIẾU DETECTION ↔ PANOPTIC ĐỂ SINH CANDIDATES
    # (class_swap, category_swap, bbox_drift, missing_box, instance_merge)
    # =========================================================================
    if candidates_path is not None:
        for img_name, item in manifest_items.items():
            label_rel = item.get("label")
            label_file = delivery_dir / label_rel if label_rel else None
            mask_rel = item.get("mask")
            mask_file = delivery_dir / mask_rel if mask_rel else None

            ann = pan_ann_by_file.get(img_name)
            if not ann:
                try:
                    numeric_id = int(img_name.lstrip("0") or "0")
                    ann = pan_ann_by_img_id.get(numeric_id)
                except ValueError:
                    ann = None

            if not label_file or not label_file.is_file() or not ann:
                continue

            # Đọc kích thước ảnh
            im_meta = pan_images.get(f"{img_name}.jpg") or pan_images.get(ann.get("file_name"))
            if not im_meta:
                im_meta = pan_images_by_id.get(ann.get("image_id"))
            W = im_meta["width"] if im_meta else 640
            H = im_meta["height"] if im_meta else 480

            # Đọc box YOLO
            det_boxes = []
            for ln in label_file.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                parts = ln.split()
                if len(parts) < 5:
                    continue
                c, x, y, w, h = int(float(parts[0])), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                if 0 <= c < len(classes80):
                    cname = classes80[c]
                else:
                    cname = f"class_{c}"
                # box tọa độ pixel [x1, y1, x2, y2]
                bx1, by1 = (x - w / 2) * W, (y - h / 2) * H
                bx2, by2 = (x + w / 2) * W, (y + h / 2) * H
                det_boxes.append({
                    "class_id": c,
                    "class_name": cname,
                    "norm": (x, y, w, h),
                    "box_px": (bx1, by1, bx2, by2),
                    "area_px": w * h * W * H,
                })

            # Đọc segment things
            thing_segs = []
            for s in ann.get("segments_info", []):
                cid = s.get("category_id")
                if cid in thing_cat_ids and not s.get("iscrowd"):
                    cname = cat_by_id.get(cid, {}).get("name", f"cat_{cid}")
                    sx, sy, sw, sh = s.get("bbox", [0, 0, 0, 0])
                    sbox_px = (sx, sy, sx + sw, sy + sh)
                    thing_segs.append({
                        "id": s["id"],
                        "category_id": cid,
                        "class_name": cname,
                        "area": s.get("area", 0),
                        "box_px": sbox_px,
                    })



            # 1. Kiểm tra instance_merge: 1 segment phủ 2 box detection cùng lớp
            for s in thing_segs:
                if s["area"] >= 512:
                    matching_same_class_boxes = []
                    for b in det_boxes:
                        if b["class_name"] == s["class_name"]:
                            # Kiểm tra xem box có nằm đáng kể trong segment không
                            biou = bbox_iou(b["box_px"], s["box_px"])
                            if biou > 0.15:
                                matching_same_class_boxes.append(b)
                    if len(matching_same_class_boxes) >= 2:
                        candidates.append({
                            "image": img_name,
                            "type": "instance_merge",
                            "class_name": s["class_name"],
                            "details": f"Segment {s['id']} ({s['class_name']}, {s['area']}px) chứa {len(matching_same_class_boxes)} box detection cùng lớp",
                        })

            # 2. Ghép từng box với segment tốt nhất
            for b in det_boxes:
                best_seg = None
                best_iou = 0.0
                for s in thing_segs:
                    iou = bbox_iou(b["box_px"], s["box_px"])
                    if iou > best_iou:
                        best_iou = iou
                        best_seg = s

                # Nếu IoU cao nhưng khác lớp -> class_swap hoặc category_swap!
                if best_seg and best_iou >= 0.40 and b["class_name"] != best_seg["class_name"]:
                    candidates.append({
                        "image": img_name,
                        "type": "class_swap",
                        "det_class": b["class_name"],
                        "pan_class": best_seg["class_name"],
                        "iou": round(best_iou, 3),
                        "details": f"Detection: {b['class_name']} vs Panoptic: {best_seg['class_name']} (IoU {best_iou:.2f})",
                    })

                # Nếu cùng lớp nhưng bbox bị lệch (bbox_drift)
                # Tín hiệu mạnh: IoU trung bình (0.15 - 0.65) và tâm bị trôi
                if best_seg and b["class_name"] == best_seg["class_name"] and b["area_px"] >= 1000:
                    bx1, by1, bx2, by2 = b["box_px"]
                    sx1, sy1, sx2, sy2 = best_seg["box_px"]
                    bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
                    scx, scy = (sx1 + sx2) / 2, (sy1 + sy2) / 2
                    bw, bh = bx2 - bx1, by2 - by1
                    sw, sh = sx2 - sx1, sy2 - sy1
                    drift_x = abs(bcx - scx) / max(1.0, bw)
                    drift_y = abs(bcy - scy) / max(1.0, bh)
                    if (drift_x > 0.12 or drift_y > 0.12) and best_iou < 0.70:
                        candidates.append({
                            "image": img_name,
                            "type": "bbox_drift",
                            "class_name": b["class_name"],
                            "iou": round(best_iou, 3),
                            "drift": round(max(drift_x, drift_y), 3),
                            "details": f"Box {b['class_name']} bị lệch khỏi mask (IoU {best_iou:.2f}, drift {max(drift_x, drift_y):.2f})",
                        })

            # 3. Kiểm tra missing_box: segment lớn mà không có box detection nào khớp cùng lớp
            matched_thing_indices = set()
            for b in det_boxes:
                best_s_idx = None
                best_s_iou = 0.0
                for idx, s in enumerate(thing_segs):
                    if s["class_name"] == b["class_name"]:
                        iou = bbox_iou(b["box_px"], s["box_px"])
                        if iou > best_s_iou:
                            best_s_iou = iou
                            best_s_idx = idx
                if best_s_idx is not None and best_s_iou > 0.35:
                    matched_thing_indices.add(best_s_idx)

            for idx, s in enumerate(thing_segs):
                if idx not in matched_thing_indices and s["area"] >= 2000:
                    candidates.append({
                        "image": img_name,
                        "type": "missing_box",
                        "class_name": s["class_name"],
                        "area": s["area"],
                        "details": f"Segment {s['class_name']} ({s['area']}px) không có box detection tương ứng",
                    })

    # Sắp xếp và loại trùng lặp
    unique_errors = sorted({(e["type"], e["target"]): e for e in errors}.values(), key=lambda x: (x["type"], x["target"]))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"errors": unique_errors}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[Validator] Đã phát hiện {len(unique_errors)} lỗi luật và ghi vào {out_path}")

    if candidates_path is not None:
        cand_p = Path(candidates_path)
        cand_p.parent.mkdir(parents=True, exist_ok=True)
        # Lọc trùng lặp candidates theo (image, type)
        seen_cand = set()
        unique_cands = []
        for c in candidates:
            key = (c["image"], c["type"])
            if key not in seen_cand:
                seen_cand.add(key)
                unique_cands.append(c)
        cand_p.write_text(json.dumps({"candidates": unique_cands}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[Validator] Đã trích xuất {len(unique_cands)} ứng viên đối chiếu và ghi vào {cand_p}")


def main():
    parser = argparse.ArgumentParser(description="Validator kiểm tra bàn giao dữ liệu")
    parser.add_argument("delivery_dir", help="Đường dẫn đến thư mục delivery/")
    parser.add_argument("--out", required=True, help="Đường dẫn file errors.json đầu ra")
    parser.add_argument("--candidates", help="Đường dẫn file candidates.json đầu ra (tùy chọn)")
    args = parser.parse_args()

    validate_delivery(Path(args.delivery_dir), Path(args.out), Path(args.candidates) if args.candidates else None)


if __name__ == "__main__":
    main()
