"""Difficulty assessment and review prioritization engine (content-based, never filename-based)."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from qc_factory_day10.adapters.delivery_reader import DeliveryContext
from qc_factory_day10.engine.geometry import box_area, box_iou, yolo_to_pixels


def _read_yolo_boxes(path: Path, width: int, height: int) -> list[tuple[int, tuple[float, float, float, float]]]:
    if not path.is_file() or width <= 0 or height <= 0:
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 5:
            try:
                cls = int(parts[0])
                vals = [float(x) for x in parts[1:]]
                out.append((cls, yolo_to_pixels(vals, width, height)))
            except ValueError:
                continue
    return out


def compute_image_complexity(ctx: DeliveryContext) -> dict[str, dict[str, Any]]:
    """Compute structural complexity metrics per image from labels + panoptic metadata."""
    items = ctx.manifest.get("items", {})
    pan_imgs = {Path(im["file_name"]).stem: im for im in ctx.panoptic.get("images", []) if "file_name" in im}
    pan_anns = {Path(a["file_name"]).stem: a for a in ctx.panoptic.get("annotations", []) if "file_name" in a}
    thing_cats = {c["id"] for c in ctx.panoptic.get("categories", []) if c.get("isthing", 1)}

    stats: dict[str, dict[str, Any]] = {}
    for name, entry in sorted(items.items()):
        im = pan_imgs.get(name, {})
        w = int(im.get("width", 640) or 640)
        h = int(im.get("height", 480) or 480)
        img_area = max(1.0, float(w * h))

        lbl_rel = entry.get("label", "")
        boxes = _read_yolo_boxes(ctx.root / lbl_rel, w, h) if lbl_rel else []
        ann = pan_anns.get(name, {})
        segs = [s for s in ann.get("segments_info", []) if s.get("category_id") in thing_cats]

        small_dets = sum(1 for _, b in boxes if box_area(b) / img_area < 0.01)
        small_ratio = small_dets / len(boxes) if boxes else 0.0

        crowd_segs = sum(1 for s in segs if s.get("iscrowd"))
        overlap_pairs = 0
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if box_iou(boxes[i][1], boxes[j][1]) >= 0.3:
                    overlap_pairs += 1

        crowding = min(1.0, (overlap_pairs / 4.0) + (0.35 if crowd_segs > 0 else 0.0))
        density = min(1.0, (len(boxes) + len(segs)) / 30.0)
        difficulty_score = round(min(1.0, 0.40 * crowding + 0.35 * small_ratio + 0.25 * density), 3)

        stats[name] = {
            "image_id": name,
            "width": w,
            "height": h,
            "num_detections": len(boxes),
            "num_panoptic_instances": len(segs),
            "small_object_proportion": round(small_ratio, 3),
            "crowding_overlap": round(crowding, 3),
            "crowd_segments": crowd_segs,
            "difficulty_score": difficulty_score,
        }
    return stats


def build_triage(
    ctx: DeliveryContext,
    rule_errors: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    out_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Classify rule errors and semantic candidates into EASY / MEDIUM / HARD and compute priority P."""
    img_stats = compute_image_complexity(ctx)
    cand_counts_by_img = Counter(c["target"] for c in candidates)
    rule_by_img: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for err in rule_errors:
        rule_by_img[err["target"]].append(err)

    rows: list[dict[str, Any]] = []

    # 1. Rule errors -> EASY (deterministic)
    for err in rule_errors:
        target = err["target"]
        st = img_stats.get(target, {})
        rows.append({
            "image_id": target,
            "kind": "rule",
            "candidate_type": err["type"],
            "difficulty_tier": "EASY",
            "difficulty_score": 0.1,
            "error_evidence_score": 1.0,
            "review_value_score": 0.9,
            "priority": round(0.40 * 1.0 + 0.25 * 0.9 + 0.20 * 1.0 + 0.15 * 1.0, 3),
            "reason": f"Lỗi luật tất định ({err['type']})",
            "handling": "Validator tự động",
            "num_detections": st.get("num_detections", 0),
            "num_panoptic_instances": st.get("num_panoptic_instances", 0),
            "evidence": err.get("why", ""),
        })

    # 2. Semantic candidates -> MEDIUM or HARD
    for c in candidates:
        target = c["target"]
        ctype = c["type"]
        score = float(c.get("score", 0.5))
        st = img_stats.get(target, {})
        diff = float(st.get("difficulty_score", 0.3))
        crowd = float(st.get("crowding_overlap", 0.0))
        small = float(st.get("small_object_proportion", 0.0))
        n_signals = cand_counts_by_img[target]

        is_hard = (
            ctype == "instance_merge"
            or diff >= 0.50
            or crowd >= 0.45
            or small >= 0.50
            or st.get("crowd_segments", 0) > 0
        )
        tier = "HARD" if is_hard else "MEDIUM"

        # E = evidence, I = impact, V = human verifiability (inverse of crowding/ambiguity), C = confidence
        E = min(1.0, max(0.2, score))
        I = 0.9 if ctype in ("class_swap", "category_swap", "missing_box") else 0.75
        V = max(0.15, 1.0 - 0.6 * diff - 0.3 * crowd)
        C = min(1.0, 0.5 + 0.2 * min(2, n_signals) + 0.3 * score)
        priority = round(0.40 * E + 0.25 * I + 0.20 * V + 0.15 * C, 3)

        if tier == "HARD":
            handling = "Reviewer chuyên sâu / Double review" if ctype == "instance_merge" or crowd >= 0.5 else "Reviewer chuyên sâu"
            reason = f"{ctype} trong vùng phức tạp (diff={diff:.2f}, crowd={crowd:.2f}, small={small:.2f})"
        else:
            handling = "Human review nhanh (overlay)"
            reason = f"{ctype} tín hiệu rõ (score={score:.2f}, diff={diff:.2f})"

        rows.append({
            "image_id": target,
            "kind": "semantic",
            "candidate_type": ctype,
            "difficulty_tier": tier,
            "difficulty_score": round(diff, 3),
            "error_evidence_score": round(E, 3),
            "review_value_score": round(V, 3),
            "priority": priority,
            "reason": reason,
            "handling": handling,
            "num_detections": st.get("num_detections", 0),
            "num_panoptic_instances": st.get("num_panoptic_instances", 0),
            "evidence": c.get("evidence", ""),
        })

    # Sort semantic candidates by priority descending, rule errors at top/separate
    rows.sort(key=lambda r: (0 if r["kind"] == "rule" else 1, -r["priority"], r["image_id"]))

    tier_counts = Counter(r["difficulty_tier"] for r in rows)
    summary = {
        "total_images": len(ctx.manifest.get("items", {})),
        "total_items_triaged": len(rows),
        "tiers": {
            "EASY": tier_counts.get("EASY", 0),
            "MEDIUM": tier_counts.get("MEDIUM", 0),
            "HARD": tier_counts.get("HARD", 0),
        },
        "rule_errors": len(rule_errors),
        "semantic_candidates": len(candidates),
        "images_requiring_human_review": len({c["target"] for c in candidates}),
    }

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "triage.csv"
        fieldnames = [
            "image_id", "kind", "candidate_type", "difficulty_tier",
            "difficulty_score", "error_evidence_score", "review_value_score",
            "priority", "reason", "handling", "num_detections",
            "num_panoptic_instances", "evidence",
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        (out_dir / "difficulty_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return rows, summary
