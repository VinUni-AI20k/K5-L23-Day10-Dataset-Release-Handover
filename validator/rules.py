"""Nine delivery-only validation rules; standard library plus lab PNG reader."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pngutil import read_rgb

# Six-decimal YOLO serialization can move an edge by 0.00000075.
ROUNDING_EPS = 1e-6
DUPLICATE_CENTER_PX = 2.0
DUPLICATE_SIZE_PX = 0.01


def delivery_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path outside delivery: {relative}")
    return path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def box_outside(box) -> bool:
    _, x, y, w, h = box
    return (not all(math.isfinite(v) for v in (x, y, w, h))
            or w <= 0 or h <= 0
            or x - w / 2 < -ROUNDING_EPS or y - h / 2 < -ROUNDING_EPS
            or x + w / 2 > 1 + ROUNDING_EPS or y + h / 2 > 1 + ROUNDING_EPS)


def duplicate_boxes(a, b, width: int, height: int) -> bool:
    return (a[0] == b[0]
            and abs(a[3] - b[3]) * width <= DUPLICATE_SIZE_PX
            and abs(a[4] - b[4]) * height <= DUPLICATE_SIZE_PX
            and abs(a[1] - b[1]) * width <= DUPLICATE_CENTER_PX + ROUNDING_EPS * width
            and abs(a[2] - b[2]) * height <= DUPLICATE_CENTER_PX + ROUNDING_EPS * height)


def validate_rules(delivery: str | Path) -> dict:
    """Return {errors: [{type, target}]} without reading any other dataset."""
    root = Path(delivery).resolve()
    manifest = read_json(delivery_path(root, "manifest.json"))["items"]
    metadata = read_json(delivery_path(root, "metadata.json"))["items"]
    panoptic = read_json(delivery_path(root, "panoptic.json"))
    classes = {int(line.split(maxsplit=1)[0]) for line in
               delivery_path(root, "classes.txt").read_text(encoding="utf-8-sig").splitlines() if line.strip()}
    with delivery_path(root, "jobs.csv").open(encoding="utf-8-sig", newline="") as stream:
        jobs = {row["job_id"]: row["guideline"] for row in csv.DictReader(stream)}
    categories = {c["id"]: c for c in panoptic["categories"]}
    images = {Path(im["file_name"]).stem: im for im in panoptic["images"]}
    annotations = {ann["image_id"]: ann for ann in panoptic["annotations"]}
    found = set()

    def add(kind, target):
        found.add((kind, target))

    for name, item in manifest.items():
        target = Path(item["image"]).stem
        for kind in ("image", "label", "mask"):
            path = delivery_path(root, item[kind])
            if not path.is_file():
                if kind == "image":
                    add("missing_image", target)
                    continue
                raise ValueError(f"Missing {kind} file: {item[kind]}")
            if sha256(path).lower() != item[f"{kind}_sha256"].lower():
                add("wrong_hash", target)

        im = images[target]
        width, height = im["width"], im["height"]
        boxes = []
        for number, line in enumerate(delivery_path(root, item["label"]).read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) != 5:
                raise ValueError(f"{item['label']}:{number}: expected five YOLO fields")
            box = tuple(float(v) for v in fields)
            if box[0] not in classes:
                add("invalid_class", target)
            if box_outside(box):
                add("bbox_out_of_bounds", target)
            boxes.append(box)
        if any(duplicate_boxes(a, b, width, height) for a, b in combinations(boxes, 2)):
            add("duplicate_box", target)

        mw, mh, pixels = read_rgb(delivery_path(root, item["mask"]))
        if (mw, mh) != (width, height):
            raise ValueError(f"Mask dimensions differ from image: {target}")
        counts = Counter(r + (g << 8) + (b << 16)
                         for r, g, b in zip(pixels[0::3], pixels[1::3], pixels[2::3]))
        for segment in annotations[im["id"]]["segments_info"]:
            category = categories.get(segment["category_id"])
            if category is None:
                add("invalid_category_id", target)
            elif (category.get("isthing") and segment["id"] != 0
                  and segment["area"] > counts[segment["id"]]):
                add("thing_overlap", target)

    scenes = defaultdict(set)
    for row in metadata:
        scenes[row["scene_id"]].add(row["split"])
        if row["guideline_version"] != jobs[row["job_id"]]:
            add("guideline_mismatch", Path(row["image"]).stem)
    for scene, splits in scenes.items():
        if "train" in splits and splits.intersection({"val", "validation"}):
            add("scene_leak", scene)
    return {"errors": [{"type": kind, "target": target} for kind, target in sorted(found)]}
