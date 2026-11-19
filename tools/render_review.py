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
            add_label(draw, x1, max(0, y1 - font.size - 5), f"DET: {label}", (190, 25, 35), font)
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
        add_label(
            draw,
            x,
            max(0, y - font.size - 5),
            f"PAN: {category_names[category_id]}",
            (0, 125, 75),
            font,
        )
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
    content = "\n".join(cards) if cards else '<p class="empty">No candidates to review.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Candidate review board</title>
<style>
  :root {{ color-scheme: light; font-family: Segoe UI, Arial, sans-serif; background: #f3f5f8; color: #17212b; }}
  body {{ margin: 0; }}
  header {{ position: sticky; top: 0; z-index: 2; background: #fff; padding: 14px 22px; box-shadow: 0 2px 8px #13223818; }}
  h1 {{ margin: 0 0 10px; font-size: 20px; }}
  .filters {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  input, select {{ padding: 8px 10px; border: 1px solid #c7d0da; border-radius: 6px; background: #fff; }}
  main {{ padding: 18px; }}
  .card {{ margin: 0 auto 20px; max-width: 1500px; background: #fff; border: 1px solid #dfe5eb; border-radius: 10px; overflow: hidden; }}
  .card-head {{ display: flex; gap: 10px; align-items: center; padding: 12px 15px; border-bottom: 1px solid #e6ebf0; }}
  .card-head strong {{ font-size: 16px; }}
  .tag {{ border-radius: 999px; padding: 4px 9px; background: #e8eef8; color: #234b80; font-size: 12px; font-weight: 650; }}
  .panels {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 12px; }}
  figure {{ min-width: 0; margin: 0; background: #f7f9fb; border: 1px solid #e2e8ef; border-radius: 7px; overflow: hidden; }}
  figcaption {{ padding: 8px 10px; font-weight: 650; font-size: 13px; }}
  figure img {{ display: block; width: 100%; max-height: 460px; object-fit: contain; background: #18212b; }}
  .empty {{ text-align: center; padding: 40px; color: #526170; }}
  @media (max-width: 850px) {{ .panels {{ grid-template-columns: 1fr; }} figure img {{ max-height: 520px; }} }}
</style>
</head>
<body>
<header>
  <h1>Visual review · <span id="visible-count">{len(cards)}</span> candidates</h1>
  <div class="filters">
    <input id="search" type="search" placeholder="Filter by image name">
    <select id="type"><option value="">All candidate types</option>{options}</select>
  </div>
</header>
<main>{content}</main>
<script>
  const search = document.getElementById("search");
  const typeFilter = document.getElementById("type");
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
    document.getElementById("visible-count").textContent = visible;
  }}
  search.addEventListener("input", filterCards);
  typeFilter.addEventListener("change", filterCards);
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
            ("Source image", source_panel),
            ("Detection · red boxes", det_panel),
            ("Panoptic · green mask", pan_panel),
        )
        figures = "".join(
            f'<figure><figcaption>{title}</figcaption><img loading="lazy" alt="{title} for {safe_stem}" src="{image_data_uri(panel)}"></figure>'
            for title, panel in panes
        )
        cards.append(
            f'<article class="card" data-image="{safe_stem}" data-type="{html.escape(candidate_type, quote=True)}">'
            f'<div class="card-head"><strong>{index}. {safe_stem}</strong><span class="tag">{safe_type}</span></div>'
            f'<div class="panels">{figures}</div></article>'
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
