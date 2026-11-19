"""Panoptic rule-based checks for Day 10 Lab (TV2).

Detects the two panoptic rule faults using Python standard library only
(plus scripts/pngutil.py for 8-bit RGB PNG decoding):
  1. invalid_category_id: segment category_id not in panoptic.json categories.
  2. thing_overlap: declared segment area > actual pixel count in mask PNG.
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


def count_mask_pixels(mask_path: Path) -> tuple[int, int, dict[int, int]]:
    """Decode an 8-bit RGB panoptic mask PNG and count pixels per segment id.

    Segment id = R + G * 256 + B * 65536. Background (id == 0) is excluded.
    Returns (width, height, {segment_id: pixel_count}).
    """
    width, height, pixels = read_rgb(mask_path)
    rgb_counts = Counter(zip(pixels[0::3], pixels[1::3], pixels[2::3]))
    actual_area: dict[int, int] = {}
    for (r, g, b), count in rgb_counts.items():
        sid = r + (g << 8) + (b << 16)
        if sid != 0:
            actual_area[sid] = count
    return width, height, actual_area


def _build_stem_map(panoptic: dict[str, Any]) -> dict[int, str]:
    """Map image_id -> image stem (works for both COCO ids and opaque img_xxxx)."""
    stem_by_id: dict[int, str] = {}
    for im in panoptic.get("images", []):
        image_id = im.get("id")
        file_name = im.get("file_name")
        if image_id is not None and file_name:
            stem_by_id[image_id] = Path(file_name).stem
    return stem_by_id


def check_panoptic_rules(delivery_dir: Path | str) -> list[dict[str, str]]:
    """Run all panoptic rule checks on a delivery directory.

    Reads only files inside `delivery_dir`.
    Returns a sorted list of unique {"type": ..., "target": ...} findings.
    """
    delivery = Path(delivery_dir)
    panoptic_path = delivery / "panoptic.json"
    if not panoptic_path.is_file():
        return []

    panoptic = json.loads(panoptic_path.read_text(encoding="utf-8"))
    valid_cat_ids = {
        cat["id"] for cat in panoptic.get("categories", []) if "id" in cat
    }
    stem_by_id = _build_stem_map(panoptic)
    masks_dir = delivery / "masks"

    found: set[tuple[str, str]] = set()

    for ann in panoptic.get("annotations", []):
        image_id = ann.get("image_id")
        ann_file = ann.get("file_name", "")
        stem = stem_by_id.get(image_id) or (Path(ann_file).stem if ann_file else str(image_id))
        segments = ann.get("segments_info", [])

        # Rule 1: invalid_category_id
        has_invalid_cat = False
        for seg in segments:
            if seg.get("category_id") not in valid_cat_ids:
                has_invalid_cat = True
                break
        if has_invalid_cat:
            found.add(("invalid_category_id", stem))

        # Rule 2: thing_overlap
        mask_name = Path(ann_file).name if ann_file else f"{stem}.png"
        mask_path = masks_dir / mask_name
        if not mask_path.is_file():
            fallback = masks_dir / f"{stem}.png"
            if fallback.is_file():
                mask_path = fallback
            else:
                continue

        _, _, actual_area = count_mask_pixels(mask_path)
        for seg in segments:
            sid = seg.get("id")
            declared_area = seg.get("area")
            if sid is None or sid == 0 or declared_area is None:
                continue
            if declared_area > actual_area.get(sid, 0):
                found.add(("thing_overlap", stem))
                break

    return [{"type": ftype, "target": target} for ftype, target in sorted(found)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run panoptic rule checks (invalid_category_id, thing_overlap) on a delivery directory."
    )
    parser.add_argument("delivery", type=Path, help="Path to delivery directory")
    parser.add_argument("--out", type=Path, default=None, help="Optional output JSON path")
    args = parser.parse_args()

    t0 = time.perf_counter()
    errors = check_panoptic_rules(args.delivery)
    elapsed = time.perf_counter() - t0

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({"errors": errors}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    counts: Counter[str] = Counter(e["type"] for e in errors)
    print(
        f"Checked {args.delivery} in {elapsed:.2f}s -> {len(errors)} panoptic rule faults: {dict(counts)}"
    )


if __name__ == "__main__":
    main()
