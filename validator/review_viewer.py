#!/usr/bin/env python3
"""Tạo trang HTML trực quan hóa các ảnh ứng viên (Detection vs Panoptic) để nhóm review bằng mắt.

  python validator/review_viewer.py runs/r7007/delivery --candidates runs/r7007/candidates.json --out runs/r7007/review_viewer.html

Chỉ dùng thư viện chuẩn Python (không cần cài Pillow). Mở file HTML bằng Chrome/Edge để xem
box Detection, box Panoptic, phóng to ảnh nhỏ, ghi nhận xét (>= 20 ký tự) và xuất review_log.csv.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import struct
from collections import defaultdict
from pathlib import Path


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
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


def _load_classes(path: Path) -> dict[int, str]:
    classes: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].lstrip("-").isdigit():
            classes[int(parts[0])] = parts[1].strip()
    return classes


def _load_yolo_boxes(label_path: Path, w: int, h: int, classes: dict[int, str]) -> list[dict]:
    if not label_path.is_file():
        return []
    boxes = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            cid = int(parts[0])
            xc, yc, bw, bh = (float(v) for v in parts[1:5])
        except ValueError:
            continue
        boxes.append({
            "label": classes.get(cid, f"class_{cid}"),
            "x": round((xc - bw / 2) * w, 1),
            "y": round((yc - bh / 2) * h, 1),
            "w": round(bw * w, 1),
            "h": round(bh * h, 1),
        })
    return boxes


def _build_cards(delivery: Path, candidates_path: Path) -> list[dict]:
    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]
    classes = _load_classes(delivery / "classes.txt")
    pan = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    categories = {c["id"]: c for c in pan["categories"]}
    pan_images = {Path(i["file_name"]).stem: i for i in pan["images"]}
    pan_ann = {Path(a["file_name"]).stem: a for a in pan["annotations"]}
    raw_cands = json.loads(candidates_path.read_text(encoding="utf-8")).get("candidates", [])

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in raw_cands:
        grouped[item["image"]].append(item)

    cards = []
    for stem, items in sorted(grouped.items()):
        m_item = manifest.get(stem, {})
        img_path = delivery / m_item.get("image", f"images/{stem}.jpg")
        img_bytes = img_path.read_bytes() if img_path.is_file() else b""
        p_info = pan_images.get(stem, {})
        size = (int(p_info["width"]), int(p_info["height"])) if p_info.get("width") and p_info.get("height") else _jpeg_size(img_bytes)
        w, h = size or (640, 480)

        lbl_path = delivery / m_item.get("label", f"labels/{stem}.txt")
        det_boxes = _load_yolo_boxes(lbl_path, w, h, classes)

        ann = pan_ann.get(stem, {})
        pan_boxes = []
        for s in ann.get("segments_info", []):
            cat = categories.get(s.get("category_id"), {})
            if not cat.get("isthing") or s.get("iscrowd"):
                continue
            bx, by, bw, bh = s["bbox"]
            pan_boxes.append({
                "label": cat.get("name", "?"),
                "area": s.get("area", 0),
                "x": bx,
                "y": by,
                "w": bw,
                "h": bh,
            })

        b64 = base64.b64encode(img_bytes).decode("ascii") if img_bytes else ""
        cards.append({
            "image": stem,
            "width": w,
            "height": h,
            "data_uri": f"data:image/jpeg;base64,{b64}" if b64 else "",
            "candidates": items,
            "det_boxes": det_boxes,
            "pan_boxes": pan_boxes,
        })
    return cards


def render_html(cards: list[dict], title: str) -> str:
    payload = json.dumps(cards, ensure_ascii=False)
    safe_title = html.escape(title)
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>{safe_title}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }}
  header {{ position: sticky; top: 0; z-index: 20; background: #1e293b; border-bottom: 1px solid #334155; padding: 12px 20px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }}
  .controls {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  button {{ background: #334155; color: #f8fafc; border: 1px solid #475569; border-radius: 6px; padding: 7px 12px; cursor: pointer; font-weight: 600; }}
  button:hover {{ background: #475569; }}
  button.primary {{ background: #2563eb; border-color: #3b82f6; }}
  button.primary:hover {{ background: #1d4ed8; }}
  main {{ max-width: 1280px; margin: 20px auto; padding: 0 16px 60px; display: grid; gap: 20px; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; display: grid; grid-template-columns: minmax(320px, 1.4fr) 1fr; gap: 16px; }}
  @media (max-width: 900px) {{ .card {{ grid-template-columns: 1fr; }} }}
  .stage {{ position: relative; background: #020617; border-radius: 8px; overflow: auto; display: flex; justify-content: center; align-items: flex-start; padding: 8px; }}
  .svg-wrap {{ position: relative; display: inline-block; transform-origin: top left; }}
  svg {{ display: block; max-width: 100%; height: auto; }}
  .zoomed svg {{ max-width: none; }}
  .legend {{ display: flex; gap: 14px; font-size: 13px; margin-bottom: 6px; }}
  .dot-det {{ color: #fb7185; font-weight: 700; }}
  .dot-pan {{ color: #22d3ee; font-weight: 700; }}
  .cand-box {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 12px; margin-bottom: 10px; }}
  .badge {{ display: inline-block; background: #f59e0b; color: #0f172a; font-weight: 700; font-size: 12px; padding: 2px 8px; border-radius: 999px; margin-right: 6px; }}
  label {{ display: block; font-size: 13px; margin: 8px 0 4px; color: #cbd5e1; }}
  select, input[type="text"], textarea {{ width: 100%; box-sizing: border-box; background: #1e293b; color: #f8fafc; border: 1px solid #475569; border-radius: 6px; padding: 7px 9px; font-size: 13px; }}
  .char-ok {{ color: #4ade80; font-size: 12px; }}
  .char-bad {{ color: #f87171; font-size: 12px; }}
  .boxes-list {{ font-size: 12px; color: #94a3b8; margin-top: 8px; line-height: 1.5; }}
</style>
</head>
<body>
<header>
  <div>
    <strong>{safe_title}</strong>
    <div style="font-size:12px;color:#94a3b8;">Đỏ đứt nét = Detection (YOLO) · Xanh liền = Panoptic (thing) · Note ≥ 20 ký tự nói rõ thấy gì</div>
  </div>
  <div class="controls">
    <button onclick="toggleLayer('det')">Bật/Tắt Detection</button>
    <button onclick="toggleLayer('pan')">Bật/Tắt Panoptic</button>
    <button onclick="toggleZoom()">Phóng to / Vừa khung</button>
    <button class="primary" onclick="exportCsv()">Xuất review_log.csv</button>
  </div>
</header>
<main id="app"></main>
<script>
const CARDS = {payload};
let showDet = true, showPan = true, zoomed = false;

function esc(s) {{
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}}

function render() {{
  const app = document.getElementById("app");
  if (!CARDS.length) {{
    app.innerHTML = "<p>Không có ứng viên nào trong candidates.json.</p>";
    return;
  }}
  app.innerHTML = CARDS.map((card, ci) => {{
    const detSvg = card.det_boxes.map(b => `
      <g class="layer-det">
        <rect x="${{b.x}}" y="${{b.y}}" width="${{b.w}}" height="${{b.h}}" fill="none" stroke="#fb7185" stroke-width="2.5" stroke-dasharray="6,3"/>
        <rect x="${{b.x}}" y="${{Math.max(0, b.y - 18)}}" width="${{b.label.length * 7 + 34}}" height="18" fill="#be123c" opacity="0.88"/>
        <text x="${{b.x + 4}}" y="${{Math.max(13, b.y - 5)}}" fill="#fff" font-size="12" font-family="monospace">det:${{esc(b.label)}}</text>
      </g>`).join("");
    const panSvg = card.pan_boxes.map(b => `
      <g class="layer-pan">
        <rect x="${{b.x}}" y="${{b.y}}" width="${{b.w}}" height="${{b.h}}" fill="none" stroke="#22d3ee" stroke-width="2"/>
        <rect x="${{b.x}}" y="${{b.y + b.h}}" width="${{b.label.length * 7 + 34}}" height="18" fill="#0e7490" opacity="0.88"/>
        <text x="${{b.x + 4}}" y="${{b.y + b.h + 13}}" fill="#fff" font-size="12" font-family="monospace">pan:${{esc(b.label)}}</text>
      </g>`).join("");

    const candForms = card.candidates.map((c, ki) => {{
      const isSwap = c.type === "class_or_category_swap";
      const typeOpts = isSwap
        ? `<option value="class_swap">class_swap (detection sai)</option><option value="category_swap">category_swap (panoptic sai)</option>`
        : `<option value="${{esc(c.type)}}">${{esc(c.type)}}</option>`;
      return `
        <div class="cand-box" data-image="${{esc(card.image)}}" id="cand-${{ci}}-${{ki}}">
          <div><span class="badge">${{esc(c.type)}}</span><strong>${{esc(card.image)}}</strong></div>
          <div style="font-size:12px;color:#cbd5e1;margin-top:4px;">Gợi ý: ${{esc(c.note)}}</div>
          <label>Loại lỗi cuối (nếu confirmed):</label>
          <select class="f-type">${{typeOpts}}</select>
          <label>Kết luận:</label>
          <select class="f-verdict">
            <option value="confirmed">confirmed (đúng là lỗi)</option>
            <option value="rejected">rejected (lệch tự nhiên COCO)</option>
          </select>
          <label>Ghi chú thấy gì trong ảnh (≥ 20 ký tự):</label>
          <textarea class="f-note" rows="2" placeholder="Ví dụ: mở ảnh thấy ..., detection ghi ..., panoptic ghi ..." oninput="updateCount(this)"></textarea>
          <div class="char-bad f-count">0 / 20 ký tự</div>
        </div>`;
    }}).join("");

    return `
      <section class="card">
        <div>
          <div class="legend">
            <span>Ảnh: <strong>${{esc(card.image)}}</strong> (${{card.width}}×${{card.height}})</span>
            <span class="dot-det">--- Detection (${{card.det_boxes.length}})</span>
            <span class="dot-pan">— Panoptic (${{card.pan_boxes.length}})</span>
          </div>
          <div class="stage">
            <div class="svg-wrap">
              <svg viewBox="0 0 ${{card.width}} ${{card.height}}" width="${{card.width}}" height="${{card.height}}">
                <image href="${{card.data_uri}}" width="${{card.width}}" height="${{card.height}}"/>
                ${{panSvg}}
                ${{detSvg}}
              </svg>
            </div>
          </div>
          <div class="boxes-list">
            <strong>Det:</strong> ${{card.det_boxes.map(b => esc(b.label)).join(", ") || "không có"}}<br>
            <strong>Pan:</strong> ${{card.pan_boxes.map(b => `${{esc(b.label)}}(${{b.area}})`).join(", ") || "không có"}}
          </div>
        </div>
        <div>${{candForms}}</div>
      </section>`;
  }}).join("");
}}

function toggleLayer(name) {{
  if (name === "det") showDet = !showDet;
  if (name === "pan") showPan = !showPan;
  document.querySelectorAll(".layer-det").forEach(el => el.style.display = showDet ? "" : "none");
  document.querySelectorAll(".layer-pan").forEach(el => el.style.display = showPan ? "" : "none");
}}

function toggleZoom() {{
  zoomed = !zoomed;
  document.querySelectorAll(".stage").forEach(el => el.classList.toggle("zoomed", zoomed));
}}

function updateCount(el) {{
  const len = el.value.trim().length;
  const c = el.parentElement.querySelector(".f-count");
  c.textContent = `${{len}} / 20 ký tự`;
  c.className = (len >= 20 ? "char-ok" : "char-bad") + " f-count";
}}

function csvCell(v) {{
  const s = String(v ?? "");
  return /[",\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}}

function exportCsv() {{
  const rows = ["image,type,verdict,note"];
  let shortNotes = 0;
  document.querySelectorAll(".cand-box").forEach(box => {{
    const image = box.dataset.image;
    const type = box.querySelector(".f-type").value;
    const verdict = box.querySelector(".f-verdict").value;
    const note = box.querySelector(".f-note").value.trim();
    if (note.length < 20) shortNotes++;
    rows.push([image, type, verdict, note].map(csvCell).join(","));
  }});
  if (shortNotes > 0 && !confirm(`Có ${{shortNotes}} dòng ghi chú dưới 20 ký tự (check_handover H3 sẽ FAIL). Vẫn tải xuống?`)) return;
  const blob = new Blob([rows.join("\\n") + "\\n"], {{type: "text/csv;charset=utf-8"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "review_log.csv";
  a.click();
}}

render();
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh trang HTML xem ảnh ứng viên để review bằng mắt")
    ap.add_argument("delivery", help="Thư mục delivery")
    ap.add_argument("--candidates", required=True, help="File candidates.json")
    ap.add_argument("--out", required=True, help="File HTML đầu ra")
    args = ap.parse_args()

    cards = _build_cards(Path(args.delivery), Path(args.candidates))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(cards, f"Review Viewer - {Path(args.delivery).parent.name}"), encoding="utf-8")
    print(f"Đã tạo {out_path} ({len(cards)} ảnh cần xem)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
