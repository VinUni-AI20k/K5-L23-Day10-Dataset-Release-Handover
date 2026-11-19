"""Kiểm tra 7 lỗi luật mức Detection & Metadata (TV1 - Zeus-AIE).

Chỉ dùng thư viện chuẩn Python và chỉ đọc bên trong thư mục delivery được truyền vào:
1. missing_image       : manifest liệt kê nhưng thiếu file ảnh
2. wrong_hash          : sha256 tính thực tế (đọc binary) khác manifest.json
3. invalid_class       : class_id không nguyên hoặc nằm ngoài [0, num_classes - 1]
4. bbox_out_of_bounds  : box YOLO vượt mép [0, 1] quá dung sai OOB_TOL hoặc kích thước <= 0
5. duplicate_box       : 2 box cùng lớp, kích thước gần y hệt và tâm chỉ lệch vài pixel
6. scene_leak          : 1 scene_id có ảnh nằm ở cả train và val (target là scene_id)
7. guideline_mismatch  : guideline_version trên metadata ảnh khác guideline của job trong jobs.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

# Các hằng số ngưỡng đặt tập trung ở đầu file để dễ điều chỉnh và giải thích khi vấn đáp
OOB_TOL = 0.005        # Dung sai tràn mép tọa độ chuẩn hóa [0, 1] (tránh sai số làm tròn 1e-6)
DUP_SIZE_PX = 1.5      # Chênh lệch tối đa chiều rộng/cao (pixel) giữa 2 box lặp
DUP_SHIFT_PX = 3.0     # Độ lệch tâm tối đa (pixel) giữa 2 box lặp


def sha256_file(path: Path) -> str:
    """Tính SHA-256 trên bytes thô (chế độ binary, tránh lệch CRLF trên Windows)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_classes(delivery: Path) -> list[str]:
    """Đọc danh sách tên lớp từ classes.txt (mỗi dòng: '<id> <name>')."""
    lines = (delivery / "classes.txt").read_text(encoding="utf-8").splitlines()
    return [ln.split(" ", 1)[1].strip() for ln in lines if ln.strip()]


def load_jobs(delivery: Path) -> dict[str, dict[str, str]]:
    """Đọc bảng jobs.csv lập chỉ mục theo job_id."""
    with (delivery / "jobs.csv").open(encoding="utf-8", newline="") as fh:
        return {row["job_id"]: row for row in csv.DictReader(fh)}


def load_image_sizes(delivery: Path) -> dict[str, tuple[int, int]]:
    """Lấy (width, height) của từng ảnh từ panoptic.json (không cần Pillow)."""
    pan = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    return {
        Path(im["file_name"]).stem: (int(im["width"]), int(im["height"]))
        for im in pan.get("images", [])
    }


def _parse_int_class(raw: str) -> int | None:
    """Ép kiểu class_id sang số nguyên chặt (từ chối số thập phân như '3.5')."""
    try:
        val_f = float(raw)
    except ValueError:
        return None
    if not val_f.is_integer():
        return None
    return int(val_f)


def _has_duplicate_box(
    boxes_px: list[tuple[int, float, float, float, float]],
) -> bool:
    """Phát hiện cặp box lặp cùng lớp, cùng kích thước và lệch tâm rất nhỏ.

    Không dùng ngưỡng IoU đơn thuần vì COCO tự nhiên có nhiều vật đứng chồng nhau
    đạt IoU tới ~0.66 nhưng khác kích thước và vị trí tâm.
    """
    n = len(boxes_px)
    for i in range(n):
        c1, cx1, cy1, w1, h1 = boxes_px[i]
        for j in range(i + 1, n):
            c2, cx2, cy2, w2, h2 = boxes_px[j]
            if c1 != c2:
                continue
            if (
                abs(w1 - w2) <= DUP_SIZE_PX
                and abs(h1 - h2) <= DUP_SIZE_PX
                and abs(cx1 - cx2) <= DUP_SHIFT_PX
                and abs(cy1 - cy2) <= DUP_SHIFT_PX
            ):
                return True
    return False


def check_detection_rules(delivery: Path) -> list[dict[str, str]]:
    """Chạy toàn bộ 7 kiểm tra luật Detection & Metadata trên thư mục delivery."""
    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta_items = json.loads((delivery / "metadata.json").read_text(encoding="utf-8"))["items"]
    meta = {row["image"]: row for row in meta_items}
    jobs = load_jobs(delivery)
    num_classes = len(load_classes(delivery))
    img_sizes = load_image_sizes(delivery)

    findings: set[tuple[str, str]] = set()
    scene_splits: dict[str, set[str]] = {}

    for stem, item in manifest.items():
        m = meta.get(stem)
        if m:
            scene_splits.setdefault(m["scene_id"], set()).add(m["split"])
            job = jobs.get(m["job_id"])
            if job and m.get("guideline_version") != job.get("guideline"):
                findings.add(("guideline_mismatch", stem))

        # 1. Kiểm tra tồn tại file ảnh & 2. Kiểm tra SHA-256 (chỉ kiểm hash khi ảnh tồn tại)
        img_path = delivery / item["image"]
        if not img_path.is_file():
            findings.add(("missing_image", stem))
        else:
            lbl_path = delivery / item["label"]
            msk_path = delivery / item["mask"]
            hash_mismatch = sha256_file(img_path) != item["image_sha256"]
            if not hash_mismatch and lbl_path.is_file() and "label_sha256" in item:
                hash_mismatch = sha256_file(lbl_path) != item["label_sha256"]
            if not hash_mismatch and msk_path.is_file() and "mask_sha256" in item:
                hash_mismatch = sha256_file(msk_path) != item["mask_sha256"]
            if hash_mismatch:
                findings.add(("wrong_hash", stem))

        # 3, 4, 5. Kiểm tra nhãn detection YOLO (.txt)
        lbl_path = delivery / item["label"]
        if not lbl_path.is_file():
            continue

        width, height = img_sizes.get(stem, (1, 1))
        boxes_px: list[tuple[int, float, float, float, float]] = []
        has_invalid_class = False
        has_oob = False

        for raw_line in lbl_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue

            cls_id = _parse_int_class(parts[0])
            x, y, w, h = (float(v) for v in parts[1:5])

            if cls_id is None or not (0 <= cls_id < num_classes):
                has_invalid_class = True
                continue

            if (
                w <= 0.0
                or h <= 0.0
                or (x - w / 2.0) < -OOB_TOL
                or (y - h / 2.0) < -OOB_TOL
                or (x + w / 2.0) > 1.0 + OOB_TOL
                or (y + h / 2.0) > 1.0 + OOB_TOL
            ):
                has_oob = True
                continue

            boxes_px.append((cls_id, x * width, y * height, w * width, h * height))

        if has_invalid_class:
            findings.add(("invalid_class", stem))
        if has_oob:
            findings.add(("bbox_out_of_bounds", stem))
        if _has_duplicate_box(boxes_px):
            findings.add(("duplicate_box", stem))

    # 6. scene_leak: target là scene_id (không phải tên ảnh)
    for scene_id, splits in scene_splits.items():
        if len(splits) > 1:
            findings.add(("scene_leak", scene_id))

    return [{"type": err_type, "target": target} for err_type, target in sorted(findings)]
