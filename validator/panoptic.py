from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# The assignment explicitly allows importing scripts/pngutil.py.
_scripts = str(Path(__file__).resolve().parents[1] / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from pngutil import read_rgb, segment_id  # noqa: E402


def _input_path(delivery: Path, relative: str) -> Path:
    path = (delivery / relative).resolve()
    if not path.is_relative_to(delivery):
        raise ValueError(f"Input is outside delivery: {relative}")
    return path


def validate_panoptic(delivery_path: str | Path) -> list[dict[str, str]]:
    """Return invalid_category_id and thing_overlap findings once per image/type."""
    delivery = Path(delivery_path).resolve(strict=True)
    document = json.loads(
        _input_path(delivery, "panoptic.json").read_text(encoding="utf-8-sig")
    )
    categories = {row["id"]: row for row in document["categories"]}
    images = {row["id"]: row for row in document["images"]}
    findings: set[tuple[str, str]] = set()

    for annotation in document["annotations"]:
        image_id = annotation["image_id"]
        if image_id not in images:
            raise ValueError(f"Unknown panoptic image_id: {image_id!r}")
        # Resolve image_id through images; do not assume numeric COCO filenames.
        target = Path(images[image_id]["file_name"]).stem
        mask = _input_path(delivery, "masks/" + annotation["file_name"])
        _, _, pixels = read_rgb(mask)
        # One count per mask, reused for all its segments. index is a BYTE offset.
        counts = Counter(
            segment_id(pixels, index) for index in range(0, len(pixels), 3)
        )

        for segment in annotation["segments_info"]:
            sid = segment["id"]
            if sid == 0:
                continue  # ID 0 is the void/background convention in this lab.
            category = categories.get(segment["category_id"])
            if category is None:
                findings.add(("invalid_category_id", target))
                continue
            if category.get("isthing") == 1:
                declared_area = segment["area"]
                actual_area = counts.get(sid, 0)
                if declared_area > actual_area:
                    findings.add(("thing_overlap", target))

    return [{"type": kind, "target": target} for kind, target in sorted(findings)]
