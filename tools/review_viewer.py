#!/usr/bin/env python3
"""Công cụ xem ảnh trực quan và tổng hợp review_log.csv cho Phần 2 (REV-07, REV-08).

Lưu ý tuân thủ RULES.md:
- File này nằm NGOÀI thư mục validator/ nên ĐƯỢC dùng Pillow để vẽ box/mask hỗ trợ con người xem ảnh.
- KHÔNG tự động sinh verdict/note bằng AI; mọi kết luận confirmed/rejected đều do thành viên tự nhìn ảnh điền.

Cách dùng:
  1) Tạo bộ ảnh overlay + crop phóng to + trang duyệt index.html (chia đều cho 4 thành viên):
     py tools/review_viewer.py build --delivery runs/r3007/delivery --candidates runs/r3007/candidates.json --out runs/r3007/review_viz --members 4

  2) Gộp các file CSV review của 4 thành viên và kiểm tra quy tắc H3 (note >= 20 ký tự, >= 70% khác nhau):
     py tools/review_viewer.py merge runs/r3007/m1.csv runs/r3007/m2.csv runs/r3007/m3.csv runs/r3007/m4.csv --out runs/r3007/review_log.csv
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import metrics  # noqa: E402
import pngutil  # noqa: E402


def _require_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise SystemExit(
            "Công cụ xem ảnh cần Pillow. Cài đặt bằng: py -m pip install pillow"
        ) from exc
    return Image, ImageDraw, ImageFont


def _load_font(ImageFont, size: int = 14):
    for candidate in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_classes(delivery: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            out[int(parts[0])] = parts[1].strip()
    return out


def _load_yolo_px(label_path: Path, width: int, height: int, classes: dict[int, str]) -> list[tuple[str, list[float]]]:
    if not label_path.is_file():
        return []
    boxes: list[tuple[str, list[float]]] = []
    for raw in label_path.read_text(encoding="utf-8").splitlines():
        parts = raw.strip().split()
        if len(parts) < 5:
            continue
        try:
            cid = int(float(parts[0]))
            xc, yc, bw, bh = map(float, parts[1:5])
        except ValueError:
            continue
        name = classes.get(cid, f"cls_{cid}")
        boxes.append((name, [(xc - bw / 2) * width, (yc - bh / 2) * height, (xc + bw / 2) * width, (yc + bh / 2) * height]))
    return boxes


def _draw_badge(draw, xy: tuple[float, float], text: str, bg: tuple[int, int, int, int], font) -> None:
    x, y = int(max(2, xy[0])), int(max(2, xy[1]))
    bbox = draw.textbbox((x, y), text, font=font)
    pad = 3
    draw.rectangle([bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad], fill=bg)
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)


def _highlight_segment(
    base_rgba,
    mask_path: Path,
    seg_id: int | None,
    pan_bbox: list[float] | None,
    Image,
):
    """Tô phủ bán trong suốt + viền sắc nét quanh đúng pixel của segment panoptic."""
    if seg_id is None or not mask_path.is_file():
        return base_rgba.copy()

    w, h, pixels = pngutil.read_rgb(mask_path)
    target = pngutil.segment_rgb(int(seg_id))
    r_ch, g_ch, b_ch = pixels[0::3], pixels[1::3], pixels[2::3]

    # Chỉ quét quanh pan_bbox (+2px biên) để render cực nhanh
    max_w = min(w, base_rgba.size[0])
    max_h = min(h, base_rgba.size[1])
    if pan_bbox:
        x1 = max(0, int(pan_bbox[0]) - 2)
        y1 = max(0, int(pan_bbox[1]) - 2)
        x2 = min(max_w, int(pan_bbox[2]) + 3)
        y2 = min(max_h, int(pan_bbox[3]) + 3)
    else:
        x1, y1, x2, y2 = 0, 0, max_w, max_h

    roi_w = max(0, x2 - x1)
    roi_h = max(0, y2 - y1)
    if roi_w == 0 or roi_h == 0:
        return base_rgba.copy()

    grid = [bytearray(roi_w) for _ in range(roi_h)]
    tr, tg, tb = target
    for ry in range(roi_h):
        off = (y1 + ry) * w + x1
        row = grid[ry]
        for rx in range(roi_w):
            idx = off + rx
            if r_ch[idx] == tr and g_ch[idx] == tg and b_ch[idx] == tb:
                row[rx] = 1

    overlay = Image.new("RGBA", base_rgba.size, (0, 0, 0, 0))
    px_out = overlay.load()
    fill_col = (0, 195, 255, 95)
    edge_col = (0, 245, 255, 255)

    for ry in range(roi_h):
        row = grid[ry]
        up = grid[ry - 1] if ry > 0 else None
        dn = grid[ry + 1] if ry + 1 < roi_h else None
        py = y1 + ry
        for rx in range(roi_w):
            if not row[rx]:
                continue
            is_edge = (
                rx == 0
                or rx + 1 == roi_w
                or ry == 0
                or ry + 1 == roi_h
                or not row[rx - 1]
                or not row[rx + 1]
                or (up is not None and not up[rx])
                or (dn is not None and not dn[rx])
            )
            px_out[x1 + rx, py] = edge_col if is_edge else fill_col

    return Image.alpha_composite(base_rgba, overlay)


def _compute_crop_box(
    det_boxes: list[list[float]],
    pan_bbox: list[float] | None,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    rects = list(det_boxes)
    if pan_bbox:
        rects.append(pan_bbox)
    if not rects:
        return 0, 0, width, height
    x1 = min(r[0] for r in rects)
    y1 = min(r[1] for r in rects)
    x2 = max(r[2] for r in rects)
    y2 = max(r[3] for r in rects)
    bw = max(16.0, x2 - x1)
    bh = max(16.0, y2 - y1)
    pad_x = max(24.0, bw * 0.35)
    pad_y = max(24.0, bh * 0.35)
    cx1 = max(0, int(x1 - pad_x))
    cy1 = max(0, int(y1 - pad_y))
    cx2 = min(width, int(x2 + pad_x))
    cy2 = min(height, int(y2 + pad_y))
    return cx1, cy1, max(cx1 + 1, cx2), max(cy1 + 1, cy2)


def _upscale_if_small(img, min_long_side: int = 380, Image=None):
    w, h = img.size
    longest = max(w, h)
    if longest >= min_long_side or longest == 0:
        return img
    scale = min(4.0, min_long_side / longest)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BICUBIC)


def _assign_members(candidates: list[dict[str, Any]], num_members: int) -> list[int]:
    """Chia đều ứng viên cho N thành viên, giữ các ứng viên cùng 1 ảnh về chung 1 người."""
    num_members = max(1, num_members)
    counts = [0] * num_members
    by_img: dict[str, list[int]] = {}
    for idx, cand in enumerate(candidates):
        by_img.setdefault(cand["image"], []).append(idx)

    assigned = [1] * len(candidates)
    for stem in sorted(by_img.keys()):
        target_member = min(range(num_members), key=lambda m: counts[m])
        for idx in by_img[stem]:
            assigned[idx] = target_member + 1
            counts[target_member] += 1
    return assigned


def _render_html(
    delivery: Path,
    cand_doc: dict[str, Any],
    items_for_ui: list[dict[str, Any]],
    num_members: int,
) -> str:
    payload_json = json.dumps(items_for_ui, ensure_ascii=False)
    summary = cand_doc.get("summary", {})
    storage_key = f"day10_review::{delivery.resolve().as_posix()}"
    member_buttons = "\n".join(
        f'<button class="tab" data-member="{m}">Thành viên {m}</button>'
        for m in range(1, num_members + 1)
    )
    template = r"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review Workbench | __TITLE__</title>
<style>
  :root { --bg:#f4f7f6; --card:#fff; --ink:#172a2e; --muted:#566d70; --line:#d8e3e0; --accent:#087b69; --red:#d93025; --cyan:#008fb3; --warn:#b26a00; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 'Segoe UI',Arial,sans-serif; background:var(--bg); color:var(--ink); }
  header { position:sticky; top:0; z-index:20; background:#fff; border-bottom:1px solid var(--line); padding:12px 20px; }
  .bar { max-width:1440px; margin:auto; display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between; }
  .title { font-weight:800; font-size:1.05rem; }
  .legend { display:flex; gap:12px; font-size:.86rem; color:var(--muted); flex-wrap:wrap; }
  .dot { display:inline-block; width:11px; height:11px; border-radius:2px; vertical-align:-1px; margin-right:5px; }
  .controls { max-width:1440px; margin:14px auto; padding:0 20px; display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
  .tab { border:1px solid var(--line); background:#fff; padding:6px 12px; border-radius:6px; cursor:pointer; font-weight:600; color:var(--ink); }
  .tab.active { background:var(--accent); color:#fff; border-color:var(--accent); }
  .btn { border:1px solid var(--accent); background:var(--accent); color:#fff; padding:7px 14px; border-radius:6px; cursor:pointer; font-weight:700; }
  input[type=text], select, textarea { font:inherit; border:1px solid #c3d3cf; border-radius:6px; padding:6px 9px; background:#fff; }
  main { max-width:1440px; margin:0 auto 60px; padding:0 20px; display:grid; gap:18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; }
  .card.done-confirmed { border-left:5px solid var(--red); }
  .card.done-rejected { border-left:5px solid var(--accent); }
  .head { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; margin-bottom:10px; }
  .badge { font-size:.78rem; font-weight:700; padding:3px 8px; border-radius:999px; background:#e8f3ef; color:var(--accent); }
  .badge.warn { background:#fff3dc; color:var(--warn); }
  .reason { font-size:.92rem; color:#2b4246; margin:4px 0 12px; }
  .imgs { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin-bottom:12px; }
  .imgbox { border:1px solid var(--line); border-radius:8px; padding:8px; background:#fafcfb; text-align:center; }
  .imgbox span { display:block; font-size:.78rem; color:var(--muted); margin-bottom:6px; font-weight:700; }
  .imgbox img { max-width:100%; max-height:340px; object-fit:contain; cursor:zoom-in; border-radius:4px; }
  .form { display:grid; grid-template-columns:220px 230px 1fr; gap:12px; align-items:start; border-top:1px solid var(--line); padding-top:12px; }
  .verdict-row { display:flex; gap:6px; }
  .vbtn { flex:1; border:1px solid var(--line); background:#fff; padding:7px 8px; border-radius:6px; cursor:pointer; font-weight:700; }
  .vbtn.on-confirmed { background:#d93025; color:#fff; border-color:#d93025; }
  .vbtn.on-rejected { background:#087b69; color:#fff; border-color:#087b69; }
  .counter { font-size:.8rem; margin-top:4px; font-weight:600; }
  .counter.bad { color:var(--red); }
  .counter.ok { color:var(--accent); }
  .hint { font-size:.8rem; color:var(--muted); margin-top:4px; }
  #lightbox { display:none; position:fixed; inset:0; background:rgba(0,0,0,.85); z-index:99; align-items:center; justify-content:center; padding:24px; cursor:zoom-out; }
  #lightbox img { max-width:95vw; max-height:92vh; border-radius:6px; }
  @media (max-width:960px) { .imgs, .form { grid-template-columns:1fr; } }
</style>
</head>
<body>
<header>
  <div class="bar">
    <div>
      <div class="title">Day 10 · Review bằng mắt (Phần 2) — __TOTAL_CANDS__ ứng viên / __UNIQUE_IMGS__ ảnh</div>
      <div class="legend">
        <span><i class="dot" style="background:#ff3b30"></i>Box Detection (YOLO) #1</span>
        <span><i class="dot" style="background:#ffcc00"></i>Box Detection #2 (nếu merge)</span>
        <span><i class="dot" style="background:#00d8ff"></i>Mask + viền Panoptic</span>
        <span><b>Lưu ý:</b> Tự nhìn ảnh gốc trước khi chọn verdict; mỗi ghi chú ≥ 20 ký tự.</span>
      </div>
    </div>
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
      <input type="text" id="reviewerName" placeholder="Tên người xem (vd: HaKhanh)" style="width:190px">
      <button class="btn" id="exportCsv">Tải review_log.csv</button>
    </div>
  </div>
</header>

<div class="controls">
  <button class="tab active" data-member="all">Tất cả</button>
  __MEMBER_BUTTONS__
  <select id="typeFilter">
    <option value="all">Mọi nhóm dấu hiệu</option>
    <option value="class_swap/category_swap">class_swap / category_swap</option>
    <option value="bbox_drift">bbox_drift</option>
    <option value="missing_box">missing_box</option>
    <option value="instance_merge">instance_merge</option>
  </select>
  <label style="display:flex;align-items:center;gap:6px;font-size:.9rem;"><input type="checkbox" id="onlyPending"> Chỉ hiện chưa review</label>
  <span id="progressStat" style="margin-left:auto;font-weight:700;color:var(--accent);"></span>
</div>

<main id="list"></main>
<div id="lightbox"><img id="lbImg" alt="zoom"></div>

<script>
const ITEMS = __PAYLOAD_JSON__;
const STORAGE_KEY = __STORAGE_KEY__;
const SEMANTIC_TYPES = ["class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge"];

let state = { reviewer: "", reviews: {} };
try {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  if (saved && typeof saved === "object") state = saved;
} catch (e) {}

const reviewerInput = document.getElementById("reviewerName");
reviewerInput.value = state.reviewer || "";
reviewerInput.addEventListener("input", () => {
  state.reviewer = reviewerInput.value.trim();
  saveState();
});

let activeMember = "all";
const typeFilter = document.getElementById("typeFilter");
const onlyPending = document.getElementById("onlyPending");

function saveState() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) {}
  updateProgress();
}

function updateProgress() {
  let done = 0, conf = 0, rej = 0;
  for (const it of ITEMS) {
    const r = state.reviews[it.candidate_id];
    if (r && r.verdict) {
      done++;
      if (r.verdict === "confirmed") conf++;
      if (r.verdict === "rejected") rej++;
    }
  }
  document.getElementById("progressStat").textContent =
    `Đã review: ${done}/${ITEMS.length} (confirmed: ${conf}, rejected: ${rej})`;
}

function csvEscape(v) {
  const s = String(v ?? "");
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function escHtml(v) {
  return String(v ?? "").replace(/[&<>"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
}

function render() {
  const root = document.getElementById("list");
  root.innerHTML = "";
  const tf = typeFilter.value;
  const pend = onlyPending.checked;

  for (const it of ITEMS) {
    if (activeMember !== "all" && String(it.assigned_member) !== activeMember) continue;
    const suggKey = it.suggested_types.join("/");
    if (tf !== "all" && suggKey !== tf) continue;
    const rev = state.reviews[it.candidate_id] || {
      type: it.suggested_types.length === 1 ? it.suggested_types[0] : "",
      verdict: "",
      note: ""
    };
    if (pend && rev.verdict) continue;

    const card = document.createElement("section");
    card.className = "card" + (rev.verdict ? " done-" + rev.verdict : "");
    const warnHtml = (it.warnings && it.warnings.length)
      ? `<span class="badge warn">⚠ ${escHtml(it.warnings.join(", "))}</span>` : "";

    const optsHtml = ['<option value="">-- Chọn loại lỗi sau khi nhìn ảnh --</option>']
      .concat(SEMANTIC_TYPES.map(t =>
        `<option value="${t}" ${rev.type === t ? "selected" : ""}>${t}${it.suggested_types.includes(t) ? " (gợi ý)" : ""}</option>`
      )).join("");

    const swapTip = it.suggested_types.length > 1
      ? `<div class="hint">Nhìn ảnh thật: <b>Detection sai → class_swap</b> · <b>Panoptic sai → category_swap</b></div>`
      : "";

    card.innerHTML = `
      <div class="head">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <strong>${escHtml(it.candidate_id)}</strong>
          <code>${escHtml(it.image)}</code>
          <span class="badge">Thành viên ${it.assigned_member}</span>
          <span class="badge">${escHtml(suggKey)}</span>
          ${warnHtml}
        </div>
        <div style="font-size:.84rem;color:var(--muted);">
          DET: <b>${escHtml(it.det_class ?? "—")}</b> · PAN: <b>${escHtml(it.pan_class ?? "—")}</b>
        </div>
      </div>
      <div class="reason">${escHtml(it.reason)}</div>
      <div class="imgs">
        <div class="imgbox"><span>1. Ảnh gốc (crop quanh vật)</span><img src="${it.img_crop_orig}" alt="orig"></div>
        <div class="imgbox"><span>2. Overlay DET (đỏ) vs PAN (xanh) — crop</span><img src="${it.img_crop_overlay}" alt="overlay"></div>
        <div class="imgbox"><span>3. Toàn ảnh (overlay)</span><img src="${it.img_full}" alt="full"></div>
      </div>
      <div class="form">
        <div>
          <label style="font-size:.82rem;font-weight:700;display:block;margin-bottom:4px;">Loại lỗi (type)</label>
          <select class="f-type" style="width:100%">${optsHtml}</select>
          ${swapTip}
        </div>
        <div>
          <label style="font-size:.82rem;font-weight:700;display:block;margin-bottom:4px;">Kết luận bằng mắt (verdict)</label>
          <div class="verdict-row">
            <button type="button" class="vbtn ${rev.verdict === "confirmed" ? "on-confirmed" : ""}" data-v="confirmed">confirmed</button>
            <button type="button" class="vbtn ${rev.verdict === "rejected" ? "on-rejected" : ""}" data-v="rejected">rejected</button>
            <button type="button" class="vbtn" data-v="">Xóa</button>
          </div>
        </div>
        <div>
          <label style="font-size:.82rem;font-weight:700;display:block;margin-bottom:4px;">Ghi chú quan sát (nói rõ thấy gì + ai xem, ≥ 20 ký tự)</label>
          <textarea class="f-note" rows="2" style="width:100%" placeholder="Vd: HaKhanh xem: xe tải mui kín, detection ghi car sai, panoptic ghi truck đúng"></textarea>
          <div class="counter"></div>
        </div>
      </div>
    `;

    card.querySelectorAll(".imgs img").forEach(im => {
      im.addEventListener("click", () => {
        document.getElementById("lbImg").src = im.src;
        document.getElementById("lightbox").style.display = "flex";
      });
    });

    const typeSel = card.querySelector(".f-type");
    const noteEl = card.querySelector(".f-note");
    const cntEl = card.querySelector(".counter");
    noteEl.value = rev.note || "";

    function syncCounter() {
      const n = noteEl.value.trim().length;
      cntEl.textContent = n >= 20 ? `${n} ký tự (đạt ≥ 20)` : `${n}/20 ký tự (cần thêm ${20 - n} ký tự để đạt H3)`;
      cntEl.className = "counter " + (n >= 20 ? "ok" : "bad");
    }
    syncCounter();

    function upsert(patch) {
      const cur = state.reviews[it.candidate_id] || {
        type: typeSel.value,
        verdict: rev.verdict,
        note: noteEl.value
      };
      state.reviews[it.candidate_id] = Object.assign({}, cur, patch);
      saveState();
    }

    typeSel.addEventListener("change", () => upsert({ type: typeSel.value }));
    noteEl.addEventListener("input", () => { syncCounter(); upsert({ note: noteEl.value }); });
    card.querySelectorAll(".vbtn").forEach(btn => {
      btn.addEventListener("click", () => {
        const v = btn.dataset.v;
        upsert({ verdict: v, type: typeSel.value, note: noteEl.value });
        render();
      });
    });

    root.appendChild(card);
  }
  updateProgress();
}

document.querySelectorAll(".tab[data-member]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab[data-member]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeMember = btn.dataset.member;
    render();
  });
});
typeFilter.addEventListener("change", render);
onlyPending.addEventListener("change", render);
document.getElementById("lightbox").addEventListener("click", () => {
  document.getElementById("lightbox").style.display = "none";
});

document.getElementById("exportCsv").addEventListener("click", () => {
  const lines = ["image,type,verdict,note"];
  const problems = [];
  const reviewer = reviewerInput.value.trim();

  for (const it of ITEMS) {
    if (activeMember !== "all" && String(it.assigned_member) !== activeMember) continue;
    const r = state.reviews[it.candidate_id];
    if (!r || !r.verdict) continue;
    if (!SEMANTIC_TYPES.includes(r.type)) {
      problems.push(`${it.candidate_id} (${it.image}): chưa chọn đúng loại lỗi (type).`);
      continue;
    }
    let note = (r.note || "").trim();
    if (reviewer && !note.toLowerCase().includes(reviewer.toLowerCase())) {
      note = `${reviewer} xem: ${note}`;
    }
    if (note.length < 20) {
      problems.push(`${it.candidate_id} (${it.image}): ghi chú mới có ${note.length} ký tự (< 20).`);
    }
    lines.push([it.image, r.type, r.verdict, note].map(csvEscape).join(","));
  }

  if (problems.length) {
    alert("Cần bổ sung trước khi chốt CSV:\n- " + problems.slice(0, 8).join("\n- "));
    return;
  }
  if (lines.length === 1) {
    alert("Chưa có dòng nào được chọn verdict trong bộ lọc hiện tại.");
    return;
  }
  const blob = new Blob([lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = activeMember === "all" ? "review_log.csv" : `review_log_member${activeMember}.csv`;
  a.click();
});

render();
</script>
</body>
</html>
"""
    return (
        template
        .replace("__TITLE__", html.escape(delivery.name))
        .replace("__TOTAL_CANDS__", str(summary.get("total_candidates", len(items_for_ui))))
        .replace("__UNIQUE_IMGS__", str(summary.get("unique_candidate_images", 0)))
        .replace("__MEMBER_BUTTONS__", member_buttons)
        .replace("__PAYLOAD_JSON__", payload_json)
        .replace("__STORAGE_KEY__", json.dumps(storage_key))
    )


def cmd_build(args: argparse.Namespace) -> int:
    Image, ImageDraw, ImageFont = _require_pillow()
    delivery = Path(args.delivery)
    cand_doc = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    candidates = cand_doc.get("candidates", [])
    out_dir = Path(args.out)
    img_dir = out_dir / "imgs"
    img_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]
    classes = _load_classes(delivery)
    font = _load_font(ImageFont, size=14)
    assigned = _assign_members(candidates, args.members)

    ui_items: list[dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        stem = cand["image"]
        cid = cand.get("candidate_id") or f"C{idx + 1:03d}"
        item = manifest.get(stem)
        if not item:
            continue
        jpg_path = delivery / item["image"]
        if not jpg_path.is_file():
            continue
        label_path = delivery / item["label"]
        mask_path = delivery / item["mask"]

        orig = Image.open(jpg_path).convert("RGBA")
        w, h = orig.size

        # Vẽ mask panoptic nghi ngờ (phủ bán trong suốt + viền xanh ngọc)
        overlay = _highlight_segment(
            orig,
            mask_path=mask_path,
            seg_id=cand.get("pan_segment_id"),
            pan_bbox=cand.get("pan_bbox_px"),
            Image=Image,
        )
        draw = ImageDraw.Draw(overlay)

        # Vẽ mờ các box detection khác để có bối cảnh
        for cls_name, box in _load_yolo_px(label_path, w, h, classes):
            draw.rectangle(box, outline=(220, 220, 220, 140), width=1)

        # Vẽ panoptic bbox nét mảnh + nhãn PAN
        pan_bbox = cand.get("pan_bbox_px")
        if pan_bbox:
            draw.rectangle(pan_bbox, outline=(0, 230, 255, 220), width=2)
            if cand.get("pan_class"):
                _draw_badge(draw, (pan_bbox[0], pan_bbox[3] - 20), f"PAN: {cand['pan_class']}", (0, 125, 165, 230), font)

        # Vẽ detection box nghi ngờ (đỏ cho box #1, vàng cho box #2 nếu là instance_merge)
        det_boxes = cand.get("det_boxes_px") or []
        palette = [(255, 59, 48, 255), (255, 204, 0, 255)]
        for bi, box in enumerate(det_boxes):
            col = palette[min(bi, len(palette) - 1)]
            draw.rectangle(box, outline=col, width=3)
            tag = f"DET#{bi + 1}: {cand.get('det_class')}" if len(det_boxes) > 1 else f"DET: {cand.get('det_class')}"
            bg = (200, 35, 28, 235) if bi == 0 else (180, 130, 0, 235)
            _draw_badge(draw, (box[0], box[1] - 20), tag, bg, font)

        crop_box = _compute_crop_box(det_boxes, pan_bbox, w, h)
        crop_orig = _upscale_if_small(orig.crop(crop_box).convert("RGB"), Image=Image)
        crop_ov = _upscale_if_small(overlay.crop(crop_box).convert("RGB"), Image=Image)
        full_ov = overlay.convert("RGB")

        f_crop_orig = f"imgs/{cid}_crop_orig.png"
        f_crop_ov = f"imgs/{cid}_crop_overlay.png"
        f_full = f"imgs/{cid}_full.png"
        crop_orig.save(out_dir / f_crop_orig)
        crop_ov.save(out_dir / f_crop_ov)
        full_ov.save(out_dir / f_full)

        ui_items.append(
            {
                "candidate_id": cid,
                "image": stem,
                "assigned_member": assigned[idx],
                "suggested_types": cand.get("suggested_types", []),
                "reason": cand.get("reason", ""),
                "det_class": cand.get("det_class"),
                "pan_class": cand.get("pan_class"),
                "warnings": cand.get("warnings", []),
                "img_crop_orig": f_crop_orig,
                "img_crop_overlay": f_crop_ov,
                "img_full": f_full,
            }
        )

    index_path = out_dir / "index.html"
    index_path.write_text(_render_html(delivery, cand_doc, ui_items, args.members), encoding="utf-8")
    print(f"Đã tạo {len(ui_items)} thẻ review (chia {args.members} thành viên) -> {index_path}")
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    """Gộp các file review_log.csv từ nhiều thành viên và kiểm tra tiêu chuẩn H3."""
    valid_types = set(metrics.SEMANTIC_TYPES)
    valid_verdicts = {"confirmed", "rejected"}
    rows: list[dict[str, str]] = []
    seen: dict[tuple[str, str], dict[str, str]] = {}
    errors: list[str] = []
    warnings: list[str] = []

    for p_str in args.inputs:
        path = Path(p_str)
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            expected = {"image", "type", "verdict", "note"}
            if not reader.fieldnames or not expected.issubset(set(reader.fieldnames)):
                errors.append(f"{path}: thiếu cột bắt buộc {sorted(expected)}")
                continue
            for line_no, raw in enumerate(reader, start=2):
                image = (raw.get("image") or "").strip()
                kind = (raw.get("type") or "").strip()
                verdict = (raw.get("verdict") or "").strip()
                note = (raw.get("note") or "").strip()
                if not image and not kind and not verdict and not note:
                    continue
                if kind not in valid_types:
                    errors.append(f"{path}:{line_no}: type '{kind}' không thuộc {sorted(valid_types)}")
                if verdict not in valid_verdicts:
                    errors.append(f"{path}:{line_no}: verdict '{verdict}' phải là confirmed hoặc rejected")
                if len(note) < 20:
                    errors.append(f"{path}:{line_no} ({image}): ghi chú chỉ có {len(note)} ký tự (< 20 ký tự theo H3)")
                key = (image, kind)
                row = {"image": image, "type": kind, "verdict": verdict, "note": note}
                if key in seen:
                    if seen[key]["verdict"] != verdict:
                        errors.append(f"Mâu thuẫn verdict cho {key}: '{seen[key]['verdict']}' vs '{verdict}'")
                    else:
                        warnings.append(f"Trùng dòng {key} ở {path}:{line_no} (giữ bản đầu)")
                    continue
                seen[key] = row
                rows.append(row)

    # Kiểm tra trùng ảnh confirmed (trong lab mỗi ảnh tối đa 1 lỗi)
    conf_by_img: dict[str, list[str]] = {}
    for row in rows:
        if row["verdict"] == "confirmed":
            conf_by_img.setdefault(row["image"], []).append(row["type"])
    for img, kinds in conf_by_img.items():
        if len(kinds) > 1:
            warnings.append(f"Ảnh {img} có >1 lỗi confirmed ({kinds}) — cần kiểm tra lại (lab: tối đa 1 lỗi/ảnh)")

    # Kiểm tra tỷ lệ ghi chú duy nhất >= 70% như check_handover.py H3
    if rows:
        unique_ratio = len({r["note"] for r in rows}) / len(rows)
        if unique_ratio < 0.7:
            errors.append(
                f"Tỷ lệ ghi chú khác nhau là {unique_ratio:.0%} (< 70% theo H3) — cần viết ghi chú cụ thể từng ảnh"
            )

    for w in warnings:
        print(f"[CẢNH BÁO] {w}")
    if errors:
        for e in errors:
            print(f"[LỖI H3] {e}")
        return 1

    rows.sort(key=lambda r: (r["image"], r["type"]))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "type", "verdict", "note"])
        writer.writeheader()
        writer.writerows(rows)

    n_conf = sum(1 for r in rows if r["verdict"] == "confirmed")
    n_rej = sum(1 for r in rows if r["verdict"] == "rejected")
    print(f"Đạt kiểm tra H3: {len(rows)} dòng ({n_conf} confirmed, {n_rej} rejected) -> {out_path}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Công cụ xem ảnh review và gộp review_log.csv (Phần 2)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Tạo ảnh overlay/crop + trang index.html cho nhóm xem ảnh")
    b.add_argument("--delivery", required=True, help="Thư mục delivery/")
    b.add_argument("--candidates", required=True, help="File candidates.json")
    b.add_argument("--out", required=True, help="Thư mục xuất ảnh + index.html (nên đặt trong runs/)")
    b.add_argument("--members", type=int, default=4, help="Số thành viên chia hàng đợi (mặc định 4)")

    m = sub.add_parser("merge", help="Gộp các file review CSV của từng thành viên và kiểm tra quy tắc H3")
    m.add_argument("inputs", nargs="+", help="Các file CSV từng phần")
    m.add_argument("--out", required=True, help="File review_log.csv tổng hợp")

    args = ap.parse_args()
    if args.cmd == "build":
        return cmd_build(args)
    return cmd_merge(args)


if __name__ == "__main__":
    raise SystemExit(main())
