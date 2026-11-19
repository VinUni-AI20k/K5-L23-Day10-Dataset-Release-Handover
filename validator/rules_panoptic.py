"""Rule checks for panoptic segment integrity and overlap."""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to path to use pngutil
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import pngutil  # noqa: E402

IMPLEMENTED = True


def count_mask_pixels(mask_path: Path) -> dict[int, int]:
    """Read a panoptic mask PNG and count pixels for each segment ID (excluding background 0)."""
    if not mask_path.is_file():
        return {}
    _, _, pixels = pngutil.read_rgb(mask_path)
    counts: dict[int, int] = {}
    for i in range(0, len(pixels), 3):
        sid = pngutil.segment_id(pixels, i)
        if sid != 0:
            counts[sid] = counts.get(sid, 0) + 1
    return counts


def check(ctx: dict) -> list[dict]:
    root = ctx["root"]
    annotations = ctx["annotations"]
    categories = ctx["categories"]
    manifest = ctx["manifest"]

    errors = []

    for name, ann in annotations.items():
        segments_info = ann.get("segments_info", [])

        # 1. invalid_category_id
        has_invalid = False
        for seg in segments_info:
            cat_id = seg.get("category_id")
            if cat_id not in categories:
                errors.append({"type": "invalid_category_id", "target": name})
                has_invalid = True
                break

        if has_invalid:
            continue

        # 2. thing_overlap
        # In COCO panoptic, normal reported area == actual mask pixels.
        # When thing_overlap occurs, a donor segment's pixels are partially stolen,
        # so reported area > actual pixels.
        mask_rel = manifest.get(name, {}).get("mask")
        if mask_rel:
            mask_path = root / mask_rel
            if mask_path.is_file():
                counts = count_mask_pixels(mask_path)
                for seg in segments_info:
                    sid = seg.get("id")
                    reported_area = seg.get("area", 0)
                    actual_px = counts.get(sid, 0)
                    if reported_area - actual_px >= 2:
                        errors.append({"type": "thing_overlap", "target": name})
                        break

    return errors
