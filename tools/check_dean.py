#!/usr/bin/env python3
"""Script Sanity Check tự động kiểm định 4 file bài nộp Đề ẩn (submission/de_an/).

Tác giả: phuchoangpath (TV4)
Cách dùng:
    python tools/check_dean.py --sub submission/de_an [--delivery delivery]

Kiểm tra:
1. errors.json: Cú pháp JSON chuẩn, không trùng lặp target, scene_leak target là scene_id.
2. review_log.csv: Mọi lỗi ngữ nghĩa đều có verdict=confirmed, note >= 20 ký tự, >= 70% unique note.
3. trace.json: Đủ tier_a, tier_b, notify; không rỗng; người notify thuộc danh sách jobs.csv.
4. Báo cáo tổng thể PASS / FAIL chuẩn xác trong 1 giây.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SEMANTIC_TYPES = {
    "class_swap",
    "bbox_drift",
    "missing_box",
    "category_swap",
    "instance_merge",
}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def check_dean(sub_dir: Path, delivery_dir: Path | None = None) -> int:
    print(f"=== BẮT ĐẦU SANITY CHECK THƯ MỤC: {sub_dir} ===")
    fails = 0

    def check(code: str, condition: bool, msg_ok: str, msg_fail: str):
        nonlocal fails
        if condition:
            print(f"  [PASS] {code:<6} {msg_ok}")
        else:
            print(f"  [FAIL] {code:<6} {msg_fail}")
            fails += 1

    # 1. errors.json
    err_file = sub_dir / "errors.json"
    errors = []
    if not err_file.is_file():
        check("E1", False, "", f"Không tìm thấy file {err_file}")
    else:
        try:
            doc = json.loads(err_file.read_text(encoding="utf-8"))
            errors = doc.get("errors", [])
            check("E1", isinstance(errors, list) and len(errors) > 0, f"errors.json hợp lệ, có {len(errors)} lỗi", "errors.json rỗng hoặc không có mảng errors")
            
            # Kiểm tra trùng lặp
            pairs = [(e.get("type"), e.get("target")) for e in errors]
            dup = len(pairs) - len(set(pairs))
            check("E2", dup == 0, "Không có lỗi (type, target) bị trùng lặp", f"Có {dup} cặp (type, target) bị khai báo trùng lặp")
            
            # Kiểm tra scene_leak target
            bad_scene = [e["target"] for e in errors if e.get("type") == "scene_leak" and not str(e.get("target", "")).startswith("scene_")]
            check("E3", len(bad_scene) == 0, "Mọi lỗi scene_leak có target là scene_id", f"scene_leak sai target (phải là scene_id): {bad_scene}")
        except Exception as ex:
            check("E1", False, "", f"Lỗi cú pháp JSON trong errors.json: {ex}")

    # 2. review_log.csv
    rev_file = sub_dir / "review_log.csv"
    if not rev_file.is_file():
        check("R1", False, "", f"Không tìm thấy file {rev_file}")
    else:
        try:
            rows = read_csv(rev_file)
            check("R1", len(rows) > 0, f"review_log.csv có {len(rows)} dòng đánh giá", "review_log.csv rỗng")
            
            # Mọi lỗi ngữ nghĩa phải có confirmed
            confirmed_set = {(r.get("type", "").strip(), r.get("image", "").strip()) for r in rows if r.get("verdict", "").strip() == "confirmed"}
            need_set = {(e.get("type"), e.get("target")) for e in errors if e.get("type") in SEMANTIC_TYPES}
            missing_conf = need_set - confirmed_set
            check("R2", len(missing_conf) == 0, f"Đủ confirmed cho {len(need_set)} lỗi gán nhãn", f"Thiếu confirmed cho các lỗi gán nhãn: {missing_conf}")

            # Kiểm tra độ dài ghi chú >= 20 ký tự
            short_notes = [r for r in rows if len(r.get("note", "").strip()) < 20]
            check("R3", len(short_notes) == 0, "100% ghi chú đạt độ dài >= 20 ký tự", f"Có {len(short_notes)} dòng ghi chú quá ngắn (< 20 ký tự)")

            # Kiểm tra tỷ lệ unique note >= 70%
            notes = [r.get("note", "").strip() for r in rows]
            uniq_rate = len(set(notes)) / len(notes) if notes else 0.0
            check("R4", uniq_rate >= 0.70, f"Tỷ lệ ghi chú độc nhất: {uniq_rate:.1%} (>= 70%)", f"Ghi chú bị chép trùng lặp nhiều: {uniq_rate:.1%} (< 70%)")
        except Exception as ex:
            check("R1", False, "", f"Lỗi đọc review_log.csv: {ex}")

    # 3. trace.json
    tr_file = sub_dir / "trace.json"
    if not tr_file.is_file():
        check("T1", False, "", f"Không tìm thấy file {tr_file}")
    else:
        try:
            tr = json.loads(tr_file.read_text(encoding="utf-8"))
            t_ok = all(isinstance(tr.get(k), list) for k in ("tier_a", "tier_b", "notify"))
            check("T1", t_ok, "trace.json chứa đủ 3 mảng: tier_a, tier_b, notify", "trace.json thiếu trường hoặc không phải dạng list")
            check("T2", len(tr.get("tier_a", [])) > 0 and len(tr.get("notify", [])) > 0, f"tier_a ({len(tr.get('tier_a', []))} ảnh) và notify ({len(tr.get('notify', []))} người) có dữ liệu", "tier_a hoặc notify bị rỗng")

            if delivery_dir and (delivery_dir / "jobs.csv").is_file():
                jobs_rows = read_csv(delivery_dir / "jobs.csv")
                valid_people = {j["annotator"] for j in jobs_rows} | {j["reviewer"] for j in jobs_rows}
                bad_notify = [p for p in tr.get("notify", []) if p not in valid_people]
                check("T3", len(bad_notify) == 0, "Người cần notify thuộc danh sách jobs.csv", f"Người notify lạ không có trong jobs.csv: {bad_notify}")
        except Exception as ex:
            check("T1", False, "", f"Lỗi đọc trace.json: {ex}")

    print("\n" + "=" * 45)
    if fails == 0:
        print("=> KẾT QUẢ: 100% ĐẠT ĐIỀU KIỆN! SẴN SÀNG COMMIT & NỘP BÀI.")
        return 0
    else:
        print(f"=> KẾT QUẢ: CÓ {fails} TIÊU CHÍ CHƯA ĐẠT! VUI LÒNG SỬA TRƯỚC KHI NỘP.")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Sanity check đề ẩn trước khi nộp")
    parser.add_argument("--sub", default="submission/de_an", help="Thư mục nộp bài đề ẩn")
    parser.add_argument("--delivery", default=None, help="Thư mục delivery của đề ẩn để đối chiếu jobs.csv")
    args = parser.parse_args()

    sub_path = Path(args.sub)
    del_path = Path(args.delivery) if args.delivery else None
    sys.exit(check_dean(sub_path, del_path))


if __name__ == "__main__":
    main()

