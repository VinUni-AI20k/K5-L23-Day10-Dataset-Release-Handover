"""Detection/panoptic semantic crosscheck candidate generation."""

from __future__ import annotations

from pathlib import Path

IMPLEMENTED = True


def _bbox_iou_xyxy(b1: tuple[float, float, float, float], b2: tuple[float, float, float, float]) -> float:
    """IoU between two bboxes [l, t, r, b]."""
    l1, t1, r1, b_1 = b1
    l2, t2, r2, b_2 = b2

    inter_w = max(0.0, min(r1, r2) - max(l1, l2))
    inter_h = max(0.0, min(b_1, b_2) - max(t1, t2))
    inter = inter_w * inter_h
    w1, h1 = r1 - l1, b_1 - t1
    w2, h2 = r2 - l2, b_2 - t2
    union = w1 * h1 + w2 * h2 - inter
    return inter / union if union > 0 else 0.0


def candidates(ctx: dict, skip_images: set[str] | None = None) -> list[dict]:
    """Find potential semantic discrepancy candidates between detection and panoptic."""
    if skip_images is None:
        skip_images = set()

    images = ctx["images"]
    detections = ctx["detections"]
    annotations = ctx["annotations"]
    categories = ctx["categories"]
    classes = ctx["classes"]

    candidates_list: list[dict] = []

    for name in sorted(images.keys()):
        if name in skip_images:
            continue

        im = images[name]
        w_img, h_img = im["width"], im["height"]
        img_area = float(w_img * h_img)
        ann = annotations.get(name)
        if not ann:
            continue

        det_boxes = detections.get(name, [])
        det_objects = []
        for d in det_boxes:
            cid = d["class_id"]
            cname = classes.get(cid, str(cid))
            l, t, r, b = d["xyxy_px"]
            w_px, h_px = r - l, b - t
            det_objects.append({
                "class": cname,
                "xyxy_px": (l, t, r, b),
                "area": w_px * h_px,
                "center": ((l + r) / 2.0, (t + b) / 2.0),
                "dim": (w_px, h_px),
            })

        pan_objects = []
        for s in ann.get("segments_info", []):
            cat = categories.get(s.get("category_id"))
            if not cat or cat.get("isthing") != 1 or s.get("iscrowd") == 1:
                continue
            sb = s.get("bbox", [0, 0, 0, 0])
            l, t, w, h = sb[0], sb[1], sb[2], sb[3]
            r, b = l + w, t + h
            pan_objects.append({
                "id": s["id"],
                "category": cat["name"],
                "xyxy_px": (float(l), float(t), float(r), float(b)),
                "area": float(s.get("area", w * h)),
                "center": (float(l) + float(w) / 2.0, float(t) + float(h) / 2.0),
                "dim": (float(w), float(h)),
            })

        det_counts: dict[str, int] = {}
        for d in det_objects:
            det_counts[d["class"]] = det_counts.get(d["class"], 0) + 1

        pan_counts: dict[str, int] = {}
        for p in pan_objects:
            pan_counts[p["category"]] = pan_counts.get(p["category"], 0) + 1

        cands_for_image = []

        # 1. instance_merge:
        # A panoptic segment merges two detection boxes of the same class (det_count > pan_count)
        for p in pan_objects:
            cname = p["category"]
            if det_counts.get(cname, 0) > pan_counts.get(cname, 0):
                pl, pt, pr, pb = p["xyxy_px"]
                matching = [
                    d for d in det_objects
                    if d["class"] == cname
                    and d["area"] >= 500
                    and (pl <= d["center"][0] <= pr and pt <= d["center"][1] <= pb)
                ]
                if len(matching) >= 2:
                    for i in range(len(matching)):
                        for j in range(i + 1, len(matching)):
                            if _bbox_iou_xyxy(matching[i]["xyxy_px"], matching[j]["xyxy_px"]) < 0.20:
                                cands_for_image.append({
                                    "image": name,
                                    "type": "instance_merge",
                                    "score": 0.95,
                                    "detail": f"Panoptic segment '{cname}' merges two distinct detection boxes (det={det_counts[cname]} > pan={pan_counts[cname]})",
                                })
                                break
                        if cands_for_image:
                            break
            if cands_for_image:
                break

        # 2. class_swap / category_swap:
        for d in det_objects:
            if d["area"] < 1000:
                continue
            for p in pan_objects:
                iou = _bbox_iou_xyxy(d["xyxy_px"], p["xyxy_px"])
                if iou >= 0.70 and d["class"] != p["category"]:
                    cands_for_image.append({
                        "image": name,
                        "type": "class_swap",
                        "score": round(iou, 3),
                        "detail": f"Disagreement: detection says '{d['class']}', panoptic says '{p['category']}' (IoU={iou:.2f})",
                    })
                    break

        # 3. bbox_drift:
        for d in det_objects:
            w_box, h_box = d["dim"]
            if d["area"] < 0.005 * img_area or w_box < 0.08 * w_img or h_box < 0.08 * h_img:
                continue
            best_iou = 0.0
            best_p = None
            for p in pan_objects:
                if d["class"] == p["category"]:
                    iou = _bbox_iou_xyxy(d["xyxy_px"], p["xyxy_px"])
                    if iou > best_iou:
                        best_iou = iou
                        best_p = p

            if best_p and 0.30 <= best_iou <= 0.68:
                dx = abs(d["center"][0] - best_p["center"][0])
                dy = abs(d["center"][1] - best_p["center"][1])
                drift_dist = (dx ** 2 + dy ** 2) ** 0.5
                min_dim = min(w_box, h_box)
                if min_dim > 0 and (drift_dist / min_dim) >= 0.18:
                    cands_for_image.append({
                        "image": name,
                        "type": "bbox_drift",
                        "score": round(best_iou, 3),
                        "detail": f"Box for '{d['class']}' has center drift {drift_dist:.1f}px (IoU={best_iou:.2f})",
                    })

        # 4. missing_box:
        for p in pan_objects:
            cname = p["category"]
            if p["area"] < max(1500.0, 0.010 * img_area):
                continue
            if pan_counts.get(cname, 0) > det_counts.get(cname, 0):
                max_iou = 0.0
                for d in det_objects:
                    iou = _bbox_iou_xyxy(d["xyxy_px"], p["xyxy_px"])
                    if iou > max_iou:
                        max_iou = iou

                if max_iou < 0.10:
                    cands_for_image.append({
                        "image": name,
                        "type": "missing_box",
                        "score": round(1.0 - max_iou, 3),
                        "detail": f"Panoptic segment '{cname}' (area={int(p['area'])}) missing detection box (max IoU={max_iou:.2f})",
                    })

        if cands_for_image:
            cands_for_image.sort(key=lambda x: x["score"], reverse=True)
            candidates_list.append(cands_for_image[0])

    return candidates_list
