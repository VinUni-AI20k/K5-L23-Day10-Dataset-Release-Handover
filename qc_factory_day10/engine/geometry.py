"""Pure-Python geometry utilities adapted from cvat_tools.quality.metrics_eval & tracking.geometry."""
from __future__ import annotations

Box = tuple[float, float, float, float]


def yolo_to_pixels(vals: list[float], width: int, height: int) -> Box:
    xc, yc, w, h = vals
    return ((xc - w / 2.0) * width, (yc - h / 2.0) * height, (xc + w / 2.0) * width, (yc + h / 2.0) * height)


def box_area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def boxes_overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def box_intersection(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def box_iou(a: Box, b: Box) -> float:
    inter = box_intersection(a, b)
    if inter <= 0.0:
        return 0.0
    union = box_area(a) + box_area(b) - inter
    return inter / union if union > 0.0 else 0.0


def boundary_deviation(a: Box, b: Box, width: int, height: int) -> float:
    """Normalized L1 deviation across 4 box edges in [0, 1]."""
    if width <= 0 or height <= 0:
        return 0.0
    dx = (abs(a[0] - b[0]) + abs(a[2] - b[2])) / (2.0 * width)
    dy = (abs(a[1] - b[1]) + abs(a[3] - b[3])) / (2.0 * height)
    return min(1.0, (dx + dy) / 2.0)
