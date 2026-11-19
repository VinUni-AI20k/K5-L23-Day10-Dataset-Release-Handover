"""Pixel-level cross-check between Detection (YOLO) and Panoptic masks (TV2).

Uses Python standard library only (+ scripts/pngutil.py).
Reads ONLY the passed `delivery` directory; never accesses _private/, data_source/,
or network.

Generates visual-review candidates for the 5 semantic fault types:
  - class_mismatch : candidate for class_swap (det wrong) or category_swap (pan wrong)
  - bbox_drift     : detection box shifted off the panoptic segment mask
  - missing_box    : significant non-crowd thing segment with no matching detection box
  - instance_merge : single non-crowd thing segment spanning >= 2 same-class det boxes

Thresholds are placed at the top of this file and calibrated on the clean calib set
(`runs/clean`, 50 fault-free images) to keep natural COCO noise minimal without
missing real labeling faults.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

# Allow importing scripts/pngutil.py regardless of current working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.pngutil import read_rgb  # noqa: E402

# ---------------------------------------------------------------------------
# Calibrated thresholds (tuned on clean calib set, zero _private access)
# ---------------------------------------------------------------------------
BOX_PAD_PX = 1.0              # 1px rounding tolerance for YOLO float -> pixel coords

# Strong same-class matching (used to lock clean pairs before cross-class check)
STRONG_SAME_COV = 0.88        # Segment pixels inside box
STRONG_SAME_IOU = 0.50        # Bbox IoU (allows partial occlusion when cov >= 0.96)
OCCLUDED_SAME_COV = 0.96      # Occluded clean objects keep ~100% visible mask inside box
OCCLUDED_SAME_IOU = 0.25

# instance_merge: 1 non-crowd thing segment spanning >= 2 same-class boxes
MERGE_MIN_SEG_AREA = 80       # Ignore tiny noise fragments
MERGE_MIN_UNION_COV = 0.82    # Combined 2 boxes cover most of the merged segment
MERGE_MAX_SINGLE_COV = 0.985  # Neither box alone explains the entire segment
MERGE_MIN_EXCL_RATIO = 0.025  # Each box has >= 2.5% exclusive pixels (or >= 60px & 15% fill)
MERGE_MIN_EXCL_PX = 25        # Each box has >= 25 exclusive pixels of the segment
MERGE_LARGE_EXCL_PX = 60      # Large absolute exclusive pixels for asymmetric size-ratio merges
MERGE_LARGE_EXCL_FILL = 0.15  # Exclusive pixels occupy >= 15% of the secondary box area
MERGE_MIN_BOX_SHARE = 0.04    # Secondary box covers >= 4% of segment pixels

# class_mismatch (class_swap / category_swap): unmatched cross-class overlap
SWAP_MIN_COV = 0.80           # Panoptic mask mostly inside the swapped box
SWAP_MIN_IOU = 0.35           # Spatial bbox agreement (handles partial occlusion too)
SWAP_MIN_SEG_AREA = 30        # Ignore sub-30px micro-fragments

# bbox_drift: same-class pair where mask pixels spill outside the detection box
DRIFT_MAX_COV = 0.96          # Clean calib minimum is >= 0.99; < 0.96 catches small hidden-test drifts
DRIFT_STRICT_COV = 0.92       # Below 0.92 only requires DRIFT_MIN_OUT_PX; 0.92..0.96 requires DRIFT_SUBTLE_OUT_PX
DRIFT_MIN_OUT_PX = 12         # Minimum segment pixels outside padded box for clear drift
DRIFT_SUBTLE_OUT_PX = 20      # Minimum outside pixels for subtle drift (0.92 <= cov < 0.96)
DRIFT_MIN_SEG_AREA = 35       # Ignore tiny < 35px segments prone to 1-2px rounding
DRIFT_WEAK_MATCH_COV = 0.05   # Minimum overlap to link drifted box to same-class seg
DRIFT_WEAK_MATCH_IOU = 0.05

# missing_box: significant unmatched non-crowd thing segment
MISSING_MIN_AREA = 350        # Minimum visible mask pixels (clean calib max noise = 299)
MISSING_MIN_AREA_RATIO = 0.001  # At least 0.1% of image area (or >= 900 px absolute)
MISSING_ABS_LARGE_AREA = 900  # Always flag if >= 900 px regardless of image resolution


def _box_iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    iw = ix2 - ix1
    ih = iy2 - iy1
    if iw <= 0.0 or ih <= 0.0:
        return 0.0
    inter = iw * ih
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    denom = area_a + area_b - inter
    return inter / denom if denom > 0.0 else 0.0


def _load_classes(delivery: Path) -> dict[int, str]:
    classes: dict[int, str] = {}
    classes_path = delivery / "classes.txt"
    if not classes_path.is_file():
        return classes
    for raw in classes_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2:
            classes[int(parts[0])] = parts[1].strip()
    return classes


def _load_yolo_boxes(
    label_path: Path,
    width: int,
    height: int,
    classes: dict[int, str],
) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    if not label_path.is_file():
        return boxes
    for raw in label_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            cid_f = float(parts[0])
            if not cid_f.is_integer():
                continue
            cid = int(cid_f)
            xc, yc, bw, bh = (float(v) for v in parts[1:5])
        except ValueError:
            continue
        if cid not in classes or bw <= 0.0 or bh <= 0.0:
            continue
        x1 = (xc - bw / 2.0) * width
        y1 = (yc - bh / 2.0) * height
        x2 = (xc + bw / 2.0) * width
        y2 = (yc + bh / 2.0) * height
        boxes.append(
            {
                "cls": classes[cid],
                "bbox": (x1, y1, x2, y2),
                "area": max(0.0, x2 - x1) * max(0.0, y2 - y1),
            }
        )
    return boxes


def _scan_segment_box_overlaps(
    pixels: bytearray,
    mw: int,
    mh: int,
    segs: list[dict[str, Any]],
    boxes: list[dict[str, Any]],
) -> tuple[dict[int, int], dict[tuple[int, int], int], dict[int, tuple[list[int], dict[int, int]]]]:
    """Compute exact pixel overlaps between each thing segment and all candidate boxes.

    For each segment, scans only inside its panoptic bbox in a single pass and
    records:
      - seg_area[si]: actual visible pixel count of segment si
      - seg_box_px[(si, bi)]: count of segment si pixels falling inside padded box bi
      - same_cls_masks[si]: (same_cls_box_indices, {bitmask: pixel_count})
        used to compute exact union & exclusive pixel counts for instance_merge.
    """
    stride = mw * 3
    seg_area: dict[int, int] = {}
    seg_box_px: dict[tuple[int, int], int] = {}
    same_cls_masks: dict[int, tuple[list[int], dict[int, int]]] = {}

    for si, seg in enumerate(segs):
        sid = seg["id"]
        sr = sid & 255
        sg = (sid >> 8) & 255
        sb = (sid >> 16) & 255
        seg_cls = seg["cls"]

        sbx1, sby1, sbx2, sby2 = seg["bbox"]
        sx1 = max(0, int(sbx1))
        sy1 = max(0, int(sby1))
        sx2 = min(mw, int(sbx2) + 1)
        sy2 = min(mh, int(sby2) + 1)

        # Pre-filter boxes whose padded bbox intersects segment bbox
        cands: list[tuple[int, float, float, float, float, int]] = []
        same_cls_bi: list[int] = []
        for bi, box in enumerate(boxes):
            bx1, by1, bx2, by2 = box["bbox"]
            px1, py1 = bx1 - BOX_PAD_PX, by1 - BOX_PAD_PX
            px2, py2 = bx2 + BOX_PAD_PX, by2 + BOX_PAD_PX
            if px2 >= sx1 and px1 <= sx2 and py2 >= sy1 and py1 <= sy2:
                same_bit = 0
                if box["cls"] == seg_cls and len(same_cls_bi) < 20:
                    same_bit = 1 << len(same_cls_bi)
                    same_cls_bi.append(bi)
                cands.append((bi, px1, py1, px2, py2, same_bit))

        if not cands:
            # No box intersects segment bbox at all; use declared area as visible count
            seg_area[si] = seg["area"]
            same_cls_masks[si] = ([], {})
            continue

        total_px = 0
        counts = [0] * len(cands)
        bit_hist: dict[int, int] = {}
        track_bits = len(same_cls_bi) >= 2

        for y in range(sy1, sy2):
            yc_px = y + 0.5
            row_off = y * stride
            row_cands = [
                (idx, px1, px2, same_bit)
                for idx, (_, px1, py1, px2, py2, same_bit) in enumerate(cands)
                if py1 <= yc_px <= py2
            ]
            for x in range(sx1, sx2):
                off = row_off + x * 3
                if pixels[off] == sr and pixels[off + 1] == sg and pixels[off + 2] == sb:
                    total_px += 1
                    xc_px = x + 0.5
                    bits = 0
                    for idx, px1, px2, same_bit in row_cands:
                        if px1 <= xc_px <= px2:
                            counts[idx] += 1
                            if track_bits and same_bit:
                                bits |= same_bit
                    if track_bits and bits:
                        bit_hist[bits] = bit_hist.get(bits, 0) + 1

        seg_area[si] = total_px
        for idx, (bi, *_) in enumerate(cands):
            if counts[idx] > 0:
                seg_box_px[(si, bi)] = counts[idx]
        same_cls_masks[si] = (same_cls_bi, bit_hist)

    return seg_area, seg_box_px, same_cls_masks


def _analyze_image(
    stem: str,
    width: int,
    height: int,
    mask_path: Path,
    boxes: list[dict[str, Any]],
    segs: list[dict[str, Any]],
    crowd_segs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run pixel-level Det <-> Panoptic cross-check on a single image."""
    if not segs and not boxes:
        return []

    img_area = max(1, width * height)

    if segs:
        mw, mh, pixels = read_rgb(mask_path)
        seg_area, seg_box_px, same_cls_masks = _scan_segment_box_overlaps(
            pixels, mw, mh, segs, boxes
        )
    else:
        seg_area, seg_box_px, same_cls_masks = {}, {}, {}

    def cov_of(si: int, bi: int) -> float:
        area = seg_area.get(si, 0)
        return seg_box_px.get((si, bi), 0) / area if area > 0 else 0.0

    # ------------------------------------------------------------------
    # Step 1: Lock clean / strong 1-to-1 same-class matches first
    # ------------------------------------------------------------------
    strong_pairs: list[tuple[float, float, int, int]] = []
    for si, seg in enumerate(segs):
        if seg_area.get(si, 0) <= 0:
            continue
        for bi, box in enumerate(boxes):
            if box["cls"] != seg["cls"]:
                continue
            cov = cov_of(si, bi)
            iou = _box_iou(seg["bbox"], box["bbox"])
            if (cov >= STRONG_SAME_COV and iou >= STRONG_SAME_IOU) or (
                cov >= OCCLUDED_SAME_COV and iou >= OCCLUDED_SAME_IOU
            ):
                strong_pairs.append((cov, iou, si, bi))

    strong_pairs.sort(key=lambda t: (t[0] + t[1], t[1], t[0]), reverse=True)
    matched_s: dict[int, tuple[int, float, float]] = {}
    matched_b: dict[int, tuple[int, float, float]] = {}
    for cov, iou, si, bi in strong_pairs:
        if si in matched_s or bi in matched_b:
            continue
        matched_s[si] = (bi, cov, iou)
        matched_b[bi] = (si, cov, iou)

    candidates: list[dict[str, Any]] = []
    merge_claimed_s: set[int] = set()
    merge_claimed_b: set[int] = set()

    # ------------------------------------------------------------------
    # Step 2: Detect instance_merge (1 non-crowd segment spanning >= 2 boxes)
    # ------------------------------------------------------------------
    for si, seg in enumerate(segs):
        area = seg_area.get(si, 0)
        if area < MERGE_MIN_SEG_AREA:
            continue
        same_bi_list, bit_hist = same_cls_masks.get(si, ([], {}))
        if len(same_bi_list) < 2 or not bit_hist:
            continue

        best_merge: tuple[float, int, int, float, float, float, float] | None = None
        m = len(same_bi_list)
        for k1 in range(m):
            b1 = same_bi_list[k1]
            # Skip if b1 is already cleanly locked to a DIFFERENT segment
            if b1 in matched_b and matched_b[b1][0] != si:
                continue
            bit1 = 1 << k1
            for k2 in range(k1 + 1, m):
                b2 = same_bi_list[k2]
                if b2 in matched_b and matched_b[b2][0] != si:
                    continue
                bit2 = 1 << k2
                both_mask = bit1 | bit2

                in1 = 0
                in2 = 0
                in1_only = 0
                in2_only = 0
                in_union = 0
                for bits, cnt in bit_hist.items():
                    has1 = bool(bits & bit1)
                    has2 = bool(bits & bit2)
                    if has1:
                        in1 += cnt
                    if has2:
                        in2 += cnt
                    if has1 and not has2:
                        in1_only += cnt
                    elif has2 and not has1:
                        in2_only += cnt
                    if bits & both_mask:
                        in_union += cnt

                cov_union = in_union / area
                best_single = max(in1, in2) / area
                min_share = min(in1, in2) / area
                min_excl_px = min(in1_only, in2_only)
                min_excl_ratio = min_excl_px / area
                sec_box_area = boxes[b2]["area"] if in2_only <= in1_only else boxes[b1]["area"]
                min_excl_fill = min_excl_px / max(sec_box_area, 1.0)

                has_balanced_excl = (
                    min_share >= MERGE_MIN_BOX_SHARE
                    and min_excl_ratio >= MERGE_MIN_EXCL_RATIO
                    and min_excl_px >= MERGE_MIN_EXCL_PX
                )
                has_asymmetric_excl = (
                    min_excl_px >= MERGE_LARGE_EXCL_PX
                    and min_excl_fill >= MERGE_LARGE_EXCL_FILL
                )

                if (
                    cov_union >= MERGE_MIN_UNION_COV
                    and best_single <= MERGE_MAX_SINGLE_COV
                    and (has_balanced_excl or has_asymmetric_excl)
                ):
                    score = cov_union + min_excl_ratio
                    if best_merge is None or score > best_merge[0]:
                        best_merge = (
                            score,
                            b1,
                            b2,
                            cov_union,
                            in1 / area,
                            in2 / area,
                            min_excl_ratio,
                        )

        if best_merge is not None:
            _, b1, b2, cov_union, c1, c2, min_excl = best_merge
            merge_claimed_s.add(si)
            merge_claimed_b.add(b1)
            merge_claimed_b.add(b2)
            # Release any single strong match on this merged segment
            if si in matched_s:
                old_b = matched_s.pop(si)[0]
                matched_b.pop(old_b, None)
            candidates.append(
                {
                    "image": stem,
                    "target": stem,
                    "type": "instance_merge",
                    "suggested_types": ["instance_merge"],
                    "segment_id": int(seg["id"]),
                    "pan_class": seg["cls"],
                    "det_class": seg["cls"],
                    "area": area,
                    "seg_in_box": round(max(c1, c2), 3),
                    "union_cov": round(cov_union, 3),
                    "min_excl_ratio": round(min_excl, 3),
                    "detail": (
                        f"1 segment '{seg['cls']}' ({area}px) phủ 2 box cùng lớp "
                        f"(cov1={c1:.2f}, cov2={c2:.2f}, union={cov_union:.2f}, excl={min_excl:.2f})"
                    ),
                }
            )

    # ------------------------------------------------------------------
    # Step 3: Detect class_mismatch (class_swap vs category_swap)
    # ------------------------------------------------------------------
    cross_pairs: list[tuple[float, float, int, int]] = []
    for si, seg in enumerate(segs):
        if si in matched_s or si in merge_claimed_s:
            continue
        area = seg_area.get(si, 0)
        if area < SWAP_MIN_SEG_AREA:
            continue
        for bi, box in enumerate(boxes):
            if bi in matched_b or bi in merge_claimed_b:
                continue
            if box["cls"] == seg["cls"]:
                continue
            cov = cov_of(si, bi)
            iou = _box_iou(seg["bbox"], box["bbox"])
            if cov >= SWAP_MIN_COV and iou >= SWAP_MIN_IOU:
                cross_pairs.append((cov, iou, si, bi))

    cross_pairs.sort(key=lambda t: (t[1] + t[0], t[1], t[0]), reverse=True)
    swap_claimed_s: set[int] = set()
    swap_claimed_b: set[int] = set()
    for cov, iou, si, bi in cross_pairs:
        if si in swap_claimed_s or bi in swap_claimed_b:
            continue
        swap_claimed_s.add(si)
        swap_claimed_b.add(bi)
        seg = segs[si]
        box = boxes[bi]
        candidates.append(
            {
                "image": stem,
                "target": stem,
                "type": "class_mismatch",
                "suggested_types": ["class_swap", "category_swap"],
                "segment_id": int(seg["id"]),
                "det_class": box["cls"],
                "pan_class": seg["cls"],
                "area": seg_area.get(si, 0),
                "seg_in_box": round(cov, 3),
                "bbox_iou": round(iou, 3),
                "detail": (
                    f"DET='{box['cls']}' vs PAN='{seg['cls']}' "
                    f"(IoU={iou:.2f}, seg_in_box={cov:.2f}, area={seg_area.get(si, 0)}px)"
                ),
            }
        )

    # ------------------------------------------------------------------
    # Step 4: Detect bbox_drift (remaining same-class pairs + low-cov strong pairs)
    # ------------------------------------------------------------------
    weak_pairs: list[tuple[float, float, int, int]] = []
    for si, seg in enumerate(segs):
        if si in matched_s or si in merge_claimed_s or si in swap_claimed_s:
            continue
        if seg_area.get(si, 0) < DRIFT_MIN_SEG_AREA:
            continue
        for bi, box in enumerate(boxes):
            if bi in matched_b or bi in merge_claimed_b or bi in swap_claimed_b:
                continue
            if box["cls"] != seg["cls"]:
                continue
            cov = cov_of(si, bi)
            iou = _box_iou(seg["bbox"], box["bbox"])
            if cov >= DRIFT_WEAK_MATCH_COV or iou >= DRIFT_WEAK_MATCH_IOU:
                weak_pairs.append((cov, iou, si, bi))

    weak_pairs.sort(key=lambda t: (t[0] + t[1], t[0], t[1]), reverse=True)
    for cov, iou, si, bi in weak_pairs:
        if si in matched_s or bi in matched_b:
            continue
        matched_s[si] = (bi, cov, iou)
        matched_b[bi] = (si, cov, iou)

    # Flag any matched same-class pair whose mask spills significantly outside box
    for si, (bi, cov, iou) in matched_s.items():
        area = seg_area.get(si, 0)
        if area < DRIFT_MIN_SEG_AREA:
            continue
        out_px = area - seg_box_px.get((si, bi), 0)
        is_clear_drift = cov < DRIFT_STRICT_COV and out_px >= DRIFT_MIN_OUT_PX
        is_subtle_drift = cov < DRIFT_MAX_COV and out_px >= DRIFT_SUBTLE_OUT_PX
        if is_clear_drift or is_subtle_drift:
            seg = segs[si]
            candidates.append(
                {
                    "image": stem,
                    "target": stem,
                    "type": "bbox_drift",
                    "suggested_types": ["bbox_drift"],
                    "segment_id": int(seg["id"]),
                    "det_class": boxes[bi]["cls"],
                    "pan_class": seg["cls"],
                    "area": area,
                    "seg_in_box": round(cov, 3),
                    "bbox_iou": round(iou, 3),
                    "detail": (
                        f"Box '{seg['cls']}' lệch mask: chỉ {cov:.2f} pixel mask trong box "
                        f"({out_px}px tràn ngoài, IoU={iou:.2f})"
                    ),
                }
            )

    # Extreme drift: unmatched segment + unmatched box of the SAME class (0 overlap)
    # Only if the orphan box does not overlap a crowd segment of that class
    orphan_segs_by_cls: dict[str, list[int]] = {}
    for si, seg in enumerate(segs):
        if si not in matched_s and si not in merge_claimed_s and si not in swap_claimed_s:
            if seg_area.get(si, 0) >= DRIFT_MIN_SEG_AREA:
                orphan_segs_by_cls.setdefault(seg["cls"], []).append(si)

    orphan_boxes_by_cls: dict[str, list[int]] = {}
    for bi, box in enumerate(boxes):
        if bi not in matched_b and bi not in merge_claimed_b and bi not in swap_claimed_b:
            in_crowd = any(
                c["cls"] == box["cls"] and _box_iou(c["bbox"], box["bbox"]) >= 0.10
                for c in crowd_segs
            )
            if not in_crowd:
                orphan_boxes_by_cls.setdefault(box["cls"], []).append(bi)

    extreme_drift_s: set[int] = set()
    for cls_name, s_list in orphan_segs_by_cls.items():
        b_list = orphan_boxes_by_cls.get(cls_name)
        if not b_list:
            continue
        # Pair largest orphan segment with nearest/most similar-area orphan box
        s_list_sorted = sorted(s_list, key=lambda idx: seg_area.get(idx, 0), reverse=True)
        used_b: set[int] = set()
        for si in s_list_sorted:
            seg = segs[si]
            s_cx = (seg["bbox"][0] + seg["bbox"][2]) / 2.0
            s_cy = (seg["bbox"][1] + seg["bbox"][3]) / 2.0
            best_bi = None
            best_dist = float("inf")
            for bi in b_list:
                if bi in used_b:
                    continue
                b = boxes[bi]["bbox"]
                b_cx = (b[0] + b[2]) / 2.0
                b_cy = (b[1] + b[3]) / 2.0
                dist = ((s_cx - b_cx) ** 2 + (s_cy - b_cy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_bi = bi
            if best_bi is not None:
                used_b.add(best_bi)
                extreme_drift_s.add(si)
                area = seg_area.get(si, 0)
                candidates.append(
                    {
                        "image": stem,
                        "target": stem,
                        "type": "bbox_drift",
                        "suggested_types": ["bbox_drift"],
                        "segment_id": int(seg["id"]),
                        "det_class": cls_name,
                        "pan_class": cls_name,
                        "area": area,
                        "seg_in_box": 0.0,
                        "bbox_iou": 0.0,
                        "detail": (
                            f"Box '{cls_name}' lệch hoàn toàn khỏi segment "
                            f"(0% overlap, khoảng cách tâm {best_dist:.0f}px, area={area}px)"
                        ),
                    }
                )

    # ------------------------------------------------------------------
    # Step 5: Detect missing_box (significant unmatched non-crowd thing seg)
    # ------------------------------------------------------------------
    for si, seg in enumerate(segs):
        if (
            si in matched_s
            or si in merge_claimed_s
            or si in swap_claimed_s
            or si in extreme_drift_s
        ):
            continue
        area = seg_area.get(si, 0)
        area_ratio = area / img_area
        if area >= MISSING_MIN_AREA and (
            area_ratio >= MISSING_MIN_AREA_RATIO or area >= MISSING_ABS_LARGE_AREA
        ):
            candidates.append(
                {
                    "image": stem,
                    "target": stem,
                    "type": "missing_box",
                    "suggested_types": ["missing_box"],
                    "segment_id": int(seg["id"]),
                    "det_class": None,
                    "pan_class": seg["cls"],
                    "area": area,
                    "seg_in_box": 0.0,
                    "bbox_iou": 0.0,
                    "detail": (
                        f"Segment thing '{seg['cls']}' ({area}px, {area_ratio * 100:.2f}% ảnh) "
                        f"không có box detection tương ứng"
                    ),
                }
            )

    # Deduplicate per (image, type): keep the highest-severity instance per type
    best_by_type: dict[str, dict[str, Any]] = {}
    for cand in candidates:
        ctype = cand["type"]
        prev = best_by_type.get(ctype)
        if prev is None or cand.get("area", 0) > prev.get("area", 0):
            best_by_type[ctype] = cand

    return list(best_by_type.values())


def find_candidates(
    delivery_dir: Path | str,
    rule_targets: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Find semantic labeling error candidates by cross-checking Det <-> Panoptic.

    Signature matches validator/validate.py:
        candidates = find_candidates(delivery, rule_targets=rule_targets)
    """
    delivery = Path(delivery_dir)
    skip = set(rule_targets) if rule_targets else set()

    panoptic_path = delivery / "panoptic.json"
    if not panoptic_path.is_file():
        return []

    classes = _load_classes(delivery)
    valid_names = set(classes.values())
    panoptic = json.loads(panoptic_path.read_text(encoding="utf-8"))

    cats = {
        c["id"]: c for c in panoptic.get("categories", []) if isinstance(c, dict) and "id" in c
    }
    im_by_id = {
        im["id"]: im for im in panoptic.get("images", []) if isinstance(im, dict) and "id" in im
    }
    masks_dir = delivery / "masks"
    labels_dir = delivery / "labels"

    all_candidates: list[dict[str, Any]] = []

    for ann in panoptic.get("annotations", []):
        im = im_by_id.get(ann.get("image_id"))
        ann_file = ann.get("file_name", "")
        if im is not None and im.get("file_name"):
            stem = Path(im["file_name"]).stem
            width = int(im["width"])
            height = int(im["height"])
        else:
            stem = Path(ann_file).stem if ann_file else str(ann.get("image_id"))
            width, height = 0, 0

        if stem in skip:
            continue

        mask_name = Path(ann_file).name if ann_file else f"{stem}.png"
        mask_path = masks_dir / mask_name
        if not mask_path.is_file():
            fallback = masks_dir / f"{stem}.png"
            if fallback.is_file():
                mask_path = fallback
            else:
                continue

        lbl_path = labels_dir / f"{stem}.txt"
        if not lbl_path.is_file():
            continue

        segs: list[dict[str, Any]] = []
        crowd_segs: list[dict[str, Any]] = []
        for s in ann.get("segments_info", []):
            cat = cats.get(s.get("category_id"))
            if not cat or cat.get("isthing") != 1:
                continue
            cname = cat.get("name", "")
            if cname not in valid_names:
                continue
            bbox = s.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            sx, sy, sw, sh = (float(v) for v in bbox[:4])
            entry = {
                "id": int(s["id"]),
                "cls": cname,
                "bbox": (sx, sy, sx + sw, sy + sh),
                "area": int(s.get("area", 0)),
            }
            if s.get("iscrowd", 0) == 0:
                segs.append(entry)
            else:
                crowd_segs.append(entry)

        if width <= 0 or height <= 0:
            mw, mh, _ = read_rgb(mask_path)
            width, height = mw, mh

        boxes = _load_yolo_boxes(lbl_path, width, height, classes)
        img_cands = _analyze_image(stem, width, height, mask_path, boxes, segs, crowd_segs)
        all_candidates.extend(img_cands)

    all_candidates.sort(key=lambda c: (c["image"], c["type"]))
    return all_candidates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run pixel-level Det <-> Panoptic cross-check on a delivery directory."
    )
    parser.add_argument("delivery", type=Path, help="Path to delivery directory")
    parser.add_argument("--out", type=Path, default=None, help="Optional candidates JSON path")
    args = parser.parse_args()

    t0 = time.perf_counter()
    cands = find_candidates(args.delivery)
    elapsed = time.perf_counter() - t0

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({"candidates": cands}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    counts = Counter(c["type"] for c in cands)
    print(
        f"Cross-checked {args.delivery} in {elapsed:.2f}s -> {len(cands)} candidates: {dict(counts)}"
    )


if __name__ == "__main__":
    main()
