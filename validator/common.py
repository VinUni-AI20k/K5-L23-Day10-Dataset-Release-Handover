"""Delivery-only loader shared by rule checks and panoptic crosschecking.

Image keys are manifest keys (opaque strings, never COCO numeric IDs).
ctx keys: root, manifest, meta, jobs, classes, panoptic, images,
annotations, categories, detections. images/annotations are keyed by image name;
categories by category ID. detections[name] is a list of dictionaries with
class_id, xywh (normalized), xyxy (normalized), xyxy_px and line.
"""

import csv
import json
import math
from pathlib import Path


def delivery_path(root, relative):
    """Resolve an input path without allowing reads outside delivery."""
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path outside delivery: {relative}")
    return path


def yolo_to_xyxy(x, y, w, h):
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def yolo_to_pixel(x, y, w, h, width, height):
    """Return pixel (left, top, right, bottom), without clipping bad boxes."""
    left, top, right, bottom = yolo_to_xyxy(x, y, w, h)
    return (left * width, top * height, right * width, bottom * height)


def read_yolo(path, width, height):
    boxes = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        values = line.split()
        if len(values) != 5:
            raise ValueError(f"{path}:{line_no}: expected 5 YOLO fields")
        try:
            c, x, y, w, h = map(float, values)
        except ValueError as exc:
            raise ValueError(f"{path}:{line_no}: invalid YOLO number") from exc
        if not all(math.isfinite(v) for v in (c, x, y, w, h)):
            raise ValueError(f"{path}:{line_no}: non-finite YOLO number")
        boxes.append({"class_id": int(c) if c.is_integer() else c,
                      "xywh": (x, y, w, h), "xyxy": yolo_to_xyxy(x, y, w, h),
                      "xyxy_px": yolo_to_pixel(x, y, w, h, width, height),
                      "line": line_no})
    return boxes


def load(delivery_dir):
    root = Path(delivery_dir).resolve()

    def read_json(relative):
        return json.loads(delivery_path(root, relative).read_text(encoding="utf-8-sig"))

    manifest = read_json("manifest.json")["items"]
    meta = {m["image"]: m for m in read_json("metadata.json")["items"]}
    with delivery_path(root, "jobs.csv").open(encoding="utf-8-sig", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}
    classes = {}
    for line in delivery_path(root, "classes.txt").read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            class_id, name = line.split(maxsplit=1)
            classes[int(class_id)] = name.strip()
    panoptic = read_json("panoptic.json")
    image_by_file = {Path(im["file_name"]).name: im for im in panoptic["images"]}
    ann_by_id = {ann["image_id"]: ann for ann in panoptic["annotations"]}
    images, annotations, detections = {}, {}, {}
    for name, item in manifest.items():
        # Validate all manifest input paths, even when a module does not read them yet.
        for key in ("image", "label", "mask"):
            delivery_path(root, item[key])
        filename = Path(item["image"]).name
        if filename not in image_by_file:
            raise ValueError(f"No panoptic image dimensions for {name}")
        image = image_by_file[filename]
        if image["width"] <= 0 or image["height"] <= 0:
            raise ValueError(f"Invalid image dimensions for {name}")
        images[name] = image
        annotations[name] = ann_by_id[image["id"]]
        jobs[meta[name]["job_id"]]  # Fail explicitly on broken metadata references.
        detections[name] = read_yolo(delivery_path(root, item["label"]),
                                     image["width"], image["height"])
    return {"root": root, "manifest": manifest, "meta": meta, "jobs": jobs,
            "classes": classes, "panoptic": panoptic, "images": images,
            "annotations": annotations, "categories": {c["id"]: c for c in panoptic["categories"]},
            "detections": detections}
