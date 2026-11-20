#!/usr/bin/env python3
"""Đối chiếu nhãn Detection (YOLO) <-> Panoptic để sinh ứng viên lỗi gán nhãn (Phần 2).

Yêu cầu chức năng: REV-01 .. REV-06 (work/02-annotation-review.md).
Ràng buộc tuân thủ (RULES.md):
- Chỉ đọc thư mục delivery/ được truyền vào.
- Chỉ dùng thư viện chuẩn Python và scripts/pngutil.py (KHÔNG dùng Pillow, KHÔNG dùng mạng).
- Không đọc _private/, data_source/, annotation COCO; không gắn cứng seed hay tên ảnh.

Giao diện tích hợp cho validator/validate.py (phối hợp Người 1):
    from cross_check import find_candidates, write_candidates
    write_candidates(delivery_dir, Path(args.candidates))

Chạy độc lập để đo trên lô sạch hoặc kiểm tra trước khi ghép entrypoint:
    py validator/cross_check.py runs/clean/delivery --out runs/clean/candidates.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Cho phép import scripts/pngutil.py (thư viện chuẩn đọc PNG của lab)
_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import pngutil  # noqa: E402


# Ngưỡng mặc định đã hiệu chỉnh dựa trên phân bố thực tế của lô sạch (runs/clean: 50 ảnh, 435 vật sạch).
# Trên runs/clean: 100% vật sạch có mask_in_box=1.0; vật nhìn rõ (>=0.3%) có IoU>=0.908, lệch tâm<=0.040.
DEFAULT_THRESHOLDS: dict[str, float] = {
    # Lọc đối tượng đủ lớn để con người nhìn rõ khi review
    "min_box_area_ratio": 0.0035,        # box chiếm >= 0.35% diện tích ảnh (swap / drift)
    "min_seg_px": 600,                   # segment >= 600 pixel (swap / drift / merge)
    # Khóa ghép 1-1 rất chắc trước khi xét instance_merge để tránh báo nhầm vật chồng lấn góc nhìn
    "exact_match_iou": 0.80,
    "exact_match_mask": 0.90,
    # REV-03: class_swap / category_swap (khớp vị trí tốt nhưng khác tên lớp)
    "swap_min_iou": 0.60,
    "swap_min_mask_in_box": 0.75,
    # REV-04: bbox_drift (cùng lớp nhưng mask tràn khỏi box hoặc box lệch mạnh)
    "drift_max_mask_in_box": 0.95,       # < 95% pixel mask nằm trong box -> dấu hiệu box lệch
    "drift_spill_max_iou": 0.92,         # tránh báo nhầm khi IoU bbox vẫn rất cao
    "drift_low_iou": 0.78,               # IoU giảm rõ rệt dù cùng lớp
    "drift_low_iou_max_mask": 0.99,      # tránh báo nhầm vật bị che (mask nằm gọn 100% trong box lớn)
    "drift_min_center_shift": 0.08,      # độ lệch tâm chuẩn hóa theo kích thước trung bình box/segment
    "drift_min_abs_seg_px": 150,         # sàn pixel tối thiểu để tránh nhiễu ảnh nhỏ
    # REV-05: missing_box (segment thing đáng kể không có box cùng lớp phù hợp)
    "missing_min_seg_px": 800,           # segment đủ lớn để là vật đáng kể (lô sạch max unmatched=299 px)
    "missing_min_area_ratio": 0.004,     # hoặc chiếm >= 0.4% diện tích ảnh
    "missing_min_abs_seg_px": 250,       # sàn pixel tối thiểu trên ảnh kích thước nhỏ
    "missing_max_same_mask_in_box": 0.45,
    # REV-06: instance_merge (1 segment chứa pixel của >= 2 box cùng lớp tách biệt)
    "merge_min_seg_px": 600,
    "merge_max_box_iou": 0.65,           # loại cặp duplicate_box (chồng gần như hoàn toàn)
    "merge_min_part_px": 150,            # mỗi box chứa ít nhất 150 pixel của segment
    "merge_min_part_ratio": 0.12,        # mỗi box chứa >= 12% pixel của segment
    "merge_min_union_gain": 0.12,        # hợp 2 box phủ thêm >= 12% pixel segment so với 1 box
    # Ngưỡng ghép cặp nội bộ
    "strong_match_iou": 0.50,
    "strong_match_mask": 0.50,
    "relaxed_match_iou": 0.12,
    "relaxed_match_mask": 0.22,
}


def _delivery_path(delivery: Path, relative: str) -> Path:
    """Bảo đảm đường dẫn từ manifest nằm hoàn toàn trong thư mục delivery/."""
    path = (delivery / relative).resolve()
    if not path.is_relative_to(delivery.resolve()):
        raise ValueError(f"Path outside delivery: {relative}")
    return path


def load_classes(delivery: Path) -> dict[int, str]:
    """REV-02: Đọc classes.txt -> map class_id YOLO (0..79) sang tên lớp."""
    classes: dict[int, str] = {}
    path = delivery / "classes.txt"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            classes[int(parts[0])] = parts[1].strip()
    return classes


def load_yolo_boxes(
    label_path: Path,
    width: int,
    height: int,
    det_classes: dict[int, str],
) -> list[dict[str, Any]]:
    """REV-01: Đọc file nhãn YOLO và quy đổi sang tọa độ pixel [x1, y1, x2, y2].

    Bỏ qua an toàn các dòng bị lỗi class_id không hợp lệ (thuộc lỗi luật invalid_class).
    """
    if not label_path.is_file():
        return []
    boxes: list[dict[str, Any]] = []
    img_area = max(1, width * height)
    for idx, raw_line in enumerate(label_path.read_text(encoding="utf-8").splitlines()):
        parts = raw_line.strip().split()
        if len(parts) < 5:
            continue
        try:
            cls_id = int(float(parts[0]))
            xc, yc, bw, bh = map(float, parts[1:5])
        except ValueError:
            continue
        if cls_id not in det_classes or bw <= 0 or bh <= 0:
            continue
        x1 = (xc - bw / 2.0) * width
        y1 = (yc - bh / 2.0) * height
        x2 = (xc + bw / 2.0) * width
        y2 = (yc + bh / 2.0) * height
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        boxes.append(
            {
                "index": idx,
                "class_id": cls_id,
                "class_name": det_classes[cls_id],
                "bbox": [x1, y1, x2, y2],
                "area": area,
                "area_ratio": area / img_area,
            }
        )
    return boxes


def bbox_iou(a: list[float], b: list[float]) -> float:
    """Tính IoU giữa 2 hình chữ nhật [x1, y1, x2, y2]."""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


def center_shift_norm(a: list[float], b: list[float]) -> float:
    """Độ lệch tâm giữa 2 bbox, chuẩn hóa theo kích thước trung bình của 2 bbox."""
    acx, acy = (a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0
    bcx, bcy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    scale_w = max(1.0, ((a[2] - a[0]) + (b[2] - b[0])) / 2.0)
    scale_h = max(1.0, ((a[3] - a[1]) + (b[3] - b[1])) / 2.0)
    dx = (acx - bcx) / scale_w
    dy = (acy - bcy) / scale_h
    return math.hypot(dx, dy)


def _clamp_box(bbox: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    """Kẹp tọa độ pixel vào [0, width] x [0, height] để cắt mảng an toàn."""
    x1 = max(0, min(width, int(math.floor(bbox[0]))))
    y1 = max(0, min(height, int(math.floor(bbox[1]))))
    x2 = max(0, min(width, int(math.ceil(bbox[2]))))
    y2 = max(0, min(height, int(math.ceil(bbox[3]))))
    return x1, y1, x2, y2


def _count_rgb_in_rect(
    r_ch: bytearray,
    g_ch: bytearray,
    b_ch: bytearray,
    width: int,
    rect: tuple[int, int, int, int],
) -> Counter[tuple[int, int, int]]:
    """Đếm số pixel theo màu RGB (mã hóa segment_id) bên trong một hình chữ nhật."""
    x1, y1, x2, y2 = rect
    counts: Counter[tuple[int, int, int]] = Counter()
    if x1 >= x2 or y1 >= y2:
        return counts
    for y in range(y1, y2):
        off = y * width
        counts.update(zip(r_ch[off + x1 : off + x2], g_ch[off + x1 : off + x2], b_ch[off + x1 : off + x2]))
    return counts


def _count_target_in_union(
    r_ch: bytearray,
    g_ch: bytearray,
    b_ch: bytearray,
    width: int,
    rect_a: tuple[int, int, int, int],
    rect_b: tuple[int, int, int, int],
    target_rgb: tuple[int, int, int],
    count_a: int,
    count_b: int,
) -> int:
    """Tính chính xác số pixel của một segment nằm trong hợp (rect_a U rect_b)."""
    ix1 = max(rect_a[0], rect_b[0])
    iy1 = max(rect_a[1], rect_b[1])
    ix2 = min(rect_a[2], rect_b[2])
    iy2 = min(rect_a[3], rect_b[3])
    if ix1 >= ix2 or iy1 >= iy2:
        return count_a + count_b
    inter_cnt = 0
    for y in range(iy1, iy2):
        off = y * width
        for rgb in zip(r_ch[off + ix1 : off + ix2], g_ch[off + ix1 : off + ix2], b_ch[off + ix1 : off + ix2]):
            if rgb == target_rgb:
                inter_cnt += 1
    return count_a + count_b - inter_cnt


def _analyze_image(
    stem: str,
    width: int,
    height: int,
    boxes: list[dict[str, Any]],
    ann: dict[str, Any],
    mask_path: Path,
    cat_by_id: dict[int, dict[str, Any]],
    cfg: dict[str, float],
) -> list[dict[str, Any]]:
    """Đối chiếu detection <-> panoptic cho một ảnh và trả về danh sách ứng viên."""
    if not mask_path.is_file():
        return []

    m_width, m_height, pixels = pngutil.read_rgb(mask_path)
    width = width or m_width
    height = height or m_height
    img_area = max(1, width * height)

    # Tách 3 kênh R, G, B một lần để đếm pixel ở tốc độ C (Counter + zip)
    r_ch = pixels[0::3]
    g_ch = pixels[1::3]
    b_ch = pixels[2::3]
    total_rgb_counts = Counter(zip(r_ch, g_ch, b_ch))

    # Lọc các segment panoptic hợp lệ: chỉ lấy thing (isthing=1), không lấy iscrowd=1
    segments: list[dict[str, Any]] = []
    for raw_seg in ann.get("segments_info", []):
        cat = cat_by_id.get(raw_seg.get("category_id"))
        if not cat or not cat.get("isthing"):
            continue
        if raw_seg.get("iscrowd"):
            continue
        sid = int(raw_seg["id"])
        rgb = pngutil.segment_rgb(sid)
        actual_px = int(total_rgb_counts.get(rgb, 0))
        declared_area = int(raw_seg.get("area", 0))
        if actual_px <= 0:
            continue
        sx, sy, sw, sh = map(float, raw_seg["bbox"])
        seg_bbox = [sx, sy, sx + sw, sy + sh]
        area_mismatch = (
            declared_area > 0 and abs(actual_px - declared_area) / declared_area > 0.05
        )
        segments.append(
            {
                "id": sid,
                "rgb": rgb,
                "category_id": int(raw_seg["category_id"]),
                "class_name": str(cat["name"]),
                "area_px": actual_px,
                "declared_area": declared_area,
                "area_ratio": actual_px / img_area,
                "bbox": seg_bbox,
                "area_mismatch": area_mismatch,
            }
        )

    if not segments and not boxes:
        return []

    # Đếm pixel của các segment nằm trong từng detection box (chỉ quét nếu box giao ít nhất 1 thing segment)
    clamped_boxes = [_clamp_box(b["bbox"], width, height) for b in boxes]
    box_seg_px: list[dict[int, int]] = [{} for _ in boxes]
    for bi, box in enumerate(boxes):
        # Kiểm tra nhanh xem box có giao bbox của bất kỳ thing segment nào không
        has_overlap = any(bbox_iou(box["bbox"], s["bbox"]) > 0.0 for s in segments)
        if not has_overlap:
            continue
        rect_counts = _count_rgb_in_rect(r_ch, g_ch, b_ch, width, clamped_boxes[bi])
        for si, seg in enumerate(segments):
            cnt = rect_counts.get(seg["rgb"], 0)
            if cnt > 0:
                box_seg_px[bi][si] = int(cnt)

    # Tính trước bảng cặp (bi, si) -> (iou, mask_in_box, inter_px)
    pair_stats: dict[tuple[int, int], tuple[float, float, int]] = {}
    for bi, box in enumerate(boxes):
        for si, seg in enumerate(segments):
            inter_px = box_seg_px[bi].get(si, 0)
            iou = bbox_iou(box["bbox"], seg["bbox"])
            if inter_px > 0 or iou > 0.0:
                mask_in_box = inter_px / seg["area_px"]
                pair_stats[(bi, si)] = (iou, mask_in_box, inter_px)

    candidates: list[dict[str, Any]] = []
    used_boxes: set[int] = set()
    used_segs: set[int] = set()
    same_matches: list[tuple[int, int]] = []

    # ------------------------------------------------------------------
    # Bước 1: Khóa trước các cặp cùng lớp khớp 1-1 rất chắc (IoU & mask_in_box cao)
    # Tránh lỗi chồng lấn trước/sau (3 vật cùng lớp che đè góc nhìn) bị báo nhầm instance_merge.
    # Các cặp này vẫn đi vào same_matches để Bước 5 kiểm tra bbox_drift.
    # ------------------------------------------------------------------
    exact_same_pairs = []
    for (bi, si), (iou, mask_in_box, inter_px) in pair_stats.items():
        if boxes[bi]["class_name"] != segments[si]["class_name"]:
            continue
        if iou >= cfg["exact_match_iou"] and mask_in_box >= cfg["exact_match_mask"]:
            exact_same_pairs.append((0.5 * iou + 0.5 * mask_in_box, inter_px, bi, si))

    exact_same_pairs.sort(reverse=True)
    for _, _, bi, si in exact_same_pairs:
        if bi in used_boxes or si in used_segs:
            continue
        used_boxes.add(bi)
        used_segs.add(si)
        same_matches.append((bi, si))

    # ------------------------------------------------------------------
    # Bước 2 (REV-06): Tìm dấu hiệu instance_merge trên các box/segment chưa khớp 1-1 chắc
    # Một segment thing là segment cùng lớp phù hợp nhất của >= 2 box tách biệt.
    # ------------------------------------------------------------------
    best_same_seg_for_box: dict[int, int] = {}
    for bi, box in enumerate(boxes):
        if bi in used_boxes:
            continue
        best_si = None
        best_key = (0.0, 0)
        for si, seg in enumerate(segments):
            if si in used_segs:
                continue
            if seg["class_name"] != box["class_name"]:
                continue
            stat = pair_stats.get((bi, si))
            if not stat:
                continue
            iou, mask_in_box, inter_px = stat
            if inter_px < cfg["merge_min_part_px"]:
                continue
            # Xếp hạng theo độ khớp tổng hợp (IoU + mask_in_box) thay vì số pixel thô
            key = (0.5 * iou + 0.5 * mask_in_box, inter_px)
            if key > best_key:
                best_key = key
                best_si = si
        if best_si is not None:
            best_same_seg_for_box[bi] = best_si

    boxes_by_dominant_seg: dict[int, list[int]] = {}
    for bi, si in best_same_seg_for_box.items():
        boxes_by_dominant_seg.setdefault(si, []).append(bi)

    for si, bi_list in boxes_by_dominant_seg.items():
        seg = segments[si]
        if len(bi_list) < 2 or seg["area_px"] < cfg["merge_min_seg_px"]:
            continue
        # Sắp theo số pixel segment chứa trong mỗi box giảm dần
        bi_sorted = sorted(bi_list, key=lambda b_idx: pair_stats[(b_idx, si)][2], reverse=True)
        best_merge_pair = None
        best_gain = 0.0
        for i_idx in range(len(bi_sorted)):
            for j_idx in range(i_idx + 1, len(bi_sorted)):
                b1, b2 = bi_sorted[i_idx], bi_sorted[j_idx]
                # Loại cặp duplicate_box (2 box gần như trùng khít nhau)
                b_pair_iou = bbox_iou(boxes[b1]["bbox"], boxes[b2]["bbox"])
                if b_pair_iou >= cfg["merge_max_box_iou"]:
                    continue
                iou1, mib1, px1 = pair_stats[(b1, si)]
                iou2, mib2, px2 = pair_stats[(b2, si)]
                if min(mib1, mib2) < cfg["merge_min_part_ratio"]:
                    continue
                union_px = _count_target_in_union(
                    r_ch, g_ch, b_ch, width,
                    clamped_boxes[b1], clamped_boxes[b2],
                    seg["rgb"], px1, px2,
                )
                union_cov = union_px / seg["area_px"]
                gain = union_cov - max(mib1, mib2)
                if gain >= cfg["merge_min_union_gain"] and gain > best_gain:
                    best_gain = gain
                    best_merge_pair = (b1, b2, b_pair_iou, mib1, mib2, union_cov, gain)

        if best_merge_pair is not None:
            b1, b2, b_pair_iou, mib1, mib2, union_cov, gain = best_merge_pair
            used_segs.add(si)
            used_boxes.add(b1)
            used_boxes.add(b2)
            note_warn = " [lưu ý: area mask khác khai báo, kiểm tra lỗi luật thing_overlap]" if seg["area_mismatch"] else ""
            candidates.append(
                {
                    "image": stem,
                    "suggested_types": ["instance_merge"],
                    "reason": (
                        f"1 segment panoptic ({seg['class_name']}, {seg['area_px']} px) phủ lên 2 box cùng lớp tách biệt "
                        f"(box IoU={b_pair_iou:.2f}, tỷ lệ mask trong từng box={mib1:.2f}/{mib2:.2f}, "
                        f"hợp 2 box phủ={union_cov:.2f}, tăng thêm={gain:.2f}){note_warn}"
                    ),
                    "det_boxes_px": [
                        [round(v, 1) for v in boxes[b1]["bbox"]],
                        [round(v, 1) for v in boxes[b2]["bbox"]],
                    ],
                    "det_class": seg["class_name"],
                    "pan_segment_id": seg["id"],
                    "pan_bbox_px": [round(v, 1) for v in seg["bbox"]],
                    "pan_class": seg["class_name"],
                    "metrics": {
                        "pair_box_iou": round(b_pair_iou, 4),
                        "mask_in_box_1": round(mib1, 4),
                        "mask_in_box_2": round(mib2, 4),
                        "union_mask_coverage": round(union_cov, 4),
                        "union_gain": round(gain, 4),
                        "seg_area_px": seg["area_px"],
                    },
                    "warnings": ["area_mismatch_possible_thing_overlap"] if seg["area_mismatch"] else [],
                }
            )

    # ------------------------------------------------------------------
    # Bước 2b: Ghép 1-1 mạnh cho các cặp cùng tên lớp còn lại
    # ------------------------------------------------------------------
    strong_same_pairs = []
    for (bi, si), (iou, mask_in_box, inter_px) in pair_stats.items():
        if bi in used_boxes or si in used_segs:
            continue
        if boxes[bi]["class_name"] != segments[si]["class_name"]:
            continue
        if iou >= cfg["strong_match_iou"] and mask_in_box >= cfg["strong_match_mask"]:
            strong_same_pairs.append((0.5 * iou + 0.5 * mask_in_box, bi, si))

    strong_same_pairs.sort(reverse=True)
    for _, bi, si in strong_same_pairs:
        if bi in used_boxes or si in used_segs:
            continue
        used_boxes.add(bi)
        used_segs.add(si)
        same_matches.append((bi, si))

    # ------------------------------------------------------------------
    # Bước 3 (REV-03): Tìm cặp khớp vị trí tốt nhưng khác tên lớp
    # -> ứng viên class_swap hoặc category_swap (mở ảnh để biết bên nào sai)
    # ------------------------------------------------------------------
    swap_pairs = []
    for (bi, si), (iou, mask_in_box, inter_px) in pair_stats.items():
        if bi in used_boxes or si in used_segs:
            continue
        if boxes[bi]["class_name"] == segments[si]["class_name"]:
            continue
        if iou >= cfg["swap_min_iou"] and mask_in_box >= cfg["swap_min_mask_in_box"]:
            if boxes[bi]["area_ratio"] >= cfg["min_box_area_ratio"] or segments[si]["area_px"] >= cfg["min_seg_px"]:
                swap_pairs.append((0.5 * iou + 0.5 * mask_in_box, bi, si))

    swap_pairs.sort(reverse=True)
    for _, bi, si in swap_pairs:
        if bi in used_boxes or si in used_segs:
            continue
        used_boxes.add(bi)
        used_segs.add(si)
        box, seg = boxes[bi], segments[si]
        iou, mask_in_box, inter_px = pair_stats[(bi, si)]
        note_warn = " [lưu ý: area mask khác khai báo]" if seg["area_mismatch"] else ""
        candidates.append(
            {
                "image": stem,
                "suggested_types": ["class_swap", "category_swap"],
                "reason": (
                    f"Cùng vị trí nhưng khác tên lớp: Detection='{box['class_name']}' vs "
                    f"Panoptic='{seg['class_name']}' (IoU={iou:.2f}, mask_in_box={mask_in_box:.2f}, "
                    f"seg={seg['area_px']} px). Mở ảnh xác định bên sai.{note_warn}"
                ),
                "det_boxes_px": [[round(v, 1) for v in box["bbox"]]],
                "det_class": box["class_name"],
                "pan_segment_id": seg["id"],
                "pan_bbox_px": [round(v, 1) for v in seg["bbox"]],
                "pan_class": seg["class_name"],
                "metrics": {
                    "iou": round(iou, 4),
                    "mask_in_box": round(mask_in_box, 4),
                    "inter_px": inter_px,
                    "box_area_ratio": round(box["area_ratio"], 5),
                    "seg_area_px": seg["area_px"],
                },
                "warnings": ["area_mismatch_possible_thing_overlap"] if seg["area_mismatch"] else [],
            }
        )

    # ------------------------------------------------------------------
    # Bước 4: Ghép 1-1 nới lỏng cho các cặp cùng lớp còn lại (bắt box bị lệch mạnh)
    # ------------------------------------------------------------------
    relaxed_same_pairs = []
    for (bi, si), (iou, mask_in_box, inter_px) in pair_stats.items():
        if bi in used_boxes or si in used_segs:
            continue
        if boxes[bi]["class_name"] != segments[si]["class_name"]:
            continue
        if iou >= cfg["relaxed_match_iou"] or mask_in_box >= cfg["relaxed_match_mask"]:
            relaxed_same_pairs.append((0.5 * iou + 0.5 * mask_in_box, bi, si))

    relaxed_same_pairs.sort(reverse=True)
    for _, bi, si in relaxed_same_pairs:
        if bi in used_boxes or si in used_segs:
            continue
        used_boxes.add(bi)
        used_segs.add(si)
        same_matches.append((bi, si))

    # ------------------------------------------------------------------
    # Bước 5 (REV-04): Kiểm tra bbox_drift trên tất cả cặp cùng lớp đã ghép
    # ------------------------------------------------------------------
    for bi, si in same_matches:
        box, seg = boxes[bi], segments[si]
        if seg["area_px"] < cfg["drift_min_abs_seg_px"]:
            continue
        if box["area_ratio"] < cfg["min_box_area_ratio"] and seg["area_px"] < cfg["min_seg_px"]:
            continue
        iou, mask_in_box, inter_px = pair_stats[(bi, si)]
        c_shift = center_shift_norm(box["bbox"], seg["bbox"])

        mask_spill = (
            mask_in_box < cfg["drift_max_mask_in_box"]
            and iou < cfg["drift_spill_max_iou"]
        )
        geom_shift = (
            iou < cfg["drift_low_iou"]
            and mask_in_box < cfg["drift_low_iou_max_mask"]
            and c_shift >= cfg["drift_min_center_shift"]
        )

        if mask_spill or geom_shift:
            note_warn = " [lưu ý: area mask khác khai báo, kiểm tra thing_overlap]" if seg["area_mismatch"] else ""
            candidates.append(
                {
                    "image": stem,
                    "suggested_types": ["bbox_drift"],
                    "reason": (
                        f"Box '{box['class_name']}' lệch khỏi mask cùng lớp: "
                        f"mask_in_box={mask_in_box:.2f} ({(1.0 - mask_in_box) * 100:.0f}% pixel mask ra ngoài box), "
                        f"IoU={iou:.2f}, lệch tâm={c_shift:.2f}{note_warn}"
                    ),
                    "det_boxes_px": [[round(v, 1) for v in box["bbox"]]],
                    "det_class": box["class_name"],
                    "pan_segment_id": seg["id"],
                    "pan_bbox_px": [round(v, 1) for v in seg["bbox"]],
                    "pan_class": seg["class_name"],
                    "metrics": {
                        "iou": round(iou, 4),
                        "mask_in_box": round(mask_in_box, 4),
                        "center_shift": round(c_shift, 4),
                        "box_area_ratio": round(box["area_ratio"], 5),
                        "seg_area_px": seg["area_px"],
                    },
                    "warnings": ["area_mismatch_possible_thing_overlap"] if seg["area_mismatch"] else [],
                }
            )

    # ------------------------------------------------------------------
    # Bước 6 (REV-05): Tìm segment thing đáng kể chưa có box cùng lớp phù hợp
    # ------------------------------------------------------------------
    for si, seg in enumerate(segments):
        if si in used_segs:
            continue
        if seg["area_px"] < cfg["missing_min_abs_seg_px"]:
            continue
        if seg["area_px"] < cfg["missing_min_seg_px"] and seg["area_ratio"] < cfg["missing_min_area_ratio"]:
            continue
        # Tránh báo nhầm nếu một box cùng lớp khác đã bao phủ phần lớn segment này
        max_same_mib = 0.0
        for bi, box in enumerate(boxes):
            if box["class_name"] == seg["class_name"]:
                stat = pair_stats.get((bi, si))
                if stat and stat[1] > max_same_mib:
                    max_same_mib = stat[1]
        if max_same_mib >= cfg["missing_max_same_mask_in_box"]:
            continue

        note_warn = " [lưu ý: area mask khác khai báo]" if seg["area_mismatch"] else ""
        candidates.append(
            {
                "image": stem,
                "suggested_types": ["missing_box"],
                "reason": (
                    f"Segment panoptic '{seg['class_name']}' đáng kể ({seg['area_px']} px, "
                    f"{seg['area_ratio'] * 100:.2f}% ảnh) không có box detection cùng lớp phù hợp "
                    f"(max mask_in_box cùng lớp={max_same_mib:.2f}){note_warn}"
                ),
                "det_boxes_px": [],
                "det_class": None,
                "pan_segment_id": seg["id"],
                "pan_bbox_px": [round(v, 1) for v in seg["bbox"]],
                "pan_class": seg["class_name"],
                "metrics": {
                    "seg_area_px": seg["area_px"],
                    "seg_area_ratio": round(seg["area_ratio"], 5),
                    "max_same_class_mask_in_box": round(max_same_mib, 4),
                },
                "warnings": ["area_mismatch_possible_thing_overlap"] if seg["area_mismatch"] else [],
            }
        )

    return candidates


def find_candidates(
    delivery_dir: str | Path,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Chạy đối chiếu Detection <-> Panoptic cho toàn bộ thư mục delivery/.

    Trả về dict có thể tuần tự hóa thẳng ra candidates.json:
        {
            "delivery": "...",
            "thresholds": {...},
            "summary": {...},
            "candidates": [...]
        }
    """
    delivery = Path(delivery_dir)
    cfg = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        cfg.update(thresholds)

    det_classes = load_classes(delivery)
    panoptic = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]

    cat_by_id = {int(c["id"]): c for c in panoptic.get("categories", [])}
    img_by_stem: dict[str, dict[str, Any]] = {}
    for im in panoptic.get("images", []):
        stem = Path(im["file_name"]).stem
        img_by_stem[stem] = im

    ann_by_image_id = {ann["image_id"]: ann for ann in panoptic.get("annotations", [])}

    all_candidates: list[dict[str, Any]] = []
    scanned_images = 0
    skipped_missing_images = 0

    for stem in sorted(manifest.keys()):
        item = manifest[stem]
        # Bỏ qua ảnh bị thiếu file (lỗi luật missing_image, không thể mở ảnh review)
        if not _delivery_path(delivery, item["image"]).is_file():
            skipped_missing_images += 1
            continue

        im_info = img_by_stem.get(stem)
        if not im_info:
            continue
        ann = ann_by_image_id.get(im_info["id"])
        if not ann:
            continue

        width = int(im_info.get("width", 0))
        height = int(im_info.get("height", 0))
        label_path = _delivery_path(delivery, item["label"])
        mask_path = _delivery_path(delivery, item["mask"])
        boxes = load_yolo_boxes(label_path, width, height, det_classes)

        img_cands = _analyze_image(
            stem=stem,
            width=width,
            height=height,
            boxes=boxes,
            ann=ann,
            mask_path=mask_path,
            cat_by_id=cat_by_id,
            cfg=cfg,
        )
        all_candidates.extend(img_cands)
        scanned_images += 1

    # Đánh mã thứ tự ứng viên ổn định để dễ chia hàng đợi cho 4 thành viên
    by_suggested: dict[str, int] = {}
    unique_images: set[str] = set()
    for idx, cand in enumerate(all_candidates, start=1):
        cand["candidate_id"] = f"C{idx:03d}"
        unique_images.add(cand["image"])
        key = "/".join(cand["suggested_types"])
        by_suggested[key] = by_suggested.get(key, 0) + 1

    return {
        "delivery": str(delivery),
        "thresholds": cfg,
        "summary": {
            "total_manifest_images": len(manifest),
            "scanned_images": scanned_images,
            "skipped_missing_images": skipped_missing_images,
            "total_candidates": len(all_candidates),
            "unique_candidate_images": len(unique_images),
            "by_suggested_type": by_suggested,
        },
        "candidates": all_candidates,
    }


def write_candidates(
    delivery_dir: str | Path,
    out_path: str | Path,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Chạy đối chiếu và ghi kết quả ra file JSON (dùng cho cờ --candidates)."""
    result = find_candidates(delivery_dir, thresholds=thresholds)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Đối chiếu Detection <-> Panoptic để sinh candidates.json (Phần 2, thuần thư viện chuẩn)"
    )
    parser.add_argument("delivery", help="Đường dẫn tới thư mục delivery/")
    parser.add_argument("--out", required=True, help="Đường dẫn file candidates.json đầu ra")
    parser.add_argument(
        "--thresholds-json",
        help="File JSON tùy chọn ghi đè một phần ngưỡng trong DEFAULT_THRESHOLDS để đo thử trên runs/clean",
    )
    args = parser.parse_args()

    overrides = None
    if args.thresholds_json:
        overrides = json.loads(Path(args.thresholds_json).read_text(encoding="utf-8"))

    res = write_candidates(args.delivery, args.out, thresholds=overrides)
    s = res["summary"]
    print(
        f"Đã quét {s['scanned_images']}/{s['total_manifest_images']} ảnh "
        f"(bỏ qua {s['skipped_missing_images']} ảnh thiếu file) -> "
        f"{s['total_candidates']} ứng viên trên {s['unique_candidate_images']} ảnh."
    )
    for kind, count in sorted(s["by_suggested_type"].items()):
        print(f"  - {kind}: {count}")
    print(f"Đã ghi: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
