"""Lỗi luật nhóm metadata + panoptic (phần của Đặng Thu Hương).

- scene_leak          : một cảnh có ảnh ở cả train và val        (target = scene_id)
- guideline_mismatch  : guideline của ảnh khác guideline của job  (target = ảnh)
- invalid_category_id : segment có category_id không có trong categories
- thing_overlap       : area khai trong segments_info > số pixel thật của segment trong mask

Chỉ đọc thư mục delivery được truyền vào, chỉ thư viện chuẩn + scripts/pngutil.py.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _stem(name: str) -> str:
    return Path(name).stem


# ---------------------------------------------------------------- metadata

def check_scene_leak(metadata: list[dict]) -> list[dict]:
    splits: dict[str, set[str]] = defaultdict(set)
    for item in metadata:
        splits[item["scene_id"]].add(item["split"])
    return [{"type": "scene_leak", "target": scene} for scene, s in sorted(splits.items()) if len(s) > 1]


def check_guideline_mismatch(metadata: list[dict], jobs: dict[str, str]) -> list[dict]:
    out = []
    for item in metadata:
        job_guideline = jobs.get(item["job_id"])
        if job_guideline is not None and item.get("guideline_version") != job_guideline:
            out.append({"type": "guideline_mismatch", "target": item["image"]})
    return out


def load_jobs(delivery: Path) -> dict[str, str]:
    with (delivery / "jobs.csv").open(encoding="utf-8", newline="") as f:
        return {row["job_id"].strip(): row["guideline"].strip() for row in csv.DictReader(f)}


# ---------------------------------------------------------------- panoptic

def check_invalid_category(panoptic: dict) -> list[dict]:
    valid = {c["id"] for c in panoptic["categories"]}
    out = []
    for ann in panoptic["annotations"]:
        if any(seg["category_id"] not in valid for seg in ann["segments_info"]):
            out.append({"type": "invalid_category_id", "target": _stem(ann["file_name"])})
    return out


def count_segment_pixels(mask_path: Path) -> Counter:
    width, height, pixels = pngutil.read_rgb(mask_path)
    counts: Counter = Counter()
    for i in range(0, width * height * 3, 3):
        counts[pixels[i] + pixels[i + 1] * 256 + pixels[i + 2] * 65536] += 1
    return counts


def check_thing_overlap(delivery: Path, panoptic: dict) -> list[dict]:
    out = []
    for ann in panoptic["annotations"]:
        mask_path = delivery / "masks" / ann["file_name"]
        if not mask_path.is_file():
            continue  # thiếu mask không phải loại lỗi này
        counts = count_segment_pixels(mask_path)
        # area khai > pixel thật => segment bị vật khác đè lên. Bỏ id 0 (nền).
        if any(seg["id"] != 0 and seg["area"] > counts.get(seg["id"], 0) for seg in ann["segments_info"]):
            out.append({"type": "thing_overlap", "target": _stem(ann["file_name"])})
    return out


# ---------------------------------------------------------------- entry

def check(delivery: Path) -> list[dict]:
    delivery = Path(delivery)
    metadata = _load_json(delivery / "metadata.json")["items"]
    panoptic = _load_json(delivery / "panoptic.json")
    errors = []
    errors += check_scene_leak(metadata)
    errors += check_guideline_mismatch(metadata, load_jobs(delivery))
    errors += check_invalid_category(panoptic)
    errors += check_thing_overlap(delivery, panoptic)
    return errors


if __name__ == "__main__":
    for e in check(Path(sys.argv[1])):
        print(e["type"], e["target"])
