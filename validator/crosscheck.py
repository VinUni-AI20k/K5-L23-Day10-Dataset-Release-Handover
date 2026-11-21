"""M3 steps 3.1-3.4: match boxes, measure mask coverage, propose review candidates.

Only Python's standard library is used. Input comes from the supplied delivery's
panoptic.json, labels/ and masks/; no original COCO data, private answers, or network.
Run: py -X utf8 validator/crosscheck.py DELIVERY --out OUTPUT.json [--match | --coverage | --candidates]
"""

import argparse
from dataclasses import asdict, dataclass
from itertools import combinations
import json
import math
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, NamedTuple, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.pngutil import read_rgb, segment_id


class PixelBox(NamedTuple):
    """Continuous (left, top, right, bottom) edges, without rounding or clipping."""

    left: float
    top: float
    right: float
    bottom: float

    def contains_pixel(self, x: int, y: int) -> bool:
        """Test a mask pixel's center; left/top inclusive, right/bottom exclusive."""
        return (
            self.left <= x + 0.5 < self.right
            and self.top <= y + 0.5 < self.bottom
        )


def _box_values(box: Sequence[float]) -> tuple[float, float, float, float]:
    if isinstance(box, (str, bytes)) or len(box) != 4:
        raise ValueError("A box must contain four numeric coordinates")
    values = tuple(float(value) for value in box)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Box coordinates must be finite")
    if values[2] <= 0 or values[3] <= 0:
        raise ValueError("Box width and height must be positive")
    return values


def _image_size(width: int, height: int) -> tuple[int, int]:
    dimensions = []
    for value in (width, height):
        number = float(value)
        if isinstance(value, bool) or not math.isfinite(number) or number <= 0:
            raise ValueError("Image dimensions must be positive integers")
        if not number.is_integer():
            raise ValueError("Image dimensions must be positive integers")
        dimensions.append(int(number))
    return dimensions[0], dimensions[1]


def yolo_to_pixel(
    box: Sequence[float], image_width: int, image_height: int
) -> PixelBox:
    """Convert normalized (xc, yc, width, height) using this image's dimensions.

    Finite boxes crossing the image boundary are preserved for M2's rule checks.
    Malformed, non-finite, or non-positive geometry raises ValueError/TypeError.
    """
    xc, yc, width, height = _box_values(box)
    image_width, image_height = _image_size(image_width, image_height)
    edges = PixelBox(
        (xc - width / 2) * image_width,
        (yc - height / 2) * image_height,
        (xc + width / 2) * image_width,
        (yc + height / 2) * image_height,
    )
    if not all(math.isfinite(edge) for edge in edges):
        raise ValueError("Converted pixel coordinates must be finite")
    return edges


def panoptic_to_pixel(box: Sequence[float]) -> PixelBox:
    """Convert panoptic pixel (x, y, width, height) to the same edge convention."""
    x, y, width, height = _box_values(box)
    edges = PixelBox(x, y, x + width, y + height)
    if not all(math.isfinite(edge) for edge in edges):
        raise ValueError("Converted pixel coordinates must be finite")
    return edges


def load_delivery_boxes(delivery_dir: str | Path) -> dict[str, Any]:
    """Read per-image geometry, reporting bad input without losing valid boxes.

    Issues are conversion diagnostics, not entries for errors.json. Detection
    class validity and other rule-error decisions remain the responsibility of M2.
    Image files need not exist to convert labels when dimensions are available.
    """
    delivery = Path(delivery_dir)
    result: dict[str, Any] = {
        "coordinate_format": "left,top,right,bottom",
        "pixel_rule": "pixel centers; left/top inclusive, right/bottom exclusive",
        "images": [],
        "issues": [],
    }

    def issue(image: str | None, source: str, message: str, line: int | None = None):
        result["issues"].append({
            "image": image, "source": source, "line_number": line,
            "message": message,
        })

    try:
        data = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("images"), list):
            raise ValueError("panoptic.json must contain an images list")
    except (OSError, UnicodeError, ValueError) as exc:
        issue(None, "panoptic.json", str(exc))
        return result

    annotations = data.get("annotations", [])
    if not isinstance(annotations, list):
        issue(None, "panoptic.json", "annotations must be a list")
        annotations = []
    segments_by_image: dict[int | str, list] = {}
    masks_by_image: dict[int | str, str] = {}
    for annotation in annotations:
        if not isinstance(annotation, dict):
            issue(None, "panoptic.json", "Annotation must be an object")
            continue
        image_id = annotation.get("image_id")
        segments = annotation.get("segments_info")
        if not isinstance(image_id, (int, str)) or not isinstance(segments, list):
            issue(None, "panoptic.json", "Annotation needs image_id and segments_info list")
            continue
        segments_by_image.setdefault(image_id, []).extend(segments)
        if isinstance(annotation.get("file_name"), str):
            masks_by_image[image_id] = annotation["file_name"]

    for image in data["images"]:
        name = None
        try:
            if not isinstance(image, dict):
                raise ValueError("Image entry must be an object")
            if not isinstance(image["file_name"], str) or not image["file_name"]:
                raise ValueError("Image file_name must be a nonempty string")
            # Take only the basename: label reads always stay under delivery/labels.
            name = Path(image["file_name"].replace("\\", "/")).stem
            if name in ("", ".", ".."):
                raise ValueError("Invalid image filename")
            image_id = image["id"]
            if not isinstance(image_id, (int, str)):
                raise ValueError("Image id must be an integer or string")
            width, height = _image_size(image["width"], image["height"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            issue(name, "panoptic.json", str(exc))
            continue

        converted = {
            "image": name, "image_id": image_id, "width": width, "height": height,
            "mask_file": masks_by_image.get(image_id),
            "detection_boxes": [], "panoptic_boxes": [],
        }
        result["images"].append(converted)
        label_source = f"labels/{name}.txt"
        try:
            lines = (delivery / "labels" / f"{name}.txt").read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            issue(name, label_source, str(exc))
            lines = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                fields = line.split()
                if len(fields) != 5:
                    raise ValueError("YOLO row must contain class_id and four coordinates")
                class_id = int(fields[0])
                bbox = yolo_to_pixel(fields[1:], width, height)
                converted["detection_boxes"].append({
                    "class_id": class_id, "line_number": line_number, "bbox": bbox,
                })
            except (TypeError, ValueError, OverflowError) as exc:
                issue(name, label_source, str(exc), line_number)

        for segment in segments_by_image.get(image_id, []):
            try:
                if not isinstance(segment, dict):
                    raise ValueError("Segment must be an object")
                bbox = panoptic_to_pixel(segment["bbox"])
                converted["panoptic_boxes"].append({
                    "segment_id": segment["id"], "category_id": segment["category_id"],
                    "iscrowd": segment.get("iscrowd", 0), "bbox": bbox,
                })
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                issue(name, "panoptic.json", str(exc))
    return result


def _pixel_box(box: Sequence[float]) -> PixelBox:
    if isinstance(box, (str, bytes)) or len(box) != 4:
        raise ValueError("Pixel box must contain four edges")
    edges = PixelBox(*(float(value) for value in box))
    if not all(math.isfinite(edge) for edge in edges):
        raise ValueError("Pixel edges must be finite")
    if edges.right < edges.left or edges.bottom < edges.top:
        raise ValueError("Pixel box edges must be ordered")
    return edges


def box_iou(first: Sequence[float], second: Sequence[float]) -> float:
    """Continuous bbox IoU; no +1 pixel padding or clipping to image boundaries."""
    first, second = _pixel_box(first), _pixel_box(second)
    intersection = (
        max(0.0, min(first.right, second.right) - max(first.left, second.left))
        * max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
    )
    first_area = (first.right - first.left) * (first.bottom - first.top)
    second_area = (second.right - second.left) * (second.bottom - second.top)
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def _match_threshold(min_iou: float) -> float:
    threshold = float(min_iou)
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("min_iou must be finite and between 0 and 1")
    return threshold


def load_class_maps(delivery_dir: str | Path) -> tuple[dict, dict, list]:
    """Read detection names and panoptic names/isthing flags from delivery only."""
    delivery = Path(delivery_dir)
    detection_classes: dict[int, str] = {}
    categories: dict[int, dict] = {}
    issues = []

    def issue(source: str, message: str, line: int | None = None):
        issues.append({"image": None, "source": source,
                       "line_number": line, "message": message})

    try:
        lines = (delivery / "classes.txt").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        issue("classes.txt", str(exc))
        lines = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            fields = line.split(maxsplit=1)
            if len(fields) != 2 or not fields[1].strip():
                raise ValueError("Class row must contain an ID and a name")
            class_id = int(fields[0])
            if class_id in detection_classes:
                raise ValueError(f"Duplicate detection class ID: {class_id}")
            detection_classes[class_id] = fields[1].strip()
        except ValueError as exc:
            issue("classes.txt", str(exc), line_number)

    try:
        data = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("categories"), list):
            raise ValueError("panoptic.json must contain a categories list")
        rows = data["categories"]
    except (OSError, UnicodeError, ValueError) as exc:
        issue("panoptic.json", str(exc))
        rows = []
    for category in rows:
        try:
            if not isinstance(category, dict):
                raise ValueError("Category must be an object")
            category_id = category["id"]
            if isinstance(category_id, bool) or not isinstance(category_id, int):
                raise ValueError("Category ID must be an integer")
            if not isinstance(category["name"], str) or not category["name"].strip():
                raise ValueError("Category name must be a nonempty string")
            if category.get("isthing") not in (0, 1):
                raise ValueError("Category isthing flag must be 0 or 1")
            if category_id in categories:
                raise ValueError(f"Duplicate panoptic category ID: {category_id}")
            categories[category_id] = {
                "name": category["name"].strip(), "isthing": category["isthing"],
            }
        except (KeyError, TypeError, ValueError) as exc:
            issue("panoptic.json", str(exc))
    return detection_classes, categories, issues


def match_image_boxes(
    image: dict[str, Any], detection_classes: dict[int, str],
    categories: dict[int, dict], min_iou: float = 0.0,
) -> dict[str, Any]:
    """Pick each detection's best positive-IoU non-crowd thing segment.

    Position determines the pair; names are compared afterward, so mismatched
    classes are retained. Equal IoU uses original segment order. Many detections
    may choose one segment to preserve evidence for the later instance-merge step.
    Lists reference zero-based indices in this image's converted box arrays.
    Matches/unmatched items are geometry observations, not confirmed errors.
    """
    threshold = _match_threshold(min_iou)
    result: dict[str, Any] = {
        "matches": [], "unmatched_detections": [], "unmatched_segments": [],
        "excluded_detections": [], "excluded_segments": [], "issues": [],
    }

    def issue(source: str, message: str, line: int | None = None):
        result["issues"].append({
            "image": image["image"], "source": source,
            "line_number": line, "message": message,
        })

    eligible = []
    for index, segment in enumerate(image["panoptic_boxes"]):
        try:
            category = categories.get(segment["category_id"])
            if category is None:
                raise ValueError(f"Unknown panoptic category: {segment['category_id']}")
            if not category["isthing"]:
                result["excluded_segments"].append({"index": index, "reason": "stuff"})
                continue
            if segment.get("iscrowd", 0):
                result["excluded_segments"].append({"index": index, "reason": "crowd"})
                continue
            bbox = _pixel_box(segment["bbox"])
            eligible.append((index, segment, bbox, category["name"]))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            result["excluded_segments"].append({"index": index, "reason": "invalid_data"})
            issue("panoptic.json", str(exc))

    used_segments = set()
    for index, detection in enumerate(image["detection_boxes"]):
        try:
            class_name = detection_classes.get(detection["class_id"])
            if class_name is None:
                raise ValueError(f"Unknown detection class: {detection['class_id']}")
            bbox = _pixel_box(detection["bbox"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            result["excluded_detections"].append({"index": index, "reason": "invalid_data"})
            issue(f"labels/{image['image']}.txt", str(exc), detection.get("line_number"))
            continue
        best = None
        best_iou = 0.0
        for segment_index, segment, segment_bbox, segment_name in eligible:
            overlap = box_iou(bbox, segment_bbox)
            if overlap > best_iou and overlap >= threshold:
                best = (segment_index, segment, segment_name)
                best_iou = overlap
        if best is None:
            result["unmatched_detections"].append(index)
            continue
        segment_index, segment, segment_name = best
        used_segments.add(segment_index)
        result["matches"].append({
            "detection_index": index, "detection_line": detection.get("line_number"),
            "class_id": detection["class_id"], "detection_class_name": class_name,
            "segment_index": segment_index, "segment_id": segment["segment_id"],
            "category_id": segment["category_id"], "segment_class_name": segment_name,
            "iou": best_iou, "same_class": class_name == segment_name,
        })
    result["unmatched_segments"] = [
        index for index, *_ in eligible if index not in used_segments
    ]
    return result


def measure_mask_pixels(
    width: int, height: int, pixels: bytes, boxes: Sequence[Sequence[float]],
) -> dict[str, Any]:
    """Count actual nonbackground segment pixels and pixels inside each box.

    Scan RGB rows once, accumulating contiguous segment runs. Intersect each run
    with boxes active on that row; avoid scanning the full mask separately for
    every detection. Pixel-center inclusion is identical to contains_pixel().
    """
    width, height = _image_size(width, height)
    if len(pixels) != width * height * 3:
        raise ValueError("RGB pixel buffer does not match mask dimensions")
    row_boxes: list[list[tuple[int, int, int]]] = [[] for _ in range(height)]
    for index, box in enumerate(boxes):
        box = _pixel_box(box)
        left = max(0, min(width, math.ceil(box.left - 0.5)))
        right = max(0, min(width, math.ceil(box.right - 0.5)))
        top = max(0, min(height, math.ceil(box.top - 0.5)))
        bottom = max(0, min(height, math.ceil(box.bottom - 0.5)))
        if left < right:
            for y in range(top, bottom):
                row_boxes[y].append((index, left, right))

    totals: dict[int, int] = {}
    inside: list[dict[int, int]] = [{} for _ in boxes]

    def accumulate(sid: int, start: int, end: int, active: list):
        if sid == 0:
            return
        totals[sid] = totals.get(sid, 0) + end - start
        for index, left, right in active:
            overlap = min(end, right) - max(start, left)
            if overlap > 0:
                inside[index][sid] = inside[index].get(sid, 0) + overlap

    stride = width * 3
    for y in range(height):
        offset = y * stride
        start = 0
        previous = segment_id(pixels, offset)
        for x in range(1, width):
            current = segment_id(pixels, offset + x * 3)
            if current != previous:
                accumulate(previous, start, x, row_boxes[y])
                start, previous = x, current
        accumulate(previous, start, width, row_boxes[y])
    return {
        "segment_pixels": totals, "inside_pixels_by_box": inside,
        "background_pixels": width * height - sum(totals.values()),
    }


def _coverage_metrics(total: int | None, inside: int | None) -> dict[str, Any]:
    fraction = inside / total if total and inside is not None else None
    return {
        "segment_pixels": total, "inside_pixels": inside,
        "outside_pixels": total - inside if total is not None and inside is not None else None,
        "coverage": fraction,
        "coverage_percent": fraction * 100 if fraction is not None else None,
    }


def _mask_path(delivery_dir: str | Path, filename: str | None) -> Path:
    if not isinstance(filename, str) or not filename:
        raise ValueError("Missing mask filename in panoptic annotation")
    relative = Path(filename.replace("\\", "/"))
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError("Mask path must stay inside delivery/masks")
    delivery = Path(delivery_dir).resolve()
    mask_root = (delivery / "masks").resolve()
    path = (delivery / relative if relative.parts[0] == "masks"
            else mask_root / relative).resolve()
    if not path.is_relative_to(delivery) or not path.is_relative_to(mask_root):
        raise ValueError("Mask path must stay inside delivery/masks")
    return path


def measure_image_coverage(
    delivery_dir: str | Path, image: dict[str, Any],
    detection_classes: dict[int, str], categories: dict[int, dict],
) -> dict[str, Any]:
    """Measure eligible thing segments against all usable detection boxes.

    Include primary matches even with zero inside pixels. Also retain nonprimary
    boxes with positive segment pixels, including same-class box pairs needed
    for later merge checks. Missing mask or zero-pixel segments have null coverage,
    not invented zero-percent evidence. No fault decisions or thresholds are made.
    """
    result: dict[str, Any] = {
        "status": "unavailable", "background_pixels": None,
        "segments": [], "issues": [],
    }

    def issue(message: str):
        result["issues"].append({
            "image": image["image"], "source": f"masks/{image.get('mask_file')}",
            "line_number": None, "message": message,
        })

    excluded_detections = {item["index"] for item in image["matching"]["excluded_detections"]}
    detection_indices = [
        index for index in range(len(image["detection_boxes"])) if index not in excluded_detections
    ]
    try:
        mask = _mask_path(delivery_dir, image.get("mask_file"))
        width, height, pixels = read_rgb(mask)
        if (width, height) != (image["width"], image["height"]):
            raise ValueError("Mask dimensions do not match image dimensions")
        counts = measure_mask_pixels(width, height, pixels, [
            image["detection_boxes"][index]["bbox"] for index in detection_indices
        ])
    except (OSError, ValueError, TypeError, OverflowError, IndexError, struct.error, zlib.error) as exc:
        issue(str(exc))
        return result
    result["background_pixels"] = counts["background_pixels"]
    excluded_segments = {item["index"] for item in image["matching"]["excluded_segments"]}
    matched_pairs = {
        (pair["detection_index"], pair["segment_index"])
        for pair in image["matching"]["matches"]
    }
    for segment_index, segment in enumerate(image["panoptic_boxes"]):
        if segment_index in excluded_segments:
            continue
        sid = segment["segment_id"]
        if isinstance(sid, bool) or not isinstance(sid, int) or not 0 < sid <= 0xFFFFFF:
            issue(f"Invalid or background segment ID excluded from coverage: {sid}")
            continue
        total = counts["segment_pixels"].get(sid, 0)
        if total == 0:
            issue(f"Segment {sid} has no actual pixels in the mask")
        segment_name = categories[segment["category_id"]]["name"]
        record = {
            "segment_index": segment_index, "segment_id": sid,
            "category_id": segment["category_id"], "segment_class_name": segment_name,
            "actual_pixels": total, "box_coverages": [], "same_class_box_indices": [],
        }
        for local_index, detection_index in enumerate(detection_indices):
            inside = counts["inside_pixels_by_box"][local_index].get(sid, 0)
            is_matched = (detection_index, segment_index) in matched_pairs
            if inside == 0 and not is_matched:
                continue
            detection = image["detection_boxes"][detection_index]
            detection_name = detection_classes[detection["class_id"]]
            same_class = detection_name == segment_name
            record["box_coverages"].append({
                "detection_index": detection_index, "detection_line": detection.get("line_number"),
                "detection_class_name": detection_name, "same_class": same_class,
                "matched": is_matched, "iou": box_iou(detection["bbox"], segment["bbox"]),
                **_coverage_metrics(total, inside),
            })
            if inside > 0 and same_class:
                record["same_class_box_indices"].append(detection_index)
        result["segments"].append(record)
    result["status"] = "partial" if result["issues"] else "ok"
    return result


def match_delivery_boxes(
    delivery_dir: str | Path, min_iou: float = 0.0, include_coverage: bool = False,
) -> dict[str, Any]:
    """Convert and match boxes, optionally measuring actual mask-pixel coverage."""
    threshold = _match_threshold(min_iou)
    result = load_delivery_boxes(delivery_dir)
    result["matching_config"] = {
        "min_iou": threshold, "strategy": "best_positive_iou_per_detection",
        "many_to_one": True, "class_comparison": "name_after_spatial_matching",
    }
    if not result["images"]:
        return result
    detection_classes, categories, issues = load_class_maps(delivery_dir)
    result["issues"].extend(issues)
    for image in result["images"]:
        image["matching"] = match_image_boxes(image, detection_classes, categories, threshold)
        result["issues"].extend(image["matching"]["issues"])
        if include_coverage:
            image["mask_coverage"] = measure_image_coverage(delivery_dir, image, detection_classes, categories)
            result["issues"].extend(image["mask_coverage"]["issues"])
            metrics = {
                (box["detection_index"], segment["segment_index"]): box
                for segment in image["mask_coverage"]["segments"] for box in segment["box_coverages"]
            }
            for pair in image["matching"]["matches"]:
                measured = metrics.get((pair["detection_index"], pair["segment_index"]))
                pair.update({
                    key: measured[key] if measured else value
                    for key, value in _coverage_metrics(None, None).items()
                })
    return result


@dataclass(frozen=True)
class CandidateConfig:
    """Initial review thresholds; calibrate them on the clean delivery in step 4.

    Coverage values and segment size fractions are proportions, not percentages.
    min_segment_pixels and min_segment_fraction must both pass for mask-based
    candidates. These defaults are general starting values, not measured accuracy.
    """

    min_iou: float = 0.0
    class_min_iou: float = 0.5
    drift_max_coverage: float = 0.9
    min_segment_pixels: int = 64
    min_segment_fraction: float = 0.0005
    missing_min_coverage: float = 0.5
    merge_min_coverage: float = 0.15
    merge_max_box_iou: float = 0.5

    def __post_init__(self):
        for name in (
            "min_iou", "class_min_iou", "drift_max_coverage",
            "min_segment_fraction", "missing_min_coverage",
            "merge_min_coverage", "merge_max_box_iou",
        ):
            original = getattr(self, name)
            value = float(original)
            if isinstance(original, bool) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")
            object.__setattr__(self, name, value)
        if (isinstance(self.min_segment_pixels, bool)
                or not isinstance(self.min_segment_pixels, int)
                or self.min_segment_pixels < 1):
            raise ValueError("min_segment_pixels must be a positive integer")


_CANDIDATE_SIGNS = {
    "class_swap": "class_disagreement", "category_swap": "class_disagreement",
    "bbox_drift": "bbox_drift", "missing_box": "missing_box",
    "instance_merge": "instance_merge",
}
_REVIEW_HINTS = {
    "class_disagreement": (
        "Open the image to decide whether the detection class or panoptic category "
        "is wrong. The two types are alternatives; confirm only the supported type."
    ),
    "bbox_drift": "Check the box against the visible object; occlusion or mask differences may explain low coverage.",
    "missing_box": "Check whether a visible, significant object really lacks a detection box.",
    "instance_merge": "Check whether the segment contains separate objects belonging to the listed same-class boxes.",
}


def _candidate_segment(image: dict, segment: dict, measured: dict | None) -> dict:
    total = measured["actual_pixels"] if measured is not None else None
    return {
        "segment_index": segment["segment_index"], "segment_id": segment["segment_id"],
        "category_id": segment["category_id"], "segment_class_name": segment["segment_class_name"],
        "segment_bbox": list(image["panoptic_boxes"][segment["segment_index"]]["bbox"]),
        "segment_pixels": total,
        "segment_fraction": total / (image["width"] * image["height"]) if total is not None else None,
    }


def _candidate_detection(image: dict, box: dict) -> dict:
    detection = image["detection_boxes"][box["detection_index"]]
    return {
        "detection_index": box["detection_index"], "detection_line": detection.get("line_number"),
        "class_id": detection["class_id"], "detection_class_name": box["detection_class_name"],
        "detection_bbox": list(detection["bbox"]), "iou": box["iou"],
        "primary_match": box.get("matched", True),
        **{name: box.get(name) for name in _coverage_metrics(None, None)},
    }


def candidates_from_matches(
    measurements: dict[str, Any], config: CandidateConfig | None = None,
) -> dict[str, Any]:
    """Build pending candidates from match_delivery_boxes(..., include_coverage=True).

    One record per (type, image) retains all object evidence. Class disagreement
    produces linked class_swap/category_swap alternatives without selecting the
    faulty source. by_sign counts image/sign review groups, so alternatives count
    once there and twice in by_type. No review verdicts or errors are produced.
    """
    match_iou = measurements.get("matching_config", {}).get("min_iou", 0.0)
    config = config if config is not None else CandidateConfig(min_iou=match_iou)
    if config.min_iou != match_iou:
        raise ValueError("Candidate min_iou differs from measurements; rerun matching with the same config")
    images = measurements["images"]
    candidates: dict[tuple[str, str], dict] = {}
    # Unreadable or invalid detection input cannot establish an absent box.
    bad_labels = {
        issue["image"] for issue in measurements.get("issues", [])
        if issue.get("image") is not None and issue.get("source", "").startswith("labels/")
    }

    def add(kind: str, target: str, evidence: dict):
        sign = _CANDIDATE_SIGNS[kind]
        entry = candidates.setdefault((kind, target), {
            "type": kind, "target": target, "image": target, "sign": sign,
            "status": "pending_review", "review_group": f"{target}:{sign}",
            "review_hint": _REVIEW_HINTS[sign], "evidence": [],
        })
        if sign == "class_disagreement":
            entry["alternative_types"] = ["class_swap", "category_swap"]
        if evidence not in entry["evidence"]:
            entry["evidence"].append(evidence)

    def significant(image: dict, segment: dict) -> bool:
        total = segment["actual_pixels"]
        return (total >= config.min_segment_pixels
                and total / (image["width"] * image["height"]) >= config.min_segment_fraction)

    for image in images:
        if "matching" not in image or "mask_coverage" not in image:
            raise ValueError("Candidate generation requires matching and mask-coverage measurements")
        target = image["image"]
        matching = image["matching"]
        measured_segments = image["mask_coverage"]["segments"]
        measured_by_index = {segment["segment_index"]: segment for segment in measured_segments}
        primary_segments = {pair["segment_index"] for pair in matching["matches"]}
        merge_detections: dict[int, set[int]] = {}

        for pair in matching["matches"]:
            sid = pair["segment_id"]
            if isinstance(sid, bool) or not isinstance(sid, int) or not 0 < sid <= 0xFFFFFF:
                continue
            measured = measured_by_index.get(pair["segment_index"])
            if measured is not None and measured["actual_pixels"] == 0:
                continue
            if not pair["same_class"] and pair["iou"] >= config.class_min_iou:
                evidence = {**_candidate_segment(image, pair, measured), **_candidate_detection(image, pair)}
                for kind in ("class_swap", "category_swap"):
                    add(kind, target, evidence)

        for segment in measured_segments:
            if not significant(image, segment):
                continue
            boxes = segment["box_coverages"]
            merge_boxes = [
                box for box in boxes if box["same_class"] and box["inside_pixels"] > 0
                and box["coverage"] is not None and box["coverage"] >= config.merge_min_coverage
            ]
            distinct_pairs = []
            involved: set[int] = set()
            for first, second in combinations(merge_boxes, 2):
                indices = [first["detection_index"], second["detection_index"]]
                first_bbox, second_bbox = [image["detection_boxes"][index]["bbox"] for index in indices]
                overlap = box_iou(first_bbox, second_bbox)
                # Nested boxes do not provide two separate-instance regions,
                # even when their IoU is low because one box is much smaller.
                nested = any(
                    outer[0] <= inner[0] and outer[1] <= inner[1]
                    and outer[2] >= inner[2] and outer[3] >= inner[3]
                    for outer, inner in ((first_bbox, second_bbox), (second_bbox, first_bbox))
                )
                if overlap <= config.merge_max_box_iou and not nested:
                    distinct_pairs.append({"detection_indices": indices, "box_iou": overlap})
                    involved.update(indices)
            if distinct_pairs:
                merge_detections[segment["segment_index"]] = involved
                add("instance_merge", target, {
                    **_candidate_segment(image, segment, segment),
                    "detections": [_candidate_detection(image, box) for box in merge_boxes
                                   if box["detection_index"] in involved],
                    "same_class_box_count": len(involved), "distinct_box_pairs": distinct_pairs,
                })
            # A segment can lose the best-IoU match while still having a useful
            # nonprimary box. Consider all measured boxes, regardless of class.
            corresponding = any(
                box["iou"] > 0 and box["iou"] >= config.min_iou
                and box["inside_pixels"] > 0 and box["coverage"] is not None
                and box["coverage"] >= config.missing_min_coverage for box in boxes
            )
            if (target not in bad_labels and segment["segment_index"] not in primary_segments
                    and not corresponding):
                add("missing_box", target, {
                    **_candidate_segment(image, segment, segment),
                    "nearby_detections": [_candidate_detection(image, box) for box in boxes],
                    "primary_match": False,
                })

        for pair in matching["matches"]:
            segment = measured_by_index.get(pair["segment_index"])
            if (not pair["same_class"] or segment is None or not significant(image, segment)
                    or pair["coverage"] is None or pair["coverage"] >= config.drift_max_coverage
                    or pair["detection_index"] in merge_detections.get(pair["segment_index"], set())):
                continue
            add("bbox_drift", target, {
                **_candidate_segment(image, segment, segment), **_candidate_detection(image, pair),
                "same_class_box_count": len(segment["same_class_box_indices"]),
            })

    entries = sorted(candidates.values(), key=lambda entry: (entry["target"], entry["type"]))
    groups = {(entry["target"], entry["sign"]) for entry in entries}
    return {
        "schema_version": 1, "review_required": True, "config": asdict(config),
        "candidates": entries,
        "summary": {
            "image_count": len(images), "candidate_count": len(entries),
            "candidate_image_count": len({entry["target"] for entry in entries}),
            "review_group_count": len(groups),
            "by_type": {kind: sum(entry["type"] == kind for entry in entries) for kind in _CANDIDATE_SIGNS},
            "by_sign": {sign: sum(group[1] == sign for group in groups)
                        for sign in dict.fromkeys(_CANDIDATE_SIGNS.values())},
        },
        "issues": list(measurements.get("issues", [])),
    }


def generate_candidates(
    delivery_dir: str | Path, config: CandidateConfig | None = None,
) -> dict[str, Any]:
    """M2 integration: return candidates and diagnostics, reading only delivery.

    Write this result to the validator's --candidates path. Keep rule errors and
    human-confirmed semantic errors in their separate, existing output workflow.
    """
    config = config if config is not None else CandidateConfig()
    measured = match_delivery_boxes(delivery_dir, config.min_iou, include_coverage=True)
    return candidates_from_matches(measured, config)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--match", action="store_true", help="Match boxes by IoU and compare class names")
    parser.add_argument("--coverage", action="store_true", help="Match boxes and measure actual mask-pixel coverage")
    parser.add_argument("--candidates", action="store_true", help="Write pending review candidates; includes matching and coverage")
    parser.add_argument("--min-iou", type=float, default=0.0, help="Minimum match IoU (0-1); overlap must be positive")
    defaults = CandidateConfig()
    parser.add_argument("--class-min-iou", type=float, default=defaults.class_min_iou, help="Minimum IoU for class-disagreement candidates")
    parser.add_argument("--drift-max-coverage", type=float, default=defaults.drift_max_coverage, help="Flag same-class coverage below this proportion")
    parser.add_argument("--min-segment-pixels", type=int, default=defaults.min_segment_pixels, help="Minimum actual pixels for mask-based candidates")
    parser.add_argument("--min-segment-fraction", type=float, default=defaults.min_segment_fraction, help="Minimum segment pixels / image pixels")
    parser.add_argument("--missing-min-coverage", type=float, default=defaults.missing_min_coverage, help="Minimum coverage for a nonprimary corresponding box")
    parser.add_argument("--merge-min-coverage", type=float, default=defaults.merge_min_coverage, help="Minimum segment coverage in each proposed merge box")
    parser.add_argument("--merge-max-box-iou", type=float, default=defaults.merge_max_box_iou, help="Maximum box-pair IoU for separate-object merge evidence")
    args = parser.parse_args()
    if args.out.resolve().is_relative_to(args.delivery.resolve()):
        parser.error("Output must be outside delivery; preserve the original release")
    try:
        _match_threshold(args.min_iou)
        config = CandidateConfig(**{name: getattr(args, name) for name in asdict(defaults)})
    except ValueError as exc:
        parser.error(str(exc))
    result = (generate_candidates(args.delivery, config) if args.candidates
              else match_delivery_boxes(args.delivery, args.min_iou, args.coverage) if args.match or args.coverage
              else load_delivery_boxes(args.delivery))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.candidates:
        summary = result["summary"]
        print(f"Images: {summary['image_count']}; candidates: {summary['candidate_count']}; "
              f"images to review: {summary['candidate_image_count']}; "
              f"review groups: {summary['review_group_count']}; issues: {len(result['issues'])}")
        print("By type: " + json.dumps(summary["by_type"]))
        print("By sign (class alternatives counted once): " + json.dumps(summary["by_sign"]))
        return 0 if summary["image_count"] else 1
    detections = sum(len(image["detection_boxes"]) for image in result["images"])
    segments = sum(len(image["panoptic_boxes"]) for image in result["images"])
    print(f"Images: {len(result['images'])}; YOLO boxes: {detections}; "
          f"panoptic boxes: {segments}; issues: {len(result['issues'])}")
    if args.match or args.coverage:
        matches = [match for image in result["images"] for match in image["matching"]["matches"]]
        print(f"Pairs: {len(matches)}; different class names: "
              f"{sum(not match['same_class'] for match in matches)}")
        if args.coverage:
            print(f"Pairs with coverage: {sum(match['coverage'] is not None for match in matches)}; "
                  f"masks measured: {sum(image['mask_coverage']['status'] != 'unavailable' for image in result['images'])}")
    return 0 if result["images"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
