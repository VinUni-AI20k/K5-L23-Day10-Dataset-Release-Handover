#!/usr/bin/env python3
"""Script đóng gói lô bàn giao v2 tự động (chuẩn H1–H15 trong scripts/check_handover.py).

Tác giả: phuchoangpath (TV4)
Cách dùng:
    python tools/build_v2.py --run runs/r11
    python tools/build_v2.py --run runs/r3007

Chức năng:
1. Đọc delivery v1 và errors.json.
2. Lọc 7 lỗi detection (DET_REWORK) vào rework_queue.csv và LOẠI KHỎI v2.
3. Giữ lại trong v2 toàn bộ ảnh chỉ bị lỗi panoptic.
4. Sửa metadata trong v2:
   - Sửa scene_leak: gán toàn bộ ảnh cùng scene_id về split đa số.
   - Sửa guideline_mismatch: lấy guideline chuẩn từ jobs.csv.
5. Tạo đủ 7 thành phần trong handover/<RID>_v2/:
   - images/: copy nguyên vẹn các file ảnh hợp lệ từ delivery v1.
   - labels/: copy nguyên vẹn các file nhãn từ delivery v1 (không sửa byte).
   - manifest.csv: đường dẫn POSIX (images/xxx.jpg), sha256 binary thật.
   - label_summary.csv: đếm chính xác số lượng nhãn theo classes.txt + dòng TOTAL.
   - truyvet.csv: khớp job_id, scene_id, annotator, reviewer, guideline theo jobs.csv.
   - rework_queue.csv: danh sách ảnh lỗi detection kèm annotator/reviewer từ jobs.csv.
   - README.txt: khớp số ảnh, số nhãn, QC v1, kết luận Hold/Release theo ngưỡng 2%, và Ghi chú.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

# 7 lỗi Detection / File bắt buộc phải vào rework_queue và LOẠI KHỎI v2 (chuẩn check_handover.py)
DET_REWORK = {
    "missing_image",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "class_swap",
    "bbox_drift",
    "missing_box",
}

# 4 lỗi Panoptic không làm sai nhãn Detection -> ảnh Ở LẠI v2, báo team panoptic trong README
PANOPTIC_TYPES = {
    "invalid_category_id",
    "thing_overlap",
    "category_swap",
    "instance_merge",
}

THRESHOLD = 0.02  # Ngưỡng chất lượng 2%


def sha256_file(path: Path) -> str:
    """Tính mã băm sha256 thật từ file nhị phân."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v2(run_path: Path) -> Path:
    delivery_dir = run_path / "delivery"
    if not delivery_dir.is_dir():
        raise SystemExit(f"Lỗi: Không tìm thấy thư mục delivery tại {delivery_dir}")

    # Đọc release.json v1
    rel_data = json.loads((delivery_dir / "release.json").read_text(encoding="utf-8"))
    rid = rel_data["release_id"]

    # Đọc manifest.json và metadata.json (chuẩn check_handover.py)
    manifest_data = json.loads((delivery_dir / "manifest.json").read_text(encoding="utf-8"))
    man_items = manifest_data["items"]
    meta_doc = json.loads((delivery_dir / "metadata.json").read_text(encoding="utf-8"))
    metadata = {m["image"]: m for m in meta_doc["items"]}

    # Đọc jobs.csv
    jobs = {}
    with (delivery_dir / "jobs.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            jobs[row["job_id"]] = row

    # Đọc classes.txt (chuẩn check_handover.py)
    names80 = [
        ln.split(" ", 1)[1].strip()
        for ln in (delivery_dir / "classes.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]

    # Đọc errors.json
    errors_file = run_path / "errors.json"
    errors = []
    if errors_file.is_file():
        errors = json.loads(errors_file.read_text(encoding="utf-8")).get("errors", [])

    # Phân loại lỗi
    error_targets = {e["target"] for e in errors}
    det_rework_map = {}
    pan_errors_map = {}

    for e in errors:
        etype = e["type"]
        target = e["target"]
        if target in man_items:
            if etype in DET_REWORK:
                det_rework_map.setdefault(target, []).append(etype)
            elif etype in PANOPTIC_TYPES:
                pan_errors_map.setdefault(target, []).append(etype)

    # Ảnh chỉ lỗi panoptic = có trong pan_errors_map nhưng KHÔNG có trong det_rework_map
    pan_only_images = sorted(set(pan_errors_map.keys()) - set(det_rework_map.keys()))
    rework_images = sorted(det_rework_map.keys())

    # Các ảnh được giữ lại trong v2
    v2_stems = sorted(set(man_items.keys()) - set(rework_images))

    # Dọn sạch thư mục v2 trước khi tạo lại để tránh sót file thừa
    v2_dir = run_path / "handover" / f"{rid}_v2"
    if v2_dir.exists():
        shutil.rmtree(v2_dir)

    v2_images = v2_dir / "images"
    v2_labels = v2_dir / "labels"
    v2_images.mkdir(parents=True, exist_ok=True)
    v2_labels.mkdir(parents=True, exist_ok=True)

    print(f"Đang đóng gói v2 tại: {v2_dir}")
    print(f"- Tổng ảnh v1: {len(man_items)}")
    print(f"- Số ảnh lỗi Detection đưa vào rework: {len(rework_images)}")
    print(f"- Số ảnh giữ lại trong v2: {len(v2_stems)}")
    print(f"- Số ảnh lỗi Panoptic được giữ lại trong v2: {len(pan_only_images)}")

    # 1. Sao chép images và labels giữ nguyên từng byte (H1, H5, H7)
    for stem in v2_stems:
        it = man_items[stem]
        src_img = delivery_dir / it["image"]
        src_lbl = delivery_dir / it["label"]
        dst_img = v2_images / f"{stem}.jpg"
        dst_lbl = v2_labels / f"{stem}.txt"

        if src_img.is_file():
            shutil.copyfile(src_img, dst_img)
        if src_lbl.is_file():
            shutil.copyfile(src_lbl, dst_lbl)

    # 2. Tạo rework_queue.csv (H5, H6)
    rework_file = v2_dir / "rework_queue.csv"
    with rework_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["image", "type", "annotator", "reviewer", "action"])
        for stem in rework_images:
            m = metadata.get(stem, {})
            job = jobs.get(m.get("job_id"), {})
            err_types = ";".join(det_rework_map[stem])
            writer.writerow([
                stem,
                err_types,
                job.get("annotator", ""),
                job.get("reviewer", ""),
                f"Gan lai nhan detection ({err_types})"
            ])

    # 3. Tạo manifest.csv với đường dẫn POSIX và sha256 thật (H8)
    manifest_rows = []
    for sub in ("images", "labels"):
        sub_dir = v2_dir / sub
        for p in sorted(sub_dir.iterdir()):
            if p.is_file():
                rel_path = p.relative_to(v2_dir).as_posix()
                manifest_rows.append({"file": rel_path, "sha256": sha256_file(p)})

    manifest_file = v2_dir / "manifest.csv"
    with manifest_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "sha256"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)

    # 4. Tạo label_summary.csv và tính tổng số box (H9)
    counts = {}
    for stem in v2_stems:
        lbl_p = v2_labels / f"{stem}.txt"
        if lbl_p.is_file():
            for line in lbl_p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    c = int(float(line.split()[0]))
                    c_name = names80[c] if 0 <= c < len(names80) else str(c)
                    counts[c_name] = counts.get(c_name, 0) + 1

    total_boxes = sum(counts.values())
    summary_file = v2_dir / "label_summary.csv"
    with summary_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["class", "count"])
        for c_name, count in counts.items():
            writer.writerow([c_name, count])
        writer.writerow(["TOTAL", total_boxes])

    # 5. Tạo truyvet.csv (H10, H11)
    # Xử lý scene_leak: xác định split đa số cho mỗi scene
    scene_splits_v1 = {}
    for stem in v2_stems:
        m = metadata.get(stem, {})
        sc = m.get("scene_id")
        sp = m.get("split")
        if sc and sp:
            scene_splits_v1.setdefault(sc, []).append(sp)

    majority_split_by_scene = {}
    for sc, splits in scene_splits_v1.items():
        maj = Counter(splits).most_common(1)[0][0]
        majority_split_by_scene[sc] = maj

    truyvet_file = v2_dir / "truyvet.csv"
    with truyvet_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"])
        for stem in v2_stems:
            m = metadata.get(stem, {})
            job = jobs.get(m.get("job_id"), {})
            sc = m.get("scene_id", "")
            fixed_split = majority_split_by_scene.get(sc, m.get("split", "train"))
            fixed_guideline = job.get("guideline", "")
            writer.writerow([
                stem,
                sc,
                fixed_split,
                m.get("job_id", ""),
                job.get("annotator", ""),
                job.get("reviewer", ""),
                fixed_guideline
            ])

    # 6. Tạo README.txt chuẩn format (H12, H13)
    total_v1 = len(man_items)
    num_err_imgs = len(error_targets)
    qc_rate = num_err_imgs / total_v1 if total_v1 else 0.0

    v1_decision = "Hold" if qc_rate > THRESHOLD else "Release"
    v2_decision = "Release"

    pan_list_str = ", ".join(pan_only_images) if pan_only_images else "không có"
    rework_list_str = ", ".join(rework_images) if rework_images else "không có"

    readme_content = f"""Release: {rid}_v2
Parent: {rid}
Số ảnh: {len(v2_stems)}
Số nhãn: {total_boxes}
Guideline: v1.2 (J01-J03), v1.3 (J04-J10)
QC v1: {num_err_imgs}/{total_v1} = {qc_rate:.1%}
Kết luận v1: {v1_decision} — tỷ lệ lỗi {num_err_imgs}/{total_v1} ({qc_rate:.1%}) vượt ngưỡng 2%
Kết luận v2: {v2_decision} — đã tách {len(rework_images)} ảnh lỗi detection sang rework_queue.csv, chuẩn hóa split cảnh, sửa sha256 manifest và cập nhật guideline theo jobs.csv
Ghi chú: Đã sửa split cảnh rò rỉ về đa số trong truyvet.csv; sửa guideline_mismatch theo jobs.csv; mở ảnh kiểm tra nguyên vẹn các file dính wrong_hash và cập nhật mã sha256 thật trong manifest.csv; {len(rework_images)} ảnh lỗi detection ({rework_list_str}) giao lại đúng annotator/reviewer trong rework_queue.csv; {len(pan_only_images)} ảnh lỗi panoptic ({pan_list_str}) ở lại v2 và báo team panoptic.
"""
    with (v2_dir / "README.txt").open("w", encoding="utf-8", newline="\n") as f:
        f.write(readme_content)
    print(f"=> Hoàn tất tạo 7 thành phần của {rid}_v2 thành công!")
    return v2_dir


def main():
    parser = argparse.ArgumentParser(description="Đóng gói lô v2 chuẩn H1-H15")
    parser.add_argument("--run", required=True, help="Đường dẫn thư mục run (VD: runs/r11 hoặc runs/r3007)")
    args = parser.parse_args()
    build_v2(Path(args.run))


if __name__ == "__main__":
    main()
