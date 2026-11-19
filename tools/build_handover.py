#!/usr/bin/env python3
"""Sinh lô bàn giao v2 (7 phần) từ delivery v1 + errors.json. Không sửa gì trong delivery/.

  py -X utf8 tools/build_handover.py runs/r13007
  py -X utf8 tools/build_handover.py runs/r13007 --broken 000000001234   # ảnh wrong_hash đã mở xem và thấy hỏng

Ghi runs/r<seed>/handover/<rid>_v2/: images/, labels/, manifest.csv, label_summary.csv,
truyvet.csv, rework_queue.csv, README.txt. Chạy lại thì thư mục v2 được tạo lại từ đầu.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

# Theo GUIDE Pha 4 / check_handover.py
DET_REWORK = {"missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box", "class_swap", "bbox_drift", "missing_box"}
PANOPTIC_ONLY = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}
THRESHOLD = 0.02


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh lô bàn giao v2")
    ap.add_argument("run", help="thư mục lô, ví dụ runs/r13007")
    ap.add_argument("--errors", help="mặc định <run>/errors.json")
    ap.add_argument("--broken", default="", help="ảnh wrong_hash đã mở xem và thấy HỎNG (phẩy ngăn cách) -> rework")
    args = ap.parse_args()

    run = Path(args.run)
    d = run / "delivery"
    rid = json.loads((d / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}
    names80 = [ln.split(" ", 1)[1].strip() for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    errors = json.loads(Path(args.errors or run / "errors.json").read_text(encoding="utf-8"))["errors"]
    broken = {s.strip() for s in args.broken.split(",") if s.strip()}

    # Phân loại lỗi: mỗi ảnh nhiều nhất một lỗi (DELIVERY mục 2), nên map ảnh -> type là đủ
    err_by_img = {e["target"]: e["type"] for e in errors if e["target"] in man}
    rework = {img: t for img, t in err_by_img.items() if t in DET_REWORK or (t == "wrong_hash" and img in broken)}
    panoptic = sorted(img for img, t in err_by_img.items() if t in PANOPTIC_ONLY)
    hash_fixed = sorted(img for img, t in err_by_img.items() if t == "wrong_hash" and img not in broken)
    guide_fixed = sorted(img for img, t in err_by_img.items() if t == "guideline_mismatch")
    leak_scenes = sorted(e["target"] for e in errors if e["type"] == "scene_leak")

    # scene_leak: cả cảnh về split đa số (tính trên mọi ảnh của cảnh trong v1)
    scene_split = {}
    for sc in leak_scenes:
        votes = Counter(m["split"] for m in meta.values() if m["scene_id"] == sc)
        if votes:
            scene_split[sc] = votes.most_common(1)[0][0]

    keep = sorted(img for img, it in man.items() if img not in rework and (d / it["image"]).is_file())

    v2 = run / "handover" / f"{rid}_v2"
    if v2.exists():
        shutil.rmtree(v2)
    (v2 / "images").mkdir(parents=True)
    (v2 / "labels").mkdir()

    # images/, labels/: chép nguyên byte (H7)
    for img in keep:
        shutil.copyfile(d / man[img]["image"], v2 / "images" / f"{img}.jpg")
        shutil.copyfile(d / man[img]["label"], v2 / "labels" / f"{img}.txt")

    # manifest.csv: hash tính lại từ file thật, nên ảnh wrong_hash còn nguyên tự có hash đúng (H8)
    files = sorted(p for sub in ("images", "labels") for p in (v2 / sub).iterdir() if p.is_file())
    write_csv(v2 / "manifest.csv", ["file", "sha256"], [[p.relative_to(v2).as_posix(), sha(p)] for p in files])

    # label_summary.csv: chỉ lớp có count > 0, dòng cuối TOTAL (H9)
    counts = Counter()
    for img in keep:
        for ln in (v2 / "labels" / f"{img}.txt").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                c = int(float(ln.split()[0]))
                counts[names80[c] if 0 <= c < len(names80) else str(c)] += 1
    total = sum(counts.values())
    write_csv(v2 / "label_summary.csv", ["class", "count"], sorted(counts.items()) + [["TOTAL", total]])

    # truyvet.csv: người + guideline theo JOB, split đã sửa rò (H10, H11)
    tv = []
    for img in keep:
        m = meta[img]
        job = jobs[m["job_id"]]
        tv.append([img, m["scene_id"], scene_split.get(m["scene_id"], m["split"]), m["job_id"],
                   job["annotator"], job["reviewer"], job["guideline"]])
    write_csv(v2 / "truyvet.csv", ["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"], tv)

    # rework_queue.csv: giao lại đúng người theo job (H5, H6)
    rq = []
    for img, t in sorted(rework.items()):
        job = jobs[meta[img]["job_id"]]
        action = "chụp/lấy lại ảnh rồi gán lại" if t in ("missing_image", "wrong_hash") else "gán lại nhãn detection"
        rq.append([img, t, job["annotator"], job["reviewer"], action])
    write_csv(v2 / "rework_queue.csv", ["image", "type", "annotator", "reviewer", "action"], rq)

    # README.txt: khoá đúng chữ theo templates/README.txt (H12, H13)
    n_bad = len({e["target"] for e in errors})
    rate = n_bad / len(man)
    rate_s = f"{rate * 100:.1f}".replace(".", ",") + "%"
    v1 = (f"Hold — {rate_s} ảnh lỗi > ngưỡng 2%" if rate > THRESHOLD else f"Release — {rate_s} ảnh lỗi ≤ ngưỡng 2%")
    by_ver = {}
    for jid in sorted(jobs):
        by_ver.setdefault(jobs[jid]["guideline"], []).append(jid)
    guide = ", ".join(f"{v} ({js[0]}-{js[-1]})" for v, js in sorted(by_ver.items()))
    notes = [
        f"split: {', '.join(f'{sc}->{sp}' for sc, sp in scene_split.items()) or 'không có'}",
        f"hash ghi lại sau khi mở ảnh kiểm còn nguyên: {', '.join(hash_fixed) or 'không có'}",
        f"guideline lấy theo job: {', '.join(guide_fixed) or 'không có'}",
        f"rework: {'; '.join(f'{r[0]}->{r[2]}/{r[3]}' for r in rq) or 'không có'}",
        f"lỗi panoptic (ảnh ở lại v2, báo team panoptic): {', '.join(panoptic) or 'không có'}",
    ]
    readme = [
        f"Release: {rid}_v2",
        f"Parent: {rid}",
        f"Số ảnh: {len(keep)}",
        f"Số nhãn: {total}",
        f"Guideline: {guide}",
        f"QC v1: {n_bad}/{len(man)} = {rate_s}",
        f"Kết luận v1: {v1}",
        f"Kết luận v2: Release — tách {len(rq)} ảnh sang rework, sửa split {len(scene_split)} cảnh, "
        f"hash {len(hash_fixed)} ảnh, guideline {len(guide_fixed)} ảnh; còn {len(panoptic)} ảnh lỗi panoptic báo team panoptic",
        "Ghi chú: " + "; ".join(notes),
    ]
    (v2 / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(f"{v2}: {len(keep)} ảnh, {total} nhãn, rework {len(rq)}, QC v1 {n_bad}/{len(man)} = {rate_s}")
    if hash_fixed:
        print(f"Nhớ MỞ ẢNH kiểm các ảnh wrong_hash (hỏng thì chạy lại với --broken): {', '.join(hash_fixed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
