#!/usr/bin/env python3
"""Validator của nhóm 13 — Day 10 Lab.

    python validator/validate.py <delivery> --out <errors.json> [--candidates <candidates.json>]

Chỉ đọc thư mục <delivery> được truyền vào. Chỉ dùng thư viện chuẩn
(+ scripts/pngutil.py để đọc mask PNG). Không đọc _private/, data_source/,
annotation COCO, không dùng mạng.

Pha 1 — 9 lỗi luật:
  file      : missing_image, wrong_hash
  detection : invalid_class, bbox_out_of_bounds, duplicate_box
  metadata  : scene_leak (target = scene_id), guideline_mismatch
  panoptic  : invalid_category_id, thing_overlap
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pngutil  # noqa: E402  (đọc PNG bằng thư viện chuẩn, được phép theo RULES)

# --------------------------------------------------------------------------
# Ngưỡng (đo trên lô sạch runs/clean + các seed luyện tập, xem REPORT.md)
# --------------------------------------------------------------------------
OOB_TOL_PX = 0.5        # box tràn mép quá 0.5 px mới tính là bbox_out_of_bounds
DUP_SIZE_TOL_PX = 0.5   # duplicate_box: hai box cùng kích thước (lệch w, h <= 0.5 px)
DUP_SHIFT_MAX_PX = 3.0  # ... và tâm chỉ lệch <= 3 px theo mỗi trục
OVERLAP_TOL_PX = 2      # thing_overlap: area khai > số pixel thật + tol


# --------------------------------------------------------------------------
# Tiện ích đọc file
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    """sha256 trên BYTES của file (mở chế độ rb), không phải trên text."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def jpeg_size(path: Path) -> tuple[int, int] | None:
    """Đọc (width, height) từ header JPEG (marker SOFn), không cần Pillow."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            pos += 1 if marker == 0xFF else 2
            continue
        length = int.from_bytes(data[pos + 2 : pos + 4], "big")
        # SOF0..SOF15, trừ DHT(C4), JPG(C8), DAC(CC)
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[pos + 5 : pos + 7], "big")
            width = int.from_bytes(data[pos + 7 : pos + 9], "big")
            return width, height
        pos += 2 + length
    return None


def read_labels(path: Path) -> list[tuple[str, float, float, float, float]] | None:
    """Đọc nhãn YOLO. Trả về list (class_token, xc, yc, w, h) — class giữ dạng chuỗi
    để kiểm invalid_class (có thể là '80', '-1', '3.5'...)."""
    if not path.exists():
        return None
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            xc, yc, w, h = (float(v) for v in parts[1:5])
        except ValueError:
            xc = yc = w = h = float("nan")
        rows.append((parts[0], xc, yc, w, h))
    return rows


def load_delivery(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    panoptic = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
    with open(root / "jobs.csv", encoding="utf-8", newline="") as f:
        jobs = {row["job_id"].strip(): row for row in csv.DictReader(f)}
    classes = {}
    for line in (root / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            idx, name = line.split(maxsplit=1)
            classes[int(idx)] = name.strip()
    return {
        "items": manifest["items"],
        "meta": metadata["items"],
        "panoptic": panoptic,
        "jobs": jobs,
        "classes": classes,
    }


# --------------------------------------------------------------------------
# Các luật
# --------------------------------------------------------------------------
def check_files(root: Path, items: dict) -> tuple[list[dict], set[str]]:
    """missing_image + wrong_hash (image, label, mask). Trả về lỗi và tập ảnh thiếu."""
    errors, missing = [], set()
    for stem, item in items.items():
        img = root / item["image"]
        if not img.exists():
            errors.append({"type": "missing_image", "target": stem})
            missing.add(stem)
            continue
        for key in ("image", "label", "mask"):
            rel, expected = item.get(key), item.get(f"{key}_sha256")
            if not rel or not expected:
                continue
            path = root / rel
            if path.exists() and sha256_file(path) != expected.lower():
                errors.append({"type": "wrong_hash", "target": stem})
                break
    return errors, missing


def image_sizes(root: Path, items: dict, panoptic: dict) -> dict[str, tuple[int, int]]:
    """Kích thước ảnh: ưu tiên header JPEG thật; thiếu file thì lấy từ panoptic.json."""
    from_pan = {Path(im["file_name"]).stem: (im["width"], im["height"]) for im in panoptic["images"]}
    sizes = {}
    for stem, item in items.items():
        size = jpeg_size(root / item["image"]) or from_pan.get(stem)
        if size:
            sizes[stem] = size
    return sizes


def check_labels(root: Path, items: dict, classes: dict, sizes: dict) -> list[dict]:
    """invalid_class, bbox_out_of_bounds, duplicate_box."""
    errors = []
    valid_ids = set(classes)
    for stem, item in items.items():
        rows = read_labels(root / item["label"])
        if rows is None or stem not in sizes:
            continue
        W, H = sizes[stem]

        # invalid_class: class_id phải là số nguyên trong 0..79
        bad_class = False
        for token, *_ in rows:
            try:
                ok = float(token).is_integer() and int(float(token)) in valid_ids
            except ValueError:
                ok = False
            if not ok:
                bad_class = True
                break
        if bad_class:
            errors.append({"type": "invalid_class", "target": stem})
            continue

        # đổi YOLO chuẩn hoá -> pixel (x1, y1, x2, y2, w, h)
        boxes = []
        for token, xc, yc, w, h in rows:
            bw, bh = w * W, h * H
            x1, y1 = xc * W - bw / 2, yc * H - bh / 2
            boxes.append((int(float(token)), x1, y1, x1 + bw, y1 + bh, bw, bh))

        # bbox_out_of_bounds: tràn mép ảnh quá OOB_TOL_PX
        if any(
            x1 < -OOB_TOL_PX or y1 < -OOB_TOL_PX or x2 > W + OOB_TOL_PX or y2 > H + OOB_TOL_PX
            for _, x1, y1, x2, y2, _, _ in boxes
        ):
            errors.append({"type": "bbox_out_of_bounds", "target": stem})
            continue

        # duplicate_box: cùng lớp, CÙNG kích thước, tâm chỉ lệch 1-2 px.
        # Không dùng IoU vì cặp box tự nhiên của COCO có thể chồng nhau tới IoU ~0.66.
        dup = False
        for i in range(len(boxes)):
            ci, ax1, ay1, _, _, aw, ah = boxes[i]
            for j in range(i + 1, len(boxes)):
                cj, bx1, by1, _, _, bw, bh = boxes[j]
                if ci != cj:
                    continue
                if abs(aw - bw) > DUP_SIZE_TOL_PX or abs(ah - bh) > DUP_SIZE_TOL_PX:
                    continue
                dx = abs((ax1 + aw / 2) - (bx1 + bw / 2))
                dy = abs((ay1 + ah / 2) - (by1 + bh / 2))
                if dx <= DUP_SHIFT_MAX_PX and dy <= DUP_SHIFT_MAX_PX:
                    dup = True
                    break
            if dup:
                break
        if dup:
            errors.append({"type": "duplicate_box", "target": stem})
    return errors


def check_metadata(meta: list[dict], jobs: dict) -> list[dict]:
    """scene_leak (target = scene_id) và guideline_mismatch (so với guideline của JOB)."""
    errors = []
    splits = defaultdict(set)
    for m in meta:
        splits[m["scene_id"]].add(m["split"])
    for scene, s in sorted(splits.items()):
        if len(s) > 1:
            errors.append({"type": "scene_leak", "target": scene})
    for m in meta:
        job = jobs.get(m["job_id"])
        if job and m["guideline_version"].strip() != job["guideline"].strip():
            errors.append({"type": "guideline_mismatch", "target": m["image"]})
    return errors


def check_panoptic(root: Path, items: dict, panoptic: dict) -> list[dict]:
    """invalid_category_id và thing_overlap (area khai > số pixel thật trong mask)."""
    errors = []
    cat_ids = {c["id"] for c in panoptic["categories"]}
    for ann in panoptic["annotations"]:
        stem = Path(ann["file_name"]).stem
        segs = ann["segments_info"]
        if any(s["category_id"] not in cat_ids for s in segs):
            errors.append({"type": "invalid_category_id", "target": stem})
            continue
        mask_rel = items.get(stem, {}).get("mask") or f"masks/{ann['file_name']}"
        mask_path = root / mask_rel
        if not mask_path.exists():
            continue
        counts = count_segment_pixels(mask_path)
        # id = R + G*256 + B*256^2; id 0 là nền nên không có trong segments_info
        if any(s["area"] > counts.get(s["id"], 0) + OVERLAP_TOL_PX for s in segs):
            errors.append({"type": "thing_overlap", "target": stem})
    return errors


def count_segment_pixels(mask_path: Path) -> Counter:
    _, _, px = pngutil.read_rgb(mask_path)
    # gom 3 byte RGB thành một số nguyên id cho từng pixel
    ids = (int.from_bytes(px[i : i + 3], "little") for i in range(0, len(px), 3))
    return Counter(ids)


# --------------------------------------------------------------------------
def validate(root: Path) -> list[dict]:
    d = load_delivery(root)
    file_errors, missing = check_files(root, d["items"])
    sizes = image_sizes(root, d["items"], d["panoptic"])
    errors = file_errors
    errors += check_labels(root, {k: v for k, v in d["items"].items() if k not in missing}, d["classes"], sizes)
    errors += check_metadata(d["meta"], d["jobs"])
    errors += check_panoptic(root, d["items"], d["panoptic"])
    # một cặp (type, target) chỉ ghi một lần
    seen, out = set(), []
    for e in errors:
        key = (e["type"], e["target"])
        if key not in seen:
            seen.add(key)
            out.append(e)
    return sorted(out, key=lambda e: (e["type"], e["target"]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validator lỗi luật — nhóm 13")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--candidates", type=Path, help="(Pha 2) ứng viên lỗi gán nhãn")
    args = ap.parse_args()

    errors = validate(args.delivery)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"errors": errors}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.candidates:
        # Pha 2 sẽ điền phần đối chiếu detection <-> panoptic
        args.candidates.parent.mkdir(parents=True, exist_ok=True)
        args.candidates.write_text(json.dumps({"candidates": []}, indent=1) + "\n", encoding="utf-8")

    by_type = Counter(e["type"] for e in errors)
    print(f"{len(errors)} lỗi luật -> {args.out}")
    for kind, n in sorted(by_type.items()):
        print(f"  {kind:22s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
