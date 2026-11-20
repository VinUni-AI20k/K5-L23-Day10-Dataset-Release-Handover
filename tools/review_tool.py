#!/usr/bin/env python3
"""Công cụ trực quan hóa và Review ảnh lỗi gán nhãn (Pha 2 Lab Day 10).

Chức năng:
1. Đọc candidates.json từ cross_check.py và thư mục delivery.
2. Vẽ bounding box Detection (Xanh lá) và bbox của segment panoptic (Cam) lên ảnh.
3. Xuất ảnh đã vẽ vào thư mục visualized/ để mở xem nhanh trên máy.
4. Tạo giao diện HTML standalone (review_dashboard.html) cho phép cả nhóm 5 người:
   - Xem ảnh phóng to, thấy rõ cả 2 nguồn nhãn.
   - Nhập tên reviewer, verdict (confirmed / rejected) và note (>= 20 ký tự).
   - Tải review_log.csv; dashboard không ghi trực tiếp vào file trên máy.
5. Cung cấp chế độ Interactive CLI (nhấn C: confirm, R: reject, S: skip) để review siêu tốc trong 40 phút đề ẩn.

Tác giả: Bạn C (Nhóm Lab Day 10)
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None


def load_classes(delivery_dir: Path) -> list[str]:
    classes_file = delivery_dir / "classes.txt"
    if not classes_file.is_file():
        return []
    lines = classes_file.read_text(encoding="utf-8").splitlines()
    classes = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        classes.append(parts[1] if len(parts) == 2 else parts[0])
    return classes


def load_yolo_boxes(label_file: Path, width: int, height: int, classes: list[str]) -> list[dict]:
    if not label_file.is_file():
        return []
    boxes = []
    for line in label_file.read_text(encoding="utf-8").splitlines():
        p = line.strip().split()
        if len(p) >= 5 and p[0].isdigit():
            cid = int(p[0])
            cname = classes[cid] if 0 <= cid < len(classes) else f"cls_{cid}"
            try:
                xc, yc, w, h = map(float, p[1:5])
            except ValueError:
                continue
            x1 = (xc - w / 2.0) * width
            y1 = (yc - h / 2.0) * height
            x2 = (xc + w / 2.0) * width
            y2 = (yc + h / 2.0) * height
            boxes.append({"cname": cname, "box": (x1, y1, x2, y2), "norm": (xc, yc, w, h)})
    return boxes


def annotate_image(
    img_path: Path,
    boxes: list[dict],
    segs: list[dict],
    cat_by_id: dict[int, dict],
    candidate_info: dict,
    out_path: Path | None = None
) -> Image.Image:
    """Vẽ bounding box của Detection và Panoptic lên ảnh với màu sắc phân biệt."""
    if Image is None:
        raise RuntimeError("Pillow is required for annotate_image. Install with: pip install pillow")

    im = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(im)

    # Thử load font mặc định
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # 1. Vẽ Panoptic segments (Màu Cam / Magenta)
    for s in segs:
        cat_name = cat_by_id.get(s["category_id"], {}).get("name", "unk")
        bx, by, bw, bh = s["bbox"]
        x1, y1, x2, y2 = bx, by, bx + bw, by + bh
        draw.rectangle([x1, y1, x2, y2], outline=(255, 140, 0), width=3)
        draw.text((x1 + 3, max(0, y1 - 12)), f"[PAN] {cat_name}", fill=(255, 140, 0), font=font)

    # 2. Vẽ Detection boxes (Màu Xanh Lá)
    for b in boxes:
        x1, y1, x2, y2 = b["box"]
        draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 100), width=2)
        draw.text((x1 + 3, y1 + 3), f"[DET] {b['cname']}", fill=(0, 255, 100), font=font)

    # 3. Vẽ Banner thông báo lỗi ứng viên ở góc trên
    banner_text = f"CANDIDATE: {candidate_info.get('type')} | {candidate_info.get('suggested_note', '')}"
    draw.rectangle([0, 0, im.width, 24], fill=(30, 30, 30))
    draw.text((8, 5), banner_text, fill=(255, 230, 100), font=font)

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_path, quality=92)

    return im


def generate_html_dashboard(
    candidates: list[dict],
    delivery_dir: Path,
    out_html: Path,
    visualized_dir: Path | None = None
) -> None:
    """Tạo file HTML dashboard tự động để review bằng mắt trong trình duyệt."""
    classes = load_classes(delivery_dir)
    pan_doc = json.loads((delivery_dir / "panoptic.json").read_text(encoding="utf-8"))
    cat_by_id = {c["id"]: c for c in pan_doc.get("categories", [])}
    ann_by_im = {a["image_id"]: a for a in pan_doc.get("annotations", [])}
    im_by_stem = {Path(im["file_name"]).stem: im for im in pan_doc.get("images", [])}

    items_html = []
    for idx, cand in enumerate(candidates):
        stem = cand["image"]
        im_entry = im_by_stem.get(stem)
        if not im_entry:
            continue
        width, height = im_entry["width"], im_entry["height"]
        ann = ann_by_im.get(im_entry["id"], {})
        segs = [s for s in ann.get("segments_info", []) if cat_by_id.get(s["category_id"], {}).get("isthing")]

        label_file = delivery_dir / "labels" / f"{stem}.txt"
        boxes = load_yolo_boxes(label_file, width, height, classes)

        # Lưu ảnh đã vẽ
        img_file = delivery_dir / "images" / f"{stem}.jpg"
        annotated_name = f"{stem}_{cand['type']}.jpg"
        if visualized_dir:
            out_img = visualized_dir / annotated_name
            annotate_image(img_file, boxes, segs, cat_by_id, cand, out_img)
            img_src = f"visualized/{annotated_name}"
        else:
            # Inline base64 nếu không lưu file ảnh
            annotated_im = annotate_image(img_file, boxes, segs, cat_by_id, cand)
            buf = BytesIO()
            annotated_im.save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            img_src = f"data:image/jpeg;base64,{b64}"

        cand_type = cand["type"]
        sug_note = cand.get("suggested_note", "")

        item_card = f"""
        <div class="card" id="card-{idx}">
            <div class="card-header">
                <span class="badge type-{cand_type}">{cand_type}</span>
                <strong>Ảnh: {stem}</strong>
                <span class="info-tag">{cand.get('class') or (cand.get('detection_class', '') + ' ↔ ' + cand.get('panoptic_class', ''))}</span>
            </div>
            <div class="card-body">
                <div class="img-container">
                    <img src="{img_src}" alt="{stem}" onclick="window.open(this.src)">
                    <div class="legend">
                        <span style="color:#00e676">■ Detection (Xanh)</span>
                        <span style="color:#ff9100">■ Panoptic (Cam)</span>
                    </div>
                </div>
                <div class="review-panel">
                    <p class="suggestion">💡 <strong>Gợi ý:</strong> {sug_note}</p>
                    <div class="btn-group">
                        <button type="button" class="btn btn-confirm" onclick="setVerdict({idx}, 'confirmed')">✅ Xác nhận LỖI (Confirmed)</button>
                        <button type="button" class="btn btn-reject" onclick="setVerdict({idx}, 'rejected')">❌ Lệch tự nhiên (Reject)</button>
                    </div>
                    <div class="form-group">
                        <label>Người trực tiếp review (bắt buộc):</label>
                        <input id="reviewer-{idx}" type="text" placeholder="Tên thành viên đã mở và xem ảnh">
                    </div>
                    <div class="form-group">
                        <label>Trạng thái (Verdict):</label>
                        <select id="verdict-{idx}" class="verdict-select" onchange="updateRow({idx})">
                            <option value="">-- Chưa đánh giá --</option>
                            <option value="confirmed">confirmed</option>
                            <option value="rejected">rejected</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Ghi chú (Note - Yêu cầu ≥ 20 ký tự theo Rubric):</label>
                        <textarea id="note-{idx}" rows="3" placeholder="Tự ghi điều quan sát được trong ảnh; không dùng nội dung gợi ý làm kết luận..." oninput="updateRow({idx})"></textarea>
                        <small id="char-count-{idx}" class="char-count">0 ký tự</small>
                    </div>
                </div>
            </div>
        </div>
        """
        items_html.append(item_card)

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Review Ứng Viên Gán Nhãn — Day 10 Lab</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: #121212; color: #e0e0e0; padding: 20px; }}
        header {{ display: flex; justify-content: space-between; align-items: center; background: #1e1e1e; padding: 15px 25px; border-radius: 8px; margin-bottom: 20px; border-bottom: 2px solid #00bcd4; }}
        h1 {{ font-size: 20px; color: #00e5ff; }}
        .toolbar {{ display: flex; gap: 10px; align-items: center; }}
        button.export-btn {{ background: #00c853; color: white; border: none; padding: 10px 18px; border-radius: 6px; font-weight: bold; cursor: pointer; }}
        button.export-btn:hover {{ background: #00b248; }}
        .card {{ background: #1e1e1e; border: 1px solid #333; border-radius: 8px; margin-bottom: 25px; overflow: hidden; }}
        .card-header {{ background: #252525; padding: 12px 20px; display: flex; align-items: center; gap: 15px; font-size: 16px; border-bottom: 1px solid #333; }}
        .badge {{ padding: 4px 10px; border-radius: 4px; font-size: 13px; font-weight: bold; text-transform: uppercase; }}
        .type-class_swap {{ background: #d50000; color: white; }}
        .type-category_swap {{ background: #c51162; color: white; }}
        .type-bbox_drift {{ background: #ff6d00; color: white; }}
        .type-missing_box {{ background: #aa00ff; color: white; }}
        .type-instance_merge {{ background: #2979ff; color: white; }}
        .info-tag {{ background: #37474f; padding: 3px 8px; border-radius: 4px; font-size: 13px; color: #eceff1; }}
        .card-body {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 20px; }}
        @media (max-width: 900px) {{ .card-body {{ grid-template-columns: 1fr; }} }}
        .img-container img {{ width: 100%; max-height: 480px; object-fit: contain; border-radius: 6px; border: 1px solid #444; cursor: pointer; background: #000; }}
        .legend {{ margin-top: 8px; font-size: 13px; display: flex; gap: 15px; }}
        .review-panel {{ display: flex; flex-direction: column; gap: 15px; }}
        .suggestion {{ background: #263238; padding: 10px 14px; border-radius: 6px; font-size: 14px; color: #80deea; line-height: 1.4; }}
        .btn-group {{ display: flex; gap: 10px; }}
        .btn {{ flex: 1; padding: 10px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; }}
        .btn-confirm {{ background: #2e7d32; color: white; }}
        .btn-confirm:hover {{ background: #388e3c; }}
        .btn-reject {{ background: #c62828; color: white; }}
        .btn-reject:hover {{ background: #d32f2f; }}
        .form-group {{ display: flex; flex-direction: column; gap: 6px; }}
        label {{ font-size: 13px; font-weight: bold; color: #b0bec5; }}
        select, textarea {{ background: #2a2a2a; border: 1px solid #444; color: white; padding: 10px; border-radius: 6px; font-size: 14px; }}
        select:focus, textarea:focus {{ outline: none; border-color: #00bcd4; }}
        .char-count {{ font-size: 12px; color: #ffb74d; }}
        .char-ok {{ color: #81c784; }}
    </style>
</head>
<body>
    <header>
        <div>
            <h1>Review Ứng Viên Gán Nhãn (Pha 2 Lab Day 10)</h1>
            <p style="font-size:13px; color:#90a4ae; margin-top:4px;">Tổng số ứng viên: {len(candidates)} | Đội ngũ: Leader Long, A, B, C, D</p>
        </div>
        <div class="toolbar">
            <button class="export-btn" onclick="exportCSV()">📥 Tải review_log.csv</button>
        </div>
    </header>

    <div id="cards-container">
        {"".join(items_html)}
    </div>

    <script>
        const candidates = {json.dumps(candidates, ensure_ascii=False)};

        function setVerdict(idx, verdict) {{
            const vSelect = document.getElementById('verdict-' + idx);
            vSelect.value = verdict;
            updateRow(idx);
        }}

        function updateRow(idx) {{
            const nText = document.getElementById('note-' + idx);
            const counter = document.getElementById('char-count-' + idx);
            const len = nText.value.length;
            counter.innerText = len + ' ký tự ' + (len >= 20 ? '(Đủ chuẩn Rubric ✅)' : '(Cảnh báo: dưới 20 ký tự ⚠️)');
            counter.className = 'char-count ' + (len >= 20 ? 'char-ok' : '');
        }}

        function exportCSV() {{
            const rows = ["image,type,verdict,note"];
            for (let idx = 0; idx < candidates.length; idx++) {{
                const c = candidates[idx];
                const v = document.getElementById('verdict-' + idx).value;
                const reviewer = document.getElementById('reviewer-' + idx).value.trim();
                const n = document.getElementById('note-' + idx).value.trim();
                if (!v) {{
                    continue;
                }}
                if (!reviewer) {{
                    alert(`Nhập tên người đã review ảnh ${{c.image}} trước khi xuất.`);
                    return;
                }}
                if (n.length < 20) {{
                    alert(`Ghi chú cho ảnh ${{c.image}} phải có ít nhất 20 ký tự.`);
                    return;
                }}
                const note = `Người review: ${{reviewer}}. ${{n}}`;
                const quote = value => '"' + String(value).replace(/"/g, '""') + '"';
                rows.push([c.image, c.type, v, note].map(quote).join(","));
            }}
            if (rows.length === 1) {{
                alert("Chưa có ứng viên nào được review.");
                return;
            }}
            const csv = rows.join("\\r\\n") + "\\r\\n";
            const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.setAttribute("download", "review_log.csv");
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }}
    </script>
</body>
</html>
"""
    out_html.write_text(html_content, encoding="utf-8")
    print(f"-> Đã tạo HTML Dashboard tại: {out_html}")


def run_cli_review(candidates: list[dict], out_csv: Path) -> None:
    """Chế độ review trực tiếp qua terminal tiện lợi cho thi đề ẩn."""
    print("\n" + "=" * 60)
    print("CHẾ ĐỘ REVIEW TƯƠNG TÁC QUA TERMINAL (CLI)")
    print("Phím tắt: [c] Xác nhận lỗi (confirmed) | [r] Bác bỏ (rejected) | [s] Bỏ qua (skip)")
    print("=" * 60 + "\n")

    reviews = []
    for idx, c in enumerate(candidates, 1):
        print(f"[{idx}/{len(candidates)}] Ảnh: {c['image']} | Loại lỗi nghi vấn: {c['type']}")
        print(f"   Chi tiết: {c.get('suggested_note', '')}")
        choice = input("   Lựa chọn ([c]onfirm/[r]eject/[s]kip) [mặc định: c]: ").strip().lower() or "c"

        if choice == "c":
            verdict = "confirmed"
        elif choice == "r":
            verdict = "rejected"
        else:
            print("   -> Đã bỏ qua.")
            print("-" * 50)
            continue

        reviewer = ""
        while not reviewer:
            reviewer = input("   Tên người trực tiếp xem ảnh: ").strip()
            if not reviewer:
                print("   Cần ghi tên người đã thực sự review ảnh.")

        note = ""
        while len(note) < 20:
            note = input("   Ghi chú quan sát cụ thể (ít nhất 20 ký tự): ").strip()
            if len(note) < 20:
                print("   Ghi chú chưa đủ 20 ký tự; hãy bổ sung bằng chứng quan sát.")

        full_note = f"Người review: {reviewer}. {note}"
        reviews.append({"image": c["image"], "type": c["type"], "verdict": verdict, "note": full_note})
        print(f"   -> Đã ghi: {verdict} ({len(note)} ký tự ghi chú)")
        print("-" * 50)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "type", "verdict", "note"])
        writer.writeheader()
        writer.writerows(reviews)
    print(f"\n✅ Đã lưu {len(reviews)} dòng review vào {out_csv}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Công cụ xem ảnh và review ứng viên gán nhãn")
    parser.add_argument("--candidates", required=True, help="Đường dẫn file candidates.json")
    parser.add_argument("--delivery", required=True, help="Đường dẫn thư mục delivery")
    parser.add_argument("--out-dir", default=None, help="Thư mục xuất ảnh đã vẽ bounding box (visualized)")
    parser.add_argument("--html", default=None, help="Đường dẫn file HTML dashboard xuất ra")
    parser.add_argument("--cli", action="store_true", help="Chạy chế độ review tương tác trên terminal")
    parser.add_argument("--out-csv", default=None, help="Đường dẫn file review_log.csv xuất ra khi chạy CLI")
    args = parser.parse_args()

    candidates_file = Path(args.candidates)
    delivery_dir = Path(args.delivery)
    if not candidates_file.is_file():
        print(f"Lỗi: Không tìm thấy file {candidates_file}", file=sys.stderr)
        return 1
    if not delivery_dir.is_dir():
        print(f"Lỗi: Không tìm thấy thư mục {delivery_dir}", file=sys.stderr)
        return 1

    doc = json.loads(candidates_file.read_text(encoding="utf-8"))
    candidates = doc.get("candidates", [])
    print(f"Đang chuẩn bị công cụ review cho {len(candidates)} ứng viên...")

    out_dir = Path(args.out_dir) if args.out_dir else delivery_dir.parent / "visualized"
    out_dir.mkdir(parents=True, exist_ok=True)

    html_path = Path(args.html) if args.html else delivery_dir.parent / "review_dashboard.html"
    generate_html_dashboard(candidates, delivery_dir, html_path, visualized_dir=out_dir)

    print(f"\n[Hoàn tất chuẩn bị công cụ review]")
    print(f"- Ảnh trực quan hóa: {out_dir}")
    print(f"- Giao diện review HTML: {html_path}")
    print(f"- Mở review_dashboard.html trong trình duyệt để cả nhóm xem và đánh giá!")

    if args.cli:
        csv_target = Path(args.out_csv) if args.out_csv else delivery_dir.parent / "review_log.csv"
        run_cli_review(candidates, csv_target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
