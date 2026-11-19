#!/usr/bin/env python3
"""Validate the delivery's machine-checkable rules using only its files."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from pngutil import read_rgb


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root: Path) -> list[dict[str, str]]:
    manifest = read_json(root / "manifest.json")["items"]
    metadata = read_json(root / "metadata.json")["items"]
    panoptic = read_json(root / "panoptic.json")
    with (root / "jobs.csv").open(encoding="utf-8", newline="") as stream:
        jobs = {row["job_id"]: row["guideline"] for row in csv.DictReader(stream)}
    classes = {int(line.split(maxsplit=1)[0]) for line in (root / "classes.txt").read_text(encoding="utf-8").splitlines() if line.strip()}
    categories = {c["id"]: c for c in panoptic["categories"]}
    dimensions = {im["id"]: (im["width"], im["height"]) for im in panoptic["images"]}
    annotations = {Path(a["file_name"]).stem: a for a in panoptic["annotations"]}
    errors: set[tuple[str, str]] = set()
    scenes: dict[str, set[str]] = defaultdict(set)
    for item in metadata:
        scenes[item["scene_id"]].add(item["split"])
        if item["guideline_version"] != jobs[item["job_id"]]:
            errors.add(("guideline_mismatch", item["image"]))
    for scene, splits in scenes.items():
        if len(splits) > 1:
            errors.add(("scene_leak", scene))

    for image, item in manifest.items():
        for kind in ("image", "label", "mask"):
            path = root / item[kind]
            if not path.is_file():
                if kind == "image":
                    errors.add(("missing_image", image))
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != item[kind + "_sha256"]:
                errors.add(("wrong_hash", image))

        annotation = annotations[Path(item["mask"]).stem]
        width, height = dimensions[annotation["image_id"]]
        label = root / item["label"]
        boxes = []
        if label.is_file():
            for line in label.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                cls, x, y, w, h = map(float, line.split())
                if not cls.is_integer() or int(cls) not in classes:
                    errors.add(("invalid_class", image))
                if not all(map(math.isfinite, (x, y, w, h))) or w <= 0 or h <= 0 or x - w / 2 < -1e-6 or y - h / 2 < -1e-6 or x + w / 2 > 1 + 1e-6 or y + h / 2 > 1 + 1e-6:
                    errors.add(("bbox_out_of_bounds", image))
                for old_cls, ox, oy, ow, oh in boxes:
                    if cls == old_cls and abs(w - ow) * width < 0.01 and abs(h - oh) * height < 0.01 and abs(x - ox) * width <= 2.1 and abs(y - oy) * height <= 2.1:
                        errors.add(("duplicate_box", image))
                boxes.append((cls, x, y, w, h))

        segments = annotation["segments_info"]
        if any(s["category_id"] not in categories for s in segments):
            errors.add(("invalid_category_id", image))
        mask = root / item["mask"]
        if mask.is_file():
            _, _, pixels = read_rgb(mask)
            counts = Counter(pixels[i] + (pixels[i + 1] << 8) + (pixels[i + 2] << 16) for i in range(0, len(pixels), 3))
            for segment in segments:
                category = categories.get(segment["category_id"], {})
                if category.get("isthing") and segment["area"] > counts[segment["id"]]:
                    errors.add(("thing_overlap", image))
                    break
    return [{"type": kind, "target": target} for kind, target in sorted(errors)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, help="Reserved for the cross-check phase")
    args = parser.parse_args()
    if args.candidates:
        parser.error("--candidates is not implemented yet; cross-check review is a separate phase")
    errors = validate(args.delivery)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(errors)} rule findings written to {args.out}")


if __name__ == "__main__":
    main()
