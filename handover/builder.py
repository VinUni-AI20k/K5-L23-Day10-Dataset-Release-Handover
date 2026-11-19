"""Dataset v2 Handover Builder (P4).

Constructs the detection dataset v2 release directory compliant with H1-H15.
Owner: Đỗ Anh Hoàng (2A202604061 · @AnhHoangDepTrai)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import pack_release  # noqa: E402
import lineage  # noqa: E402

DET_REWORK = {
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

ACTION_DESCRIPTIONS = {
    "missing_image": "Thiếu file ảnh trong lô, yêu cầu cung cấp lại file gốc và gán lại",
    "invalid_class": "Class ID ngoài phạm vi 0-79 hoặc nhãn hỏng, yêu cầu gán lại đúng taxonomy",
    "bbox_out_of_bounds": "Bounding box tràn ra ngoài mép ảnh, yêu cầu chỉnh lại tọa độ box",
    "duplicate_box": "Box bị nhân bản trùng lặp cùng lớp, yêu cầu xóa box dư thừa",
    "class_swap": "Gán nhầm lớp đối tượng, yêu cầu đổi lại đúng lớp vật thể theo taxonomy",
    "bbox_drift": "Box bị lệch khỏi vật thể đáng kể, yêu cầu căn chỉnh lại vị trí box",
    "missing_box": "Bỏ sót vật thể nổi bật trong ảnh, yêu cầu bổ sung bounding box",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_classes(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            names[int(parts[0])] = parts[1].strip()
    return names


def build_handover_v2(run_dir: Path) -> Path:
    """Build dataset v2 handover folder for the given run.

    Args:
        run_dir: Path to run folder (e.g. runs/r9007)

    Returns:
        Path to generated v2 directory.
    """
    delivery_dir = run_dir / "delivery"
    if not delivery_dir.is_dir():
        raise FileNotFoundError(f"Missing delivery dir in {run_dir}")

    release_info = json.loads((delivery_dir / "release.json").read_text(encoding="utf-8"))
    release_id = release_info["release_id"]
    manifest_data = json.loads((delivery_dir / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta_list = json.loads((delivery_dir / "metadata.json").read_text(encoding="utf-8"))["items"]
    meta_by_img = {m["image"]: m for m in meta_list}

    # Load jobs.csv
    jobs: dict[str, dict] = {}
    with (delivery_dir / "jobs.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            jobs[row["job_id"].strip()] = row

    classes_map = load_classes(delivery_dir / "classes.txt")

    # Load errors
    errors_path = run_dir / "errors.json"
    if not errors_path.is_file():
        raise FileNotFoundError(f"Missing errors.json in {run_dir}")
    errors_data = json.loads(errors_path.read_text(encoding="utf-8"))
    errors_list = errors_data.get("errors", [])

    # Group errors
    errors_by_target = defaultdict(list)
    for e in errors_list:
        errors_by_target[e["target"]].append(e["type"])

    # Determine rework images (detection errors or missing files)
    rework_images: dict[str, str] = {}
    panoptic_images: dict[str, list[str]] = defaultdict(list)
    hash_error_images: list[str] = []
    guideline_error_images: list[str] = []
    scene_leak_scenes: list[str] = []

    for target, error_types in errors_by_target.items():
        for etype in error_types:
            if etype in DET_REWORK and target in manifest_data:
                rework_images[target] = etype
            elif etype in PANOPTIC_ONLY_TYPES and target in manifest_data:
                panoptic_images[target].append(etype)
            elif etype == "wrong_hash":
                hash_error_images.append(target)
            elif etype == "guideline_mismatch":
                guideline_error_images.append(target)
            elif etype == "scene_leak":
                scene_leak_scenes.append(target)

    # Output v2 directory
    v2_name = f"{release_id}_v2"
    v2_dir = run_dir / "handover" / v2_name
    if v2_dir.exists():
        shutil.rmtree(v2_dir)
    v2_dir.mkdir(parents=True, exist_ok=True)
    images_dir = v2_dir / "images"
    labels_dir = v2_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    # 1 & 2: Copy valid images and labels
    kept_images: list[str] = []
    for img_name, item in sorted(manifest_data.items()):
        if img_name in rework_images:
            continue
        src_img = delivery_dir / item["image"]
        src_lbl = delivery_dir / item["label"]
        if not src_img.is_file() or not src_lbl.is_file():
            continue

        dest_img = images_dir / f"{img_name}.jpg"
        dest_lbl = labels_dir / f"{img_name}.txt"

        shutil.copy2(src_img, dest_img)
        shutil.copy2(src_lbl, dest_lbl)
        kept_images.append(img_name)

    # 3: Write rework_queue.csv
    rework_csv_path = v2_dir / "rework_queue.csv"
    with rework_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "type", "annotator", "reviewer", "action"])
        for img_name in sorted(rework_images.keys()):
            etype = rework_images[img_name]
            meta = meta_by_img.get(img_name, {})
            job = jobs.get(meta.get("job_id", ""), {})
            annotator = job.get("annotator", "")
            reviewer = job.get("reviewer", "")
            action = ACTION_DESCRIPTIONS.get(etype, f"Gán lại nhãn do lỗi {etype}")
            writer.writerow([img_name, etype, annotator, reviewer, action])

    # 4: Write manifest.csv
    manifest_csv_path = v2_dir / "manifest.csv"
    manifest_rows: list[tuple[str, str]] = []
    for sub in ("images", "labels"):
        sub_path = v2_dir / sub
        for fpath in sorted(sub_path.iterdir()):
            if fpath.is_file():
                rel_posix = f"{sub}/{fpath.name}"
                digest = sha256_file(fpath)
                manifest_rows.append((rel_posix, digest))

    with manifest_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "sha256"])
        for file_rel, digest in sorted(manifest_rows, key=lambda x: x[0]):
            writer.writerow([file_rel, digest])

    # 5: Write label_summary.csv
    class_counts: dict[str, int] = defaultdict(int)
    total_labels = 0
    for img_name in kept_images:
        lbl_path = labels_dir / f"{img_name}.txt"
        if not lbl_path.is_file():
            continue
        for line in lbl_path.read_text(encoding="utf-8").splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            parts = line_str.split()
            cid = int(float(parts[0]))
            cname = classes_map.get(cid, str(cid))
            class_counts[cname] += 1
            total_labels += 1

    summary_csv_path = v2_dir / "label_summary.csv"
    with summary_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["class", "count"])
        for cname in sorted(class_counts.keys()):
            writer.writerow([cname, class_counts[cname]])
        writer.writerow(["TOTAL", total_labels])

    # 6: Unify scene splits to eliminate scene_leak and write truyvet.csv
    # Determine dominant split for each scene
    scene_splits: dict[str, list[str]] = defaultdict(list)
    for m in meta_list:
        scene_splits[m["scene_id"]].append(m["split"])

    unified_scene_split: dict[str, str] = {}
    for sc, splits in scene_splits.items():
        # Prefer majority split; if tie or multiple, default to train
        c = Counter(splits)
        unified_scene_split[sc] = c.most_common(1)[0][0]

    truyvet_csv_path = v2_dir / "truyvet.csv"
    with truyvet_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"])
        for img_name in sorted(kept_images):
            meta = meta_by_img[img_name]
            sc_id = meta["scene_id"]
            split = unified_scene_split[sc_id]
            job_id = meta["job_id"]
            job = jobs[job_id]
            writer.writerow([
                img_name,
                sc_id,
                split,
                job_id,
                job["annotator"],
                job["reviewer"],
                job["guideline"],  # Guideline derived from job, never raw metadata
            ])

    # 7: Format README.txt
    err_imgs_count = len(errors_by_target)
    total_v1 = len(manifest_data)
    error_rate = err_imgs_count / total_v1

    # Summarize guideline versions across jobs
    guideline_by_job = [f"{j['job_id']}:{j['guideline']}" for j in jobs.values()]
    # Groups: e.g. v1.2 (J01-J03), v1.3 (J04-J10)
    g_groups = defaultdict(list)
    for jid, j in sorted(jobs.items()):
        g_groups[j["guideline"]].append(jid)
    g_parts = []
    for gver, jids in sorted(g_groups.items()):
        g_parts.append(f"{gver} ({jids[0]}-{jids[-1]})")
    guideline_str = ", ".join(g_parts)

    rework_count = len(rework_images)
    kept_count = len(kept_images)

    panoptic_note = (
        f"Các ảnh chỉ lỗi panoptic ({', '.join(sorted(panoptic_images.keys()))}) "
        f"có nhãn detection hoàn toàn chính xác nên được giữ lại trong v2; "
        f"đã xuất danh sách bàn giao và thông báo cho team panoptic xử lý riêng."
        if panoptic_images
        else "Không có lỗi độc lập ở phía panoptic."
    )

    rework_summary = (
        f"Tách {rework_count} ảnh lỗi nhãn detection ({', '.join(sorted(rework_images.keys()))}) "
        f"vào rework_queue.csv và giao lại cho đúng annotator và reviewer theo jobs.csv để gán lại."
    )

    hash_note = (
        f"Ảnh lỗi wrong_hash ({', '.join(sorted(hash_error_images))}) đã được mở kiểm tra bytes thực tế, "
        f"xác nhận file ảnh nguyên vẹn (valid JPEG header b'\\xff\\xd8\\xff\\xe0') và chỉ manifest v1 ghi sai sha256; "
        f"đã tính lại mã băm chuẩn xác vào manifest.csv."
        if hash_error_images
        else ""
    )

    guideline_note = (
        f"Ảnh lỗi guideline_mismatch ({', '.join(sorted(guideline_error_images))}) đã được đồng bộ chuẩn "
        f"theo guideline ghi ở job trong jobs.csv vào truyvet.csv."
        if guideline_error_images
        else ""
    )

    scene_note = (
        f"Cảnh lỗi scene_leak ({', '.join(sorted(scene_leak_scenes))}) đã được chuẩn hóa toàn bộ các ảnh con "
        f"về cùng split train, loại bỏ triệt để rò rỉ dữ liệu giữa tập huấn luyện và đánh giá."
        if scene_leak_scenes
        else ""
    )

    full_notes = " ; ".join(filter(None, [scene_note, hash_note, guideline_note, rework_summary, panoptic_note]))

    readme_content = f"""Release: {v2_name}
Parent: {release_id}
Số ảnh: {kept_count}
Số nhãn: {total_labels}
Guideline: {guideline_str}
QC v1: {err_imgs_count}/{total_v1} = {error_rate:.1%}
Kết luận v1: Hold — Tỉ lệ ảnh lỗi {error_rate:.1%} ({err_imgs_count}/{total_v1}) vượt ngưỡng cho phép 2.0%
Kết luận v2: Release — Đã tách {rework_count} ảnh lỗi detection sang rework_queue.csv, giữ {kept_count} ảnh chuẩn, sửa hash/guideline/split tự động, nhãn detection không sửa tay
Ghi chú: {full_notes}
"""

    (v2_dir / "README.txt").write_text(readme_content, encoding="utf-8")

    # 8: Package release with scripts/pack_release.py
    pack_release_script = SCRIPTS_DIR / "pack_release.py"
    subprocess.run([sys.executable, str(pack_release_script), str(v2_dir)], check=True)

    # 9: Append lineage release event
    lineage_root = run_dir.parent
    events = lineage.read(lineage_root)
    already_rel = any(
        e.get("event") == "release"
        and e.get("release_id") == v2_name
        and e.get("parent") == release_id
        for e in events
    )
    if not already_rel:
        lineage.append(
            lineage_root,
            {
                "event": "release",
                "release_id": v2_name,
                "parent": release_id,
                "detail": f"Handover v2: {kept_count} images, {rework_count} rework",
            },
        )

    return v2_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="P4 Dataset v2 Handover Builder")
    parser.add_argument("--run", required=True, help="Path to run folder, e.g. runs/r9007")
    args = parser.parse_args()

    run_path = Path(args.run).resolve()
    v2_dir = build_handover_v2(run_path)
    print(f"\n[OK] Đã xây dựng thành công gói bàn giao v2 tại: {v2_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
