"""Luật file + detection (Tùng). Chỉ đọc thư mục delivery, chỉ dùng thư viện chuẩn.

Loại lỗi: missing_image, wrong_hash, invalid_class, bbox_out_of_bounds, duplicate_box.
Giao diện chung với module của Hương: check(delivery: Path) -> list[{"type", "target"}]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# bbox_out_of_bounds: chỉ bỏ qua sai số làm tròn của nhãn (6 chữ số thập phân).
BOUND_EPS = 1e-4
# duplicate_box (docs/DELIVERY.md): cùng lớp, cùng kích thước, lệch 1-2 pixel.
DUP_SIZE_TOL_PX = 0.5
DUP_SHIFT_MAX_PX = 2.5


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:  # đọc bytes, không đọc text
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _num_classes(d: Path) -> int:
    p = d / "classes.txt"
    if not p.is_file():
        return 80
    n = sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())
    return n or 80


def _image_sizes(d: Path) -> dict:
    p = d / "panoptic.json"
    if not p.is_file():
        return {}
    return {Path(im["file_name"]).stem: (im["width"], im["height"]) for im in _load_json(p).get("images", [])}


def _parse_class(tok: str):
    """[sửa] Trả về int nếu tok là số nguyên ("3" hoặc "3.0"), ngược lại None (= class không hợp lệ)."""
    try:
        v = float(tok)
    except ValueError:
        return None
    return int(v) if v.is_integer() else None  # "3.7", "nan", "inf" -> None


def _read_boxes(path: Path) -> list:
    boxes = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        parts = ln.split()
        if len(parts) < 5:
            continue
        try:
            coords = tuple(map(float, parts[1:5]))
        except ValueError:
            continue
        boxes.append((_parse_class(parts[0]), *coords))  # [sửa] không còn int(float(...))
    return boxes


def _out_of_bounds(boxes: list) -> bool:
    for _, x, y, w, h in boxes:
        if x - w / 2 < -BOUND_EPS or y - h / 2 < -BOUND_EPS or x + w / 2 > 1 + BOUND_EPS or y + h / 2 > 1 + BOUND_EPS:
            return True
    return False


def _has_duplicate(boxes: list, size) -> bool:
    if size is None:
        return False
    width, height = size
    for i in range(len(boxes)):
        c1, x1, y1, w1, h1 = boxes[i]
        for j in range(i + 1, len(boxes)):
            c2, x2, y2, w2, h2 = boxes[j]
            if c1 is None or c1 != c2:  # [sửa] class không hợp lệ thì không xét lặp
                continue
            if abs(w1 - w2) * width > DUP_SIZE_TOL_PX or abs(h1 - h2) * height > DUP_SIZE_TOL_PX:
                continue
            if abs(x1 - x2) * width <= DUP_SHIFT_MAX_PX and abs(y1 - y2) * height <= DUP_SHIFT_MAX_PX:
                return True
    return False


def check(delivery) -> list:
    d = Path(delivery)
    items = _load_json(d / "manifest.json")["items"]
    n_classes = _num_classes(d)
    sizes = _image_sizes(d)
    errors = []
    for name in sorted(items):
        it = items[name]
        img = d / it["image"]
        if not img.is_file():
            errors.append({"type": "missing_image", "target": name})
        elif it.get("image_sha256") and _sha256(img) != it["image_sha256"].lower():
            errors.append({"type": "wrong_hash", "target": name})
        if not it.get("label"):  # [sửa] manifest thiếu khoá label thì bỏ qua, không crash
            continue
        lab = d / it["label"]
        if not lab.is_file():
            continue
        boxes = _read_boxes(lab)
        if any(c is None or not 0 <= c < n_classes for c, *_ in boxes):  # [sửa]
            errors.append({"type": "invalid_class", "target": name})
        if _out_of_bounds(boxes):
            errors.append({"type": "bbox_out_of_bounds", "target": name})
        size = sizes.get(name)
        if size is None and boxes:  # [sửa] không còn bỏ qua im lặng
            print(f"[cảnh báo] {name}: không có width/height trong panoptic.json, bỏ qua duplicate_box", file=sys.stderr)
        if _has_duplicate(boxes, size):
            errors.append({"type": "duplicate_box", "target": name})
    return errors