#!/usr/bin/env python3
"""Công cụ tự động hóa truy vết ticket AI cho Day 10 Lab.
Chuyên trách: TV5 (Virgoboyy - Huy Vượng).

Sử dụng:
    python tools/trace_ticket.py <thư_mục_delivery> --out <đường_dẫn_trace.json>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Tự động trích xuất trace.json từ thư mục delivery")
    parser.add_argument("delivery", type=Path, help="Đường dẫn thư mục delivery")
    parser.add_argument("--out", type=Path, required=True, help="Đường dẫn file trace.json xuất ra")
    return parser.parse_args()


def main():
    args = parse_args()
    delivery = args.delivery

    if not delivery.exists():
        sys.exit(f"Lỗi: Không tìm thấy thư mục delivery tại {delivery}")

    # 1. Trích xuất tên lớp bị đổi quy tắc từ guideline/changelog.md
    changelog_path = delivery / "guideline" / "changelog.md"
    if not changelog_path.exists():
        sys.exit(f"Lỗi: Không tìm thấy {changelog_path}")
    changelog_text = changelog_path.read_text(encoding="utf-8")

    # Mẫu chuẩn: - Lớp `<rule_class>`:
    m_class = re.search(r"-\s*Lớp\s*`([^`]+)`\s*:", changelog_text)
    if not m_class:
        m_class = re.search(r"`([^`]+)`", changelog_text)
    if not m_class:
        sys.exit("Lỗi: Không tìm thấy tên lớp trong changelog.md")
    rule_class = m_class.group(1).strip()

    # Xác định phiên bản guideline mới từ changelog (thường là v1.3)
    m_new_ver = re.search(r"##\s*(v\d+(?:\.\d+)?)", changelog_text)
    new_version = m_new_ver.group(1).strip() if m_new_ver else "v1.3"

    # 2. Trích xuất các cảnh bị team AI phản ánh từ incoming/ticket.md
    ticket_path = delivery / "incoming" / "ticket.md"
    if not ticket_path.exists():
        sys.exit(f"Lỗi: Không tìm thấy {ticket_path}")
    ticket_text = ticket_path.read_text(encoding="utf-8")
    reported_scenes = set(re.findall(r"\bscene_\w+\b", ticket_text))

    # 3. Đọc 80 lớp detection từ classes.txt
    classes_path = delivery / "classes.txt"
    if not classes_path.exists():
        sys.exit(f"Lỗi: Không tìm thấy {classes_path}")
    
    class_names = []
    for line in classes_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        class_names.append(parts[1].strip() if len(parts) > 1 else parts[0].strip())

    if rule_class not in class_names:
        sys.exit(f"Lỗi: Lớp '{rule_class}' không có trong classes.txt")
    target_class_id = class_names.index(rule_class)

    # 4. Đọc jobs.csv (BẮT BUỘC: Guideline lấy theo job trong jobs.csv, KHÔNG lấy từ metadata.json)
    jobs_path = delivery / "jobs.csv"
    if not jobs_path.exists():
        sys.exit(f"Lỗi: Không tìm thấy {jobs_path}")

    jobs = {}
    with jobs_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs[row["job_id"]] = {
                "guideline": row["guideline"],
                "annotator": row["annotator"],
                "reviewer": row["reviewer"],
            }

    # 5. Đọc metadata.json (lấy thông tin job_id và scene_id cho từng ảnh)
    metadata_path = delivery / "metadata.json"
    if not metadata_path.exists():
        sys.exit(f"Lỗi: Không tìm thấy {metadata_path}")
    metadata_items = json.loads(metadata_path.read_text(encoding="utf-8"))["items"]
    img_meta = {item["image"]: item for item in metadata_items}

    # 6. Lọc các ảnh thuộc job guideline cũ (< new_version hoặc != new_version) và có chứa box target_class_id
    labels_dir = delivery / "labels"
    has_target = []

    for img_name, meta in img_meta.items():
        job_id = meta.get("job_id")
        job_info = jobs.get(job_id)
        if not job_info:
            continue

        # Guideline cũ: không phải version mới ban hành (ví dụ: v1.2)
        if job_info["guideline"] == new_version:
            continue

        label_file = labels_dir / f"{img_name}.txt"
        if not label_file.is_file():
            continue

        # Kiểm tra xem có ít nhất 1 box detection thuộc target_class_id
        has_box = False
        for line in label_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            try:
                c_id = int(float(parts[0]))
            except ValueError:
                continue
            if 0 <= c_id < 80 and c_id == target_class_id:
                has_box = True
                break

        if has_box:
            has_target.append({
                "image": img_name,
                "scene_id": meta.get("scene_id"),
                "job_id": job_id,
            })

    # 7. Phân tầng ảnh
    tier_a = sorted([it["image"] for it in has_target if it["scene_id"] in reported_scenes])
    tier_b = sorted([it["image"] for it in has_target if it["scene_id"] not in reported_scenes])

    # 8. Xác định notify: CHỈ lấy annotator + reviewer của các job chứa ảnh trong tier_a hoặc tier_b
    affected_jobs = {it["job_id"] for it in has_target}
    notify_set = set()
    for j_id in affected_jobs:
        notify_set.add(jobs[j_id]["annotator"])
        notify_set.add(jobs[j_id]["reviewer"])
    notify = sorted(list(notify_set))

    # 9. Ghi kết quả ra trace.json
    result = {
        "tier_a": tier_a,
        "tier_b": tier_b,
        "notify": notify,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] Đã ghi {args.out}")
    print(f"     - Rule class: {rule_class} (ID: {target_class_id})")
    print(f"     - Cảnh team AI báo: {sorted(list(reported_scenes))}")
    print(f"     - tier_a: {len(tier_a)} ảnh")
    print(f"     - tier_b: {len(tier_b)} ảnh")
    print(f"     - notify: {len(notify)} người ({', '.join(notify)})")


if __name__ == "__main__":
    main()
