#!/usr/bin/env python3
"""Validator Day 10 — Pha 1: luật file, detection, metadata và panoptic.

    python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

Chỉ dùng thư viện chuẩn; chỉ đọc thư mục delivery được truyền vào (không đọc _private/, data_source/,
annotation COCO, không dùng mạng).

Phần A (file này) làm 5 loại lỗi:
    missing_image, wrong_hash, invalid_class, bbox_out_of_bounds, duplicate_box
Phần B kiểm scene_leak, guideline_mismatch, invalid_category_id, thing_overlap.
Phần C (đối chiếu det <-> panoptic) gắn vào `find_candidates`.

Quy ước: mỗi ảnh mang nhiều nhất MỘT lỗi luật; kiểm theo thứ tự trong `PER_IMAGE_CHECKS`, lỗi đầu tiên thắng
(file thiếu/hash sai trước, rồi nhãn).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402

# ---- ngưỡng (đo trên lô sạch runs/clean và nhiều seed; ghi lý do vào REPORT.md) ---------------------
OOB_TOL = 1e-4        # box tràn mép quá mức này (tỉ lệ ảnh) mới là lỗi. Nhãn YOLO làm tròn 6 chữ số nên sai số tự nhiên <= 1e-6.
DUP_SIZE_PX = 1.5     # duplicate_box: chênh w, h tối đa (px). Box lặp "cùng kích thước"; cặp tự nhiên chồng nhau thường khác kích thước.
DUP_SHIFT_PX = 3.0    # duplicate_box: chênh tâm tối đa (px). Lỗi gài lệch 1-2 px.


# ---- đọc dữ liệu --------------------------------------------------------------------------------
def sha256(path: Path) -> str:
    h = hashlib.sha256()                      # tính trên BYTES của file (mở "rb")
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_delivery(d: Path) -> dict:
    """Đọc các file mô tả lô. Trả về dict dùng chung cho mọi check (phần B dùng thêm metadata/jobs/panoptic)."""
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    classes = {}
    for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            k, _, name = ln.strip().partition(" ")
            classes[int(k)] = name
    pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
    size = {Path(i["file_name"]).stem: (i["width"], i["height"]) for i in pan["images"]}
    metadata = json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]
    with (d / "jobs.csv").open(encoding="utf-8-sig", newline="") as handle:
        jobs = {row["job_id"]: row for row in csv.DictReader(handle)}
    image_names = {i["id"]: Path(i["file_name"]).stem for i in pan["images"]}
    annotations = {image_names[a["image_id"]]: a for a in pan["annotations"]}
    return {"dir": d, "manifest": man, "classes": classes, "size": size, "panoptic": pan,
            "metadata": {row["image"]: row for row in metadata}, "jobs": jobs,
            "annotations": annotations, "categories": {c["id"]: c for c in pan["categories"]}}


def read_boxes(path: Path):
    """[(số dòng, class_id, cx, cy, w, h)]. Dòng hỏng (sai số cột, không phải số) bị bỏ qua, không làm chết script."""
    out = []
    if not path.exists():
        return out
    for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        p = ln.split()
        if len(p) != 5:
            continue
        try:
            out.append((i, int(float(p[0])), *map(float, p[1:])))
        except ValueError:
            continue
    return out


# ---- các check của phần A (mỗi hàm: (ctx, image, item) -> True nếu ảnh vi phạm) -----------------
def check_missing_image(ctx, img, it) -> bool:
    """manifest có ảnh nhưng file không có trên đĩa."""
    return not (ctx["dir"] / it["image"]).exists()


def check_wrong_hash(ctx, img, it) -> bool:
    """sha256 ghi trong manifest khác sha256 tự tính, với ảnh / nhãn / mask còn file."""
    for k in ("image", "label", "mask"):
        rel, want = it.get(k), it.get(k + "_sha256")
        if rel and want and (ctx["dir"] / rel).exists() and sha256(ctx["dir"] / rel) != want:
            return True
    return False


def check_invalid_class(ctx, img, it) -> bool:
    """class_id không có trong classes.txt (0-79)."""
    return any(c not in ctx["classes"] for _, c, *_ in read_boxes(ctx["dir"] / it["label"]))


def check_bbox_out_of_bounds(ctx, img, it) -> bool:
    """mép box vượt [0, 1] quá OOB_TOL. Mép trái = cx - w/2, mép phải = cx + w/2 (tương tự trục y)."""
    return any(cx - w / 2 < -OOB_TOL or cy - h / 2 < -OOB_TOL or cx + w / 2 > 1 + OOB_TOL or cy + h / 2 > 1 + OOB_TOL
               for _, _c, cx, cy, w, h in read_boxes(ctx["dir"] / it["label"]))


def check_duplicate_box(ctx, img, it) -> bool:
    """hai box cùng lớp, cùng kích thước (chênh <= DUP_SIZE_PX), tâm lệch <= DUP_SHIFT_PX. Đổi sang pixel bằng kích thước ảnh."""
    wh = ctx["size"].get(img)
    if not wh:
        return False
    W, H = wh
    b = read_boxes(ctx["dir"] / it["label"])
    return any(a[1] == c[1] and abs(a[4] - c[4]) * W < DUP_SIZE_PX and abs(a[5] - c[5]) * H < DUP_SIZE_PX
               and abs(a[2] - c[2]) * W <= DUP_SHIFT_PX and abs(a[3] - c[3]) * H <= DUP_SHIFT_PX
               for i, a in enumerate(b) for c in b[i + 1:])


# ---- phần B: metadata và panoptic -----------------------------------------------------------------
def check_guideline_mismatch(ctx, img, it) -> bool:
    """So guideline từng ảnh với job của ảnh; không coi mọi job v1.2 là sai."""
    meta = ctx["metadata"][img]
    return meta["guideline_version"] != ctx["jobs"][meta["job_id"]]["guideline"]


def check_invalid_category_id(ctx, img, it) -> bool:
    return any(s["category_id"] not in ctx["categories"]
               for s in ctx["annotations"][img]["segments_info"])


def check_thing_overlap(ctx, img, it) -> bool:
    """Đếm pixel id RGB thật; chỉ báo thing có area khai lớn hơn diện tích còn lại.

    Không dùng giao bbox: hai bbox giao nhau chưa chứng minh mask bị đè.
    Crowd vẫn là thing; stuff và vùng void (id 0) không là đối tượng kiểm.
    """
    things = [s for s in ctx["annotations"][img]["segments_info"]
              if ctx["categories"].get(s["category_id"], {}).get("isthing")]
    if not things:
        return False
    _, _, pixels = pngutil.read_rgb(ctx["dir"] / it["mask"])
    counts = Counter(r + (g << 8) + (b << 16)
                     for r, g, b in zip(pixels[0::3], pixels[1::3], pixels[2::3]))
    return any(s["area"] > counts[s["id"]] for s in things)


def check_scene_leak(ctx):
    splits = {}
    for row in ctx["metadata"].values():
        splits.setdefault(row["scene_id"], set()).add(row["split"])
    return [{"type": "scene_leak", "target": scene}
            for scene, values in sorted(splits.items()) if {"train", "val"} <= values]


# ---- ĐIỂM GẮN cho phần C --------------------------------------------------------------------------
# Thứ tự = độ ưu tiên khi một ảnh vi phạm nhiều luật (lỗi đầu tiên thắng).
PER_IMAGE_CHECKS = [
    ("missing_image", check_missing_image),
    ("wrong_hash", check_wrong_hash),
    ("invalid_class", check_invalid_class),
    ("bbox_out_of_bounds", check_bbox_out_of_bounds),
    ("duplicate_box", check_duplicate_box),
    ("guideline_mismatch", check_guideline_mismatch),
    ("invalid_category_id", check_invalid_category_id),
    ("thing_overlap", check_thing_overlap),
]
# B: các check cả lô, mỗi hàm (ctx) -> list[{"type":..., "target":...}], ví dụ scene_leak (target là scene_id).
DATASET_CHECKS = [check_scene_leak]


def find_candidates(ctx, skip_images):
    """C: ghép box detection <-> segment panoptic, trả list ứng viên lỗi gán nhãn. Phần A chưa làm."""
    return []


# ---- chạy ------------------------------------------------------------------------------------------
def rule_errors(ctx):
    found = {}
    for img, it in ctx["manifest"].items():
        if check_missing_image(ctx, img, it):
            found[img] = "missing_image"      # file không có thì các check sau không có gì để đọc
            continue
        for typ, fn in PER_IMAGE_CHECKS[1:]:
            if fn(ctx, img, it):
                found[img] = typ
                break
    errors = [{"type": t, "target": i} for i, t in sorted(found.items())]
    for fn in DATASET_CHECKS:
        errors += fn(ctx)
    return errors, found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("delivery", help="thư mục delivery của lô")
    ap.add_argument("--out", required=True, help="ghi errors.json (lỗi luật)")
    ap.add_argument("--candidates", help="ghi candidates.json (ứng viên lỗi gán nhãn)")
    a = ap.parse_args()
    ctx = load_delivery(Path(a.delivery))
    errors, found = rule_errors(ctx)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"errors": errors}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"số ảnh quét: {len(ctx['manifest'])} | lỗi luật: {len(errors)}", dict(Counter(e["type"] for e in errors)))
    if a.candidates:
        c = find_candidates(ctx, set(found))
        Path(a.candidates).write_text(json.dumps({"candidates": c}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"ứng viên: {len(c)}")


if __name__ == "__main__":
    main()
