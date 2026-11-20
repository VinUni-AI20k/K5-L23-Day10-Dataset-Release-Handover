# validator/cross_check.py
import json
from pathlib import Path
import sys

# Cho phép import pngutil từ thư mục scripts
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import pngutil


def yolo_to_pixel(box, img_w, img_h):
    cls_id, x, y, w, h = box
    xmin = (x - w / 2.0) * img_w
    ymin = (y - h / 2.0) * img_h
    xmax = (x + w / 2.0) * img_w
    ymax = (y + h / 2.0) * img_h
    return int(cls_id), xmin, ymin, xmax, ymax


def bbox_iou(b1, b2):
    # b1, b2 = [xmin, ymin, xmax, ymax]
    ixmin = max(b1[0], b2[0])
    iymin = max(b1[1], b2[1])
    ixmax = min(b1[2], b2[2])
    iymax = min(b1[3], b2[3])
    inter = max(0.0, ixmax - ixmin) * max(0.0, iymax - iymin)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / (a1 + a2 - inter + 1e-12)


def extract_candidates(delivery_dir: Path, exclude_targets: set[str] | None = None) -> list[dict]:
    candidates = []
    excluded = set(exclude_targets or set())

    # 1. Đọc categories mapping từ classes.txt và panoptic.json
    classes_names = [line.split(" ", 1)[1].strip() for line in (delivery_dir / "classes.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    pan_doc = json.loads((delivery_dir / "panoptic.json").read_text(encoding="utf-8"))

    # Lấy các category là 'thing' và không phải crowd
    thing_cats = {c["id"]: c["name"] for c in pan_doc["categories"] if c.get("isthing")}
    pan_annotations = {a["image_id"]: a for a in pan_doc["annotations"]}
    pan_images = {im["file_name"].replace(".jpg", ""): im for im in pan_doc["images"]}

    # 2. Duyệt qua từng ảnh trong delivery/images
    for img_path in sorted((delivery_dir / "images").glob("*.jpg")):
        stem = img_path.stem

        # Bỏ qua các ảnh đã có lỗi luật (mỗi ảnh nhiều nhất 1 lỗi)
        if stem in excluded:
            continue

        label_path = delivery_dir / "labels" / f"{stem}.txt"
        mask_path = delivery_dir / "masks" / f"{stem}.png"

        if not label_path.is_file() or not mask_path.is_file():
            continue

        im_info = pan_images.get(stem)
        if not im_info:
            continue
        img_w, img_h = im_info["width"], im_info["height"]
        ann = pan_annotations.get(im_info["id"], {})

        # Đọc box YOLO theo index đếm từ 0 (khớp D0, D1... trên tool xem ảnh của nhóm)
        yolo_boxes = []
        for line_no, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=0):
            if line.strip():
                parts = line.split()
                cls_id = int(float(parts[0]))
                if 0 <= cls_id < len(classes_names):
                    _, bx1, by1, bx2, by2 = yolo_to_pixel([cls_id] + [float(p) for p in parts[1:5]], img_w, img_h)
                    yolo_boxes.append((line_no, cls_id, bx1, by1, bx2, by2))

        # Đọc segments thing từ panoptic
        thing_segs = [s for s in ann.get("segments_info", []) if s["category_id"] in thing_cats and not s.get("iscrowd")]

        # Đọc mask PNG để phân tích pixel
        width, height, pixels = pngutil.read_rgb(mask_path)

        # Đếm pixel và phân bố tọa độ thực của từng segment
        seg_pixels = {}
        for idx in range(0, len(pixels), 3):
            sid = pngutil.segment_id(pixels, idx)
            if sid:
                px = (idx // 3) % width
                py = (idx // 3) // width
                seg_pixels.setdefault(sid, []).append((px, py))

        # --- A. Kiểm tra instance_merge (2 box YOLO tách biệt bị gộp chung 1 mask panoptic) ---
        for seg in thing_segs:
            sid = seg["id"]
            pts = seg_pixels.get(sid, [])
            if len(pts) < 1024:
                continue
            seg_name = thing_cats[seg["category_id"]]

            box_matches = []
            for box in yolo_boxes:
                b_line, c_id, bx1, by1, bx2, by2 = box
                if classes_names[c_id] == seg_name:
                    in_box = sum(1 for (px, py) in pts if bx1 <= px <= bx2 and by1 <= py <= by2)
                    box_area = max(1.0, (bx2 - bx1) * (by2 - by1))
                    if (in_box >= 0.20 * len(pts) and in_box >= 0.35 * box_area) or (in_box >= 0.50 * box_area and in_box >= 500):
                        box_matches.append((b_line, in_box, box_area, (bx1, by1, bx2, by2)))

            for i in range(len(box_matches)):
                for j in range(i + 1, len(box_matches)):
                    b1_line, in1, a1, b1_coords = box_matches[i]
                    b2_line, in2, a2, b2_coords = box_matches[j]
                    # Hai box tách rời nhau nhưng gộp chung 1 segment lớn
                    if bbox_iou(b1_coords, b2_coords) < 0.25 and ((in1 + in2) >= 0.70 * len(pts) or (in1 / a1 >= 0.60 and in2 / a2 >= 0.60 and min(in1, in2) >= 800)):
                        candidates.append({
                            "target": stem,
                            "type": "instance_merge",
                            "box": [b1_line, b2_line],  # 0-based index
                            "segment": sid,
                            "note": f"Hai box {seg_name} tách biệt (D{b1_line}, D{b2_line}) bị gộp chung 1 segment (id {sid})."
                        })

        # --- B. Ghép cặp Box ↔ Segment để bắt class_swap, category_swap, bbox_drift ---
        matched_seg_ids = set()
        for box in yolo_boxes:
            b_line, c_id, bx1, by1, bx2, by2 = box
            b_name = classes_names[c_id]
            b_area = (bx2 - bx1) * (by2 - by1)

            best_iou = 0.0
            best_seg = None

            for seg in thing_segs:
                sx, sy, sw, sh = seg["bbox"]
                s_bbox = [sx, sy, sx + sw, sy + sh]
                iou = bbox_iou([bx1, by1, bx2, by2], s_bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_seg = seg

            if best_seg and best_iou > 0.3:
                matched_seg_ids.add(best_seg["id"])
                seg_name = thing_cats[best_seg["category_id"]]
                pts = seg_pixels.get(best_seg["id"], [])

                # 1. Trùng vị trí nhưng khác class -> class_swap hoặc category_swap
                if b_name != seg_name and best_iou > 0.4:
                    candidates.append({
                        "target": stem,
                        "type": "class_swap",
                        "box": b_line,  # 0-based index
                        "segment": best_seg["id"],
                        "note": f"Lệch lớp tại D{b_line}: YOLO={b_name} vs Panoptic={seg_name} (IoU={best_iou:.2f})"
                    })

                # 2. Cùng class nhưng lệch vị trí / pixel tràn ra ngoài -> bbox_drift
                elif b_name == seg_name and len(pts) > 0:
                    in_box_pts = sum(1 for (px, py) in pts if bx1 <= px <= bx2 and by1 <= py <= by2)
                    coverage = in_box_pts / len(pts)
                    if (coverage < 0.70 or best_iou < 0.42 or (best_iou < 0.74 and b_area > (0.02 * img_w * img_h))) and b_area > (0.005 * img_w * img_h):
                        candidates.append({
                            "target": stem,
                            "type": "bbox_drift",
                            "box": b_line,  # 0-based index
                            "segment": best_seg["id"],
                            "note": f"Box {b_name} tại D{b_line} lệch: IoU={best_iou:.2f}, tỷ lệ pixel trong box={coverage:.2f}"
                        })

        # --- C. Kiểm tra missing_box (Segment thing lớn nhưng không có box YOLO nào) ---
        for seg in thing_segs:
            if seg["id"] not in matched_seg_ids:
                pts = seg_pixels.get(seg["id"], [])
                seg_area_ratio = len(pts) / (img_w * img_h)
                if seg_area_ratio > 0.01 and len(pts) >= 1024:
                    seg_name = thing_cats[seg["category_id"]]
                    candidates.append({
                        "target": stem,
                        "type": "missing_box",
                        "box": None,
                        "segment": seg["id"],
                        "note": f"Thiếu box detection cho {seg_name} (id {seg['id']}, diện tích {len(pts)} px)"
                    })

    # --- D. Deduplicate: Mỗi ảnh chỉ giữ đúng 1 ứng viên duy nhất ---
    # Thứ tự ưu tiên khi trùng ảnh: class_swap > missing_box > instance_merge > bbox_drift
    TYPE_PRIORITY = {"class_swap": 4, "missing_box": 3, "instance_merge": 2, "bbox_drift": 1}
    by_target = {}
    for c in candidates:
        tgt = c["target"]
        pri = TYPE_PRIORITY.get(c["type"], 0)
        if tgt not in by_target or pri > by_target[tgt][0]:
            by_target[tgt] = (pri, c)

    return [item[1] for tgt, item in sorted(by_target.items())]
