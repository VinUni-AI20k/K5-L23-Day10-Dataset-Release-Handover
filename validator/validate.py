#!/usr/bin/env python3
"""Validator 9 loại lỗi luật cho một thư mục delivery (Day 10 Lab — vai trò M2).

Giao diện:
    python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

Chỉ đọc thư mục delivery được truyền vào. Không đọc _private/, data_source/,
cache COCO, không dùng mạng. Chỉ thư viện chuẩn + scripts/pngutil.py.

9 loại lỗi luật:
  missing_image, wrong_hash, invalid_class, bbox_out_of_bounds, duplicate_box,
  scene_leak, guideline_mismatch, invalid_category_id, thing_overlap.

target = tên ảnh không đuôi; riêng scene_leak có target = scene_id.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path


def _find_repo_root() -> Path:
    """Tìm thư mục gốc repo để import scripts/pngutil.py.

    Chạy `python validator/validate.py` thì sys.path[0] là validator/, nên phải
    tự đưa thư mục gốc repo vào sys.path.
    """
    here = Path(__file__).resolve()
    for base in (here.parent.parent, Path.cwd().resolve()):
        if (base / "scripts" / "pngutil.py").is_file():
            return base
    return here.parent.parent


ROOT = _find_repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.pngutil import read_rgb  # noqa: E402
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Không import được scripts/pngutil.py. Chạy validator từ thư mục gốc repo "
        f"(hiện tại: {Path.cwd()}). Chi tiết: {exc}"
    )

RULE_ORDER = [
    "missing_image",
    "wrong_hash",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "scene_leak",
    "guideline_mismatch",
    "invalid_category_id",
    "thing_overlap",
]

# Ngưỡng hình học: chọn theo bản chất dữ liệu, không theo tham số seed nào.
BBOX_TOL = 0.005          # box được phép tràn 0,5% cạnh (nhiễu làm tròn)
DUP_SIZE_TOL = 2e-3       # hai box "cùng kích thước": lệch <= 0,2%
DUP_CENTER_PX = 2.5       # tâm lệch <= 2,5 pixel
DUP_CENTER_NORM = 0.004   # dự phòng khi không biết W/H (~2,5 px / 640 px)
AREA_MIN_DIFF = 2         # thing_overlap: mask PNG là lossless, lệch > 2 px là bất thường


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:  # hash trên bytes, không phải text
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Context:
    """Dữ liệu đọc từ delivery/, không đọc gì bên ngoài."""

    def __init__(self, delivery: Path) -> None:
        self.d = delivery
        self.manifest: dict[str, dict] = read_json(delivery / "manifest.json")["items"]
        self.meta: dict[str, dict] = {
            row["image"]: row for row in read_json(delivery / "metadata.json")["items"]
        }

        pandoc = read_json(delivery / "panoptic.json")
        self.categories = pandoc["categories"]
        self.category_ids = {cat["id"] for cat in self.categories}
        self.thing_ids = {cat["id"] for cat in self.categories if cat.get("isthing")}
        self.ann_by_name: dict[str, dict] = {
            Path(ann["file_name"]).stem: ann for ann in pandoc["annotations"]
        }
        self.dims: dict[str, tuple[int, int]] = {
            Path(im["file_name"]).stem: (int(im["width"]), int(im["height"]))
            for im in pandoc["images"]
        }

        self.jobs: dict[str, dict] = {}
        with (delivery / "jobs.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                self.jobs[row["job_id"].strip()] = row

        self.class_names = [
            line.split(" ", 1)[1].strip()
            for line in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.num_classes = len(self.class_names)

    def dims_of(self, name: str) -> tuple[int, int] | None:
        return self.dims.get(name)


def check_files(ctx: Context) -> list[dict]:
    """missing_image + wrong_hash."""
    out: list[dict] = []
    for name, item in ctx.manifest.items():
        image = ctx.d / item["image"]
        if not image.is_file():
            out.append({"type": "missing_image", "target": name})
            continue
        expected = item.get("image_sha256")
        if expected and sha256_file(image) != expected:
            out.append({"type": "wrong_hash", "target": name})
            continue
        # Hash label/mask cũng ghi trong manifest; lệch cũng là wrong_hash.
        for key, sha_key in (("label", "label_sha256"), ("mask", "mask_sha256")):
            path = ctx.d / item[key]
            expected_part = item.get(sha_key)
            if expected_part and path.is_file() and sha256_file(path) != expected_part:
                out.append({"type": "wrong_hash", "target": name})
                break
    return out


def parse_label(path: Path) -> list[tuple[int, float, float, float, float]]:
    boxes: list[tuple[int, float, float, float, float]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            class_id = int(float(parts[0]))
            values = [float(parts[i]) for i in range(1, 5)]
        except ValueError:
            continue
        boxes.append((class_id, values[0], values[1], values[2], values[3]))
    return boxes


def check_detection(ctx: Context) -> list[dict]:
    """invalid_class + bbox_out_of_bounds + duplicate_box."""
    out: list[dict] = []
    for name in ctx.manifest:
        item = ctx.manifest[name]
        label_path = ctx.d / item["label"]
        if not label_path.is_file():
            continue
        boxes = parse_label(label_path)

        flagged: str | None = None
        for class_id, *_ in boxes:
            if not 0 <= class_id < ctx.num_classes:
                flagged = "invalid_class"
                break
        if flagged is None:
            for _, x, y, w, h in boxes:
                left, right = x - w / 2, x + w / 2
                top, bottom = y - h / 2, y + h / 2
                if (
                    left < -BBOX_TOL
                    or top < -BBOX_TOL
                    or right > 1 + BBOX_TOL
                    or bottom > 1 + BBOX_TOL
                ):
                    flagged = "bbox_out_of_bounds"
                    break
        if flagged is None:
            flagged = _duplicate(boxes, ctx.dims_of(name))
        if flagged:
            out.append({"type": flagged, "target": name})
    return out


def _duplicate(
    boxes: list[tuple[int, float, float, float, float]],
    dims: tuple[int, int] | None,
) -> str | None:
    """Box lặp: cùng lớp, cùng kích thước, tâm lệch 1-2 px.

    Không dùng IoU: COCO có cặp box tự nhiên chồng nhau tới IoU ~0,66 và khác cỡ.
    """
    if dims:
        limit_x, limit_y = DUP_CENTER_PX / dims[0], DUP_CENTER_PX / dims[1]
    else:
        limit_x = limit_y = DUP_CENTER_NORM

    for i in range(len(boxes)):
        c1, x1, y1, w1, h1 = boxes[i]
        for j in range(i + 1, len(boxes)):
            c2, x2, y2, w2, h2 = boxes[j]
            if c1 != c2:
                continue
            if abs(w1 - w2) > DUP_SIZE_TOL or abs(h1 - h2) > DUP_SIZE_TOL:
                continue
            if abs(x1 - x2) <= limit_x and abs(y1 - y2) <= limit_y:
                return "duplicate_box"
    return None


def check_metadata(ctx: Context) -> list[dict]:
    """scene_leak + guideline_mismatch."""
    out: list[dict] = []

    scene_splits: dict[str, set[str]] = {}
    for meta in ctx.meta.values():
        scene_splits.setdefault(meta["scene_id"], set()).add(meta["split"])
    for scene_id, splits in scene_splits.items():
        if "train" in splits and "val" in splits:
            out.append({"type": "scene_leak", "target": scene_id})

    for name, meta in ctx.meta.items():
        job = ctx.jobs.get(meta["job_id"])
        if job is None:
            continue
        if meta["guideline_version"] != job["guideline"]:
            out.append({"type": "guideline_mismatch", "target": name})
    return out


def check_panoptic(ctx: Context) -> list[dict]:
    """invalid_category_id + thing_overlap."""
    out: list[dict] = []
    for name, ann in ctx.ann_by_name.items():
        segments = ann.get("segments_info", [])
        if any(seg["category_id"] not in ctx.category_ids for seg in segments):
            out.append({"type": "invalid_category_id", "target": name})
        if _thing_overlap(ctx, ann, segments):
            out.append({"type": "thing_overlap", "target": name})
    return out


def _thing_overlap(ctx: Context, ann: dict, segments: list[dict]) -> bool:
    """So `area` khai với số pixel thật của segment (bỏ id 0 và iscrowd)."""
    targets = [
        seg
        for seg in segments
        if seg["category_id"] in ctx.thing_ids
        and not seg.get("iscrowd")
        and seg["id"] != 0
    ]
    if not targets:
        return False

    mask_path = ctx.d / "masks" / Path(ann["file_name"]).name
    if not mask_path.is_file():
        return False
    try:
        _, _, pixels = read_rgb(mask_path)
    except (ValueError, OSError) as exc:  # pragma: no cover
        print(f"cảnh báo: không đọc được mask {mask_path}: {exc}", file=sys.stderr)
        return False

    # Đếm id segment bằng list comprehension + Counter (nhanh hơn cộng dồn từng pixel).
    ids = [
        pixels[i] | (pixels[i + 1] << 8) | (pixels[i + 2] << 16)
        for i in range(0, len(pixels) - 2, 3)
    ]
    counts: Counter[int] = Counter(ids)

    for seg in targets:
        declared = int(seg.get("area", 0))
        if declared <= 0:
            continue
        actual = counts.get(seg["id"], 0)
        # Mask PNG lossless: khai nhiều hơn pixel thật quá 2 px là bất thường.
        if declared - actual > AREA_MIN_DIFF:
            return True
    return False


def build_candidates_if_possible(delivery: Path, out_path: Path) -> bool:
    """--candidates do M3 cung cấp module validator/crosscheck.py."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import crosscheck  # type: ignore
    except ImportError:
        print("chưa có validator/crosscheck.py — bỏ qua --candidates", file=sys.stderr)
        return False
    payload = crosscheck.build_candidates(delivery)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Validator 9 loại lỗi luật cho delivery")
    parser.add_argument("delivery", help="thư mục delivery cần kiểm")
    parser.add_argument("--out", required=True, help="file errors.json đầu ra")
    parser.add_argument("--candidates", help="file candidates.json (do M3 cung cấp module)")
    args = parser.parse_args()

    started = time.time()
    delivery = Path(args.delivery)
    if not (delivery / "manifest.json").is_file():
        raise SystemExit(f"không phải thư mục delivery (thiếu manifest.json): {delivery}")

    ctx = Context(delivery)
    findings: list[dict] = []
    findings += check_files(ctx)
    findings += check_detection(ctx)
    findings += check_metadata(ctx)
    findings += check_panoptic(ctx)

    unique = sorted({(row["type"], row["target"]) for row in findings})
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"errors": [{"type": kind, "target": target} for kind, target in unique]},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )

    counts = Counter(kind for kind, _ in unique)
    detail = ", ".join(f"{kind}={counts[kind]}" for kind in RULE_ORDER if counts[kind])
    elapsed = time.time() - started
    print(f"{len(unique)} lỗi luật ({detail or 'không có'}) -> {out_path} [{elapsed:.1f}s]")

    if args.candidates:
        build_candidates_if_possible(delivery, Path(args.candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
