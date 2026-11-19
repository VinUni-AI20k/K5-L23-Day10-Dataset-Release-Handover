"""Chia candidates.json thành 5 file review, mỗi người một file.

    py -X utf8 tools/split_queue.py runs/r<seed>/candidates.json
    py -X utf8 tools/split_queue.py submission/de_an/candidates.json --prefix de_an_review

Ghi work/<prefix>_<ten>.csv (cột image,type,verdict,note; verdict/note để trống).
Chia vòng tròn theo thứ tự score giảm dần để mỗi người có tải đều.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

NAMES = ["huy", "quan", "nui", "phuc", "dat"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--prefix", default="review")
    ap.add_argument("--out-dir", default="work")
    ap.add_argument("--names", nargs="+", default=NAMES)
    a = ap.parse_args()

    data = json.loads(Path(a.candidates).read_text(encoding="utf-8"))
    if isinstance(data, dict):  # chấp nhận {"candidates": [...]}
        data = data.get("candidates", [])
    # một ảnh một dòng (giữ ứng viên score cao nhất), vì mỗi ảnh nhiều nhất một lỗi
    best: dict[str, dict] = {}
    for c in data:
        k = c["image"]
        if k not in best or c.get("score", 0) > best[k].get("score", 0):
            best[k] = c
    rows = sorted(best.values(), key=lambda c: (-float(c.get("score", 0)), c["image"]))

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = {n: [] for n in a.names}
    for i, c in enumerate(rows):
        parts[a.names[i % len(a.names)]].append(c)
    for n, items in parts.items():
        p = out_dir / f"{a.prefix}_{n}.csv"
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["image", "type", "verdict", "note"])
            for c in sorted(items, key=lambda c: c["image"]):
                w.writerow([c["image"], c["type"], "", ""])
        print(f"{p}: {len(items)} ảnh")
    print(f"tổng {len(rows)} ảnh ứng viên / {len(data)} dòng")


if __name__ == "__main__":
    main()
