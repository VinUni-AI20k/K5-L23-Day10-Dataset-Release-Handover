"""Công cụ xem ảnh review (cần Pillow; KHÔNG phải validator).

    py -X utf8 tools/view.py <delivery> --candidates c.json [--out-dir DIR]
    py -X utf8 tools/view.py <delivery> --images 000000000139 img_0001 ...
    py -X utf8 tools/view.py <delivery> --csv work/review_phuc.csv
    py -X utf8 tools/view.py <delivery> --images X --crop 100,50,300,250   # pixel gốc

Mỗi ảnh ra một PNG ghép đôi: TRÁI = box detection (tên lớp), PHẢI = viền
segment panoptic (tên category). Ảnh nhỏ được phóng to (--min-side).
Segment crowd viền đứt (nét mờ). Chỉ đọc delivery; ghi ra --out-dir.
"""
from __future__ import annotations

import argparse
import colorsys
import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def color(i: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb((i * 0.61803) % 1.0, 0.85, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def load_classes(d: Path) -> list[str]:
    names = {}
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        p = line.strip().split(None, 1)
        if len(p) == 2 and p[0].isdigit():
            names[int(p[0])] = p[1]
    return [names.get(i, f"?{i}") for i in range(max(names) + 1)] if names else []


def find_file(d: Path, sub: str, stem: str, exts: tuple[str, ...]):
    for e in exts:
        p = d / sub / f"{stem}{e}"
        if p.exists():
            return p
    return None


def draw_detection(img: Image.Image, label: Path | None, classes, scale: float, ox: int, oy: int):
    dr = ImageDraw.Draw(img)
    f = font(max(12, int(13 * max(scale, 1))))
    w0, h0 = img.size[0] / scale, img.size[1] / scale  # kích thước gốc (đã crop)
    if label is None or not label.exists():
        dr.text((6, 6), "KHÔNG CÓ FILE NHÃN", fill=(255, 0, 0), font=f)
        return
    iw, ih = IMG_SIZE
    for line in label.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        try:
            cid = int(p[0])
            xc, yc, bw, bh = (float(v) for v in p[1:5])
        except ValueError:
            continue
        x0, y0 = (xc - bw / 2) * iw - ox, (yc - bh / 2) * ih - oy
        x1, y1 = (xc + bw / 2) * iw - ox, (yc + bh / 2) * ih - oy
        c = color(cid if cid >= 0 else 0)
        name = classes[cid] if 0 <= cid < len(classes) else f"BAD_ID_{cid}"
        dr.rectangle([x0 * scale, y0 * scale, x1 * scale, y1 * scale], outline=c, width=2)
        tw = dr.textlength(name, font=f)
        ty = max(0, y0 * scale - f.size - 2)
        dr.rectangle([x0 * scale, ty, x0 * scale + tw + 4, ty + f.size + 2], fill=c)
        dr.text((x0 * scale + 2, ty), name, fill=(0, 0, 0), font=f)


def draw_panoptic(img: Image.Image, mask_path: Path | None, segs: dict, cats: dict, scale: float, ox: int, oy: int):
    f = font(max(12, int(13 * max(scale, 1))))
    dr = ImageDraw.Draw(img)
    if mask_path is None or not mask_path.exists():
        dr.text((6, 6), "KHÔNG CÓ MASK", fill=(255, 0, 0), font=f)
        return
    m = Image.open(mask_path).convert("RGB")
    iw, ih = IMG_SIZE
    if m.size != (iw, ih):
        m = m.resize((iw, ih), Image.NEAREST)
    px = m.load()
    ids = [[px[x, y][0] + px[x, y][1] * 256 + px[x, y][2] * 65536 for x in range(iw)] for y in range(ih)]
    # tô mờ + viền biên: pixel có láng giềng (phải/dưới) khác id
    over = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
    op = over.load()
    for y in range(ih):
        row = ids[y]
        for x in range(iw):
            sid = row[x]
            if sid == 0 or sid not in segs:
                continue
            cat = segs[sid]
            if not cats.get(cat["category_id"], {}).get("isthing", 1):
                continue
            c = color(cat["category_id"])
            edge = (x + 1 < iw and row[x + 1] != sid) or (y + 1 < ih and ids[y + 1][x] != sid) or x == 0 or y == 0
            op[x, y] = c + ((255,) if edge else (70,))
    over = over.crop((ox, oy, ox + int(img.size[0] / scale), oy + int(img.size[1] / scale)))
    over = over.resize(img.size, Image.NEAREST)
    img.paste(Image.alpha_composite(img.convert("RGBA"), over).convert("RGB"))
    dr = ImageDraw.Draw(img)
    for sid, s in segs.items():
        cat = cats.get(s["category_id"])
        if not cat or not cat.get("isthing", 1):
            continue
        bx, by, bw, bh = s["bbox"]
        name = cat["name"] + (" (crowd)" if s.get("iscrowd") else "")
        tx, ty = (bx - ox) * scale, (by - oy) * scale
        if -5 < tx < img.size[0] and -5 < ty < img.size[1]:
            c = color(s["category_id"])
            tw = dr.textlength(name, font=f)
            ty = max(0, ty - f.size - 2)
            dr.rectangle([tx, ty, tx + tw + 4, ty + f.size + 2], fill=c)
            dr.text((tx + 2, ty), name, fill=(0, 0, 0), font=f)


def render(d: Path, stem: str, panoptic, classes, out_dir: Path, crop, min_side: int):
    global IMG_SIZE
    ip = find_file(d, "images", stem, (".jpg", ".jpeg", ".png"))
    if ip is None:
        print(f"{stem}: thiếu file ảnh (có thể đúng là lỗi missing_image)", file=sys.stderr)
        return None
    base = Image.open(ip).convert("RGB")
    IMG_SIZE = base.size
    ox, oy, x1, y1 = crop if crop else (0, 0, base.size[0], base.size[1])
    ox, oy = max(0, ox), max(0, oy)
    x1, y1 = min(base.size[0], x1), min(base.size[1], y1)
    view = base.crop((ox, oy, x1, y1))
    scale = max(1.0, min_side / max(view.size)) if min_side else 1.0
    scale = min(scale, 6.0)
    big = view.resize((int(view.size[0] * scale), int(view.size[1] * scale)), Image.LANCZOS)

    left, right = big.copy(), big.copy()
    draw_detection(left, d / "labels" / f"{stem}.txt", classes, scale, ox, oy)
    ann = panoptic["ann"].get(stem)
    segs = {s["id"]: s for s in ann["segments_info"]} if ann else {}
    draw_panoptic(right, find_file(d, "masks", stem, (".png",)), segs, panoptic["cats"], scale, ox, oy)

    f = font(15)
    head = 24
    canvas = Image.new("RGB", (left.size[0] * 2 + 6, left.size[1] + head), (20, 20, 20))
    canvas.paste(left, (0, head))
    canvas.paste(right, (left.size[0] + 6, head))
    dr = ImageDraw.Draw(canvas)
    dr.text((4, 3), f"{stem}  |  DETECTION (nhãn YOLO)", fill=(255, 255, 255), font=f)
    dr.text((left.size[0] + 10, 3), "PANOPTIC (thing, viền segment)", fill=(255, 255, 255), font=f)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_crop" if crop else ""
    p = out_dir / f"{stem}{suffix}.png"
    canvas.save(p)
    return p


def load_panoptic(d: Path):
    p = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
    ann = {Path(a["file_name"]).stem: a for a in p["annotations"]}
    cats = {c["id"]: c for c in p["categories"]}
    return {"ann": ann, "cats": cats}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("delivery", nargs="?", default=None, help="thư mục delivery (nếu bỏ trống sẽ tự động tìm)")
    ap.add_argument("--candidates")
    ap.add_argument("--csv", help="file review của một người (cột image)")
    ap.add_argument("--images", nargs="*", default=[])
    ap.add_argument("--out-dir", default=None, help="mặc định: <delivery>/../view")
    ap.add_argument("--crop", help="x0,y0,x1,y1 theo pixel ảnh gốc")
    ap.add_argument("--min-side", type=int, default=800, help="phóng to cạnh dài tới ít nhất giá trị này (0 = không)")
    a = ap.parse_args()

    # Tự động nhận diện nếu bấm nút Run trực tiếp trong IDE (không truyền tham số)
    if not a.delivery:
        if Path("delivery").is_dir():
            d = Path("delivery")
        else:
            candidates_d = sorted(Path("runs").glob("r*/delivery"), key=lambda p: p.stat().st_mtime, reverse=True)
            if candidates_d:
                d = candidates_d[0]
            else:
                ap.error("Không tìm thấy thư mục delivery nào trong runs/. Vui lòng chỉ định: py tools/view.py <delivery>")
        print(f"[Auto-detect] Tự động chọn delivery: {d}")
    else:
        d = Path(a.delivery)

    names = list(a.images)
    if a.candidates:
        data = json.loads(Path(a.candidates).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("candidates", [])
        names += [c["image"] for c in data]
    if a.csv:
        with open(a.csv, encoding="utf-8-sig", newline="") as f:
            names += [r["image"] for r in csv.DictReader(f)]

    # Nếu chưa chỉ định danh sách ảnh khi chạy trực tiếp từ nút Run
    if not names:
        # Ưu tiên tìm file review cá nhân của Phúc
        if Path("work/review_phuc.csv").is_file():
            print("[Auto-detect] Đọc danh sách ảnh từ: work/review_phuc.csv")
            with open("work/review_phuc.csv", encoding="utf-8-sig", newline="") as f:
                names += [r["image"] for r in csv.DictReader(f) if r.get("image")]
        elif (d.parent / "candidates.json").is_file():
            print(f"[Auto-detect] Đọc danh sách ảnh từ: {d.parent / 'candidates.json'}")
            data = json.loads((d.parent / "candidates.json").read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = data.get("candidates", [])
            names += [c["image"] for c in data]
        else:
            # Lấy 3 ảnh đầu tiên trong images/ để demo chạy thử
            img_files = sorted((d / "images").glob("*.jpg"))[:3]
            names += [p.stem for p in img_files]
            if names:
                print(f"[Auto-detect] Không có file review/candidates, hiển thị thử 3 ảnh đầu: {names}")

    names = list(dict.fromkeys(names))
    if not names:
        ap.error("cần --candidates, --csv hoặc --images")
    crop = tuple(int(v) for v in a.crop.split(",")) if a.crop else None
    out_dir = Path(a.out_dir) if a.out_dir else d.resolve().parent / "view"

    panoptic, classes = load_panoptic(d), load_classes(d)
    print(f"Đang xuất ảnh vào thư mục: {out_dir}")
    for stem in names:
        p = render(d, stem, panoptic, classes, out_dir, crop, a.min_side)
        if p:
            print(f"  -> Đã tạo: {p}")
    return 0


IMG_SIZE = (0, 0)

if __name__ == "__main__":
    raise SystemExit(main())
