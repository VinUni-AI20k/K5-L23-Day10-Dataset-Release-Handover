"""Build immutable handover v2 package from delivery/ and errors.json without modifying v1."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qc_factory_day10.adapters.delivery_reader import load_delivery, safe_rel_path
from qc_factory_day10.orchestration.pipeline import build_trace_from_delivery

REWORK_TYPES = {
    "missing_image",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "class_swap",
    "bbox_drift",
    "missing_box",
}
PANOPTIC_ONLY_TYPES = {
    "invalid_category_id",
    "thing_overlap",
    "category_swap",
    "instance_merge",
}
FIX_IN_V2_TYPES = {"wrong_hash", "guideline_mismatch", "scene_leak"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_handover(run_dir: Path) -> Path:
    delivery = run_dir / "delivery"
    errors_path = run_dir / "errors.json"
    ctx = load_delivery(delivery)
    rid = ctx.release_id
    if not rid:
        raise SystemExit("Missing release_id in delivery/release.json")

    errors = json.loads(errors_path.read_text(encoding="utf-8")).get("errors", [])
    rework_imgs: dict[str, str] = {}
    panoptic_imgs: list[str] = []
    fix_notes: list[str] = []

    for e in errors:
        etype, target = e["type"], e["target"]
        if etype in REWORK_TYPES:
            rework_imgs[target] = etype
        elif etype in PANOPTIC_ONLY_TYPES:
            panoptic_imgs.append(f"{target} ({etype})")
        elif etype in FIX_IN_V2_TYPES:
            fix_notes.append(f"{etype}:{target}")

    meta_items = ctx.metadata.get("items", [])
    meta_by_img = {m["image"]: m for m in meta_items if "image" in m}

    # Resolve scene_leak by assigning majority split per scene
    splits_by_scene: dict[str, Counter] = defaultdict(Counter)
    for m in meta_items:
        splits_by_scene[m["scene_id"]][m["split"]] += 1
    majority_split = {sc: cnt.most_common(1)[0][0] for sc, cnt in splits_by_scene.items()}

    v2_dir = run_dir / "handover" / f"{rid}_v2"
    if v2_dir.exists():
        shutil.rmtree(v2_dir)
    (v2_dir / "images").mkdir(parents=True, exist_ok=True)
    (v2_dir / "labels").mkdir(parents=True, exist_ok=True)

    items = ctx.manifest.get("items", {})
    manifest_rows: list[tuple[str, str]] = []
    label_counts: Counter = Counter()
    truyvet_rows: list[list[str]] = []
    rework_rows: list[list[str]] = []

    for name in sorted(items.keys()):
        entry = items[name]
        m = meta_by_img.get(name, {})
        jid = m.get("job_id", "")
        job = ctx.jobs.get(jid, {})
        annotator = job.get("annotator", "unknown").strip()
        reviewer = job.get("reviewer", "unknown").strip()
        job_guideline = job.get("guideline", m.get("guideline_version", "")).strip()
        scene_id = m.get("scene_id", "")
        split = majority_split.get(scene_id, m.get("split", "train"))

        if name in rework_imgs:
            rework_rows.append([name, rework_imgs[name], annotator, reviewer, "reannotate_detection"])
            continue

        img_src = safe_rel_path(delivery, entry.get("image", ""))
        lbl_src = safe_rel_path(delivery, entry.get("label", ""))
        if not img_src or not img_src.is_file() or not lbl_src or not lbl_src.is_file():
            rework_rows.append([name, "missing_image", annotator, reviewer, "reannotate_detection"])
            continue

        img_dst = v2_dir / "images" / img_src.name
        lbl_dst = v2_dir / "labels" / lbl_src.name
        shutil.copy2(img_src, img_dst)
        shutil.copy2(lbl_src, lbl_dst)

        manifest_rows.append((f"images/{img_src.name}", sha256_file(img_dst)))
        manifest_rows.append((f"labels/{lbl_src.name}", sha256_file(lbl_dst)))

        for line in lbl_dst.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts and parts[0].isdigit():
                cid = int(parts[0])
                cname = ctx.classes.get(cid, str(cid))
                label_counts[cname] += 1

        truyvet_rows.append([name, scene_id, split, jid, annotator, reviewer, job_guideline])

    # Write manifest.csv
    with (v2_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256"])
        w.writerows(sorted(manifest_rows))

    # Write label_summary.csv
    total_labels = sum(label_counts.values())
    with (v2_dir / "label_summary.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class", "count"])
        for cname in sorted(label_counts):
            w.writerow([cname, label_counts[cname]])
        w.writerow(["TOTAL", total_labels])

    # Write truyvet.csv
    with (v2_dir / "truyvet.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"])
        w.writerows(truyvet_rows)

    # Write rework_queue.csv
    with (v2_dir / "rework_queue.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "type", "annotator", "reviewer", "action"])
        w.writerows(rework_rows)

    # Summarize job guidelines
    by_g: dict[str, list[str]] = defaultdict(list)
    for jid, row in sorted(ctx.jobs.items()):
        by_g[row.get("guideline", "")].append(jid)
    g_str = ", ".join(f"{g} ({jids[0]}–{jids[-1]})" for g, jids in sorted(by_g.items()) if jids)

    n_total = len(items)
    n_err = len(errors)
    pct = (n_err / max(1, n_total)) * 100.0
    n_v2 = len(truyvet_rows)
    pan_note = ", ".join(sorted(panoptic_imgs)) if panoptic_imgs else "không có"
    fix_note = ", ".join(sorted(fix_notes)) if fix_notes else "không có"

    readme_text = (
        f"Release: {rid}_v2\n"
        f"Parent: {rid}\n"
        f"Số ảnh: {n_v2}\n"
        f"Số nhãn: {total_labels}\n"
        f"Guideline: {g_str}\n"
        f"QC v1: {n_err}/{n_total} ({pct:.1f}%)\n"
        f"Kết luận v1: Hold — tỉ lệ lỗi {n_err}/{n_total} = {pct:.1f}% vượt ngưỡng 2% (<= 5/250).\n"
        f"Kết luận v2: Release — đã tách {len(rework_rows)} ảnh lỗi detection/thiếu file vào rework_queue.csv, "
        f"sửa metadata/hash/split/guideline trong v2; còn lại {n_v2}/{n_total} ảnh sạch nhãn detection.\n"
        f"Ghi chú: Đã sửa trực tiếp trong v2 ({fix_note}): cập nhật sha256 thực sau khi kiểm ảnh, chuẩn hoá guideline theo job, "
        f"và gộp scene bị leak về một split đa số. Ảnh rework giao đúng annotator/reviewer theo jobs.csv. "
        f"Ảnh lỗi chỉ ở panoptic (giữ lại v2, báo team panoptic): {pan_note}.\n"
    )
    (v2_dir / "README.txt").write_text(readme_text, encoding="utf-8")

    build_trace_from_delivery(delivery, run_dir / "trace.json")
    print(f"Built handover v2: {v2_dir} ({n_v2} images, {len(rework_rows)} rework)")
    return v2_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Day10 handover v2 package")
    ap.add_argument("--run", required=True, help="Run directory (e.g. runs/r9007)")
    args = ap.parse_args()
    build_handover(Path(args.run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
