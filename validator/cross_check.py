"""Detection–Panoptic cross-checks for generating human-review candidates.

This module reports disagreements only. A candidate is not a confirmed error;
the image must be reviewed before adding it to errors.json.
"""

from __future__ import annotations

import json
import math
import sys
import warnings
from pathlib import Path

_scripts = str(Path(__file__).resolve().parents[1] / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from pngutil import read_rgb, segment_id  # noqa: E402


MIN_SEGMENT_PIXELS = 1024
MIN_BOX_SEGMENT_IOU = 0.10
MIN_BOX_MASK_COVERAGE = 0.20
MIN_SEGMENT_BOX_COVERAGE = 0.20
DRIFT_OUTSIDE_FRACTION = 0.20


def _safe_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Input is outside delivery: {relative}")
    return path


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    intersection = iw * ih
    return intersection / (aw * ah + bw * bh - intersection) if intersection else 0.0


def _box(row: list[str], width: int, height: int) -> dict:
    class_id, cx, cy, bw, bh = int(row[0]), *map(float, row[1:5])
    x, y, w, h = (cx - bw / 2) * width, (cy - bh / 2) * height, bw * width, bh * height
    return {"class_id": class_id, "bbox": (x, y, w, h), "name": None}


def generate_candidates(delivery_path: str | Path) -> list[dict]:
    """Return stable candidates with pixel-mask evidence for each image.

    Candidate records contain type, target and evidence. Class disagreement
    records include both possible interpretations; only image review can tell
    whether Detection or Panoptic is wrong.
    """
    root = Path(delivery_path).resolve(strict=True)
    document = json.loads(_safe_file(root, "panoptic.json").read_text(encoding="utf-8-sig"))
    categories = {row["id"]: row for row in document["categories"]}
    images = {Path(row["file_name"]).stem: row for row in document["images"]}
    annotations = {Path(row["file_name"]).stem: row for row in document["annotations"]}
    classes = {}
    for line_no, line in enumerate(_safe_file(root, "classes.txt").read_text(encoding="utf-8-sig").splitlines(), 1):
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        if len(parts) != 2:
            raise ValueError(f"Invalid classes.txt entry at line {line_no}")
        classes[int(parts[0])] = parts[1].strip()
    manifest = json.loads(_safe_file(root, "manifest.json").read_text(encoding="utf-8-sig"))
    items = manifest.get("items")
    if not isinstance(items, dict):
        raise ValueError("manifest.items must be an object")

    candidates = []
    for target, item in sorted(items.items()):
        if not isinstance(item, dict) or target not in images or target not in annotations:
            warnings.warn(f"{target}: missing manifest or panoptic metadata; skipped", RuntimeWarning)
            continue
        try:
            label_path = _safe_file(root, item["label"])
            mask_path = _safe_file(root, item["mask"])
            label_lines = label_path.read_text(encoding="utf-8-sig").splitlines()
            image_row = images[target]
            width, height, pixels = read_rgb(mask_path)
            if width != int(image_row["width"]) or height != int(image_row["height"]):
                raise ValueError("mask dimensions do not match panoptic image metadata")
        except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
            warnings.warn(f"{target}: cross-check skipped: {exc}", RuntimeWarning)
            continue

        counts: dict[int, int] = {}
        for offset in range(0, len(pixels), 3):
            sid = segment_id(pixels, offset)
            counts[sid] = counts.get(sid, 0) + 1
        segments = []
        for segment in annotations[target]["segments_info"]:
            category = categories.get(segment["category_id"])
            actual_area = counts.get(segment["id"], 0)
            if not category or category.get("isthing") != 1 or segment.get("iscrowd") == 1 or actual_area < MIN_SEGMENT_PIXELS:
                continue
            x, y, w, h = map(float, segment["bbox"])
            segments.append({"id": segment["id"], "name": category["name"], "bbox": (x, y, w, h), "area": actual_area, "inside": 0})

        boxes = []
        for row_no, line in enumerate(label_lines, 1):
            parts = line.split()
            if len(parts) != 5:
                continue
            try:
                box = _box(parts, width, height)
            except (ValueError, OverflowError):
                continue
            box["name"] = classes.get(box["class_id"])
            if box["name"] is None or not all(math.isfinite(v) for v in box["bbox"]) or box["bbox"][2] <= 0 or box["bbox"][3] <= 0:
                continue
            box["line"] = row_no
            box["inside"] = 0
            boxes.append(box)

        # Count mask pixels within each box. This keeps exact per-pair evidence
        # while limiting work to the box area instead of every segment × pixel.
        segment_by_id = {segment["id"]: segment for segment in segments}
        intersections = {}
        stride = width * 3
        for box in boxes:
            x0, y0, bw, bh = box["bbox"]
            left, top = max(0, math.floor(x0)), max(0, math.floor(y0))
            right, bottom = min(width, math.ceil(x0 + bw)), min(height, math.ceil(y0 + bh))
            local = {}
            for y in range(top, bottom):
                for x in range(left, right):
                    if x + 0.5 < x0 or x + 0.5 >= x0 + bw or y + 0.5 < y0 or y + 0.5 >= y0 + bh:
                        continue
                    sid = segment_id(pixels, y * stride + x * 3)
                    if sid in segment_by_id:
                        local[sid] = local.get(sid, 0) + 1
            for sid, count in local.items():
                intersections[(box["line"], sid)] = count

        eligible = []
        for segment in segments:
            for box in boxes:
                overlap_iou = _iou(segment["bbox"], box["bbox"])
                # Mask coverage can match a substantially drifted box even where bbox IoU is low.
                overlap_pixels = intersections.get((box["line"], segment["id"]), 0)
                segment_coverage = overlap_pixels / segment["area"]
                box_coverage = overlap_pixels / max(1, round(box["bbox"][2] * box["bbox"][3]))
                if overlap_iou >= MIN_BOX_SEGMENT_IOU or (segment_coverage >= MIN_SEGMENT_BOX_COVERAGE and box_coverage >= MIN_BOX_MASK_COVERAGE):
                    eligible.append((overlap_iou, segment, box, segment_coverage, box_coverage))

        # Prefer a unique best geometric pairing before drawing conclusions.
        best_segment_for_box = {}
        best_box_for_segment = {}
        for score, segment, box, seg_cov, box_cov in eligible:
            key = box["line"]
            if key not in best_segment_for_box or score > best_segment_for_box[key][0]:
                best_segment_for_box[key] = (score, segment, seg_cov, box_cov)
            sid = segment["id"]
            if sid not in best_box_for_segment or score > best_box_for_segment[sid][0]:
                best_box_for_segment[sid] = (score, box, seg_cov, box_cov)

        for box in boxes:
            match = best_segment_for_box.get(box["line"])
            if not match:
                continue
            score, segment, seg_cov, box_cov = match
            if box["name"] != segment["name"] and score >= 0.15:
                candidates.append({"type": "class_swap", "alternate_type": "category_swap", "target": target,
                    "evidence": {"detection_class": box["name"], "panoptic_class": segment["name"], "box_line": box["line"], "segment_id": segment["id"], "bbox_iou": round(score, 4)}})
            elif box["name"] == segment["name"] and seg_cov < 1 - DRIFT_OUTSIDE_FRACTION and box_cov >= MIN_BOX_MASK_COVERAGE:
                candidates.append({"type": "bbox_drift", "target": target,
                    "evidence": {"class": box["name"], "box_line": box["line"], "segment_id": segment["id"], "segment_pixels_in_box": round(seg_cov, 4), "bbox_iou": round(score, 4)}})

        for segment in segments:
            match = best_box_for_segment.get(segment["id"])
            same_class_boxes = [b for b in boxes if b["name"] == segment["name"] and segment["area"]]
            boxes_covering = [b for b in same_class_boxes if intersections.get((b["line"], segment["id"]), 0) / segment["area"] >= MIN_SEGMENT_BOX_COVERAGE]
            # Natural duplicate/near-nested boxes can both cover the same
            # segment. Require a spatially distinct pair before flagging merge.
            distinct_pair = next(((a, b) for i, a in enumerate(boxes_covering) for b in boxes_covering[i + 1:]
                                  if _iou(a["bbox"], b["bbox"]) <= 0.05
                                  and math.dist((a["bbox"][0] + a["bbox"][2] / 2, a["bbox"][1] + a["bbox"][3] / 2),
                                                (b["bbox"][0] + b["bbox"][2] / 2, b["bbox"][1] + b["bbox"][3] / 2)) >= 10), None)
            if distinct_pair:
                pair = list(distinct_pair)
                candidates.append({"type": "instance_merge", "target": target,
                    "evidence": {"class": segment["name"], "segment_id": segment["id"], "box_lines": sorted(b["line"] for b in pair), "segment_pixels_in_boxes": round(sum(intersections.get((b["line"], segment["id"]), 0) for b in pair) / segment["area"], 4)}})
            elif not match or (match[1]["name"] != segment["name"] and match[0] < 0.15):
                candidates.append({"type": "missing_box", "target": target,
                    "evidence": {"class": segment["name"], "segment_id": segment["id"], "segment_pixels": segment["area"]}})

    return sorted(candidates, key=lambda row: (row["type"], row["target"], json.dumps(row.get("evidence", {}), sort_keys=True)))
