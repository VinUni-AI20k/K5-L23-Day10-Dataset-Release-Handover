"""Class validity, box bounds and near-identical detection duplicates."""

from itertools import combinations

BOUNDS_TOLERANCE = 0.01
# Normalized labels are written with finite precision. Allow tiny rounding
# differences in width/height, not real differences between overlapping objects.
SIZE_TOLERANCE_PX = 0.01
CENTER_TOLERANCE_PX = 2.01


def is_duplicate(a, b):
    if a["class_id"] != b["class_id"]:
        return False
    al, at, ar, ab = a["xyxy_px"]
    bl, bt, br, bb = b["xyxy_px"]
    return (abs((ar - al) - (br - bl)) <= SIZE_TOLERANCE_PX
            and abs((ab - at) - (bb - bt)) <= SIZE_TOLERANCE_PX
            and abs((al + ar - bl - br) / 2) <= CENTER_TOLERANCE_PX
            and abs((at + ab - bt - bb) / 2) <= CENTER_TOLERANCE_PX)


def check(ctx):
    errors = []
    for name, boxes in ctx["detections"].items():
        error = None
        if any(b["class_id"] not in ctx["classes"] for b in boxes):
            error = "invalid_class"
        elif any(b["xywh"][2] <= 0 or b["xywh"][3] <= 0
                 or min(b["xyxy"][:2]) < -BOUNDS_TOLERANCE
                 or max(b["xyxy"][2:]) > 1 + BOUNDS_TOLERANCE for b in boxes):
            error = "bbox_out_of_bounds"
        elif any(is_duplicate(a, b) for a, b in combinations(boxes, 2)):
            error = "duplicate_box"
        if error:
            errors.append({"type": error, "target": name})
    return errors
