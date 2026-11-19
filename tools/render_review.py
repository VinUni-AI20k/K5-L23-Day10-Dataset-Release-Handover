#!/usr/bin/env python3
"""Render a visual review board for detection/panoptic candidates."""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


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
        if isinstance(category, dict) and category.get("isthing") == 1
        and "id" in category
    }
    annotation_by_image = {
        annotation["image_id"]: annotation
        for annotation in panoptic.get("annotations", [])
        if isinstance(annotation, dict) and "image_id" in annotation
    }

    image_by_id = {
        image["id"]: Path(image["file_name"]).stem
        for image in panoptic.get("images", [])
        if isinstance(image, dict) and "id" in image and "file_name" in image
    }
    segments_by_stem: dict[str, list[dict]] = {}
    masks_by_stem: dict[str, Path] = {}
    for image_id, stem in image_by_id.items():
        annotation = annotation_by_image.get(image_id)
        if annotation is None:
            continue
        segments_by_stem[stem] = annotation.get("segments_info", [])
        mask_name = Path(annotation["file_name"]).name
        masks_by_stem[stem] = masks_dir / mask_name

    class_names: dict[int, str] = {}
    for line_number, line in enumerate(classes_text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            class_id_text, name = line.split(maxsplit=1)
            class_names[int(class_id_text)] = name
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid classes.txt line {line_number}") from exc
    return images, masks_by_stem, segments_by_stem, class_names, category_names, thing_category_ids


def load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def scale_small(image: Image.Image) -> Image.Image:
    if image.width < 480:
        factor = min(3, max(2, (480 + image.width - 1) // image.width))
        return image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
    return image


def add_label(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color: tuple[int, int, int], font: ImageFont.ImageFont) -> None:
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    draw.rectangle((left - 2, top - 1, right + 3, bottom + 2), fill=color)
    draw.text((x, y), text, fill="white", font=font)


def detection_panel(
    image: Image.Image, label_path: Path, class_names: dict[int, str]
) -> Image.Image:
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    font = load_font(max(12, canvas.width // 50))
    label_bounds: list[tuple[int, int, int, int]] = []
    if label_path.is_file():
        for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 5:
                raise ValueError(f"invalid YOLO label {label_path}:{line_number}")
            try:
                class_id = int(parts[0])
                center_x, center_y, width, height = map(float, parts[1:])
            except ValueError as exc:
                raise ValueError(f"invalid YOLO label {label_path}:{line_number}") from exc
            x1 = round((center_x - width / 2) * canvas.width)
            y1 = round((center_y - height / 2) * canvas.height)
            x2 = round((center_x + width / 2) * canvas.width)
            y2 = round((center_y + height / 2) * canvas.height)
            draw.rectangle((x1, y1, x2, y2), outline=(255, 55, 55), width=max(2, canvas.width // 320))
            label = class_names.get(class_id, f"class {class_id}")
            text = f"DET: {label}"
            label_y = max(0, y1 - font.size - 5)
            left, top, right, bottom = draw.textbbox((x1, label_y), text, font=font)
            bounds = (left - 2, top - 1, right + 3, bottom + 2)
            if any(
                bounds[0] < other[2] and bounds[2] > other[0]
                and bounds[1] < other[3] and bounds[3] > other[1]
                for other in label_bounds
            ):
                continue
            add_label(draw, x1, label_y, text, (190, 25, 35), font)
            label_bounds.append(bounds)
    return canvas


def panoptic_panel(
    image: Image.Image,
    mask_path: Path,
    segments: list[dict],
    category_names: dict[int, str],
    thing_category_ids: set[int],
    selected_segment_id: int | None,
) -> Image.Image:
    if not mask_path.is_file():
        raise ValueError(f"panoptic mask is missing: {mask_path}")
    try:
        mask = Image.open(mask_path).convert("RGB")
    except OSError as exc:
        raise ValueError(f"cannot open panoptic mask {mask_path}: {exc}") from exc
    if mask.size != image.size:
        raise ValueError(f"panoptic mask dimensions do not match image: {mask_path}")

    width, height = mask.size
    raw = mask.tobytes()
    ids = [
        raw[index] + raw[index + 1] * 256 + raw[index + 2] * 65536
        for index in range(0, len(raw), 3)
    ]
    overlay_bytes = bytearray(width * height * 4)
    for index, segment_id in enumerate(ids):
        if segment_id == 0:
            continue
        x = index % width
        y = index // width
        edge = (
            (x > 0 and ids[index - 1] != segment_id)
            or (x + 1 < width and ids[index + 1] != segment_id)
            or (y > 0 and ids[index - width] != segment_id)
            or (y + 1 < height and ids[index + width] != segment_id)
        )
        offset = index * 4
        overlay_bytes[offset : offset + 4] = (0, 245, 125, 235 if edge else 32)

    overlay = Image.frombytes("RGBA", mask.size, bytes(overlay_bytes))
    canvas = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = load_font(max(12, canvas.width // 50))
    label_bounds: list[tuple[int, int, int, int]] = []
    for segment in segments:
        category_id = segment.get("category_id")
        if (
            category_id not in thing_category_ids
            or category_id not in category_names
            or segment.get("iscrowd")
        ):
            continue
        bbox = segment.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x, y, box_width, box_height = map(round, bbox)
        if segment.get("id") == selected_segment_id:
            draw.rectangle(
                (x, y, x + box_width, y + box_height),
                outline=(255, 235, 0),
                width=max(3, canvas.width // 240),
            )
        if segment.get("area", 0) < 1200:
            continue
        label = f"PAN: {category_names[category_id]}"
        label_y = max(0, y - font.size - 5)
        left, top, right, bottom = draw.textbbox((x, label_y), label, font=font)
        bounds = (left - 2, top - 1, right + 3, bottom + 2)
        if any(
            bounds[0] < other[2] and bounds[2] > other[0]
            and bounds[1] < other[3] and bounds[3] > other[1]
            for other in label_bounds
        ):
            continue
        add_label(
            draw,
            x,
            label_y,
            label,
            (0, 125, 75),
            font,
        )
        label_bounds.append(bounds)
    return canvas


def image_data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=86, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def build_html(cards: list[str], types: list[str]) -> str:
    options = "\n".join(
        f'<option value="{html.escape(candidate_type, quote=True)}">{html.escape(candidate_type)}</option>'
        for candidate_type in types
    )
    content = "\n".join(cards) if cards else """
      <section class="empty-state">
        <div class="empty-icon">✓</div>
        <h2>Chưa có ứng viên cần xem</h2>
        <p>Danh sách candidates đang rỗng. Hãy chạy validator với tùy chọn <code>--candidates</code> sau khi phần đối chiếu được tích hợp.</p>
      </section>
    """
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#101827">
<title>Bảng xem xét ứng viên</title>
<style>
  :root {{
    color-scheme: light;
    font-family: "Segoe UI", Inter, Arial, sans-serif;
    background: #f4f7fb;
    color: #182230;
    font-synthesis: none;
    text-rendering: optimizeLegibility;
    --muted: #64748b;
    --line: #e2e8f0;
    --accent: #2563eb;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; min-height: 100vh; }}
  .topbar {{
    color: #f8fafc;
    background: radial-gradient(900px 300px at 85% -25%, #315b91 0%, transparent 65%), #101827;
    padding: 30px max(24px, calc((100vw - 1440px) / 2));
  }}
  .eyebrow {{ color: #93c5fd; font-size: 11px; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; }}
  .title-row {{ display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-top: 8px; }}
  h1 {{ margin: 0; font-size: clamp(24px, 3vw, 34px); letter-spacing: -.035em; }}
  .subtitle {{ margin: 8px 0 0; color: #b6c3d4; font-size: 14px; }}
  .total {{
    flex: 0 0 auto; display: flex; align-items: baseline; gap: 8px;
    padding: 10px 14px; border: 1px solid #ffffff24; border-radius: 12px;
    background: #ffffff0d; color: #dbeafe;
  }}
  .total strong {{ color: #fff; font-size: 24px; }}
  .toolbar {{
    position: sticky; top: 0; z-index: 5; display: flex; align-items: center;
    justify-content: space-between; gap: 14px; flex-wrap: wrap;
    padding: 14px max(24px, calc((100vw - 1440px) / 2));
    background: #ffffffed; border-bottom: 1px solid var(--line); backdrop-filter: blur(12px);
  }}
  .filters {{ display: flex; flex: 1; min-width: 260px; gap: 10px; flex-wrap: wrap; }}
  .control {{
    min-height: 42px; padding: 9px 12px; border: 1px solid #d6deea; border-radius: 9px;
    background: #fff; color: #182230; font: inherit; outline: none;
    transition: border-color .15s, box-shadow .15s;
  }}
  .control:focus {{ border-color: #60a5fa; box-shadow: 0 0 0 3px #3b82f626; }}
  input.control {{ flex: 1; min-width: 220px; }}
  select.control {{ min-width: 210px; }}
  .reset {{
    min-height: 42px; padding: 9px 14px; border: 1px solid #d6deea; border-radius: 9px;
    background: #fff; color: #334155; font: inherit; font-weight: 650; cursor: pointer;
  }}
  .reset:hover {{ border-color: #94a3b8; background: #f8fafc; }}
  main {{ width: min(100% - 40px, 1440px); margin: 0 auto; padding: 24px 0 48px; }}
  .results {{ margin: 0 0 14px; color: var(--muted); font-size: 13px; }}
  .card {{
    margin: 0 0 18px; overflow: hidden; border: 1px solid var(--line); border-radius: 14px;
    background: #fff; box-shadow: 0 5px 20px #0f172a0a;
    transition: box-shadow .18s, transform .18s;
  }}
  .card:hover {{ transform: translateY(-1px); box-shadow: 0 12px 30px #0f172a12; }}
  .card-head {{
    display: flex; align-items: center; gap: 12px; padding: 15px 18px;
    border-bottom: 1px solid #edf1f6;
  }}
  .index {{
    display: grid; width: 34px; height: 34px; flex: 0 0 auto; place-items: center;
    border-radius: 10px; background: #eff6ff; color: #1d4ed8; font-size: 13px; font-weight: 800;
  }}
  .candidate-info {{ min-width: 0; }}
  .candidate-info strong {{ display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; }}
  .candidate-info small {{ display: block; margin-top: 3px; color: var(--muted); font-size: 12px; }}
  .tag {{
    margin-left: auto; flex: 0 0 auto; padding: 6px 10px; border: 1px solid #dbeafe;
    border-radius: 999px; background: #eff6ff; color: #1d4ed8; font-size: 12px; font-weight: 750;
  }}
  .panels {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; padding: 16px; }}
  figure {{ min-width: 0; margin: 0; overflow: hidden; border: 1px solid #e5eaf1; border-radius: 10px; background: #f8fafc; }}
  figcaption {{ display: flex; align-items: center; gap: 8px; padding: 10px 12px; color: #334155; font-size: 12px; font-weight: 750; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }}
  .dot.det {{ background: #ef4444; }} .dot.pan {{ background: #10b981; }}
  figure img {{ display: block; width: 100%; height: clamp(220px, 25vw, 380px); object-fit: contain; background: #111827; }}
  .legend {{ display: flex; gap: 16px; padding: 0 18px 15px; color: var(--muted); font-size: 12px; }}
  .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
  .legend i {{ width: 9px; height: 9px; border-radius: 50%; background: #ef4444; }}
  .legend .green {{ background: #10b981; }}
  .empty-state {{
    max-width: 650px; margin: 55px auto; padding: 42px 32px; text-align: center;
    border: 1px solid var(--line); border-radius: 16px; background: #fff;
    box-shadow: 0 8px 28px #0f172a0b;
  }}
  .empty-icon {{ display: grid; width: 54px; height: 54px; margin: 0 auto 16px; place-items: center; border-radius: 16px; background: #ecfdf5; color: #059669; font-size: 26px; font-weight: 800; }}
  .empty-state h2 {{ margin: 0; font-size: 20px; }}
  .empty-state p {{ margin: 10px 0 0; color: var(--muted); line-height: 1.65; }}
  .empty-state code {{ padding: 2px 5px; border-radius: 5px; background: #f1f5f9; color: #334155; }}
  [hidden] {{ display: none !important; }}
  @media (max-width: 900px) {{
    .panels {{ grid-template-columns: 1fr; }}
    figure img {{ height: min(64vw, 480px); }}
  }}
  @media (max-width: 560px) {{
    .topbar {{ padding: 24px 18px; }}
    .title-row {{ align-items: flex-start; }}
    .total {{ padding: 8px 10px; }}
    .toolbar {{ padding: 12px 18px; }}
    main {{ width: min(100% - 24px, 1440px); padding-top: 16px; }}
    .filters {{ min-width: 100%; }}
    input.control, select.control {{ width: 100%; }}
    .reset {{ width: 100%; }}
    .panels {{ padding: 10px; gap: 10px; }}
    .card-head {{ padding: 12px; }}
  }}
</style>
</head>
<body>
<header class="topbar">
  <div class="eyebrow">Day 10 · Dataset quality review</div>
  <div class="title-row">
    <div>
      <h1>Bảng xem xét ứng viên</h1>
      <p class="subtitle">Đối chiếu ảnh gốc, detection và panoptic trước khi xác nhận lỗi.</p>
    </div>
    <div class="total"><strong>{len(cards)}</strong><span>ứng viên</span></div>
  </div>
</header>
<section class="toolbar" aria-label="Bộ lọc ứng viên">
  <div class="filters">
    <input class="control" id="search" type="search" placeholder="Tìm theo tên ảnh..." aria-label="Tìm theo tên ảnh">
    <select class="control" id="type" aria-label="Lọc theo loại lỗi"><option value="">Tất cả loại ứng viên</option>{options}</select>
  </div>
  <button class="reset" id="reset" type="button">Xóa bộ lọc</button>
</section>
<main>
  <p class="results" id="results" aria-live="polite">Hiển thị {len(cards)} / {len(cards)} ứng viên</p>
  {content}
</main>
<script>
  const search = document.getElementById("search");
  const typeFilter = document.getElementById("type");
  const reset = document.getElementById("reset");
  const cards = [...document.querySelectorAll(".card")];
  function filterCards() {{
    const query = search.value.toLowerCase();
    const type = typeFilter.value;
    let visible = 0;
    for (const card of cards) {{
      const show = card.dataset.image.toLowerCase().includes(query)
        && (!type || card.dataset.type === type);
      card.hidden = !show;
      if (show) visible++;
    }}
    document.getElementById("results").textContent =
      `Hiển thị ${{visible}} / ${{cards.length}} ứng viên`;
  }}
  search.addEventListener("input", filterCards);
  typeFilter.addEventListener("change", filterCards);
  reset.addEventListener("click", () => {{
    search.value = "";
    typeFilter.value = "";
    filterCards();
    search.focus();
  }});
</script>
</body>
</html>
"""


def render(delivery: Path, candidates_path: Path, out: Path) -> int:
    delivery = delivery.resolve()
    out = out.resolve()
    if delivery == out or delivery in out.parents:
        raise ValueError("output must be outside the read-only delivery directory")
    candidates = read_candidates(candidates_path)
    images, masks, segments, class_names, category_names, thing_category_ids = read_delivery(delivery)
    cards: list[str] = []
    candidate_types: set[str] = set()

    for index, candidate in enumerate(candidates, start=1):
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
        safe_stem = html.escape(stem)
        safe_type = html.escape(candidate_type)
        panes = (
            ("Ảnh gốc", source_panel, ""),
            ("Detection", det_panel, "det"),
            ("Panoptic", pan_panel, "pan"),
        )
        figures = "".join(
            f'<figure><figcaption><span class="dot {dot_class}"></span>{title}</figcaption>'
            f'<img loading="lazy" alt="{title} · {safe_stem}" src="{image_data_uri(panel)}"></figure>'
            for title, panel, dot_class in panes
        )
        cards.append(
            f'<article class="card" data-image="{safe_stem}" data-type="{html.escape(candidate_type, quote=True)}">'
            f'<div class="card-head"><span class="index">{index:02d}</span>'
            f'<div class="candidate-info"><strong>{safe_stem}</strong><small>Kiểm tra trực quan trước khi chốt verdict</small></div>'
            f'<span class="tag">{safe_type}</span></div>'
            f'<div class="panels">{figures}</div>'
            f'<div class="legend"><span><i></i> Detection box</span><span><i class="green"></i> Panoptic mask</span></div></article>'
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(cards, sorted(candidate_types)), encoding="utf-8")
    return len(candidates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an HTML board for visual review.")
    parser.add_argument("delivery", type=Path, help="read-only delivery directory")
    parser.add_argument("candidates", type=Path, help="JSON list or {'candidates': [...]} with image and type")
    parser.add_argument("--out", required=True, type=Path, help="output HTML path, outside delivery")
    args = parser.parse_args()
    try:
        count = render(args.delivery, args.candidates, args.out)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Rendered {count} candidates to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
