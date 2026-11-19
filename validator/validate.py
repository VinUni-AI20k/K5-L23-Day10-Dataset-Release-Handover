#!/usr/bin/env python3
"""Validator Day 10: bắt 9 loại lỗi LUẬT trong một lô delivery.

    python validator/validate.py <delivery> --out <rules.json> [--candidates <candidates.json>]

Phần lỗi luật (file này): Tuấn Anh. Phần sinh ứng viên đối chiếu: Lâm, viết trong
validator/crosscheck.py với hàm find_candidates(delivery) -> list[dict].

Quy tắc của lab mà file này tuân thủ:
- CHỈ đọc thư mục delivery được truyền vào (không _private/, data_source/, annotation COCO).
- Không dùng mạng, chỉ thư viện chuẩn + scripts/pngutil.py (đọc PNG).
- Không nhúng tên ảnh, id hay đáp án của seed nào.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pngutil import read_rgb  # noqa: E402  (đọc PNG bằng thư viện chuẩn, được RULES cho phép)

# --- Ngưỡng (đơn vị ghi rõ) -------------------------------------------------
# Toạ độ YOLO ghi 6 chữ số thập phân, nên box sát mép tự nhiên có thể lệch ~1e-6.
# Box bị "tràn mép một chút" do lỗi gài thì lệch cỡ pixel (>= ~1e-3), nên lấy 1e-4.
OOB_EPS = 1e-4
# duplicate_box: box lặp cùng lớp, CÙNG kích thước, tâm lệch 1–2 px.
# Cho sai số kích thước <= 1 px (làm tròn) và tâm lệch <= 3 px mỗi trục.
DUP_SIZE_PX = 1.0
DUP_SHIFT_PX = 3.0


def sha256_file(path: Path) -> str:
    """sha256 trên BYTES của file (mở 'rb'), không phải kiểm định dạng 64 ký tự."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# --- Nhóm luật FILE ---------------------------------------------------------
def check_files(delivery: Path, manifest: dict, errors: list) -> None:
    """missing_image: manifest có ảnh mà thiếu file.
    wrong_hash: sha256 trong manifest không khớp bytes của file ảnh, nhãn hoặc mask."""
    for stem, item in manifest["items"].items():
        img = delivery / item["image"]
        if not img.is_file():
            errors.append(("missing_image", stem))
            continue
        # kiểm cả ảnh, nhãn và mask: hash nào trong manifest không khớp file thì là wrong_hash
        for key in ("image", "label", "mask"):
            path = delivery / item[key]
            if path.is_file() and sha256_file(path) != item[f"{key}_sha256"].lower():
                errors.append(("wrong_hash", stem))
                break


# --- Nhóm luật NHÃN DETECTION -------------------------------------------------
def read_boxes(path: Path) -> list[tuple[str, float, float, float, float]]:
    """Mỗi dòng YOLO: class_id x_center y_center width height (chuẩn hoá 0–1).
    Giữ class_id dạng chuỗi để bắt được cả class không phải số nguyên."""
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        cls, *nums = parts
        try:
            xc, yc, w, h = (float(v) for v in nums)
        except ValueError:
            continue
        boxes.append((cls, xc, yc, w, h))
    return boxes


def check_labels(delivery: Path, manifest: dict, num_classes: int, sizes: dict, errors: list) -> None:
    for stem, item in manifest["items"].items():
        label = delivery / item["label"]
        if not label.is_file():
            continue
        boxes = read_boxes(label)

        # invalid_class: class_id phải là số nguyên trong 0..num_classes-1 (classes.txt)
        if any(not cls.isdigit() or int(cls) >= num_classes for cls, *_ in boxes):
            errors.append(("invalid_class", stem))
            continue

        # bbox_out_of_bounds: mép box (tâm ± nửa cạnh) vượt khỏi [0, 1]
        def out(b):
            _, xc, yc, w, h = b
            return (xc - w / 2 < -OOB_EPS or xc + w / 2 > 1 + OOB_EPS
                    or yc - h / 2 < -OOB_EPS or yc + h / 2 > 1 + OOB_EPS)
        if any(out(b) for b in boxes):
            errors.append(("bbox_out_of_bounds", stem))
            continue

        # duplicate_box: so từng cặp box CÙNG lớp, đổi sang pixel bằng kích thước ảnh
        # (lấy từ panoptic.json trong delivery). Cùng kích thước + tâm lệch vài pixel.
        W, H = sizes.get(stem, (640, 480))
        if has_duplicate(boxes, W, H):
            errors.append(("duplicate_box", stem))


def has_duplicate(boxes, W: int, H: int) -> bool:
    by_class = defaultdict(list)
    for cls, xc, yc, w, h in boxes:
        by_class[cls].append((xc * W, yc * H, w * W, h * H))
    for group in by_class.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                same_size = abs(a[2] - b[2]) <= DUP_SIZE_PX and abs(a[3] - b[3]) <= DUP_SIZE_PX
                near = abs(a[0] - b[0]) <= DUP_SHIFT_PX and abs(a[1] - b[1]) <= DUP_SHIFT_PX
                if same_size and near:
                    return True
    return False


# --- Nhóm luật METADATA -------------------------------------------------------
def check_metadata(delivery: Path, errors: list) -> None:
    items = load_json(delivery / "metadata.json")["items"]
    with (delivery / "jobs.csv").open(encoding="utf-8", newline="") as f:
        job_guideline = {row["job_id"]: row["guideline"].strip() for row in csv.DictReader(f)}

    # scene_leak: một cảnh có ảnh ở cả train và val -> target là scene_id
    splits = defaultdict(set)
    for it in items:
        splits[it["scene_id"]].add(it["split"])
    for scene, s in sorted(splits.items()):
        if len(s) > 1:
            errors.append(("scene_leak", scene))

    # guideline_mismatch: so guideline của ảnh với guideline GHI Ở JOB (jobs.csv),
    # không so với các ảnh khác (cả job có thể lệch nếu so theo đa số)
    for it in items:
        expected = job_guideline.get(it["job_id"])
        if expected is not None and it["guideline_version"].strip() != expected:
            errors.append(("guideline_mismatch", it["image"]))


# --- Nhóm luật PANOPTIC -------------------------------------------------------
def check_panoptic(delivery: Path, panoptic: dict, errors: list) -> None:
    valid_ids = {c["id"] for c in panoptic["categories"]}
    for ann in panoptic["annotations"]:
        stem = Path(ann["file_name"]).stem
        segs = ann["segments_info"]

        # invalid_category_id: category_id không có trong categories
        if any(s["category_id"] not in valid_ids for s in segs):
            errors.append(("invalid_category_id", stem))
            continue

        # thing_overlap: area khai > số pixel thật của segment trong mask
        # (id segment = R + G*256 + B*256^2; bỏ id 0 là nền)
        mask = delivery / "masks" / ann["file_name"]
        if not mask.is_file():
            continue
        _, _, px = read_rgb(mask)
        counts = Counter(zip(px[0::3], px[1::3], px[2::3]))  # đếm theo (R,G,B), nhanh hơn lặp từng pixel
        for s in segs:
            sid = s["id"]
            if sid == 0:
                continue
            real = counts.get((sid & 255, (sid >> 8) & 255, (sid >> 16) & 255), 0)
            if s["area"] > real:
                errors.append(("thing_overlap", stem))
                break


# --- Ứng viên đối chiếu (phần của Lâm) ---------------------------------------
def write_candidates(delivery: Path, out: Path) -> None:
    try:
        from crosscheck import find_candidates  # validator/crosscheck.py do Lâm viết
        candidates = find_candidates(delivery)
    except ImportError:
        print("chưa có validator/crosscheck.py -> candidates rỗng", file=sys.stderr)
        candidates = []
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"candidates": candidates}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(candidates)} ứng viên -> {out}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validator lỗi luật Day 10")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--candidates", type=Path)
    args = ap.parse_args()
    d = args.delivery

    manifest = load_json(d / "manifest.json")
    panoptic = load_json(d / "panoptic.json")
    num_classes = sum(1 for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines() if line.strip())
    sizes = {Path(im["file_name"]).stem: (im["width"], im["height"]) for im in panoptic["images"]}

    errors: list[tuple[str, str]] = []
    check_files(d, manifest, errors)
    check_labels(d, manifest, num_classes, sizes, errors)
    check_metadata(d, errors)
    check_panoptic(d, panoptic, errors)

    unique = sorted(set(errors))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"errors": [{"type": t, "target": g} for t, g in unique]}, indent=1) + "\n",
                        encoding="utf-8")
    by_type = Counter(t for t, _ in unique)
    print(f"{len(unique)} lỗi luật -> {args.out}: " + ", ".join(f"{t}={n}" for t, n in sorted(by_type.items())),
          file=sys.stderr)

    if args.candidates:
        write_candidates(d, args.candidates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
