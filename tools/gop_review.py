#!/usr/bin/env python3
"""Gộp các file review_log của từng người thành một review_log.csv và báo lỗi.

  python tools/gop_review.py runs/r30007/review_parts --candidates runs/r30007/candidates.json --out runs/r30007/review_log.csv

Kiểm tra: ảnh chưa ai xem, ảnh không có trong candidates, đổi type, note < 20 ký tự,
note trùng, cùng một ảnh nhưng kết luận khác nhau. Chỉ ghi file khi không còn lỗi (hoặc --force).
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

SEMANTIC = {"class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge"}
COLS = ["image", "type", "verdict", "note", "reviewer"]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap =argparse.ArgumentParser()
    ap.add_argument("parts", help="thư mục chứa các file .csv của từng người")
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true", help="vẫn ghi file dù còn lỗi")
    a = ap.parse_args()

    data = json.loads(Path(a.candidates).read_text(encoding="utf-8"))
    items = data.get("candidates", data) if isinstance(data, dict) else data
    cand = {c.get("target") or c.get("image"): c.get("type", "") for c in items}

    rows = []
    for f in sorted(Path(a.parts).glob("*.csv")):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                r = {k: (r.get(k) or "").strip() for k in COLS}
                r["_file"] = f.name
                rows.append(r)

    errs, warns = [], []
    notes = collections.Counter(r["note"] for r in rows)
    by_img = collections.defaultdict(list)
    for r in rows:
        tag = f"{r['_file']}: {r['image']} ({r['reviewer'] or '?'})"
        by_img[r["image"]].append(r)
        if r["verdict"] not in ("confirmed", "rejected"):
            errs.append(f"{tag} verdict '{r['verdict']}' không hợp lệ")
        if r["type"] not in SEMANTIC:
            errs.append(f"{tag} type '{r['type']}' không phải lỗi gán nhãn")
        if r["image"] not in cand:
            errs.append(f"{tag} ảnh không có trong candidates")
        elif r["type"] != cand[r["image"]].split("/")[0] and r["type"] not in cand[r["image"]].split("/"):
            warns.append(f"{tag} đổi type {cand[r['image']]} -> {r['type']} (ok nếu note giải thích)")
        if len(r["note"]) < 20:
            errs.append(f"{tag} note chỉ {len(r['note'])} ký tự (< 20)")
        if notes[r["note"]] > 1:
            errs.append(f"{tag} note trùng với dòng khác")
        if not r["reviewer"]:
            errs.append(f"{tag} thiếu tên người xem")
    for img, rs in by_img.items():
        if len({(r["type"], r["verdict"]) for r in rs}) > 1:
            errs.append(f"{img}: nhiều người kết luận khác nhau {[(r['reviewer'], r['type'], r['verdict']) for r in rs]}")
        elif len(rs) > 1:
            warns.append(f"{img}: {len(rs)} người cùng xem, cùng kết luận")
    missing = sorted(set(cand) - set(by_img))
    for img in missing:
        errs.append(f"{img}: CHƯA ai review")

    uniq = len(notes) / max(len(rows), 1)
    print(f"{len(rows)} dòng, {len(by_img)}/{len(cand)} ảnh, note duy nhất {uniq:.0%}")
    for w in warns:
        print("  [chú ý]", w)
    for e in errs:
        print("  [LỖI]  ", e)
    if errs and not a.force:
        print("Chưa ghi file. Sửa các LỖI trên rồi chạy lại.")
        return 1
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["image"], r["reviewer"])))
    print("Đã ghi", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
