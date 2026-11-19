#!/usr/bin/env python3
"""Truy vết ticket (Pha 5): tìm tier_a, tier_b, notify từ một thư mục delivery.

  py tools/trace_query.py runs/r7007/delivery --class truck --old v1.2 --scenes scene_370,scene_532 --out runs/r7007/trace.json
"""
import argparse, csv, json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("delivery")
ap.add_argument("--class", dest="cls", required=True, help="lớp bị đổi quy tắc (đọc changelog.md)")
ap.add_argument("--old", required=True, help="phiên bản guideline cũ, ví dụ v1.2")
ap.add_argument("--scenes", required=True, help="các cảnh ticket nêu, cách nhau dấu phẩy")
ap.add_argument("--out", required=True)
a = ap.parse_args()
d = Path(a.delivery)

# 1) id của lớp trong classes.txt (dòng "7 truck")
names = dict(line.split(" ", 1) for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines() if line.strip())
cls_id = next(int(i) for i, n in names.items() if n.strip() == a.cls)

# 2) job nào làm theo guideline cũ -> lấy theo jobs.csv, KHÔNG theo metadata ảnh
with open(d / "jobs.csv", encoding="utf-8", newline="") as f:
    jobs = {r["job_id"]: r for r in csv.DictReader(f)}
old_jobs = {j for j, r in jobs.items() if r["guideline"] == a.old}

# 3) ảnh thuộc job cũ và có ít nhất một box lớp đó trong labels/
meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]
scenes = set(s.strip() for s in a.scenes.split(","))
tier_a, tier_b, used_jobs = [], [], set()
for m in meta:
    if m["job_id"] not in old_jobs:
        continue
    lab = d / "labels" / f"{m['image']}.txt"
    if not lab.is_file():
        continue
    has = any(ln.split() and int(float(ln.split()[0])) == cls_id for ln in lab.read_text(encoding="utf-8").splitlines())
    if not has:
        continue
    (tier_a if m["scene_id"] in scenes else tier_b).append(m["image"])
    used_jobs.add(m["job_id"])

# 4) notify = người gán + người kiểm của các job chứa ảnh tầng a, b
notify = sorted({jobs[j]["annotator"] for j in used_jobs} | {jobs[j]["reviewer"] for j in used_jobs})
out = {"tier_a": sorted(tier_a), "tier_b": sorted(tier_b), "notify": notify}
Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"lớp {a.cls} (id {cls_id}), job cũ {sorted(old_jobs)}, job liên quan {sorted(used_jobs)}")
print(f"tier_a {len(tier_a)} ảnh, tier_b {len(tier_b)} ảnh, notify {notify} -> {a.out}")
