#!/usr/bin/env python3
"""Phần của người C: đối chiếu detection (YOLO) <-> panoptic, sinh ứng viên lỗi gán nhãn.

Chỉ đọc thư mục delivery được truyền vào, chỉ dùng thư viện chuẩn + scripts/pngutil.py.
Không đọc _private/, data_source/, annotation COCO; không dùng mạng.

Dùng riêng:
    python validator/crosscheck.py <delivery> --out <candidates.json> [--stats]
Dùng trong validate.py (A/B ghép vào):
    from crosscheck import find_candidates, write_candidates
    cands = find_candidates(Path(delivery))
    write_candidates(args.candidates, cands)

Cách ghép (không dựa vào IoU bbox thô):
  1. Mỗi box YOLO đổi sang pixel. Mỗi segment thing (không crowd) có số pixel trong mask.
  2. Với mọi cặp (box, segment) đếm số pixel của segment nằm TRONG box (đọc mask thật).
     pixel_iou = inter / (pixel_segment + area_box - inter).
  3. Ghép tham lam 1-1 theo pixel_iou giảm dần, bỏ cặp dưới `match_min`. Ghép KHÔNG xét lớp,
     để còn thấy cặp trùng vị trí mà khác lớp.
  4. Ứng viên:
       class_or_category_swap : cặp ghép được nhưng tên lớp khác nhau (mở ảnh xem bên nào sai)
       bbox_drift             : cặp cùng lớp nhưng pixel segment rơi ra ngoài box nhiều
       instance_merge         : một segment có pixel nằm trong >= 2 box cùng lớp, không chồng nhau
       missing_box            : segment thing đủ lớn, không box nào ghép / che nó
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pngutil  # noqa: E402  (thư viện chuẩn, được phép dùng)

# Ngưỡng mặc định. Hãy đo trên lô sạch (runs/clean) rồi chỉnh; ghi lý do vào REPORT.md.
DEFAULTS = {
    "match_min": 0.15,        # IoU(box, bbox sát của segment) tối thiểu để coi là một cặp
    "drift_inside_min": 0.88,  # cặp cùng lớp: phần pixel segment nằm trong box < ngưỡng này => drift
    "drift_iou_min": 0.60,     # cặp cùng lớp: IoU giữa box và bbox sát của segment (đo từ mask) < ngưỡng này => drift
    "orphan_iou_min": 0.05,    # box chưa ghép chỉ bị coi là drift nếu còn chạm bbox segment cùng lớp ít nhất chừng này
    "merge_part_min": 0.20,    # box nhận ít nhất chừng này pixel của segment mới tính vào merge
    "merge_total_min": 0.60,   # tổng pixel segment nằm trong các box cùng lớp
    "merge_total_max": 1.25,   # pixel segment phải được CHIA ra giữa các box; tổng quá lớn = các box chồng nhau (người đứng cạnh nhau)
    "merge_single_max": 0.80,  # nếu đã có một box chứa >= chừng này segment thì segment có box riêng, không phải merge
    "merge_box_iou_max": 0.30, # hai box merge không được chồng nhau (tránh nhầm duplicate_box)
    "missing_area_frac": 0.01, # segment nhỏ hơn tỉ lệ này của ảnh thì bỏ qua
    "missing_cover_max": 0.30, # box nào che >= chừng này pixel segment thì không tính là thiếu box
}


def _read_classes(path: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            out[int(parts[0])] = parts[1].strip()
    return out


def _read_boxes(path: Path, classes: dict[int, str], width: int, height: int) -> list[dict]:
    boxes = []
    if not path.is_file():
        return boxes
    for line in path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) != 5:
            continue
        try:
            cid = int(p[0])
            xc, yc, w, h = (float(v) for v in p[1:])
        except ValueError:
            continue
        if cid not in classes:  # invalid_class là lỗi luật của A, không đối chiếu
            continue
        x0 = max(0, round((xc - w / 2) * width))
        y0 = max(0, round((yc - h / 2) * height))
        x1 = min(width, round((xc + w / 2) * width))
        y1 = min(height, round((yc + h / 2) * height))
        if x1 <= x0 or y1 <= y0:
            continue
        boxes.append({"name": classes[cid], "xyxy": (x0, y0, x1, y1), "area": (x1 - x0) * (y1 - y0)})
    return boxes


def _box_iou(a: tuple, b: tuple) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _segment_rows(pixels: bytearray, width: int, height: int) -> list[list[int]]:
    r, g, b = pixels[0::3], pixels[1::3], pixels[2::3]
    flat = [rv + gv * 256 + bv * 65536 for rv, gv, bv in zip(r, g, b)]
    return [flat[y * width : (y + 1) * width] for y in range(height)]


def _tight_boxes(rows: list[list[int]], ids: set[int]) -> dict[int, tuple]:
    """bbox sát (x0, y0, x1, y1) của từng segment, đo từ pixel mask."""
    ext: dict[int, list[int]] = {}
    for y, row in enumerate(rows):
        for sid in set(row) & ids:
            lo = row.index(sid)
            hi = len(row) - row[::-1].index(sid)
            e = ext.get(sid)
            if e is None:
                ext[sid] = [lo, y, hi, y + 1]
            else:
                e[0], e[2], e[3] = min(e[0], lo), max(e[2], hi), y + 1
    return {k: tuple(v) for k, v in ext.items()}


def _check_image(stem: str, width: int, height: int, boxes: list[dict], segs: list[dict],
                 rows: list[list[int]], p: dict) -> list[dict]:
    out: list[dict] = []
    seg_by_id = {s["id"]: s for s in segs}
    # Đếm pixel thật của từng segment và pixel nằm trong mỗi box.
    total = Counter()
    for row in rows:
        total.update(row)
    tight = _tight_boxes(rows, set(seg_by_id))
    inside: list[Counter] = []
    for bx in boxes:
        x0, y0, x1, y1 = bx["xyxy"]
        c: Counter = Counter()
        for y in range(y0, y1):
            c.update(rows[y][x0:x1])
        inside.append(c)

    # instance_merge (làm trước để ghép cặp bỏ qua segment bị gộp): một segment trải trên >= 2 box cùng lớp không chồng nhau.
    merged: set[int] = set()
    for sid, s in seg_by_id.items():
        n_s = total[sid]
        if n_s == 0:
            continue
        parts = [(bi, inside[bi][sid] / n_s) for bi, bx in enumerate(boxes)
                 if bx["name"] == s["name"] and inside[bi][sid] / n_s >= p["merge_part_min"]]
        tot = sum(f for _, f in parts)
        if len(parts) < 2 or not p["merge_total_min"] <= tot <= p["merge_total_max"]:
            continue
        if max(inside[bi][sid] / n_s for bi in range(len(boxes)) if boxes[bi]["name"] == s["name"]) >= p["merge_single_max"]:
            continue
        apart = [(a, b) for i, (a, _) in enumerate(parts) for b, _ in parts[i + 1 :]
                 if _box_iou(boxes[a]["xyxy"], boxes[b]["xyxy"]) <= p["merge_box_iou_max"]]
        if apart:
            merged.add(sid)
            out.append({"image": stem, "type": "instance_merge", "score": round(sum(f for _, f in parts), 3),
                        "detail": f"{s['name']} segment={sid} phủ {len(parts)} box cùng lớp"})

    pairs = []
    for bi, bx in enumerate(boxes):
        for sid, n_in in inside[bi].items():
            s = seg_by_id.get(sid)
            if s is None or n_in <= 0:
                continue
            n_s = total[sid]
            # điểm ghép = IoU giữa box và bbox sát của segment (đo từ mask). Pixel IoU không dùng được vì
            # vật mảnh/chéo (dao, gậy, thìa) chỉ chiếm dưới 30% diện tích box của chính nó.
            iou = _box_iou(bx["xyxy"], tight[sid]) if sid in tight else 0.0
            if iou >= p["match_min"]:
                pairs.append((iou, bi, sid, n_in, n_s))
    pairs.sort(reverse=True)

    used_box: set[int] = set()
    used_seg: set[int] = set()
    for iou, bi, sid, n_in, n_s in pairs:
        if bi in used_box or sid in used_seg or sid in merged:
            continue
        used_box.add(bi)
        used_seg.add(sid)
        bx, s = boxes[bi], seg_by_id[sid]
        seg_in_box = n_in / n_s
        tb_iou = _box_iou(bx["xyxy"], tight[sid]) if sid in tight else 1.0
        if bx["name"] != s["name"]:
            out.append({"image": stem, "type": "class_or_category_swap", "score": round(iou, 3),
                        "detail": f"detection='{bx['name']}' panoptic='{s['name']}' segment={sid} bbox_iou={iou:.2f}"})
        elif seg_in_box < p["drift_inside_min"] or tb_iou < p["drift_iou_min"]:
            out.append({"image": stem, "type": "bbox_drift", "score": round(1 - min(seg_in_box, tb_iou), 3),
                        "detail": f"{bx['name']} segment={sid} seg_in_box={seg_in_box:.2f} bbox_iou={tb_iou:.2f}"})

    # box không ghép được nhưng cùng lớp và còn chạm segment chưa ghép: box lệch quá xa => bbox_drift.
    drifted: set[int] = set()
    for bi, bx in enumerate(boxes):
        if bi in used_box:
            continue
        cand = [(inside[bi][sid], sid) for sid, s in seg_by_id.items()
                if s["name"] == bx["name"] and sid not in used_seg and sid not in merged and inside[bi][sid] > 0
                and sid in tight and _box_iou(bx["xyxy"], tight[sid]) >= p["orphan_iou_min"]]
        if cand:
            n_in, sid = max(cand)
            drifted.add(sid)
            out.append({"image": stem, "type": "bbox_drift", "score": round(1 - n_in / total[sid], 3),
                        "detail": f"{bx['name']} segment={sid} box lệch xa, chỉ {n_in / total[sid]:.0%} segment nằm trong box"})

    # missing_box: segment đủ lớn không ai che.
    for sid, s in seg_by_id.items():
        if sid in used_seg or sid in merged or sid in drifted:
            continue
        n_s = total[sid]
        if n_s < p["missing_area_frac"] * width * height:
            continue
        # chỉ tính box CHƯA ghép với vật nào: box đã dành cho vật khác che lấn sang không làm segment này có box.
        best = max((inside[bi][sid] / n_s for bi in range(len(boxes)) if bi not in used_box), default=0.0)
        if best < p["missing_cover_max"]:
            out.append({"image": stem, "type": "missing_box", "score": round(n_s / (width * height), 3),
                        "detail": f"{s['name']} segment={sid} chiếm {n_s / (width * height):.1%} ảnh, không có box"})
    return out


def find_candidates(delivery: Path, params: dict | None = None, skip_images=()) -> list[dict]:
    """skip_images: tên ảnh (stem) đã dính lỗi luật (missing_image, wrong_hash...), không đối chiếu nữa."""
    p = {**DEFAULTS, **(params or {})}
    skip = set(skip_images)
    delivery = Path(delivery)
    classes = _read_classes(delivery / "classes.txt")
    doc = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in doc["categories"]}
    img_by_id = {im["id"]: im for im in doc["images"]}
    out: list[dict] = []
    for ann in doc["annotations"]:
        im = img_by_id.get(ann["image_id"])
        if im is None:
            continue
        stem = Path(im["file_name"]).stem
        if stem in skip:
            continue
        mask =delivery / "masks" / Path(ann["file_name"]).name
        if not mask.is_file():
            continue
        try:
            width, height, pixels = pngutil.read_rgb(mask)
        except (ValueError, OSError):
            continue
        segs = []
        for s in ann.get("segments_info", []):
            c = cats.get(s.get("category_id"))
            # category_id lạ (invalid_category_id) và crowd/stuff không đối chiếu
            if c is None or not c.get("isthing") or s.get("iscrowd"):
                continue
            segs.append({"id": s["id"], "name": c["name"]})
        boxes = _read_boxes(delivery / "labels" / f"{stem}.txt", classes, width, height)
        rows = _segment_rows(pixels, width, height)
        out += _check_image(stem, width, height, boxes, segs, rows, p)
    return sorted(out, key=lambda c: (c["image"], c["type"]))


def write_candidates(path, candidates: list[dict], params: dict | None = None) -> None:
    doc = {"params": {**DEFAULTS, **(params or {})}, "count": len(candidates), "candidates": candidates}
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh ứng viên lỗi gán nhãn (det <-> panoptic)")
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stats", action="store_true", help="in số ứng viên theo loại và số ảnh")
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k.replace('_', '-')}", type=float, default=v)
    a = ap.parse_args()
    params = {k: getattr(a, k) for k in DEFAULTS}
    cands = find_candidates(Path(a.delivery), params)
    write_candidates(a.out, cands, params)
    if a.stats:
        print(f"{len(cands)} ứng viên / {len({c['image'] for c in cands})} ảnh")
        for t, n in sorted(Counter(c["type"] for c in cands).items()):
            print(f"  {t}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
