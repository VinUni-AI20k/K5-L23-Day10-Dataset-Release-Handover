"""Ghép các file review của từng người thành một review_log.csv.

    py -X utf8 tools/merge_parts.py work/review_huy.csv work/review_quan.csv ... --out runs/r<seed>/review_log.csv

Bỏ dòng chưa điền verdict. Báo lỗi (exit 1) nếu verdict không phải
confirmed/rejected, note < 20 ký tự, hoặc ảnh bị ghi hai lần. Cảnh báo nếu
nhiều note giống hệt nhau (check_handover.py H3 không chấp nhận chép giống nhau).
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

MIN_NOTE = 20


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    rows, errors, seen = [], [], {}
    pending = 0
    for part in a.parts:
        p = Path(part)
        if not p.exists():
            errors.append(f"{part}: không có file")
            continue
        with p.open(encoding="utf-8-sig", newline="") as f:
            for n, r in enumerate(csv.DictReader(f), start=2):
                verdict = (r.get("verdict") or "").strip().lower()
                note = (r.get("note") or "").strip()
                if not verdict:
                    pending += 1
                    continue
                where = f"{p.name}:{n} ({r.get('image')})"
                if verdict not in ("confirmed", "rejected"):
                    errors.append(f"{where}: verdict '{verdict}' không hợp lệ")
                if len(note) < MIN_NOTE:
                    errors.append(f"{where}: note {len(note)} ký tự (< {MIN_NOTE})")
                if r["image"] in seen:
                    errors.append(f"{where}: trùng với {seen[r['image']]}")
                seen[r["image"]] = p.name
                rows.append({"image": r["image"], "type": r["type"].strip(), "verdict": verdict, "note": note})

    dup = [n for n, c in Counter(r["note"] for r in rows).items() if c > 1]
    total = len(rows)
    if total and sum(Counter(r["note"] for r in rows)[n] for n in dup) / total > 0.3:
        print("CẢNH BÁO: > 30% note trùng nhau (H3 sẽ FAIL)", file=sys.stderr)

    for e in errors:
        print("LỖI:", e, file=sys.stderr)
    if pending:
        print(f"CHÚ Ý: {pending} dòng chưa điền verdict, bị bỏ qua", file=sys.stderr)
    if errors:
        return 1

    rows.sort(key=lambda r: r["image"])
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image", "type", "verdict", "note"])
        w.writeheader()
        w.writerows(rows)
    c = Counter(r["verdict"] for r in rows)
    print(f"{out}: {total} dòng (confirmed={c['confirmed']}, rejected={c['rejected']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
