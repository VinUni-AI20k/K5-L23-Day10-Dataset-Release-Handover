#!/usr/bin/env python3
"""Validator của Nhóm 7: bắt lỗi luật và sinh ứng viên đối chiếu detection <-> panoptic.

  python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

- Chỉ đọc thư mục delivery được truyền vào, chỉ thư viện chuẩn (+ scripts/pngutil.py), không mạng.
- `--out` chỉ chứa lỗi LUẬT (9 loại). Lỗi gán nhãn phải qua xem ảnh rồi gộp bằng scripts/merge_review.py.
- `--candidates` ghi hàng đợi ứng viên lỗi gán nhãn để nhóm mở ảnh xem.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pngutil  # noqa: E402

NUM_CLASSES = 80

# ---- Ngưỡng luật (đơn vị pixel) ----
OOB_TOL_PX = 0.5          # box tràn mép quá 0.5 px mới tính là vượt ảnh (bù sai số làm tròn YOLO)
DUP_SIZE_TOL_PX = 1.0     # box lặp: chênh rộng/cao không quá 1 px ("cùng kích thước")
DUP_SHIFT_MAX_PX = 3.0    # box lặp: tâm lệch không quá 3 px ("lệch 1–2 pixel")
OVERLAP_TOL_PX = 0        # area khai > số pixel thật + tol thì là thing_overlap


# =============================================================== đọc file

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jpeg_size(path: Path) -> tuple[int, int] | None:
    """(width, height) từ marker SOF của JPEG; None nếu không đọc được."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        length = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[pos + 5 : pos + 9])
            return w, h
        pos += 2 + length
    return None


def read_mask(path: Path) -> tuple[int, int, bytes]:
    """Đọc mask RGB. Đường nhanh khi mọi dòng dùng filter 0; còn lại nhờ pngutil."""
    data = path.read_bytes()
    pos, width, height, idat = 8, None, None, bytearray()
    simple = data[:8] == b"\x89PNG\r\n\x1a\n"
    while simple and pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit, color, _c, _f, inter = struct.unpack(">IIBBBBB", chunk)
            simple = (bit, color, inter) == (8, 2, 0)
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
    if simple and width:
        raw = zlib.decompress(bytes(idat))
        stride = width * 3 + 1
        if len(raw) == stride * height and all(raw[y * stride] == 0 for y in range(height)):
            return width, height, b"".join(raw[y * stride + 1 : (y + 1) * stride] for y in range(height))
    w, h, px = pngutil.read_rgb(path)
    return w, h, bytes(px)


def id_counts(pixels: bytes) -> Counter:
    """Số pixel theo segment id (R + G*256 + B*65536)."""
    rgb = Counter(zip(pixels[0::3], pixels[1::3], pixels[2::3]))
    return Counter({r + g * 256 + b * 65536: n for (r, g, b), n in rgb.items()})


class Delivery:
    def __init__(self, root: Path):
        self.root = root
        self.manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["items"]
        self.meta = {m["image"]: m for m in json.loads((root / "metadata.json").read_text(encoding="utf-8"))["items"]}
        with open(root / "jobs.csv", encoding="utf-8", newline="") as f:
            self.jobs = {r["job_id"].strip(): r for r in csv.DictReader(f)}
        self.classes = {}
        for line in (root / "classes.txt").read_text(encoding="utf-8").splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0].lstrip("-").isdigit():
                self.classes[int(parts[0])] = parts[1].strip()
        pan = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
        self.categories = {c["id"]: c for c in pan["categories"]}
        self.pan_images = {Path(i["file_name"]).stem: i for i in pan["images"]}
        self.pan_ann = {Path(a["file_name"]).stem: a for a in pan["annotations"]}
        self._size: dict[str, tuple[int, int] | None] = {}
        self._mask: dict[str, tuple[int, int, bytes] | None] = {}

    def images(self) -> list[str]:
        return sorted(self.manifest)

    def path(self, stem: str, key: str) -> Path:
        return self.root / self.manifest[stem][key]

    def size(self, stem: str) -> tuple[int, int] | None:
        if stem not in self._size:
            info = self.pan_images.get(stem)
            if info and info.get("width") and info.get("height"):
                self._size[stem] = (int(info["width"]), int(info["height"]))
            else:
                self._size[stem] = jpeg_size(self.path(stem, "image"))
        return self._size[stem]

    def mask(self, stem: str) -> tuple[int, int, bytes] | None:
        if stem not in self._mask:
            p = self.path(stem, "mask")
            try:
                self._mask[stem] = read_mask(p) if p.exists() else None
            except (ValueError, zlib.error, struct.error):
                self._mask[stem] = None
        return self._mask[stem]

    def labels(self, stem: str) -> list[tuple[str, list[str]]]:
        """[(class_token, [x, y, w, h])] — giữ dạng chuỗi để kiểm class_id hợp lệ."""
        p = self.path(stem, "label")
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts:
                out.append((parts[0], parts[1:]))
        return out

    def boxes_px(self, stem: str) -> list[tuple[int, float, float, float, float]]:
        """Box hợp lệ dạng pixel: (class_id, x0, y0, x1, y1)."""
        size = self.size(stem)
        if not size:
            return []
        w, h = size
        out = []
        for tok, nums in self.labels(stem):
            try:
                c = int(tok)
                xc, yc, bw, bh = (float(v) for v in nums[:4])
            except ValueError:
                continue
            out.append((c, (xc - bw / 2) * w, (yc - bh / 2) * h, (xc + bw / 2) * w, (yc + bh / 2) * h))
        return out


# =============================================================== lỗi luật

def check_files(d: Delivery, found: dict[str, str]) -> None:
    for stem in d.images():
        item = d.manifest[stem]
        if not d.path(stem, "image").exists():
            found.setdefault(stem, "missing_image")
            continue
        for key in ("image", "label", "mask"):
            p = d.path(stem, key)
            want = item.get(f"{key}_sha256", "")
            if p.exists() and sha256_file(p) != want.lower():
                found.setdefault(stem, "wrong_hash")
                break


def check_detection(d: Delivery, found: dict[str, str]) -> None:
    for stem in d.images():
        if stem in found:
            continue
        rows = d.labels(stem)
        bad_class = False
        for tok, nums in rows:
            try:
                c = int(tok)
            except ValueError:
                bad_class = True
                break
            if not 0 <= c < NUM_CLASSES or (d.classes and c not in d.classes):
                bad_class = True
                break
        if bad_class:
            found[stem] = "invalid_class"
            continue

        size = d.size(stem)
        if not size:
            continue
        w, h = size
        boxes = d.boxes_px(stem)
        if any(x0 < -OOB_TOL_PX or y0 < -OOB_TOL_PX or x1 > w + OOB_TOL_PX or y1 > h + OOB_TOL_PX
               for _c, x0, y0, x1, y1 in boxes):
            found[stem] = "bbox_out_of_bounds"
            continue

        if has_duplicate(boxes):
            found[stem] = "duplicate_box"


def has_duplicate(boxes: list[tuple[int, float, float, float, float]]) -> bool:
    for i in range(len(boxes)):
        ci, ax0, ay0, ax1, ay1 = boxes[i]
        for j in range(i + 1, len(boxes)):
            cj, bx0, by0, bx1, by1 = boxes[j]
            if ci != cj:
                continue
            if abs((ax1 - ax0) - (bx1 - bx0)) > DUP_SIZE_TOL_PX or abs((ay1 - ay0) - (by1 - by0)) > DUP_SIZE_TOL_PX:
                continue
            dx = abs((ax0 + ax1) - (bx0 + bx1)) / 2
            dy = abs((ay0 + ay1) - (by0 + by1)) / 2
            if max(dx, dy) <= DUP_SHIFT_MAX_PX:
                return True
    return False


def check_metadata(d: Delivery, found: dict[str, str], scene_errors: list[str]) -> None:
    splits: dict[str, set[str]] = defaultdict(set)
    for stem, m in d.meta.items():
        splits[m.get("scene_id", "")].add(m.get("split", ""))
    scene_errors.extend(sorted(s for s, v in splits.items() if s and len(v) > 1))

    for stem, m in d.meta.items():
        if stem in found:
            continue
        job = d.jobs.get(str(m.get("job_id", "")).strip())
        if job and str(m.get("guideline_version", "")).strip() != job.get("guideline", "").strip():
            found[stem] = "guideline_mismatch"


def check_panoptic(d: Delivery, found: dict[str, str]) -> None:
    for stem in d.images():
        if stem in found:
            continue
        ann = d.pan_ann.get(stem)
        if not ann:
            continue
        segs = ann.get("segments_info", [])
        if any(s.get("category_id") not in d.categories for s in segs):
            found[stem] = "invalid_category_id"
            continue
        m = d.mask(stem)
        if not m:
            continue
        counts = id_counts(m[2])
        if any(s.get("area", 0) > counts.get(s["id"], 0) + OVERLAP_TOL_PX for s in segs if s.get("id")):
            found[stem] = "thing_overlap"


def rule_errors(d: Delivery) -> list[dict]:
    found: dict[str, str] = {}   # mỗi ảnh nhiều nhất một lỗi; thứ tự kiểm = thứ tự ưu tiên
    scenes: list[str] = []
    check_files(d, found)
    check_detection(d, found)
    check_metadata(d, found, scenes)
    check_panoptic(d, found)
    errs = [{"type": t, "target": s} for s, t in found.items()]
    errs += [{"type": "scene_leak", "target": s} for s in scenes]
    return sorted(errs, key=lambda e: (e["type"], e["target"]))


# =============================================================== ứng viên đối chiếu

def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def pixels_in_box(pixels: bytes, width: int, height: int, box) -> Counter:
    """Đếm pixel theo segment id bên trong một box pixel."""
    x0 = max(0, int(box[0])); x1 = min(width, int(box[2] + 0.999))
    y0 = max(0, int(box[1])); y1 = min(height, int(box[3] + 0.999))
    c: Counter = Counter()
    if x1 <= x0 or y1 <= y0:
        return c
    for y in range(y0, y1):
        row = pixels[(y * width + x0) * 3 : (y * width + x1) * 3]
        c.update(zip(row[0::3], row[1::3], row[2::3]))
    return Counter({r + g * 256 + b * 65536: n for (r, g, b), n in c.items()})


# Ngưỡng ứng viên — chỉnh bằng lô sạch (runs/clean), ghi lý do vào REPORT.md.
MATCH_IOU = 0.3           # box và segment coi là cùng một vật
SWAP_IOU = 0.50           # trùng vị trí chặt khi lớp khác nhau (hạ từ 0.60 để bắt ca box hơi lệch)
DRIFT_INSIDE_MAX = 0.82   # < 82% pixel segment nằm trong box cùng lớp gần nhất -> lệch
DRIFT_IOU_MIN = 0.15      # nhưng box vẫn đang "nhắm" vào segment đó (bắt cả ca lệch mạnh)
MISSING_MIN_FRAC = 0.008  # segment thing chiếm ≥0.8% ảnh mà không box nào phủ
MERGE_SHARE_MIN = 0.25    # mỗi box cùng lớp chứa ≥25% pixel của segment -> có thể gộp
MERGE_SINGLE_MAX = 0.80   # ...và không box nào một mình chứa ≥80% segment
MERGE_PAIR_IOU_MAX = 0.3  # ...và có hai box giữ segment mà ít chồng nhau


def candidates(d: Delivery, skip: set[str]) -> list[dict]:
    out = []
    for stem in d.images():
        if stem in skip:
            continue
        ann = d.pan_ann.get(stem)
        m = d.mask(stem)
        if not ann or not m:
            continue
        width, height, pixels = m
        boxes = d.boxes_px(stem)
        segs = [s for s in ann.get("segments_info", [])
                if d.categories.get(s.get("category_id"), {}).get("isthing") and not s.get("iscrowd")]
        name_of_box = [d.classes.get(b[0], "?") for b in boxes]
        name_of_seg = [d.categories[s["category_id"]]["name"] for s in segs]
        seg_box = [(s["bbox"][0], s["bbox"][1], s["bbox"][0] + s["bbox"][2], s["bbox"][1] + s["bbox"][3]) for s in segs]
        seg_area = {s["id"]: max(1, s.get("area", 1)) for s in segs}
        inside = [pixels_in_box(pixels, width, height, b[1:]) for b in boxes]

        reasons: dict[str, list[str]] = defaultdict(list)
        covered = set()
        for si, s in enumerate(segs):
            sid, sname = s["id"], name_of_seg[si]
            best_same, best_other = None, None
            for bi, b in enumerate(boxes):
                ov = iou(b[1:], seg_box[si])
                frac = inside[bi].get(sid, 0) / seg_area[sid]
                if ov >= MATCH_IOU or frac >= 0.5:
                    covered.add(si)
                key = (ov, frac, bi)
                if name_of_box[bi] == sname:
                    if best_same is None or key > best_same:
                        best_same = key
                elif best_other is None or key > best_other:
                    best_other = key

            # Lệch lớp: trùng vị trí chặt với box khác lớp, không có box cùng lớp nào khớp.
            if best_other and best_other[0] >= SWAP_IOU and (best_same is None or best_same[0] < MATCH_IOU):
                bi = best_other[2]
                reasons["class_or_category_swap"].append(
                    f"segment {sname} ↔ box {name_of_box[bi]} (IoU {best_other[0]:.2f})"
                )
                continue

            # Gộp: kiểm trước bbox_drift để tránh báo đúp khi ≥2 box cùng lớp chia nhau 1 segment.
            share = {bi: inside[bi].get(sid, 0) / seg_area[sid] for bi in range(len(boxes)) if name_of_box[bi] == sname}
            holders = [bi for bi, f in share.items() if f >= MERGE_SHARE_MIN]
            if len(holders) >= 2 and max(share.values()) < MERGE_SINGLE_MAX:
                separate = any(iou(boxes[a][1:], boxes[b][1:]) < MERGE_PAIR_IOU_MAX
                               for i, a in enumerate(holders) for b in holders[i + 1:])
                if separate:
                    reasons["instance_merge"].append(
                        f"segment {sname} trải trên {len(holders)} box {sname}, box lớn nhất giữ {max(share.values()):.0%}"
                    )
                    continue

            # Lệch box: box cùng lớp nhắm vào segment nhưng để rơi nhiều pixel ra ngoài.
            if best_same and best_same[0] >= DRIFT_IOU_MIN and best_same[1] < DRIFT_INSIDE_MAX:
                reasons["bbox_drift"].append(
                    f"{sname}: chỉ {best_same[1]:.0%} pixel segment trong box (IoU {best_same[0]:.2f})"
                )

        for si, s in enumerate(segs):
            if si not in covered and s.get("area", 0) >= MISSING_MIN_FRAC * width * height:
                reasons["missing_box"].append(f"segment {name_of_seg[si]} area {s.get('area')} không có box")

        for kind, notes in sorted(reasons.items()):
            out.append({"image": stem, "type": kind, "note": "; ".join(notes)})
    return out


# =============================================================== main

def main() -> int:
    ap = argparse.ArgumentParser(description="Validator Nhóm 7")
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True, help="errors.json (chỉ lỗi luật)")
    ap.add_argument("--candidates", help="candidates.json (ứng viên lỗi gán nhãn để xem ảnh)")
    args = ap.parse_args()

    d = Delivery(Path(args.delivery))
    errs = rule_errors(d)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"errors": errs}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    by_type = Counter(e["type"] for e in errs)
    print(f"{len(errs)} lỗi luật -> {args.out}: " + ", ".join(f"{t}={n}" for t, n in sorted(by_type.items())))

    if args.candidates:
        skip = {e["target"] for e in errs}  # mỗi ảnh nhiều nhất một lỗi
        cands = candidates(d, skip)
        Path(args.candidates).parent.mkdir(parents=True, exist_ok=True)
        Path(args.candidates).write_text(json.dumps({"candidates": cands}, indent=1, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
        imgs = len({c["image"] for c in cands})
        kinds = Counter(c["type"] for c in cands)
        print(f"{len(cands)} ứng viên trên {imgs} ảnh -> {args.candidates}: "
              + ", ".join(f"{t}={n}" for t, n in sorted(kinds.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
