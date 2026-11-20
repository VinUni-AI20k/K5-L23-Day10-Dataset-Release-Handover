"""Check declared panoptic categories and mask areas."""

import json
from collections import Counter
from pathlib import Path

from scripts.pngutil import read_rgb


def check_panoptic(delivery: Path) -> list[dict[str, str]]:
    delivery = delivery.resolve()
    data = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    categories = {row["id"]: row["isthing"] for row in data["categories"]}
    images = {row["id"]: Path(row["file_name"]).stem for row in data["images"]}
    findings = set()
    for annotation in data["annotations"]:
        target = images[annotation["image_id"]]
        segments = annotation["segments_info"]
        if any(segment["category_id"] not in categories for segment in segments):
            findings.add(("invalid_category_id", target))

        things = [
            segment for segment in segments
            if segment["id"] != 0 and categories.get(segment["category_id"])
        ]
        if not things:
            continue
        mask = (delivery / "masks" / annotation["file_name"]).resolve()
        if not mask.is_relative_to(delivery):
            raise ValueError(f"Mask path outside delivery: {annotation['file_name']}")
        _, _, pixels = read_rgb(mask)
        # Each RGB triple uniquely encodes a segment ID.
        counts = Counter(zip(pixels[0::3], pixels[1::3], pixels[2::3]))
        for segment in things:
            sid = segment["id"]
            color = (sid & 255, (sid >> 8) & 255, (sid >> 16) & 255)
            if segment["area"] > counts[color]:
                findings.add(("thing_overlap", target))
                break

    return [{"type": kind, "target": target} for kind, target in sorted(findings)]
