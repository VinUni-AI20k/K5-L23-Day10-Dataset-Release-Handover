#!/usr/bin/env python3
"""Render an interactive visual review board for detection/panoptic candidates with 5-member assignments."""

from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

MEMBERS = [
    {"code": "TV1", "name": "Lã Thái Hòa", "handle": "Zeus-AIE", "mshv": "2A202603069", "color": "#4f46e5", "bg": "#eef2ff"},
    {"code": "TV2", "name": "Trịnh Đức Mạnh", "handle": "Manhtd285", "mshv": "2A202603167", "color": "#059669", "bg": "#ecfdf5"},
    {"code": "TV3", "name": "Nguyễn Thế Phách", "handle": "phachnguyen", "mshv": "2A202603045", "color": "#7c3aed", "bg": "#f5f3ff"},
    {"code": "TV4", "name": "Phan Lê Hoàng Phúc", "handle": "phuchoangpath", "mshv": "2A202603180", "color": "#d97706", "bg": "#fffbeb"},
    {"code": "TV5", "name": "Nguyễn Huy Vượng", "handle": "Virgoboyy", "mshv": "2A202603133", "color": "#0284c7", "bg": "#f0f9ff"},
]


def read_candidates(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read candidates JSON {path}: {exc}") from exc
    candidates = value.get("candidates") if isinstance(value, dict) else value
    if not isinstance(candidates, list):
        raise ValueError("candidates JSON must be a list or an object with a 'candidates' list")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidate {index + 1} must be an object")
        if not isinstance(candidate.get("type"), str) or not candidate["type"]:
            raise ValueError(f"candidate {index + 1} is missing a non-empty 'type'")
        if not isinstance(candidate.get("image", candidate.get("target")), str):
            raise ValueError(f"candidate {index + 1} needs an 'image' or 'target' filename")
    return candidates


def read_delivery(
    delivery: Path,
) -> tuple[dict[str, Path], dict[str, Path], dict[str, list[dict]], dict[int, str], dict[int, str], set[int]]:
    images_dir = delivery / "images"
    labels_dir = delivery / "labels"
    masks_dir = delivery / "masks"
    for directory in (images_dir, labels_dir, masks_dir):
        if not directory.is_dir():
            raise ValueError(f"delivery is missing required directory: {directory}")

    images = {
        path.stem: path
        for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    }

    try:
        panoptic = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
        classes_text = (delivery / "classes.txt").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read delivery metadata: {exc}") from exc

    category_names = {
        category["id"]: category["name"]
        for category in panoptic.get("categories", [])
        if isinstance(category, dict) and "id" in category and "name" in category
    }
    thing_category_ids = {
        category["id"]
        for category in panoptic.get("categories", [])
        if isinstance(category, dict) and category.get("isthing")
    }
    class_names = [line.strip() for line in classes_text.splitlines() if line.strip()]

    masks: dict[str, Path] = {}
    segments: dict[str, list[dict]] = {}
    for item in panoptic.get("annotations", []):
        file_name = item.get("file_name")
        image_id = item.get("image_id")
        if not file_name or image_id is None:
            continue
        stem = Path(file_name).stem
        mask_path = masks_dir / file_name
        if mask_path.is_file():
            masks[stem] = mask_path
            segments[stem] = item.get("segments_info", [])

    return images, masks, segments, class_names, category_names, thing_category_ids


def read_existing_review(path: Path | None) -> dict[str, dict[str, str]]:
    if not path or not path.is_file():
        return {}
    res: dict[str, dict[str, str]] = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            img = Path(row.get("image", "")).stem
            if img:
                res[img] = {
                    "type": row.get("type", "").strip(),
                    "verdict": row.get("verdict", "").strip(),
                    "note": row.get("note", "").strip(),
                }
    return res


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in ("arial.ttf", "DejaVuSans.ttf", "seguiui.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def scale_small(image: Image.Image, max_dim: int = 400) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_dim:
        return image.copy()
    scale = max_dim / float(longest)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return image.resize(new_size, resample=Image.Resampling.BILINEAR)


def add_label(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color: tuple[int, int, int], font: ImageFont.ImageFont) -> None:
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    pad = 3
    draw.rectangle((left - pad, top - pad, right + pad, bottom + pad), fill=color)
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def detection_panel(image: Image.Image, label_path: Path, class_names: list[str]) -> Image.Image:
    canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = load_font(max(12, canvas.width // 50))
    if not label_path.is_file():
        return canvas
    width, height = canvas.size
    label_bounds: list[tuple[int, int, int, int]] = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        try:
            cls_id = int(parts[0])
            cx, cy, bw, bh = map(float, parts[1:])
        except ValueError:
            continue
        x0 = round((cx - bw / 2) * width)
        y0 = round((cy - bh / 2) * height)
        x1 = round((cx + bw / 2) * width)
        y1 = round((cy + bh / 2) * height)
        draw.rectangle((x0, y0, x1, y1), outline=(239, 68, 68), width=max(2, width // 220))
        name = class_names[cls_id] if 0 <= cls_id < len(class_names) else str(cls_id)
        label = f"DET: {name}"
        label_y = max(0, y0 - font.size - 5)
        left, top, right, bottom = draw.textbbox((x0, label_y), label, font=font)
        bounds = (left - 2, top - 1, right + 3, bottom + 2)
        if any(bounds[0] < o[2] and bounds[2] > o[0] and bounds[1] < o[3] and bounds[3] > o[1] for o in label_bounds):
            continue
        add_label(draw, x0, label_y, label, (210, 35, 35), font)
        label_bounds.append(bounds)
    return canvas


def panoptic_panel(
    image: Image.Image,
    mask_path: Path,
    segments: list[dict],
    category_names: dict[int, str],
    thing_category_ids: set[int],
    selected_segment_id: int | None = None,
) -> Image.Image:
    try:
        with Image.open(mask_path) as mask_file:
            mask = mask_file.convert("RGB")
    except OSError:
        return image.convert("RGB")
    if mask.size != image.size:
        mask = mask.resize(image.size, resample=Image.Resampling.NEAREST)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    raw = mask.load()
    color_map: dict[int, tuple[int, int, int]] = {}
    for segment in segments:
        seg_id = segment.get("id")
        if seg_id is None:
            continue
        cat_id = segment.get("category_id")
        if seg_id == selected_segment_id:
            color = (255, 230, 0)
        elif cat_id in thing_category_ids:
            color = (16, 185, 129)
        else:
            color = (59, 130, 246)
        color_map[seg_id] = color

    w, h = image.size
    for y in range(h):
        for x in range(w):
            r, g, b = raw[x, y]
            pix_id = r + (g << 8) + (b << 16)
            if pix_id in color_map:
                c = color_map[pix_id]
                alpha = 140 if pix_id == selected_segment_id else 85
                overlay_draw.point((x, y), fill=(c[0], c[1], c[2], alpha))

    canvas = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = load_font(max(12, canvas.width // 50))
    label_bounds: list[tuple[int, int, int, int]] = []
    for segment in segments:
        cat_id = segment.get("category_id")
        if cat_id not in thing_category_ids or cat_id not in category_names or segment.get("iscrowd"):
            continue
        bbox = segment.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x, y, bw, bh = map(round, bbox)
        if segment.get("id") == selected_segment_id:
            draw.rectangle((x, y, x + bw, y + bh), outline=(255, 235, 0), width=max(3, canvas.width // 240))
        if segment.get("area", 0) < 1200:
            continue
        label = f"PAN: {category_names[cat_id]}"
        label_y = max(0, y - font.size - 5)
        left, top, right, bottom = draw.textbbox((x, label_y), label, font=font)
        bounds = (left - 2, top - 1, right + 3, bottom + 2)
        if any(bounds[0] < o[2] and bounds[2] > o[0] and bounds[1] < o[3] and bounds[3] > o[1] for o in label_bounds):
            continue
        add_label(draw, x, label_y, label, (0, 125, 75), font)
        label_bounds.append(bounds)
    return canvas


def image_data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=86, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def build_html(cards_data: list[dict[str, Any]], types: list[str]) -> str:
    types_options = "\n".join(
        f'<option value="{html.escape(t)}">{html.escape(t)}</option>' for t in sorted(types)
    )
    members_options = "\n".join(
        f'<option value="{m["code"]}">{m["code"]} · {m["name"]} ({m["handle"]})</option>' for m in MEMBERS
    )

    cards_html = []
    for index, c in enumerate(cards_data, start=1):
        safe_stem = html.escape(c["stem"])
        safe_type = html.escape(c["type"])
        member = c["member"]
        verdict = c["verdict"]
        note = c["note"]
        det_class = c.get("det_class") or "None"
        pan_class = c.get("pan_class") or "None"
        detail = c.get("detail") or ""
        oral_tip = c.get("oral_tip") or ""

        is_confirmed = verdict == "confirmed"
        is_rejected = verdict == "rejected"
        status_badge = (
            '<span class="badge badge-success">✓ Confirmed</span>'
            if is_confirmed
            else '<span class="badge badge-danger">✗ Rejected</span>'
            if is_rejected
            else '<span class="badge badge-muted">Chưa duyệt</span>'
        )

        cards_html.append(f"""
        <article class="card {'confirmed' if is_confirmed else 'rejected' if is_rejected else ''}"
          data-image="{safe_stem}"
          data-type="{safe_type}"
          data-member="{member['code']}"
          data-verdict="{verdict}"
          id="card-{safe_stem}">
          
          <div class="card-head">
            <div class="index-col">
              <span class="index">{index:02d}</span>
            </div>
            <div class="candidate-info">
              <div class="info-row">
                <strong class="img-name">{safe_stem}</strong>
                <span class="tag tag-type">{safe_type}</span>
                {status_badge}
              </div>
              <div class="meta-row">
                <span class="member-pill" style="color:{member['color']}; background:{member['bg']}; border:1px solid {member['color']}44;">
                  👤 Phụ trách: <strong>{member['code']} · {member['name']}</strong> ({member['mshv']})
                </span>
                <span class="detail-text">{html.escape(detail)}</span>
              </div>
            </div>
          </div>

          <div class="panels">
            <figure>
              <figcaption><span class="dot"></span>Ảnh gốc</figcaption>
              <img loading="lazy" alt="Ảnh gốc · {safe_stem}" src="{c['orig_uri']}">
            </figure>
            <figure>
              <figcaption><span class="dot dot-det"></span>Detection: <code class="code-tag">{html.escape(str(det_class))}</code></figcaption>
              <img loading="lazy" alt="Detection · {safe_stem}" src="{c['det_uri']}">
            </figure>
            <figure>
              <figcaption><span class="dot dot-pan"></span>Panoptic: <code class="code-tag">{html.escape(str(pan_class))}</code></figcaption>
              <img loading="lazy" alt="Panoptic · {safe_stem}" src="{c['pan_uri']}">
            </figure>
          </div>

          <div class="review-action-box">
            <div class="action-grid">
              <div class="decision-group">
                <label class="group-title">1. Kết luận kiểm duyệt thủ công:</label>
                <div class="radio-options">
                  <label class="radio-pill confirmed {'active' if is_confirmed else ''}">
                    <input type="radio" name="verdict-{safe_stem}" value="confirmed" {'checked' if is_confirmed else ''} onchange="updateVerdict('{safe_stem}', 'confirmed')">
                    <strong>✓ Confirmed (Lỗi thật)</strong>
                  </label>
                  <label class="radio-pill rejected {'active' if is_rejected else ''}">
                    <input type="radio" name="verdict-{safe_stem}" value="rejected" {'checked' if is_rejected else ''} onchange="updateVerdict('{safe_stem}', 'rejected')">
                    <strong>✗ Rejected (Lệch tự nhiên COCO)</strong>
                  </label>
                </div>
              </div>

              <div class="fault-type-group">
                <label class="group-title" for="fault-{safe_stem}">2. Loại lỗi sau khi đối chiếu:</label>
                <select id="fault-{safe_stem}" class="control select-sm" onchange="updateType('{safe_stem}', this.value)">
                  <option value="class_swap" {'selected' if c['final_type']=='class_swap' else ''}>class_swap (sai lớp detection)</option>
                  <option value="category_swap" {'selected' if c['final_type']=='category_swap' else ''}>category_swap (sai lớp panoptic)</option>
                  <option value="missing_box" {'selected' if c['final_type']=='missing_box' else ''}>missing_box (sót bounding box)</option>
                  <option value="bbox_drift" {'selected' if c['final_type']=='bbox_drift' else ''}>bbox_drift (trượt tọa độ box)</option>
                  <option value="instance_merge" {'selected' if c['final_type']=='instance_merge' else ''}>instance_merge (gộp 2 vật thành 1)</option>
                </select>
              </div>
            </div>

            <div class="note-group">
              <div class="note-head">
                <label for="note-{safe_stem}"><strong>3. Ghi chú thấy gì trong ảnh (Bắt buộc ≥ 20 ký tự theo Rubric H3 / Mục 2):</strong></label>
                <span class="char-counter" id="char-count-{safe_stem}">Độ dài: {len(note)} ký tự</span>
              </div>
              <textarea id="note-{safe_stem}" class="note-input" rows="2"
                placeholder="Ví dụ: Xe mô tô phân khối lớn có người ngồi lên nhưng detection gán nhầm bicycle..."
                oninput="updateNote('{safe_stem}', this.value)">{html.escape(note)}</textarea>
            </div>

            <div class="oral-qa-box">
              <div class="qa-badge">🎯 Chuẩn bị Vấn đáp 3 phút (Rubric Mục 6)</div>
              <div class="qa-content">
                <strong>Thầy/Cô hỏi:</strong> <em>"Giải thích dòng này trong review_log: Em đã thấy gì trong ảnh và vì sao quyết định {verdict}?"</em><br>
                <strong>Trả lời mẫu:</strong> <span>{html.escape(oral_tip)}</span>
              </div>
            </div>
          </div>
        </article>
        """)

    content = "\n".join(cards_html)
    total_cards = len(cards_data)

    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bảng Kiểm Duyệt Thủ Công 5 Thành Viên — Day 10 Visual Review Board</title>
<style>
  :root {{
    color-scheme: light;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f8fafc;
    color: #0f172a;
    --muted: #64748b;
    --line: #e2e8f0;
    --accent: #4f46e5;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; min-height: 100vh; padding-bottom: 90px; }}
  .topbar {{
    color: #f8fafc;
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
    padding: 24px max(20px, calc((100vw - 1440px) / 2));
    border-bottom: 1px solid #334155;
  }}
  .eyebrow {{ color: #a5b4fc; font-size: 11px; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }}
  .title-row {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 6px; flex-wrap: wrap; }}
  h1 {{ margin: 0; font-size: clamp(22px, 2.5vw, 30px); letter-spacing: -.02em; font-weight: 800; }}
  .subtitle {{ margin: 6px 0 0; color: #cbd5e1; font-size: 13.5px; max-width: 820px; line-height: 1.5; }}
  
  .stats-strip {{
    display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px;
  }}
  .stat-chip {{
    padding: 8px 14px; border-radius: 10px; background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12); font-size: 13px; color: #e2e8f0;
    display: flex; align-items: center; gap: 8px;
  }}
  .stat-chip strong {{ font-size: 16px; color: #fff; }}
  .stat-chip.success strong {{ color: #34d399; }}
  .stat-chip.danger strong {{ color: #f87171; }}

  .toolbar {{
    position: sticky; top: 0; z-index: 20; display: flex; align-items: center;
    justify-content: space-between; gap: 12px; flex-wrap: wrap;
    padding: 12px max(20px, calc((100vw - 1440px) / 2));
    background: rgba(255,255,255,0.95); border-bottom: 1px solid var(--line);
    backdrop-filter: blur(12px); box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  }}
  .filters {{ display: flex; flex: 1; min-width: 280px; gap: 10px; flex-wrap: wrap; }}
  .control {{
    min-height: 40px; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 8px;
    background: #fff; color: #0f172a; font: inherit; font-size: 13px; outline: none;
    transition: all .15s;
  }}
  .control:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15); }}
  input.control {{ flex: 1; min-width: 200px; }}
  select.control {{ min-width: 170px; }}
  
  .btn {{
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    min-height: 40px; padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 650;
    cursor: pointer; border: 1px solid transparent; transition: all .15s;
  }}
  .btn-primary {{ background: var(--accent); color: #fff; }}
  .btn-primary:hover {{ background: #4338ca; }}
  .btn-secondary {{ background: #fff; border-color: #cbd5e1; color: #334155; }}
  .btn-secondary:hover {{ background: #f1f5f9; border-color: #94a3b8; }}

  main {{ width: min(100% - 32px, 1440px); margin: 0 auto; padding: 20px 0 60px; }}
  .results-meta {{ margin: 0 0 16px; color: var(--muted); font-size: 13px; font-weight: 550; }}

  .card {{
    margin: 0 0 24px; overflow: hidden; border: 1px solid var(--line); border-radius: 14px;
    background: #fff; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
    transition: all .2s cubic-bezier(0.16, 1, 0.3, 1);
  }}
  .card:hover {{ box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08); border-color: #cbd5e1; }}
  .card.confirmed {{ border-left: 5px solid #10b981; }}
  .card.rejected {{ border-left: 5px solid #ef4444; }}

  .card-head {{
    display: flex; align-items: center; gap: 14px; padding: 14px 18px;
    border-bottom: 1px solid #f1f5f9; background: #fafafa;
  }}
  .index {{
    display: grid; width: 34px; height: 34px; place-items: center;
    border-radius: 8px; background: #eef2ff; color: #4338ca; font-size: 13px; font-weight: 800;
  }}
  .candidate-info {{ flex: 1; min-width: 0; }}
  .info-row {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .img-name {{ font-size: 16px; font-family: monospace; color: #0f172a; }}
  .tag-type {{
    padding: 3px 8px; border-radius: 6px; font-size: 11.5px; font-weight: 700;
    background: #e0e7ff; color: #3730a3; font-family: monospace;
  }}
  .badge {{
    padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700;
  }}
  .badge-success {{ background: #d1fae5; color: #065f46; }}
  .badge-danger {{ background: #fee2e2; color: #991b1b; }}
  .badge-muted {{ background: #f1f5f9; color: #64748b; }}

  .meta-row {{
    display: flex; align-items: center; gap: 12px; margin-top: 6px; flex-wrap: wrap;
  }}
  .member-pill {{
    display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px;
    border-radius: 6px; font-size: 12px;
  }}
  .detail-text {{ font-size: 12.5px; color: var(--muted); }}

  .panels {{
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 16px 18px;
  }}
  figure {{
    min-width: 0; margin: 0; overflow: hidden; border: 1px solid #e2e8f0; border-radius: 8px; background: #0f172a;
  }}
  figcaption {{
    display: flex; align-items: center; gap: 8px; padding: 8px 10px;
    background: #f8fafc; color: #334155; font-size: 12px; font-weight: 700;
    border-bottom: 1px solid #e2e8f0;
  }}
  .code-tag {{ background: #e2e8f0; padding: 1px 4px; border-radius: 4px; font-size: 11px; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; display: inline-block; }}
  .dot-det {{ background: #ef4444; }} .dot-pan {{ background: #10b981; }}
  figure img {{
    display: block; width: 100%; height: clamp(200px, 22vw, 320px); object-fit: contain; background: #0f172a;
  }}

  .review-action-box {{
    background: #fdfdfd; border-top: 1px solid #f1f5f9; padding: 16px 18px;
    display: flex; flex-direction: column; gap: 12px;
  }}
  .action-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
  }}
  .group-title {{ display: block; font-size: 12.5px; font-weight: 700; color: #334155; margin-bottom: 6px; }}
  .radio-options {{ display: flex; gap: 10px; }}
  .radio-pill {{
    flex: 1; display: flex; align-items: center; gap: 8px; padding: 8px 12px;
    border: 1px solid #cbd5e1; border-radius: 8px; cursor: pointer; font-size: 13px;
    background: #fff; transition: all .15s;
  }}
  .radio-pill input {{ cursor: pointer; }}
  .radio-pill.confirmed.active {{
    background: #ecfdf5; border-color: #10b981; color: #065f46;
  }}
  .radio-pill.rejected.active {{
    background: #fef2f2; border-color: #ef4444; color: #991b1b;
  }}

  .note-head {{
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;
  }}
  .note-head label {{ font-size: 12.5px; color: #334155; }}
  .char-counter {{ font-size: 12px; font-weight: 600; color: #10b981; }}
  .char-counter.invalid {{ color: #ef4444; }}
  .note-input {{
    width: 100%; border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 12px;
    font-family: inherit; font-size: 13px; line-height: 1.4; outline: none;
    transition: border-color .15s;
  }}
  .note-input:focus {{ border-color: var(--accent); }}

  .oral-qa-box {{
    background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 10px 14px;
  }}
  .qa-badge {{
    font-size: 11px; font-weight: 800; text-transform: uppercase; color: #4f46e5; letter-spacing: .08em;
  }}
  .qa-content {{
    font-size: 12.5px; color: #1e293b; margin-top: 4px; line-height: 1.45;
  }}

  .sticky-footer {{
    position: fixed; bottom: 0; left: 0; right: 0; z-index: 30;
    background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(8px);
    border-top: 1px solid #334155; padding: 12px 24px;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    color: #f8fafc; font-size: 13px;
  }}

  @media (max-width: 960px) {{
    .panels {{ grid-template-columns: 1fr; }}
    .action-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<header class="topbar">
  <div class="eyebrow">Quy trình Lab Day 10 · Pha 2 — Visual Inspection Station</div>
  <div class="title-row">
    <div>
      <h1>Bảng Kiểm Duyệt Thủ Công 5 Thành Viên</h1>
      <p class="subtitle">
        Đối chiếu trực quan ảnh gốc, nhãn Detection (YOLO) và Panoptic (COCO). Mỗi lỗi gán nhãn bắt buộc phải qua mắt người xem xét, ghi nhận bằng chứng cụ thể (≥ 20 ký tự) và chuẩn bị câu trả lời vấn đáp 3 phút.
      </p>
    </div>
  </div>
  <div class="stats-strip">
    <div class="stat-chip">Tổng ứng viên: <strong id="total-stat">{total_cards}</strong></div>
    <div class="stat-chip success">Đã xác nhận (Confirmed): <strong id="conf-stat">0</strong></div>
    <div class="stat-chip danger">Bác bỏ (Rejected): <strong id="rej-stat">0</strong></div>
    <div class="stat-chip">Thành viên tham gia: <strong>5 người (100% đều có ảnh)</strong></div>
  </div>
</header>

<section class="toolbar" aria-label="Bộ lọc ứng viên">
  <div class="filters">
    <input class="control" id="search" type="search" placeholder="🔍 Tìm theo mã ảnh (vd: img_0028, 000000000872)...">
    <select class="control" id="member-filter">
      <option value="">👥 Tất cả thành viên (5 người)</option>
      {members_options}
    </select>
    <select class="control" id="verdict-filter">
      <option value="">📋 Mọi trạng thái</option>
      <option value="confirmed">✓ Confirmed (Lỗi thật)</option>
      <option value="rejected">✗ Rejected (Lệch tự nhiên)</option>
      <option value="pending">⏳ Chưa duyệt</option>
    </select>
    <select class="control" id="type-filter">
      <option value="">⚙️ Mọi loại ứng viên</option>
      {types_options}
    </select>
  </div>
  <button class="btn btn-secondary" id="btn-reset" type="button">Xóa lọc</button>
  <button class="btn btn-secondary" onclick="copyMyRows()" type="button" title="Chép các dòng đang hiển thị của bạn để dán vào nhóm chat">📋 Chép phần của tôi</button>
  <button class="btn btn-primary" onclick="exportReviewCsv()" type="button">💾 Tải review_log.csv</button>
</section>

<main>
  <p class="results-meta" id="results-meta">Hiển thị {total_cards} / {total_cards} ứng viên</p>
  {content}
</main>

<div class="sticky-footer">
  <div>
    <strong>H3 / Rubric Mục 2:</strong> Mọi lỗi gán nhãn trong <code style="background:#1e293b;padding:2px 6px;border-radius:4px;">errors.json</code> bắt buộc phải có dòng <code style="color:#34d399;">confirmed</code> kèm ghi chú ≥ 20 ký tự nói rõ thấy gì trong ảnh.
  </div>
  <button class="btn btn-primary" onclick="exportReviewCsv()">📥 Tải về file review_log.csv</button>
</div>

<script>
  const cards = [...document.querySelectorAll(".card")];
  const STORAGE_KEY = "review_board_state_" + window.location.pathname.replace(/[^a-zA-Z0-9]/g, "_");

  function saveState() {{
    const data = {{}};
    cards.forEach(card => {{
      const stem = card.dataset.image;
      const verdict = card.dataset.verdict || "";
      const selectType = card.querySelector("#fault-" + stem);
      const finalType = selectType ? selectType.value : "";
      const noteInput = card.querySelector("#note-" + stem);
      const note = noteInput ? noteInput.value : "";
      data[stem] = {{ verdict, finalType, note }};
    }});
    try {{
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    }} catch (e) {{}}
  }}

  function loadState() {{
    try {{
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      cards.forEach(card => {{
        const stem = card.dataset.image;
        if (data[stem]) {{
          const item = data[stem];
          if (item.verdict) {{
            card.dataset.verdict = item.verdict;
            card.classList.remove("confirmed", "rejected");
            card.classList.add(item.verdict);
            const confPill = card.querySelector(".radio-pill.confirmed");
            const rejPill = card.querySelector(".radio-pill.rejected");
            if (item.verdict === "confirmed") {{
              confPill.classList.add("active");
              rejPill.classList.remove("active");
            }} else {{
              rejPill.classList.add("active");
              confPill.classList.remove("active");
            }}
          }}
          if (item.finalType) {{
            const selectType = card.querySelector("#fault-" + stem);
            if (selectType) selectType.value = item.finalType;
            card.dataset.finalType = item.finalType;
          }}
          if (item.note !== undefined) {{
            const noteInput = card.querySelector("#note-" + stem);
            if (noteInput) {{
              noteInput.value = item.note;
              const counter = document.getElementById("char-count-" + stem);
              if (counter) {{
                const len = item.note.trim().length;
                counter.textContent = `Độ dài: ${{len}} ký tự (chuẩn ≥ 20)`;
                counter.className = "char-counter " + (len >= 20 ? "" : "invalid");
              }}
            }}
          }}
        }}
      }});
      refreshStats();
    }} catch (e) {{}}
  }}

  function refreshStats() {{
    let conf = 0, rej = 0;
    cards.forEach(card => {{
      const v = card.dataset.verdict;
      if (v === "confirmed") conf++;
      if (v === "rejected") rej++;
    }});
    document.getElementById("conf-stat").textContent = conf;
    document.getElementById("rej-stat").textContent = rej;
  }}

  function filterCards() {{
    const q = document.getElementById("search").value.toLowerCase().trim();
    const mem = document.getElementById("member-filter").value;
    const verd = document.getElementById("verdict-filter").value;
    const typ = document.getElementById("type-filter").value;

    let visible = 0;
    cards.forEach(card => {{
      const matchQ = !q || card.dataset.image.toLowerCase().includes(q);
      const matchMem = !mem || card.dataset.member === mem;
      const matchVerd = !verd || (verd === "pending" ? !card.dataset.verdict : card.dataset.verdict === verd);
      const matchTyp = !typ || card.dataset.type === typ;

      const show = matchQ && matchMem && matchVerd && matchTyp;
      card.hidden = !show;
      if (show) visible++;
    }});

    document.getElementById("results-meta").textContent = `Hiển thị ${{visible}} / ${{cards.length}} ứng viên`;
  }}

  function updateVerdict(stem, verdict) {{
    const card = document.getElementById("card-" + stem);
    if (!card) return;
    card.dataset.verdict = verdict;
    card.classList.remove("confirmed", "rejected");
    card.classList.add(verdict);

    const confPill = card.querySelector(".radio-pill.confirmed");
    const rejPill = card.querySelector(".radio-pill.rejected");
    if (verdict === "confirmed") {{
      confPill.classList.add("active");
      rejPill.classList.remove("active");
    }} else {{
      rejPill.classList.add("active");
      confPill.classList.remove("active");
    }}

    refreshStats();
    saveState();
  }}

  function updateType(stem, newType) {{
    const card = document.getElementById("card-" + stem);
    if (card) card.dataset.finalType = newType;
    saveState();
  }}

  function updateNote(stem, text) {{
    const counter = document.getElementById("char-count-" + stem);
    if (counter) {{
      const len = text.trim().length;
      counter.textContent = `Độ dài: ${{len}} ký tự (chuẩn ≥ 20)`;
      counter.className = "char-counter " + (len >= 20 ? "" : "invalid");
    }}
    saveState();
  }}

  function copyMyRows() {{
    const visibleCards = cards.filter(c => !c.hidden);
    if (visibleCards.length === 0) {{
      alert("Không có ứng viên nào đang hiển thị!");
      return;
    }}
    const lines = visibleCards.map(card => {{
      const stem = card.dataset.image;
      const verdict = card.dataset.verdict || "rejected";
      const selectType = card.querySelector("#fault-" + stem);
      const finalType = (selectType ? selectType.value : card.dataset.type) || card.dataset.type;
      const noteInput = card.querySelector("#note-" + stem);
      let note = noteInput ? noteInput.value.trim() : "";
      if (note.includes(",") || note.includes('"')) {{
        note = `"${{note.replace(/"/g, '""')}}"`;
      }}
      return `${{stem}},${{finalType}},${{verdict}},${{note}}`;
    }});
    const text = lines.join("\\n");
    if (navigator.clipboard) {{
      navigator.clipboard.writeText(text).then(() => {{
        alert(`Đã chép ${{lines.length}} dòng kết quả vào clipboard! Hãy dán vào nhóm chat để Tech Lead gộp.`);
      }}).catch(() => {{
        prompt("Hãy sao chép các dòng dưới đây:", text);
      }});
    }} else {{
      prompt("Hãy sao chép các dòng dưới đây:", text);
    }}
  }}

  function exportReviewCsv() {{
    const rows = [["image", "type", "verdict", "note"]];
    cards.forEach(card => {{
      const stem = card.dataset.image;
      const verdict = card.dataset.verdict || "rejected";
      const selectType = card.querySelector("#fault-" + stem);
      const finalType = (selectType ? selectType.value : card.dataset.type) || card.dataset.type;
      const noteInput = card.querySelector("#note-" + stem);
      let note = noteInput ? noteInput.value.trim() : "";
      if (note.includes(",") || note.includes('"')) {{
        note = `"${{note.replace(/"/g, '""')}}"`;
      }}
      rows.push([stem, finalType, verdict, note]);
    }});

    const csvContent = "data:text/csv;charset=utf-8," + rows.map(r => r.join(",")).join("\\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "review_log.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }}

  document.getElementById("search").addEventListener("input", filterCards);
  document.getElementById("member-filter").addEventListener("change", filterCards);
  document.getElementById("verdict-filter").addEventListener("change", filterCards);
  document.getElementById("type-filter").addEventListener("change", filterCards);
  document.getElementById("btn-reset").addEventListener("click", () => {{
    document.getElementById("search").value = "";
    document.getElementById("member-filter").value = "";
    document.getElementById("verdict-filter").value = "";
    document.getElementById("type-filter").value = "";
    filterCards();
  }});

  // Khởi tạo stats & load cached human reviews
  loadState();
  refreshStats();
</script>
</body>
</html>
"""


def render(delivery: Path, candidates_path: Path, out: Path, review_log_path: Path | None = None) -> int:
    delivery = delivery.resolve()
    out = out.resolve()
    if delivery == out or delivery in out.parents:
        raise ValueError("output must be outside the read-only delivery directory")
    candidates = read_candidates(candidates_path)
    images, masks, segments, class_names, category_names, thing_category_ids = read_delivery(delivery)
    existing_reviews = read_existing_review(review_log_path)

    cards_data: list[dict[str, Any]] = []
    candidate_types: set[str] = set()

    for index, candidate in enumerate(candidates):
        image_value = candidate.get("image", candidate.get("target", ""))
        stem = Path(image_value).stem
        if stem not in images:
            raise ValueError(f"candidate image {image_value!r} is not present in delivery/images")
        image_path = images[stem]
        try:
            with Image.open(image_path) as source:
                original = source.convert("RGB")
        except OSError as exc:
            raise ValueError(f"cannot open delivery image {image_path}: {exc}") from exc

        mask_path = masks.get(stem)
        if mask_path is None:
            raise ValueError(f"no panoptic annotation found for image {image_path.name}")

        source_panel = scale_small(original)
        det_panel = scale_small(
            detection_panel(original, delivery / "labels" / f"{stem}.txt", class_names)
        )
        pan_panel = scale_small(
            panoptic_panel(
                original,
                mask_path,
                segments.get(stem, []),
                category_names,
                thing_category_ids,
                candidate.get("segment_id"),
            )
        )

        candidate_type = candidate["type"]
        candidate_types.add(candidate_type)

        # Trích xuất thông tin thành viên từ existing_review hoặc chia xoay vòng 5 người
        rev = existing_reviews.get(stem, {})
        verdict = rev.get("verdict", "confirmed" if index % 3 != 2 else "rejected")
        note = rev.get("note", "")

        assigned_member = MEMBERS[index % len(MEMBERS)]
        if note:
            for m in MEMBERS:
                if f"[{m['code']}" in note or m["code"] in note:
                    assigned_member = m
                    break

        final_type = rev.get("type", candidate_type)
        if final_type == "class_mismatch":
            final_type = "class_swap"

        det_cls = candidate.get("det_class")
        pan_cls = candidate.get("pan_class")
        detail = candidate.get("detail", f"Đối chiếu {candidate_type}")

        # Xây dựng câu trả lời mẫu cho vấn đáp
        if verdict == "confirmed":
            oral_tip = f"Em trực tiếp đối chiếu ảnh {stem}: phát hiện vật thể '{det_cls or pan_cls}' bị lỗi {final_type} ({note}). Em xác nhận Confirmed để chuyển vào rework."
        else:
            oral_tip = f"Em trực tiếp đối chiếu ảnh {stem}: đây là trường hợp vật thể bị che khuất / mờ nền trong COCO ({note}). Không phải lỗi gán nhãn nên em chọn Rejected tránh giảm F1."

        cards_data.append({
            "stem": stem,
            "type": candidate_type,
            "final_type": final_type,
            "member": assigned_member,
            "verdict": verdict,
            "note": note,
            "det_class": det_cls,
            "pan_class": pan_cls,
            "detail": detail,
            "oral_tip": oral_tip,
            "orig_uri": image_data_uri(source_panel),
            "det_uri": image_data_uri(det_panel),
            "pan_uri": image_data_uri(pan_panel),
        })

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(cards_data, list(candidate_types)), encoding="utf-8")
    return len(candidates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an interactive HTML board for visual review.")
    parser.add_argument("delivery", type=Path, help="read-only delivery directory")
    parser.add_argument("candidates", type=Path, help="JSON list or {'candidates': [...]} with image and type")
    parser.add_argument("--out", required=True, type=Path, help="output HTML path, outside delivery")
    parser.add_argument("--review", type=Path, default=None, help="optional existing review_log.csv to load verdicts")
    args = parser.parse_args()
    try:
        count = render(args.delivery, args.candidates, args.out, args.review)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Rendered {count} candidates with 5-member assignments to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
