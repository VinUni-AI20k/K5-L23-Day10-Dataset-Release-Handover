#!/usr/bin/env python3
"""Script kiểm tra nhanh tính toàn vẹn và tính tái lập của lô bàn giao v2 (TV4).

Cách dùng:
    python tools/verify_v2.py --v2 runs/r3007/handover/lab250_95697c6d4612_v2
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_v2(v2_dir: Path) -> bool:
    if not v2_dir.is_dir():
        print(f"[FAIL] Không tìm thấy thư mục v2: {v2_dir}")
        return False

    required = [
        "images",
        "labels",
        "manifest.csv",
        "label_summary.csv",
        "truyvet.csv",
        "README.txt",
        "rework_queue.csv",
    ]
    for req in required:
        if not (v2_dir / req).exists():
            print(f"[FAIL] Thiếu thành phần bắt buộc: {req}")
            return False

    images = sorted(p.stem for p in (v2_dir / "images").glob("*.jpg"))
    labels = sorted(p.stem for p in (v2_dir / "labels").glob("*.txt"))
    if images != labels:
        print(f"[FAIL] images ({len(images)}) và labels ({len(labels)}) không khớp danh sách!")
        return False

    # Kiểm tra manifest.csv
    manifest_file = v2_dir / "manifest.csv"
    with manifest_file.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fpath = v2_dir / row["file"]
            if not fpath.is_file():
                print(f"[FAIL] File trong manifest không tồn tại: {row['file']}")
                return False
            actual_hash = sha256_file(fpath)
            if actual_hash != row["sha256"]:
                print(f"[FAIL] Sai lệch SHA-256: {row['file']}")
                return False

    print(f"[PASS] Toàn bộ {len(images)} ảnh và file nhãn trong {v2_dir.name} hợp lệ 100%!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Kiểm tra tính toàn vẹn lô bàn giao v2")
    parser.add_argument("--v2", required=True, help="Đường dẫn thư mục lô v2")
    args = parser.parse_args()
    success = verify_v2(Path(args.v2))
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
