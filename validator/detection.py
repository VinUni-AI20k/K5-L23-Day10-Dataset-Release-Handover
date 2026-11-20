"""Read-only Detection rules for a Day 10 delivery (Python standard library).

Contract: validate_detection(path) returns sorted, unique {type, target} records.
Only image bytes are hashed. No input is repaired and no output file is written.

Technical assumptions, not official lab thresholds:
* normalized bbox boundaries tolerate 1e-6 six-decimal serialization noise;
  comparisons at that limit allow 1e-15 arithmetic noise only;
* duplicate centers differ by at most 2 pixels on EACH axis (inclusive);
* duplicate normalized widths/heights differ by at most 1e-9;
* non-finite coordinates or non-positive sizes are invalid bboxes.

Dimensions come from delivery/panoptic.json images (file_name, width, height).
Missing labels, malformed rows, unreadable images and unavailable dimensions
produce RuntimeWarning diagnostics, not invented submission error types. Thus a
caller must inspect warnings: an empty result alone does not certify valid input.
Missing/malformed manifest or classes are fatal configuration errors.
"""

from __future__ import annotations

import hashlib
import json
import math
import warnings
from decimal import Decimal, InvalidOperation
from itertools import combinations
from pathlib import Path


BBOX_EPSILON = 1e-6
DUPLICATE_CENTER_PIXELS = 2.0
DUPLICATE_SIZE_EPSILON = 1e-9
PIXEL_EPSILON = 1e-9


def _diagnostic(message: str) -> None:
    warnings.warn(message, RuntimeWarning, stacklevel=3)


def _delivery_file(root: Path, relative: str) -> Path:
    """Do not follow manifest paths or symlinks outside the supplied delivery."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes delivery: {relative!r}")
    return path


def _class_id(text: str) -> int | None:
    # Accept integral spellings such as 1.0, but never truncate class 1.5 to 1.
    try:
        value = Decimal(text)
        if value.is_finite() and value == value.to_integral_value():
            return int(value)
    except (InvalidOperation, ValueError):
        pass
    return None


def _classes(root: Path) -> set[int]:
    ids = set()
    for number, line in enumerate((root / "classes.txt").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        class_id = _class_id(parts[0])
        if len(parts) != 2 or class_id is None or class_id < 0 or class_id in ids:
            raise ValueError(f"Invalid classes.txt entry at line {number}")
        ids.add(class_id)
    if not ids:
        raise ValueError("classes.txt contains no classes")
    return ids


def _dimensions(root: Path) -> dict[str, tuple[float, float]]:
    """Use local metadata only; never decode images with an external library."""
    try:
        document = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
        images = document["images"]
        if not isinstance(images, list):
            raise ValueError("images must be a list")
        dimensions = {}
        for image in images:
            width, height = float(image["width"]), float(image["height"])
            if not (math.isfinite(width) and math.isfinite(height) and width > 0 and height > 0):
                raise ValueError("image dimensions must be finite and positive")
            name = Path(image["file_name"]).stem
            if name in dimensions:
                raise ValueError(f"ambiguous image dimensions for {name}")
            dimensions[name] = (width, height)
        return dimensions
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _diagnostic(f"Cannot load image dimensions from panoptic.json: {exc}")
        return {}


def _out_of_bounds(box: tuple[float, float, float, float]) -> bool:
    x, y, width, height = box
    if not all(math.isfinite(value) for value in box) or width <= 0 or height <= 0:
        return True
    left = x - width / 2
    right = x + width / 2
    top = y - height / 2
    bottom = y + height / 2
    # A boundary intended to equal -1e-6 can calculate as
    # -1.000000000001e-6. Ignore arithmetic noise, not real extra overflow.
    return any(
        margin < -BBOX_EPSILON
        and not math.isclose(margin, -BBOX_EPSILON, rel_tol=0.0, abs_tol=1e-15)
        for margin in (left, top, 1 - right, 1 - bottom)
    )


def _duplicate(first: tuple, second: tuple, dimensions: tuple[float, float]) -> bool:
    c1, x1, y1, w1, h1 = first
    c2, x2, y2, w2, h2 = second
    width, height = dimensions
    return (
        c1 == c2
        and abs(w1 - w2) <= DUPLICATE_SIZE_EPSILON
        and abs(h1 - h2) <= DUPLICATE_SIZE_EPSILON
        and abs(x1 - x2) * width <= DUPLICATE_CENTER_PIXELS + PIXEL_EPSILON
        and abs(y1 - y2) * height <= DUPLICATE_CENTER_PIXELS + PIXEL_EPSILON
    )


def validate_detection(delivery_path: str | Path) -> list[dict[str, str]]:
    """Find the five assigned Detection error types without modifying delivery.

    Manifest schema: {"items": {"image_stem": {"image": relative_path,
    "image_sha256": hex_digest, "label": relative_path, ...}}}.
    Targets are the manifest's string keys, preserving leading zeros.
    Missing individual files do not stop processing other images. Diagnostics
    use warnings; missing global inputs still raise OSError/ValueError.
    """
    root = Path(delivery_path).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    items = manifest["items"]
    if not isinstance(items, dict):
        raise ValueError("manifest.items must be an object keyed by image stem")
    valid_classes = _classes(root)
    found: set[tuple[str, str]] = set()
    dimensions = None  # Load only if duplicate candidates actually need them.

    for target, item in sorted(items.items()):
        if not isinstance(item, dict):
            _diagnostic(f"{target}: invalid manifest item; skipped")
            continue
        try:
            image_path = _delivery_file(root, item["image"])
        except (KeyError, TypeError, ValueError, OSError) as exc:
            _diagnostic(f"{target}: invalid manifest paths; skipped: {exc}")
            continue

        if not image_path.is_file():
            found.add(("missing_image", target))
        else:
            try:
                digest = hashlib.sha256()
                with image_path.open("rb") as image_file:
                    for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
                        digest.update(chunk)
                expected = item.get("image_sha256")
                if not isinstance(expected, str):
                    _diagnostic(f"{target}: missing or invalid image_sha256")
                elif digest.hexdigest() != expected.lower():
                    found.add(("wrong_hash", target))
            except OSError as exc:
                _diagnostic(f"{target}: cannot read image bytes: {exc}")

        try:
            label_path = _delivery_file(root, item["label"])
            label_lines = label_path.read_text(encoding="utf-8").splitlines()
        except (KeyError, TypeError, ValueError, OSError, UnicodeError) as exc:
            _diagnostic(f"{target}: cannot read label; label checks skipped: {exc}")
            continue

        boxes = []
        for number, line in enumerate(label_lines, 1):
            parts = line.split()
            if not parts:
                continue
            class_id = _class_id(parts[0])
            if class_id not in valid_classes:
                found.add(("invalid_class", target))
            if len(parts) != 5:
                _diagnostic(f"{target}: malformed YOLO row {number}; geometry skipped")
                continue
            try:
                box = tuple(float(value) for value in parts[1:])
            except ValueError:
                _diagnostic(f"{target}: nonnumeric YOLO row {number}; geometry skipped")
                continue
            if _out_of_bounds(box):
                found.add(("bbox_out_of_bounds", target))
            elif class_id in valid_classes:
                boxes.append((class_id, *box))

        pairs = [(a, b) for a, b in combinations(boxes, 2) if a[0] == b[0]]
        if not pairs:
            continue
        if dimensions is None:
            dimensions = _dimensions(root)
        size = dimensions.get(target)
        if size is None:
            _diagnostic(f"{target}: no image dimensions; duplicate_box check skipped")
            continue
        if any(_duplicate(a, b, size) for a, b in pairs):
            found.add(("duplicate_box", target))

    return [{"type": kind, "target": target} for kind, target in sorted(found)]
