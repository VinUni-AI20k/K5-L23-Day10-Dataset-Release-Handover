#!/usr/bin/env python3
"""Day 10: tao anh overlay review COCO detection + panoptic (Pillow only).

Vi du:
  python tools/review_overlay.py --delivery runs/r7007/delivery --candidates runs/r7007/candidates.json --images 000000000785 000000001353
  python tools/review_overlay.py --delivery runs/r7007/delivery --candidates runs/r7007/candidates.json --all-candidates

Chi doc delivery; chi ghi anh ra output. KHONG sua du lieu goc.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PALETTE = [(236, 88, 75), (65, 168, 227), (245, 184, 65), (133, 211, 117),
           (187, 119, 216), (59, 210, 178), (226, 117, 176), (155, 180, 74)]


def read_classes(file: Path) -> dict[int, str]:
    mapping = {}
    for idx, line in enumerate(file.read_text(encoding="utf-8-sig").splitlines()):
        words = line.strip().split(maxsplit=1)
        if not words:
            continue
        if len(words) == 2 and words[0].isdigit():
            mapping[int(words[0])] = words[1]
        else:
            mapping[idx] = line.strip()
    return mapping


def candidate_rows(path: Path | None) -> dict[str, list[dict]]:
    by_img = defaultdict(list)
    if path is None:
        return by_img
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = raw if isinstance(raw, list) else raw.get("candidates", [])
    if not isinstance(rows, list):
        raise ValueError("candidates JSON must be a list or object containing 'candidates' list")
    for row in rows:
        if isinstance(row, dict) and row.get("target") is not None:
            by_img[str(row["target"])].append(row)
    return by_img


def pretty_image(image: Image.Image, width: int, height: int) -> Image.Image:
    img = image.copy()
    img.thumbnail((width, height), Image.Resampling.LANCZOS)
    return img


def class_and_box(label: str, w: int, h: int):
    parts = label.split()
    if len(parts) != 5:
        return None
    try:
        class_id = int(float(parts[0]))
        cx, cy, bw, bh = map(float, parts[1:])
    except ValueError:
        return None
    return class_id, ((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h)


def draw_boxes(image: Image.Image, label_path: Path, names: dict[int, str], highlights: set[int]) -> Image.Image:
    img = image.copy().convert("RGB")
    pen = ImageDraw.Draw(img)
    if not label_path.is_file():
        pen.text((10, 10), "KHONG CO LABEL", fill="red", stroke_width=2, stroke_fill="white")
        return img
    for line_no, label in enumerate(label_path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        parsed = class_and_box(label, img.width, img.height)
        if not parsed:
            continue
        class_id, bb = parsed
        active = line_no in highlights
        color = (245, 65, 38) if active else (65, 220, 76)
        pen.rectangle(bb, outline=color, width=5 if active else 2)
        msg = f"L{line_no} {names.get(class_id, str(class_id))}"
        tx, ty = max(0, bb[0]), max(0, bb[1] - 17)
        pen.rectangle((tx, ty, tx + 8 * len(msg) + 6, ty + 16), fill=(24, 24, 24))
        pen.text((tx + 3, ty + 2), msg, fill=color)
    return img


def colorize_mask(mask_path: Path, size: tuple[int, int], highlights: set[int]) -> Image.Image:
    if not mask_path.is_file():
        return Image.new("RGB", size, (35, 35, 35))
    with Image.open(mask_path) as raw:
        rgb = raw.convert("RGB")
        if rgb.size != size:
            raise ValueError(f"Mask size {rgb.size} != photo size {size}")
        pixels = rgb.load()
        result = Image.new("RGB", rgb.size, (40, 40, 40))
        out = result.load()
        for y in range(rgb.height):
            for x in range(rgb.width):
                r, g, b = pixels[x, y]
                sid = r + 256 * g + 65536 * b
                if sid == 0:
                    continue
                color = PALETTE[sid % len(PALETTE)]
                if highlights:
                    if sid in highlights:
                        color = (255, 230, 50)
                    else:
                        color = tuple(max(20, c // 3) for c in color)
                out[x, y] = color
    return result


def export_one(root: Path, out_dir: Path, target: str, entries: list[dict], names: dict[int, str]) -> Path:
    image_path = root / "images" / f"{target}.jpg"
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    with Image.open(image_path) as f:
        photo = f.convert("RGB")
    highlighted_lines = set()
    highlighted_segments = set()
    for row in entries:
        ev = row.get("evidence") or {}
        if isinstance(ev, dict):
            if ev.get("box_line") is not None:
                highlighted_lines.add(int(ev["box_line"]))
            for line in ev.get("box_lines", []):
                highlighted_lines.add(int(line))
            if ev.get("segment_id") is not None:
                highlighted_segments.add(int(ev["segment_id"]))
    boxes = draw_boxes(photo, root / "labels" / f"{target}.txt", names, highlighted_lines)
    mask = colorize_mask(root / "masks" / f"{target}.png", photo.size, highlighted_segments)
    combined = Image.blend(photo, mask, .40)
    combined = draw_boxes(combined, root / "labels" / f"{target}.txt", names, highlighted_lines)

    tiles = [photo, boxes, mask, combined]
    titles = ["1. ANH GOC", "2. DETECTION (BOX)", "3. PANOPTIC (MASK)", "4. CHONG BOX + MASK"]
    max_w, max_h = 750, 560
    resized = [pretty_image(img, max_w, max_h) for img in tiles]
    cell_w, cell_h = max_w + 20, max_h + 40
    details = []
    for row in entries:
        e = row.get("evidence") or {}
        details.append(f"{row.get('type')}: {json.dumps(e, ensure_ascii=False)}")
    footer_lines = ["UNG VIEN (CHUA PHAI LOI THAT):"] + (details or ["Khong co ung vien cho anh nay"])
    # Wrap long evidence without requiring fonts outside standard PIL.
    wrapped = []
    for line in footer_lines:
        while len(line) > 115:
            wrapped.append(line[:115])
            line = "    " + line[115:]
        wrapped.append(line)
    footer_h = max(75, len(wrapped) * 18 + 25)
    canvas = Image.new("RGB", (cell_w * 2, cell_h * 2 + footer_h + 40), (249, 250, 253))
    painter = ImageDraw.Draw(canvas)
    painter.text((14, 9), f"DAY 10 | IMAGE {target} | highlight: box do, mask vang", fill=(15, 25, 36))
    for i, im in enumerate(resized):
        x = i % 2 * cell_w + 10
        y = i // 2 * cell_h + 40
        canvas.paste(im, (x, y))
        painter.text((x, y + max_h + 4), titles[i], fill=(15, 25, 36))
    by = 40 + 2 * cell_h
    for j, line in enumerate(wrapped):
        painter.text((14, by + 18 * j), line, fill=(20, 30, 45))
    out = out_dir / f"{target}_review.png"
    canvas.save(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Review overlay: Anh goc / Detection / Panoptic / Tong hop")
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--images", nargs="*", help="ID anh (giu so 0 dau)")
    parser.add_argument("--all-candidates", action="store_true", help="Tao anh cho tat ca image IDs trong candidates")
    parser.add_argument("--outdir", type=Path, default=Path("runs/r7007/review_overlays"))
    args = parser.parse_args()
    root = args.delivery.resolve()
    if not root.is_dir():
        parser.error(f"Missing delivery: {root}")
    candidates = candidate_rows(args.candidates)
    ids = list(dict.fromkeys(args.images or []))
    if args.all_candidates:
        ids = sorted(set(ids) | set(candidates))
    if not ids:
        parser.error("Choose --images IMAGE_ID [IMAGE_ID...] or --all-candidates")
    names = read_classes(root / "classes.txt")
    args.outdir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for image_id in ids:
        try:
            file = export_one(root, args.outdir, image_id, candidates.get(image_id, []), names)
            print(f"OK {image_id}: {file}")
        except (OSError, ValueError, KeyError, TypeError) as err:
            failed += 1
            print(f"FAIL {image_id}: {err}", file=sys.stderr)
    print(f"Da xu ly {len(ids)} anh; that bai {failed}; output: {args.outdir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
