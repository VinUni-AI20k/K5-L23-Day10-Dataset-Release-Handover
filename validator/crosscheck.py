#!/usr/bin/env python3
"""Sinh ứng viên đối chiếu detection (YOLO) <-> panoptic cho một lô delivery.

validate.py gọi:  find_candidates(delivery) -> list[dict]
Chạy riêng:       python validator/crosscheck.py <delivery> [--out candidates.json]

Phần của Lâm (CP1-CP2). Quy tắc lab mà file này tuân thủ:
- CHỈ đọc thư mục delivery được truyền vào (không _private/, data_source/, annotation COCO).
- Không dùng mạng, chỉ thư viện chuẩn + scripts/pngutil.py (đọc PNG).
- Không nhúng tên ảnh, id hay đáp án của seed nào.

Cách làm: dùng PIXEL CỦA MASK, không chỉ IoU giữa hai bbox.
  1. Với mỗi box YOLO (đổi sang pixel) đếm số pixel của từng segment nằm trong box.
  2. Ghép box với segment thing có IoU-mask cao nhất:  I / (S + B - I)
       I = pixel của segment nằm trong box, S = pixel của segment, B = diện tích box.
  3. Từ cặp ghép sinh ứng viên:
       class_or_category_swap : cặp ghép tốt nhưng khác TÊN lớp (xem ảnh để biết bên nào sai)
       bbox_drift             : cùng lớp nhưng phần lớn pixel segment rơi ra ngoài box
       missing_box            : segment thing đủ lớn mà không box nào phủ
       instance_merge         : hai box cùng lớp cùng ghép vào một segment
Đây chỉ là ỨNG VIÊN: phải mở ảnh xem rồi ghi review_log.csv (confirmed / rejected).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from pngutil import read_rgb  # noqa: E402

# --- Ngưỡng (đơn vị ghi rõ; chọn dựa trên lô sạch, xem REPORT.md) ---------------
# Tỉ lệ IoU-mask tối thiểu để coi box và segment là "cùng một vật" (ghép được).
MATCH_IOU = 0.30
# Cặp ghép "chắc chắn": đủ chắc để so tên lớp. Thấp hơn thì chỉ là ghép yếu, không kết luận.
STRONG_IOU = 0.50
# bbox_drift: tỉ lệ pixel segment nằm TRONG box nhỏ hơn mức này thì coi là box lệch.
DRIFT_INSIDE_FRAC = 0.75
# missing_box: segment thing nhỏ hơn mức này (pixel) thì bỏ qua (vật quá nhỏ không đáng kể).
MISSING_MIN_PIXELS = 1500
# missing_box: box nào phủ >= tỉ lệ này pixel segment thì coi là segment đã có box.
COVERED_FRAC = 0.30
# instance_merge: hai box gần như trùng nhau (IoU hộp > mức này) là lặp box, KHÔNG phải gộp vật.
SAME_BOX_IOU = 0.60


def _load_classes(delivery: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            out[int(parts[0])] = parts[1].strip()
    return out


def _read_boxes(path: Path, classes: dict[int, str], W: int, H: int) -> list[dict]:
    """Box YOLO -> pixel (x0, y0, x1, y1), kẹp trong ảnh. Bỏ box có class ngoài classes.txt."""
    boxes = []
    if not path.is_file():
        return boxes
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5 or not parts[0].isdigit() or int(parts[0]) not in classes:
            continue
        try:
            xc, yc, w, h = (float(v) for v in parts[1:])
        except ValueError:
            continue
        x0 = max(0, int(round((xc - w / 2) * W)))
        x1 = min(W, int(round((xc + w / 2) * W)))
        y0 = max(0, int(round((yc - h / 2) * H)))
        y1 = min(H, int(round((yc + h / 2) * H)))
        if x1 > x0 and y1 > y0:
            boxes.append({"cls": classes[int(parts[0])], "rect": (x0, y0, x1, y1), "area": (x1 - x0) * (y1 - y0)})
    return boxes


def _box_iou(a: tuple, b: tuple) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def analyse_image(delivery: Path, ann: dict, cats: dict, det_names: set, classes: dict, W: int, H: int) -> list[dict]:
    stem = Path(ann["file_name"]).stem
    mask_path = delivery / "masks" / ann["file_name"]
    if not mask_path.is_file():
        return []
    boxes = _read_boxes(delivery / "labels" / f"{stem}.txt", classes, W, H)

    # Chỉ xét segment THING thuộc lớp có trong detection, bỏ crowd và category lạ.
    things = {}
    for s in ann["segments_info"]:
        cat = cats.get(s["category_id"])
        if cat and cat.get("isthing") and not s.get("iscrowd") and cat["name"] in det_names and s["id"] != 0:
            things[s["id"]] = cat["name"]

    mw, mh, px = read_rgb(mask_path)
    if (mw, mh) != (W, H):  # kích thước mask khác panoptic.json: tin kích thước mask
        W, H = mw, mh
        boxes = _read_boxes(delivery / "labels" / f"{stem}.txt", classes, W, H)
    ids = [r | (g << 8) | (b << 16) for r, g, b in zip(px[0::3], px[1::3], px[2::3])]
    seg_pix = Counter(ids)

    # inside[i][sid] = số pixel của segment sid nằm trong box i (chỉ quét trong box).
    inside: list[Counter] = []
    for b in boxes:
        x0, y0, x1, y1 = b["rect"]
        cnt: Counter = Counter()
        for y in range(y0, y1):
            cnt.update(ids[y * W + x0: y * W + x1])
        inside.append(cnt)

    cands: list[dict] = []

    def add(kind: str, reason: str, **extra) -> None:
        cands.append({"image": stem, "type": kind, "reason": reason, **extra})

    # --- ghép box -> segment tốt nhất theo IoU-mask -----------------------------
    match: list[tuple[int, float] | None] = []
    for i, b in enumerate(boxes):
        best_sid, best = None, 0.0
        for sid in things:
            inter = inside[i].get(sid, 0)
            if not inter:
                continue
            iou = inter / (seg_pix[sid] + b["area"] - inter)
            if iou > best:
                best_sid, best = sid, iou
        match.append((best_sid, best) if best_sid is not None and best >= MATCH_IOU else None)

    # --- khác lớp / lệch box ---------------------------------------------------
    for i, m in enumerate(match):
        if m is None:
            continue
        sid, iou = m
        b = boxes[i]
        if iou >= STRONG_IOU and b["cls"] != things[sid]:
            add("class_or_category_swap",
                f"box ghi '{b['cls']}' nhưng segment ghi '{things[sid]}' (IoU-mask {iou:.2f})",
                detection=b["cls"], panoptic=things[sid], box=list(b["rect"]), segment=sid, iou=round(iou, 3))
        elif b["cls"] == things[sid]:
            frac = inside[i].get(sid, 0) / seg_pix[sid]
            if frac < DRIFT_INSIDE_FRAC:
                add("bbox_drift",
                    f"chỉ {frac:.0%} pixel segment '{things[sid]}' nằm trong box (IoU-mask {iou:.2f})",
                    detection=b["cls"], box=list(b["rect"]), segment=sid, inside_frac=round(frac, 3))

    # --- thiếu box ---------------------------------------------------------------
    for sid, name in things.items():
        S = seg_pix.get(sid, 0)
        if S < MISSING_MIN_PIXELS:
            continue
        covered = max((inside[i].get(sid, 0) / S for i in range(len(boxes))), default=0.0)
        if covered < COVERED_FRAC:
            add("missing_box", f"segment '{name}' {S} pixel không có box nào phủ (tối đa {covered:.0%})",
                panoptic=name, segment=sid, pixels=S)

    # --- gộp vật: hai box cùng lớp cùng ghép một segment ------------------------
    by_seg: dict[int, list[int]] = {}
    for i, m in enumerate(match):
        if m is not None and boxes[i]["cls"] == things[m[0]]:
            by_seg.setdefault(m[0], []).append(i)
    for sid, idxs in by_seg.items():
        distinct = [i for k, i in enumerate(idxs)
                    if all(_box_iou(boxes[i]["rect"], boxes[j]["rect"]) <= SAME_BOX_IOU for j in idxs[:k])]
        if len(distinct) >= 2:
            add("instance_merge", f"{len(distinct)} box '{things[sid]}' cùng ghép vào một segment",
                detection=things[sid], segment=sid, boxes=[list(boxes[i]["rect"]) for i in distinct])
    return cands


def find_candidates(delivery) -> list[dict]:
    delivery = Path(delivery)
    pan = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in pan["categories"]}
    classes = _load_classes(delivery)
    det_names = set(classes.values())
    sizes = {Path(im["file_name"]).stem: (im["width"], im["height"]) for im in pan["images"]}
    out: list[dict] = []
    for ann in pan["annotations"]:
        W, H = sizes.get(Path(ann["file_name"]).stem, (640, 480))
        out.extend(analyse_image(delivery, ann, cats, det_names, classes, W, H))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh ứng viên đối chiếu det <-> panoptic")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    cands = find_candidates(args.delivery)
    by_type = Counter(c["type"] for c in cands)
    imgs = len({c["image"] for c in cands})
    print(f"{len(cands)} ứng viên trên {imgs} ảnh: " + ", ".join(f"{t}={n}" for t, n in sorted(by_type.items())),
          file=sys.stderr)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"candidates": cands}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
