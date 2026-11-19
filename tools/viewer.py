#!/usr/bin/env python3
"""Công cụ xem ảnh để review (nhóm 30). Vẽ box detection và viền segment panoptic lên ảnh.

Không phải validator: được dùng Pillow, không nằm trong validator/.
Chỉ đọc thư mục delivery được truyền vào (không đọc _private/, data_source/).

Ví dụ:
  # xem vài ảnh theo tên (có hoặc không có đuôi)
  python tools/viewer.py runs/r30007/delivery 000000004765 000000004795

  # xem cả một cảnh
  python tools/viewer.py runs/r30007/delivery --scene scene_497

  # xem hàng đợi ứng viên do validator sinh ra, chia cho 5 người, tạo trang review
  python tools/viewer.py runs/r30007/delivery --candidates runs/r30007/candidates.json \
      --assign "Tung,Huong,Viet,Huynh,Khanh"

  # đề ẩn
  python tools/viewer.py delivery --candidates submission/de_an/candidates.json --assign "..."

Kết quả nằm trong --out (mặc định <delivery>/../review_out):
  <ảnh>__<type>.png   trái: ảnh gốc, phải: ảnh có vẽ nhãn (đỏ = detection, màu khác = panoptic)
  index.html          mở bằng trình duyệt: xem từng ảnh, chọn confirmed/rejected, ghi chú,
                      bấm "Tải review_log.csv" để lấy file đúng định dạng.

candidates.json chấp nhận {"candidates": [...]}, {"errors": [...]} hoặc một list. Mỗi mục cần
"target" (hoặc "image") và "type"; tuỳ chọn:
  "box":     chỉ số dòng (0-based) trong labels/<ảnh>.txt, hoặc list chỉ số -> tô vàng box đó
  "segment": id segment panoptic, hoặc list id                               -> tô vàng segment đó
  "note"/"reason": lý do validator nghi, in lên ảnh
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    raise SystemExit("Cần Pillow cho công cụ xem ảnh: pip install pillow")

DET_COLOR = (255, 40, 40)
HL_COLOR = (255, 230, 0)
# màu panoptic: KHÔNG có vàng/cam/đỏ, vì đỏ = detection, vàng = bị nghi
PALETTE = [(0, 150, 255), (0, 230, 120), (255, 90, 255), (240, 240, 240), (150, 110, 255),
           (0, 220, 220), (255, 170, 220), (0, 140, 110), (120, 190, 255), (200, 150, 255)]
SEMANTIC = {"class_swap", "bbox_drift", "missing_box", "category_swap", "instance_merge"}
MIN_SIDE = 800  # phóng ảnh nhỏ (vd 240x320) lên để dễ nhìn


FONT_FILES = ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(size: int):
    for name in FONT_FILES:  # font có dấu tiếng Việt
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow cũ
        return ImageFont.load_default()


# ---------------------------------------------------------------- đọc delivery

class Delivery:
    def __init__(self, root: Path):
        self.root = root
        if not (root / "manifest.json").is_file():
            raise SystemExit(f"{root} không có manifest.json: không phải thư mục delivery")
        self.manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["items"]
        self.classes = {}
        for ln in (root / "classes.txt").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                cid, name = ln.split(" ", 1)
                self.classes[int(cid)] = name.strip()
        pan = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
        self.cats = {c["id"]: c for c in pan["categories"]}
        imgs = {im["id"]: im for im in pan["images"]}
        self.pan = {}  # stem -> (image info, annotation)
        for a in pan["annotations"]:
            im = imgs.get(a["image_id"], {})
            stem = Path(im.get("file_name") or a["file_name"]).stem
            self.pan[stem] = (im, a)
        meta_path = root / "metadata.json"
        self.meta = {}
        if meta_path.is_file():
            self.meta = {m["image"]: m for m in json.loads(meta_path.read_text(encoding="utf-8"))["items"]}

    def stems(self) -> list[str]:
        return sorted(self.manifest)

    def boxes(self, stem: str) -> list[dict]:
        it = self.manifest.get(stem, {})
        p = self.root / it.get("label", f"labels/{stem}.txt")
        out = []
        if not p.is_file():
            return out
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines()):
            parts = ln.split()
            if len(parts) < 5:
                continue
            c = int(float(parts[0]))
            x, y, w, h = map(float, parts[1:5])
            out.append({"idx": i, "cls": c, "name": self.classes.get(c, f"?{c}"), "xywh": (x, y, w, h)})
        return out

    def image(self, stem: str):
        it = self.manifest.get(stem, {})
        p = self.root / it.get("image", f"images/{stem}.jpg")
        if p.is_file():
            try:
                return Image.open(p).convert("RGB"), None
            except Exception as exc:  # ảnh hỏng
                return None, f"không mở được ảnh: {exc}"
        return None, "THIẾU FILE ẢNH"

    def mask(self, stem: str):
        it = self.manifest.get(stem, {})
        p = self.root / it.get("mask", f"masks/{stem}.png")
        if not p.is_file():
            return None
        return Image.open(p).convert("RGB")


# ---------------------------------------------------------------- vẽ

def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def draw_labels(img, items, f) -> int:
    """Vẽ chữ, tự né nhau: thử dịch lên/xuống, chỗ nào cũng đè thì bỏ. Trả về số nhãn bị bỏ."""
    d = ImageDraw.Draw(img)
    placed, skipped = [], 0
    for (x, y), text, color in items:
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        w, h = r - l + 4, b - t + 2
        for dy in (0, h, -h, 2 * h, -2 * h, 3 * h):
            box = (x, y + dy, x + w, y + dy + h)
            if box[1] < 0 or box[3] > img.height:
                continue
            if not any(box[0] < p[2] and p[0] < box[2] and box[1] < p[3] and p[1] < box[3] for p in placed):
                placed.append(box)
                d.rectangle(box, fill=(0, 0, 0))
                d.text((box[0] + 2 - l, box[1] + 1 - t), text, fill=color, font=f)
                break
        else:
            skipped += 1
    return skipped


def caption(img, text, f):
    """Thêm dải tiêu đề phía trên một khung."""
    bar = 30
    out = Image.new("RGB", (img.width, img.height + bar), (40, 40, 46))
    ImageDraw.Draw(out).text((8, 5), text, fill=(235, 235, 235), font=f)
    out.paste(img, (0, bar))
    return out


def render(dv: Delivery, stem: str, cand: dict | None, show_stuff: bool) -> Image.Image:
    cand = cand or {}
    hl_boxes = {int(i) for i in as_list(cand.get("box"))}
    hl_segs = {int(i) for i in as_list(cand.get("segment"))}
    img, err = dv.image(stem)
    im_info, ann = dv.pan.get(stem, ({}, {"segments_info": []}))
    if img is None:
        w, h = im_info.get("width", 640), im_info.get("height", 480)
        img = Image.new("RGB", (w, h), (60, 60, 60))
    W, H = img.size
    scale = max(1.0, MIN_SIDE / max(W, H))
    S = lambda v: int(round(v * scale))  # noqa: E731
    base = img.resize((S(W), S(H)), Image.LANCZOS) if scale > 1 else img.copy()

    # --- panoptic: viền + tô nhạt từng segment
    segs = {s["id"]: s for s in ann.get("segments_info", [])}
    seg_color = {}
    for k, sid in enumerate(sorted(segs)):
        seg_color[sid] = PALETTE[k % len(PALETTE)]
    m = dv.mask(stem)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if m is not None and m.size == (W, H):
        px = list(m.getdata())
        ids = [r + g * 256 + b * 65536 for r, g, b in px]
        out = [(0, 0, 0, 0)] * (W * H)
        for i, sid in enumerate(ids):
            s = segs.get(sid)
            if s is None or (not show_stuff and not dv.cats.get(s["category_id"], {}).get("isthing")):
                continue
            hl = sid in hl_segs
            right = ids[i + 1] if (i + 1) % W else -1
            down = ids[i + W] if i + W < W * H else -1
            left = ids[i - 1] if i % W else -1
            up = ids[i - W] if i >= W else -1
            edge = sid != right or sid != down or sid != left or sid != up
            col = HL_COLOR if hl else seg_color[sid]
            out[i] = col + ((255,) if edge else ((110,) if hl else (45,)))
        overlay.putdata(out)
    elif m is not None:
        err = (err + "; " if err else "") + f"mask {m.size} khác ảnh {(W, H)}"
    big_overlay = overlay.resize(base.size, Image.NEAREST)
    f = font(max(13, S(10)))
    lw = max(2, S(2))

    # --- 4 lớp riêng: detection / panoptic / chồng cả hai (không chữ)
    det_img = base.copy()
    pan_img = base.convert("RGBA")
    pan_img.alpha_composite(big_overlay)
    pan_img = pan_img.convert("RGB")
    both = pan_img.copy()
    dd, db = ImageDraw.Draw(det_img), ImageDraw.Draw(both)

    det_texts, pan_texts = [], []
    focus = [tuple(segs[s]["bbox"]) for s in hl_segs if s in segs]  # vùng bị nghi (x, y, w, h) px gốc
    for b in dv.boxes(stem):
        x, y, w, h = b["xywh"]
        x0, y0, x1, y1 = (x - w / 2) * W, (y - h / 2) * H, (x + w / 2) * W, (y + h / 2) * H
        hl = b["idx"] in hl_boxes
        if hl:
            focus.append((x0, y0, x1 - x0, y1 - y0))
        col = HL_COLOR if hl else DET_COLOR
        for dr in (dd, db):
            dr.rectangle((S(x0), S(y0), S(x1), S(y1)), outline=col, width=lw * (2 if hl else 1))
        det_texts.append(((S(x0) + 2, S(y0) + 2), f"D{b['idx']}:{b['name']}", col))
    for sid, s in segs.items():
        cat = dv.cats.get(s["category_id"], {})
        if not show_stuff and not cat.get("isthing"):
            continue
        x, y, w, h = s["bbox"]
        tag = cat.get("name", f"?{s['category_id']}") + (" (crowd)" if s.get("iscrowd") else "")
        pan_texts.append(((S(x) + 2, S(y) + 2), tag, HL_COLOR if sid in hl_segs else seg_color[sid]))

    plain_both = both.copy()  # cho khung phóng to: không chữ
    skip = draw_labels(det_img, det_texts, f) + draw_labels(pan_img, pan_texts, f)

    # --- phóng to quanh vật bị nghi (khi candidates có "box"/"segment")
    zoom = None
    if focus:
        x0 = min(f_[0] for f_ in focus); y0 = min(f_[1] for f_ in focus)
        x1 = max(f_[0] + f_[2] for f_ in focus); y1 = max(f_[1] + f_[3] for f_ in focus)
        pad = max(40, 0.5 * max(x1 - x0, y1 - y0))  # chừa ngữ cảnh, tránh phóng quá to vật tí hon
        box = (max(0, S(x0 - pad)), max(0, S(y0 - pad)), min(base.width, S(x1 + pad)), min(base.height, S(y1 + pad)))
        if box[2] > box[0] and box[3] > box[1]:
            k = min(base.width / (box[2] - box[0]), base.height / (box[3] - box[1]))
            size = (max(1, int((box[2] - box[0]) * k)), max(1, int((box[3] - box[1]) * k)))
            zoom = (base.crop(box).resize(size, Image.LANCZOS), plain_both.crop(box).resize(size, Image.LANCZOS))

    # --- ghép lưới 2 cột
    cf = font(17)
    cells = [caption(base, "1. ẢNH GỐC: vật thật là gì?", cf),
             caption(both, "2. CHỒNG CẢ HAI: viền màu có nằm gọn trong khung đỏ?", cf),
             caption(det_img, "3. DETECTION (khung đỏ D#)", cf),
             caption(pan_img, "4. PANOPTIC (tô màu)", cf)]
    if zoom:
        cells += [caption(zoom[0], "5. PHÓNG TO: ảnh gốc", cf), caption(zoom[1], "6. PHÓNG TO: chồng cả hai", cf)]
    head = font(18)
    meta = dv.meta.get(stem, {})
    lines = [f"{stem}   {cand.get('type', '')}   scene={meta.get('scene_id', '?')} job={meta.get('job_id', '?')} "
             f"split={meta.get('split', '?')}   (đỏ = detection, màu khác = panoptic, vàng = bị nghi)"]
    why = cand.get("note") or cand.get("reason")
    if why:
        lines.append(f"validator: {why}")
    if skip:
        lines.append(f"({skip} nhãn quá chật không vẽ chữ được: xem danh sách in ở terminal)")
    if err:
        lines.append(f"!! {err}")
    top = 10 + 26 * len(lines)
    gap = 10
    cw = max(c.width for c in cells)
    rows = [cells[i:i + 2] for i in range(0, len(cells), 2)]
    heights = [max(c.height for c in r) for r in rows]
    canvas = Image.new("RGB", (cw * 2 + gap, top + sum(heights) + gap * (len(rows) - 1)), (25, 25, 25))
    cd = ImageDraw.Draw(canvas)
    for k, t in enumerate(lines):
        cd.text((10, 6 + 26 * k), t, fill=(255, 120, 120) if t.startswith("!!") else (230, 230, 230), font=head)
    y = top
    for r, h in zip(rows, heights):
        for j, c in enumerate(r):
            canvas.paste(c, (j * (cw + gap), y))
        y += h + gap
    return canvas


def describe(dv: Delivery, stem: str) -> str:
    """Danh sách box/segment dạng chữ (in ra terminal)."""
    rows = [f"== {stem}"]
    im_info, ann = dv.pan.get(stem, ({}, {"segments_info": []}))
    W, H = im_info.get("width", 0), im_info.get("height", 0)
    for b in dv.boxes(stem):
        x, y, w, h = b["xywh"]
        rows.append(f"  D{b['idx']:<3} {b['name']:<16} box px=({(x - w / 2) * W:.0f},{(y - h / 2) * H:.0f},{w * W:.0f},{h * H:.0f})")
    for s in ann.get("segments_info", []):
        cat = dv.cats.get(s["category_id"], {})
        if not cat.get("isthing"):
            continue
        rows.append(f"  P{s['id']:<9} {cat.get('name', '?'):<16} bbox={s['bbox']} area={s['area']}"
                    + (" crowd" if s.get("iscrowd") else ""))
    return "\n".join(rows)


# ---------------------------------------------------------------- hàng đợi + trang review

def load_candidates(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else (data.get("candidates") or data.get("errors") or [])
    out = []
    for c in items:
        stem = Path(str(c.get("target") or c.get("image") or "")).stem
        if stem:
            c = {**c, "target": stem, "type": c.get("type", "")}
            if "segment" not in c:  # lấy "(id 123456)" trong reason/note nếu validator ghi ở đó
                ids = re.findall(r"\bid\s*(\d+)", str(c.get("reason") or c.get("note") or ""))
                if ids:
                    c["segment"] = [int(i) for i in ids]
            out.append(c)
    return out


def write_html(out_dir: Path, rows: list[dict]) -> Path:
    data = json.dumps(rows, ensure_ascii=False)
    page = PAGE.replace("__DATA__", data).replace("__TITLE__", html.escape(out_dir.resolve().as_posix()))
    p = out_dir / "index.html"
    p.write_text(page, encoding="utf-8")
    return p


PAGE = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review ảnh</title>
<style>
:root{--bg:#16181c;--card:#22252b;--fg:#e8e8e8;--muted:#9aa0a6;--ok:#2fbf71;--no:#e5484d;--line:#33363d}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Arial}
header{position:sticky;top:0;z-index:5;background:#0f1013;border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
header b{font-size:16px} select,button,input,textarea{font:inherit;color:var(--fg);background:#2b2e35;border:1px solid var(--line);border-radius:6px;padding:6px 8px}
button{cursor:pointer} button.primary{background:#2d6cdf;border-color:#2d6cdf}
main{padding:16px;display:grid;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.card.done-confirmed{border-color:var(--ok)} .card.done-rejected{border-color:var(--no)}
.card img{width:100%;height:auto;border-radius:6px;cursor:zoom-in;background:#000}
.card img.big{cursor:zoom-out;width:auto;max-width:none}
.imgwrap{overflow:auto}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:8px}
textarea{width:100%;min-height:54px;box-sizing:border-box}
.muted{color:var(--muted)} .warn{color:#ffb020} .tag{padding:2px 8px;border-radius:99px;background:#33363d}
label.v{padding:4px 10px;border-radius:6px;border:1px solid var(--line)}
</style></head><body>
<header>
 <b>Review ảnh</b><span class="muted" id="count"></span>
 <label>Người xem: <select id="who"><option value="">(tất cả)</option></select></label>
 <label><input type="checkbox" id="todo"> chỉ ảnh chưa xem</label>
 <button class="primary" id="dl">Tải review_log.csv</button>
 <span class="muted">Mở CSV bằng VS Code/Notepad. KHÔNG lưu bằng Excel (mất số 0 đầu tên ảnh, hỏng dấu).</span>
 <span class="warn" id="warn"></span>
</header>
<main id="list"></main>
<script>
const ROWS = __DATA__;
const KEY = "review:" + "__TITLE__";
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const id = r => r.target + "|" + r.type;
const who = document.getElementById("who"), list = document.getElementById("list");
[...new Set(ROWS.map(r => r.reviewer).filter(Boolean))].forEach(n => who.add(new Option(n, n)));
function draw() {
  list.innerHTML = "";
  const onlyTodo = document.getElementById("todo").checked;
  ROWS.forEach(r => {
    const s = state[id(r)] || {};
    if (who.value && r.reviewer !== who.value) return;
    if (onlyTodo && s.verdict) return;
    const c = document.createElement("div");
    c.className = "card" + (s.verdict ? " done-" + s.verdict : "");
    c.innerHTML = `<div class="row"><b>${r.target}</b><span class="tag">${r.type || "(xem)"}</span>
      <span class="muted">${r.reviewer ? "người xem: " + r.reviewer : ""}</span>
      <span class="muted">${r.why || ""}</span></div>
      <div class="imgwrap"><img loading="lazy" src="${r.png}" alt="${r.target}"></div>
      <div class="row">
        <label class="v"><input type="radio" name="v${r.i}" value="confirmed"> confirmed (đúng là lỗi)</label>
        <label class="v"><input type="radio" name="v${r.i}" value="rejected"> rejected (lệch tự nhiên)</label>
        <select class="t"></select>
      </div>
      <textarea placeholder="Thấy gì trong ảnh? vd: xe tải thùng kín, detection D2 ghi car; panoptic ghi truck đúng (>= 20 ký tự)"></textarea>
      <div class="row muted n"></div>`;
    const img = c.querySelector("img"); img.onclick = () => img.classList.toggle("big");
    const t = c.querySelector("select.t");
    ["class_swap","bbox_drift","missing_box","category_swap","instance_merge"].forEach(x => t.add(new Option(x, x)));
    const first = (r.type || "").split("/")[0];
    t.value = s.type || (t.querySelector(`option[value="${first}"]`) ? first : "class_swap");
    c.querySelectorAll("input[type=radio]").forEach(x => { x.checked = x.value === s.verdict; });
    const ta = c.querySelector("textarea"); ta.value = s.note || "";
    const n = c.querySelector(".n");
    const upd = () => {
      const v = c.querySelector("input[type=radio]:checked");
      state[id(r)] = { verdict: v ? v.value : "", note: ta.value.replace(/\s+/g, " ").trim(), type: t.value };
      c.className = "card" + (v ? " done-" + v.value : "");
      n.textContent = ta.value.trim().length < 20 ? `ghi chú ${ta.value.trim().length}/20 ký tự` : "";
      save(); stats();
    };
    c.addEventListener("change", upd); ta.addEventListener("input", upd); upd();
    list.appendChild(c);
  });
  stats();
}
function stats() {
  const done = ROWS.filter(r => (state[id(r)] || {}).verdict).length;
  document.getElementById("count").textContent = `${done}/${ROWS.length} đã xem`;
}
const q = v => /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
document.getElementById("dl").onclick = () => {
  const out = [["image","type","verdict","note","reviewer"]], short = [], seen = new Set(), dup = [];
  ROWS.forEach(r => {
    const s = state[id(r)]; if (!s || !s.verdict) return;
    if (s.note.length < 20) short.push(r.target);
    if (seen.has(s.note)) dup.push(r.target); seen.add(s.note);
    out.push([r.target, s.type, s.verdict, s.note, r.reviewer || ""]);
  });
  const w = [];
  if (short.length) w.push(`${short.length} ghi chú < 20 ký tự`);
  if (dup.length) w.push(`${dup.length} ghi chú trùng nhau`);
  document.getElementById("warn").textContent = w.join(" · ");
  const blob = new Blob([out.map(r => r.map(q).join(",")).join("\n") + "\n"], { type: "text/csv" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "review_log.csv"; a.click();
};
who.onchange = draw; document.getElementById("todo").onchange = draw;
draw();
</script></body></html>
"""


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Vẽ box detection + viền panoptic lên ảnh để review")
    ap.add_argument("delivery", help="thư mục delivery")
    ap.add_argument("images", nargs="*", help="tên ảnh (có/không đuôi)")
    ap.add_argument("--candidates", help="candidates.json do validator sinh ra")
    ap.add_argument("--scene", action="append", help="xem mọi ảnh của một cảnh (lặp lại được)")
    ap.add_argument("--all", action="store_true", help="vẽ toàn bộ lô (chậm, dùng khi tìm ảnh có mặt người...)")
    ap.add_argument("--semantic-only", action="store_true", help="chỉ lấy ứng viên lỗi gán nhãn trong candidates")
    ap.add_argument("--assign", help='chia hàng đợi lần lượt cho các người, vd "Tung,Huong,Viet,Huynh,Khanh"')
    ap.add_argument("--stuff", action="store_true", help="vẽ cả segment nền (trời, đường...)")
    ap.add_argument("--out", help="thư mục ảnh ra (mặc định <delivery>/../review_out)")
    ap.add_argument("--quiet", action="store_true", help="không in danh sách box/segment")
    args = ap.parse_args()

    dv = Delivery(Path(args.delivery))
    out_dir = Path(args.out) if args.out else Path(args.delivery).resolve().parent / "review_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    queue: list[dict] = []
    if args.candidates:
        queue += load_candidates(Path(args.candidates))
        if args.semantic_only:
            queue = [c for c in queue if c["type"] in SEMANTIC]
    for name in args.images:
        queue.append({"target": Path(name).stem, "type": ""})
    for sc in args.scene or []:
        queue += [{"target": s, "type": ""} for s, m in sorted(dv.meta.items()) if m.get("scene_id") == sc]
    if args.all:
        queue += [{"target": s, "type": ""} for s in dv.stems()]
    if not queue:
        ap.error("chưa chọn ảnh: đưa tên ảnh, --scene, --candidates hoặc --all")

    # gộp các mục cùng ảnh (mỗi ảnh mang nhiều nhất một lỗi): một thẻ, một người xem
    merged: dict[str, dict] = {}
    for c in queue:
        m = merged.get(c["target"])
        if m is None:
            merged[c["target"]] = {**c, "types": [c["type"]] if c["type"] else [],
                                   "whys": [str(c.get("reason") or c.get("note") or "")]}
            continue
        if c["type"] and c["type"] not in m["types"]:
            m["types"].append(c["type"])
        m["whys"].append(str(c.get("reason") or c.get("note") or ""))
        for k in ("box", "segment"):
            if c.get(k) is not None:
                m[k] = as_list(m.get(k)) + as_list(c[k])
    queue = []
    for m in merged.values():
        m["type"] = "/".join(m["types"])
        m["note"] = " | ".join(w for w in dict.fromkeys(m["whys"]) if w)
        m.pop("reason", None)
        queue.append(m)

    people = [p.strip() for p in (args.assign or "").split(",") if p.strip()]
    rows = []
    for i, c in enumerate(queue):
        stem = c["target"]
        if stem not in dv.manifest and stem not in dv.pan:
            print(f"[bỏ qua] {stem}: không có trong lô (scene_leak? tên sai?)", file=sys.stderr)
            continue
        png = out_dir / f"{stem}__{(c['type'] or 'xem').replace('/', '+')}.png"
        render(dv, stem, c, args.stuff).save(png)
        if not args.quiet:
            print(describe(dv, stem))
        rows.append({"i": i, "target": stem, "type": c["type"], "png": png.name,
                     "why": str(c.get("note") or c.get("reason") or ""),
                     "reviewer": people[len(rows) % len(people)] if people else ""})
        print(f"  -> {png}")
    page = write_html(out_dir, rows)
    if people:
        with (out_dir / "phan_cong.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["image", "type", "reviewer"])
            w.writerows([r["target"], r["type"], r["reviewer"]] for r in rows)
    print(f"\n{len(rows)} ảnh. Mở trang review: {page.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
