#!/usr/bin/env python3
"""Module đối chiếu nhãn Detection ↔ Panoptic Segmentation (Pha 2 Lab Day 10).

Chức năng:
- Đọc thư mục delivery (chỉ dùng thư viện chuẩn Python).
- Đối chiếu nhãn YOLO (labels/*.txt) với Panoptic (panoptic.json + masks/*.png).
- Phát hiện các ứng viên nghi vấn cho 5 loại lỗi gán nhãn:
    1. class_swap: Detection gán nhầm lớp (khác với panoptic).
    2. category_swap: Panoptic gán nhầm lớp (khác với detection).
    3. bbox_drift: Box detection bị lệch tâm/kích thước so với segment.
    4. missing_box: Panoptic có vật thể thing nhưng detection thiếu box.
    5. instance_merge: Panoptic gộp nhiều vật thể cùng lớp thành một segment.
- Xuất file candidates.json và review_queue.csv để phân chia review bằng mắt.

Tác giả: Bạn C (Nhóm Lab Day 10)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


def calculate_iou(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    """Tính Intersection-over-Union (IoU) giữa 2 bounding box dạng [x, y, w, h]."""
    x1, y1, w1, h1 = box_a
    x2, y2, w2, h2 = box_b
    ix = max(0.0, min(x1 + w1, x2 + w2) - max(x1, x2))
    iy = max(0.0, min(y1 + h1, y2 + h2) - max(y1, y2))
    inter = ix * iy
    union = w1 * h1 + w2 * h2 - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def calculate_box_intersection(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    """Tính diện tích phần giao nhau giữa 2 bounding box."""
    x1, y1, w1, h1 = box_a
    x2, y2, w2, h2 = box_b
    ix = max(0.0, min(x1 + w1, x2 + w2) - max(x1, x2))
    iy = max(0.0, min(y1 + h1, y2 + h2) - max(y1, y2))
    return ix * iy


def greedy_match_boxes(boxes: list[dict], segments: list[dict]) -> list[tuple[float, int, int]]:
    """Ghép box với segment cùng lớp theo IoU giảm dần, bỏ các cặp không giao nhau."""
    pairs = []
    for segment_index, segment in enumerate(segments):
        for box_index, box in enumerate(boxes):
            iou = calculate_iou(box["bbox"], tuple(segment["bbox"]))
            if iou > 0.0:
                pairs.append((iou, segment_index, box_index))
    pairs.sort(reverse=True, key=lambda pair: pair[0])

    matched_segments = set()
    matched_boxes = set()
    matches = []
    for iou, segment_index, box_index in pairs:
        if segment_index in matched_segments or box_index in matched_boxes:
            continue
        matched_segments.add(segment_index)
        matched_boxes.add(box_index)
        matches.append((iou, segment_index, box_index))
    return matches


def has_distinct_box_pair(boxes: list[dict], max_iou: float = 0.40) -> bool:
    return any(
        calculate_iou(box_a["bbox"], box_b["bbox"]) < max_iou
        for index, box_a in enumerate(boxes)
        for box_b in boxes[index + 1 :]
    )


def load_classes(delivery_dir: Path) -> list[str]:
    """Đọc danh sách lớp từ classes.txt trong delivery."""
    classes_file = delivery_dir / "classes.txt"
    if not classes_file.is_file():
        return []
    lines = classes_file.read_text(encoding="utf-8").splitlines()
    classes = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            classes.append(parts[1])
        else:
            classes.append(parts[0])
    return classes


def load_yolo_boxes(label_file: Path, width: int, height: int, classes: list[str]) -> list[dict]:
    """Đọc nhãn YOLO và quy đổi về tọa độ pixel [x, y, w, h]."""
    if not label_file.is_file():
        return []
    boxes = []
    lines = label_file.read_text(encoding="utf-8").splitlines()
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        if not parts[0].isdigit():
            continue
        cid = int(parts[0])
        if not (0 <= cid < len(classes)):
            continue
        cname = classes[cid]
        try:
            xc, yc, w, h = map(float, parts[1:5])
        except ValueError:
            continue
        # Bounding box tọa độ pixel: x_min, y_min, w_px, h_px
        x_min = (xc - w / 2.0) * width
        y_min = (yc - h / 2.0) * height
        w_px = w * width
        h_px = h * height
        boxes.append({
            "cid": cid,
            "cname": cname,
            "bbox": (x_min, y_min, w_px, h_px),
            "norm": (xc, yc, w, h),
            "norm_area": w * h,
        })
    return boxes


def generate_candidates(delivery_dir: Path) -> list[dict]:
    """Hàm chính: Đối chiếu Detection ↔ Panoptic và trích xuất các ứng viên nghi vấn.
    
    Chỉ đọc từ thư mục delivery được truyền vào.
    Trả về danh sách các candidate dict.
    """
    delivery_dir = Path(delivery_dir)
    classes = load_classes(delivery_dir)
    panoptic_file = delivery_dir / "panoptic.json"
    if not panoptic_file.is_file():
        return []

    pan_doc = json.loads(panoptic_file.read_text(encoding="utf-8"))
    cat_by_id = {c["id"]: c for c in pan_doc.get("categories", [])}
    ann_by_im = {a["image_id"]: a for a in pan_doc.get("annotations", [])}
    images = pan_doc.get("images", [])

    candidates: list[dict] = []

    for im_entry in images:
        stem = Path(im_entry["file_name"]).stem
        img_id = im_entry["id"]
        width = im_entry["width"]
        height = im_entry["height"]
        total_px = width * height

        ann = ann_by_im.get(img_id)
        if not ann:
            continue

        # Chỉ xét các thing segments trong panoptic (bỏ qua stuff và iscrowd)
        segs = [
            s for s in ann.get("segments_info", [])
            if cat_by_id.get(s["category_id"], {}).get("isthing") and not s.get("iscrowd")
        ]

        label_file = delivery_dir / "labels" / f"{stem}.txt"
        boxes = load_yolo_boxes(label_file, width, height, classes)

        # -------------------------------------------------------------
        # 1. Phát hiện Class Mismatch (class_swap / category_swap)
        # -------------------------------------------------------------
        for b in boxes:
            best_s = None
            best_i = 0.0
            for s in segs:
                sc = calculate_iou(b["bbox"], tuple(s["bbox"]))
                if sc > best_i:
                    best_i = sc
                    best_s = s
            if best_s and best_i >= 0.40:
                sname = cat_by_id[best_s["category_id"]]["name"]
                if b["cname"] != sname:
                    # Ghi nhận cả class_swap và category_swap để người review quyết định
                    candidates.append({
                        "image": stem,
                        "type": "class_swap",
                        "detection_class": b["cname"],
                        "panoptic_class": sname,
                        "iou": round(best_i, 3),
                        "suggested_note": f"Lệch lớp: detection ghi {b['cname']}, panoptic ghi {sname} (IoU {best_i:.2f})"
                    })
                    candidates.append({
                        "image": stem,
                        "type": "category_swap",
                        "detection_class": b["cname"],
                        "panoptic_class": sname,
                        "iou": round(best_i, 3),
                        "suggested_note": f"Lệch lớp: panoptic ghi {sname}, detection ghi {b['cname']} (IoU {best_i:.2f})"
                    })

        # -------------------------------------------------------------
        # 2. Phát hiện Instance Merge (Panoptic gộp nhiều box cùng lớp)
        # -------------------------------------------------------------
        for s in segs:
            sname = cat_by_id[s["category_id"]]["name"]
            matching_boxes = [b for b in boxes if b["cname"] == sname and b["norm_area"] * total_px >= 400]
            matching_segs = [seg for seg in segs if cat_by_id[seg["category_id"]]["name"] == sname]
            # Nếu số box detection nhiều hơn số segment panoptic cùng lớp
            if len(matching_boxes) > len(matching_segs):
                contained_boxes = []
                for b in matching_boxes:
                    inter = calculate_box_intersection(b["bbox"], tuple(s["bbox"]))
                    b_area = b["bbox"][2] * b["bbox"][3]
                    if b_area > 0 and (inter / b_area) >= 0.65:
                        contained_boxes.append(b)
                if len(contained_boxes) >= 2:
                    if has_distinct_box_pair(contained_boxes):
                        candidates.append({
                            "image": stem,
                            "type": "instance_merge",
                            "class": sname,
                            "num_boxes": len(contained_boxes),
                            "suggested_note": f"Panoptic gộp {len(contained_boxes)} vật thể {sname} thành một segment"
                        })

        # -------------------------------------------------------------
        # 3. Greedy Bipartite Matching cho BBox Drift và Missing Box
        # -------------------------------------------------------------
        unique_classes = set(cat_by_id[s["category_id"]]["name"] for s in segs)
        for cat_name in unique_classes:
            c_segs = [s for s in segs if cat_by_id[s["category_id"]]["name"] == cat_name]
            c_boxes = [b for b in boxes if b["cname"] == cat_name]

            matches = greedy_match_boxes(c_boxes, c_segs)
            matched_segs = {segment_index for _, segment_index, _ in matches}
            matched_boxes_indices = {box_index for _, _, box_index in matches}

            for sc, s_idx, b_idx in matches:
                s = c_segs[s_idx]
                b = c_boxes[b_idx]

                # Kiểm tra bbox_drift
                if b["norm_area"] >= 0.005:
                    bx_c = b["bbox"][0] + b["bbox"][2] / 2.0
                    by_c = b["bbox"][1] + b["bbox"][3] / 2.0
                    sx_c = s["bbox"][0] + s["bbox"][2] / 2.0
                    sy_c = s["bbox"][1] + s["bbox"][3] / 2.0
                    b_diag = math.sqrt(b["bbox"][2] ** 2 + b["bbox"][3] ** 2)
                    c_dist = math.sqrt((bx_c - sx_c) ** 2 + (by_c - sy_c) ** 2)
                    drift_ratio = c_dist / (b_diag + 1e-6)

                    # IoU giảm đáng kể hoặc tâm bị dịch chuyển
                    if 0.35 <= sc <= 0.78 and drift_ratio >= 0.08:
                        candidates.append({
                            "image": stem,
                            "type": "bbox_drift",
                            "class": cat_name,
                            "iou": round(sc, 3),
                            "drift_ratio": round(drift_ratio, 3),
                            "suggested_note": f"Box detection {cat_name} bị lệch tâm {drift_ratio*100:.1f}%, IoU đạt {sc:.2f}"
                        })

            # Danh sách các box chưa được ghép với segment nào
            matched_box_ids = {id(c_boxes[idx]) for idx in matched_boxes_indices}
            unmatched_boxes = [b for b in boxes if id(b) not in matched_box_ids]

            # Kiểm tra missing_box: segment thing lớn không có box matching
            for s_idx, s in enumerate(c_segs):
                if s_idx not in matched_segs:
                    s_norm_area = (s["bbox"][2] * s["bbox"][3]) / (total_px + 1e-6)
                    if s.get("area", 0) >= 1000 and s_norm_area >= 0.01:
                        # Kiểm tra xem có box nào chưa ghép đè lên không (tránh trùng với class_swap)
                        best_unmatched = max([calculate_iou(b["bbox"], tuple(s["bbox"])) for b in unmatched_boxes] or [0.0])
                        if best_unmatched < 0.40:
                            candidates.append({
                                "image": stem,
                                "type": "missing_box",
                                "class": cat_name,
                                "area": s.get("area", 0),
                                "norm_area": round(s_norm_area, 4),
                                "suggested_note": f"Thiếu box detection cho {cat_name} (diện tích segment {s.get('area', 0)} px)"
                            })

    # Khử trùng lặp candidate theo (image, type)
    unique_candidates: list[dict] = []
    seen = set()
    for c in candidates:
        key = (c["image"], c["type"])
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    unique_candidates.sort(key=lambda x: (x["image"], x["type"]))
    return unique_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Đối chiếu Detection ↔ Panoptic để tìm ứng viên lỗi gán nhãn")
    parser.add_argument("delivery", help="Đường dẫn thư mục delivery cần đối chiếu")
    parser.add_argument("--out", default="candidates.json", help="Đường dẫn file candidates.json xuất ra")
    parser.add_argument("--csv", default=None, help="Đường dẫn file review_queue.csv xuất ra")
    args = parser.parse_args()

    delivery_dir = Path(args.delivery)
    if not delivery_dir.is_dir():
        print(f"Lỗi: Không tìm thấy thư mục {delivery_dir}", file=sys.stderr)
        return 1

    candidates = generate_candidates(delivery_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"candidates": candidates}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"-> Đã xuất {len(candidates)} ứng viên vào {out_path}")

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["image", "type", "verdict", "note"])
            writer.writeheader()
            for c in candidates:
                writer.writerow({
                    "image": c["image"],
                    "type": c["type"],
                    "verdict": "",
                    "note": c.get("suggested_note", "")
                })
        print(f"-> Đã xuất hàng đợi review vào {csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
