#!/usr/bin/env python3
"""Pha 4: dựng lô v2 từ errors.json, KHÔNG sửa delivery/ (v1).

  py tools/build_v2.py --run runs/r7007
  py tools/build_v2.py --run runs/r7007 --hash-checked                # đã mở xem ảnh wrong_hash, còn nguyên
  py tools/build_v2.py --run runs/r7007 --broken-hash 000000xxxxxx    # ảnh wrong_hash mở ra thấy HỎNG -> rework

Tạo runs/<run>/handover/<release_id>_v2/ gồm:
  images/, labels/, rework_queue.csv, truyvet.csv, label_summary.csv, README.txt, manifest.csv
Sau đó chạy (lệnh của lab):
  py scripts/pack_release.py runs/r7007/handover/<release_id>_v2
  py scripts/lineage.py record --event release --release-id <release_id>_v2 --parent <release_id>
  py scripts/check_handover.py --run runs/r7007
"""
import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

# Lỗi ở nhãn detection hoặc thiếu file -> ảnh rời v2, vào rework_queue (GUIDE Pha 4)
DET_REWORK = {"missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box",
              "class_swap", "bbox_drift", "missing_box"}
# Lỗi chỉ ở panoptic -> ảnh ở lại v2, ghi chú báo team panoptic
PANOPTIC_ONLY = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}
# Sửa ngay trong v2: wrong_hash (nếu ảnh còn nguyên), guideline_mismatch, scene_leak
ACTION = {
    "missing_image": "giao lại file ảnh rồi kiểm lại nhãn",
    "invalid_class": "gán lại box có class_id ngoài 0-79",
    "bbox_out_of_bounds": "gán lại box vượt mép ảnh",
    "duplicate_box": "xoá box lặp, kiểm lại nhãn",
    "class_swap": "gán lại lớp detection cho đúng vật",
    "bbox_drift": "vẽ lại box khớp vật",
    "missing_box": "thêm box cho vật bị thiếu",
    "wrong_hash": "ảnh hỏng: giao lại file ảnh gốc",
}
THRESHOLD = 0.02


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, header: list, rows: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Dựng lô v2 (Pha 4)")
    ap.add_argument("--run", required=True, help="thư mục runs/r<seed>")
    ap.add_argument("--broken-hash", default="", help="ảnh wrong_hash mở ra thấy hỏng (cách nhau dấu phẩy) -> rework")
    ap.add_argument("--hash-checked", action="store_true", help="đã MỞ XEM mọi ảnh wrong_hash còn lại và thấy còn nguyên")
    a = ap.parse_args()
    run = Path(a.run)
    d = run / "delivery"
    rid = json.loads((d / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    with open(d / "jobs.csv", encoding="utf-8", newline="") as f:
        jobs = {r["job_id"]: r for r in csv.DictReader(f)}
    names80 = {}
    for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            i, n = ln.split(" ", 1)
            names80[int(i)] = n.strip()
    errors = json.loads((run / "errors.json").read_text(encoding="utf-8"))["errors"]
    broken = {s.strip() for s in a.broken_hash.split(",") if s.strip()}

    # 1) Phân loại lỗi
    by_img = {}            # ảnh -> loại lỗi (mỗi ảnh tối đa 1 lỗi)
    leak_scenes = set()
    for e in errors:
        if e["type"] == "scene_leak":
            leak_scenes.add(e["target"])
        else:
            by_img[e["target"]] = e["type"]
    rework = sorted(n for n, t in by_img.items() if n in man and (t in DET_REWORK or (t == "wrong_hash" and n in broken)))
    unknown = sorted(n for n in by_img if n not in man)
    if unknown:
        print("CẢNH BÁO: errors.json có tên ảnh không có trong lô:", unknown[:5])
    keep = sorted(n for n in man if n not in set(rework))

    # 2) Tạo thư mục v2 (xoá bản cũ nếu dựng lại)
    v2 = run / "handover" / f"{rid}_v2"
    if v2.exists():
        shutil.rmtree(v2)
    (v2 / "images").mkdir(parents=True)
    (v2 / "labels").mkdir(parents=True)

    # 3) images/ + labels/: chép NGUYÊN BYTE từ v1, không sửa nhãn
    for n in keep:
        shutil.copyfile(d / man[n]["image"], v2 / "images" / f"{n}.jpg")
        shutil.copyfile(d / man[n]["label"], v2 / "labels" / f"{n}.txt")

    # 4) rework_queue.csv: người gán/kiểm theo job của ảnh (jobs.csv)
    rows = []
    for n in rework:
        job = jobs[meta[n]["job_id"]]
        rows.append([n, by_img[n], job["annotator"], job["reviewer"], ACTION.get(by_img[n], "gán lại")])
    write_csv(v2 / "rework_queue.csv", ["image", "type", "annotator", "reviewer", "action"], rows)

    # 5) truyvet.csv: guideline THEO JOB; cảnh rò train/val -> cả cảnh về một split (theo đa số, hoà thì train)
    scene_imgs = {}
    for n, m in meta.items():
        scene_imgs.setdefault(m["scene_id"], []).append(m["split"])
    fixed_split = {}
    for sc, splits in scene_imgs.items():
        if len(set(splits)) > 1:
            c = Counter(splits)
            fixed_split[sc] = "train" if c["train"] >= c["val"] else "val"
    missed_leak = sorted(set(fixed_split) - leak_scenes)
    if missed_leak:
        print("CẢNH BÁO: cảnh rò train/val chưa có trong errors.json:", missed_leak)
    rows = []
    for n in keep:
        m = meta[n]
        job = jobs[m["job_id"]]
        split = fixed_split.get(m["scene_id"], m["split"])
        rows.append([n, m["scene_id"], split, m["job_id"], job["annotator"], job["reviewer"], job["guideline"]])
    write_csv(v2 / "truyvet.csv", ["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"], rows)

    # 6) label_summary.csv: đếm nhãn trong v2 theo tên lớp, dòng TOTAL
    counts = Counter()
    for n in keep:
        for ln in (v2 / "labels" / f"{n}.txt").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                c = int(float(ln.split()[0]))
                counts[names80.get(c, str(c))] += 1
    total = sum(counts.values())
    write_csv(v2 / "label_summary.csv", ["class", "count"],
              [[k, v] for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))] + [["TOTAL", total]])

    # 7) README.txt theo templates/README.txt
    n_err = len({e["target"] for e in errors})
    rate = n_err / len(man)
    v1 = "Hold" if rate > THRESHOLD else "Release"
    gl = {}
    for j, r in jobs.items():
        gl.setdefault(r["guideline"], []).append(j)
    gl_txt = ", ".join(f"{g} ({min(js)}-{max(js)})" for g, js in sorted(gl.items()))
    pct = f"{rate * 100:.1f}".replace(".", ",")
    hash_ok = sorted(n for n, t in by_img.items() if t == "wrong_hash" and n not in broken)
    gm = sorted(n for n, t in by_img.items() if t == "guideline_mismatch")
    pan = sorted(n for n, t in by_img.items() if t in PANOPTIC_ONLY)
    rq_owner = sorted({f"{jobs[meta[n]['job_id']]['annotator']}+{jobs[meta[n]['job_id']]['reviewer']}" for n in rework})
    notes = []
    if fixed_split:
        notes.append("split: đưa cả cảnh về một split (" + "; ".join(f"{s} -> {v}" for s, v in sorted(fixed_split.items())) + ")")
    if hash_ok:
        state = "đã mở ảnh kiểm, ảnh còn nguyên" if a.hash_checked else "CHƯA MỞ ẢNH KIỂM"
        notes.append(f"hash: {state}, chỉ manifest v1 ghi sai; manifest.csv v2 tính lại sha256 (" + ", ".join(hash_ok) + ")")
    if gm:
        notes.append("guideline: ghi theo job trong jobs.csv thay cho guideline ghi sai ở ảnh (" + ", ".join(gm) + ")")
    if rework:
        notes.append(f"rework: {len(rework)} ảnh lỗi nhãn detection/thiếu file tách khỏi v2, giao lại người gán+kiểm theo job ({', '.join(rq_owner)}), xem rework_queue.csv")
    if pan:
        notes.append("lỗi chỉ ở panoptic, nhãn detection vẫn đúng nên ảnh ở lại v2, báo team panoptic: " + ", ".join(f"{n} ({by_img[n]})" for n in pan))
    readme = "\n".join([
        f"Release: {rid}_v2",
        f"Parent: {rid}",
        f"Số ảnh: {len(keep)}",
        f"Số nhãn: {total}",
        f"Guideline: {gl_txt}",
        f"QC v1: {n_err}/{len(man)} = {pct}%",
        f"Kết luận v1: {v1} — {pct}% ảnh lỗi {'>' if rate > THRESHOLD else '<='} ngưỡng 2% (Day 7)",
        f"Kết luận v2: Release — tách {len(rework)} ảnh lỗi nhãn detection sang rework; sửa hash, guideline theo job, split theo cảnh; nhãn còn lại giữ nguyên như v1",
        "Ghi chú: " + " | ".join(notes),
    ]) + "\n"
    (v2 / "README.txt").write_text(readme, encoding="utf-8")

    # 8) manifest.csv: LÀM CUỐI, sha256 mọi file trong images/ và labels/
    rows = []
    for sub in ("images", "labels"):
        for p in sorted((v2 / sub).iterdir()):
            if p.is_file():
                rows.append([f"{sub}/{p.name}", sha(p)])
    write_csv(v2 / "manifest.csv", ["file", "sha256"], rows)

    # Tóm tắt
    print(f"v1 {rid}: QC {n_err}/{len(man)} = {pct}% -> {v1}")
    print(f"v2 {v2}: {len(keep)} ảnh, {total} nhãn, rework {len(rework)} ảnh, panoptic ở lại {len(pan)} ảnh")
    if hash_ok and not a.hash_checked:
        print("NHỚ MỞ XEM các ảnh wrong_hash (còn nguyên: chạy lại thêm --hash-checked; hỏng: thêm --broken-hash <tên>):", ", ".join(hash_ok))
    print("Tiếp theo:")
    print(f"  py scripts/pack_release.py {v2.as_posix()}")
    print(f"  py scripts/lineage.py record --event release --release-id {rid}_v2 --parent {rid}")
    print(f"  py scripts/check_handover.py --run {run.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
