#!/usr/bin/env python3
"""Validator của nhóm — Day 10 Lab (TV1 - Zeus-AIE điều phối CLI).

Giao diện cố định:
  python validator/validate.py <thu_muc_delivery> --out <errors.json> [--candidates <candidates.json>]

Ràng buộc tuân thủ RULES.md:
- Chỉ đọc bên trong thư mục <thu_muc_delivery> được truyền vào.
- Chỉ sử dụng thư viện chuẩn Python (cùng scripts/pngutil.py cho module panoptic).
- Không truy cập _private/, data_source/, annotation COCO hay mạng.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VALIDATOR_DIR = Path(__file__).resolve().parent
if str(VALIDATOR_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATOR_DIR))

from det_rules import check_detection_rules  # noqa: E402

try:
    from pan_rules import check_panoptic_rules  # noqa: E402
except ImportError:
    check_panoptic_rules = None

try:
    from cross_check import find_candidates  # noqa: E402
except ImportError:
    find_candidates = None


def run_validation(delivery: Path, candidates_out: Path | None = None) -> tuple[list[dict], list[dict] | None]:
    """Chạy lỗi luật Detection + Panoptic và (tuỳ chọn) đối chiếu sinh ứng viên."""
    errors: list[dict] = []
    errors.extend(check_detection_rules(delivery))

    if check_panoptic_rules is not None:
        errors.extend(check_panoptic_rules(delivery))
    else:
        print(
            "[WARN] Chưa có validator/pan_rules.py (TV2 - Manhtd285): tạm bỏ qua 2 lỗi luật panoptic.",
            file=sys.stderr,
        )

    # Khử trùng lặp và sắp xếp cố định theo (type, target)
    unique_pairs = sorted({(e["type"], e["target"]) for e in errors})
    final_errors = [{"type": t, "target": g} for t, g in unique_pairs]

    candidates: list[dict] | None = None
    if candidates_out is not None:
        rule_targets = {g for t, g in unique_pairs if t != "scene_leak"}
        if find_candidates is not None:
            candidates = find_candidates(delivery, rule_targets=rule_targets)
        else:
            print(
                "[WARN] Chưa có validator/cross_check.py (TV2 - Manhtd285): ghi danh sách ứng viên rỗng.",
                file=sys.stderr,
            )
            candidates = []

    return final_errors, candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kiểm tra lỗi luật và đối chiếu detection <-> panoptic trên thư mục delivery."
    )
    parser.add_argument("delivery", help="Đường dẫn tới thư mục delivery (v1 hoặc đề ẩn)")
    parser.add_argument("--out", required=True, help="Đường dẫn file JSON ghi danh sách lỗi luật")
    parser.add_argument(
        "--candidates",
        help="Đường dẫn file JSON ghi danh sách ứng viên lỗi gán nhãn cần mở ảnh review",
    )
    args = parser.parse_args()

    delivery = Path(args.delivery)
    if not delivery.is_dir():
        raise SystemExit(f"Không tìm thấy thư mục delivery: {delivery}")

    out_path = Path(args.out)
    cand_path = Path(args.candidates) if args.candidates else None

    errors, candidates = run_validation(delivery, candidates_out=cand_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"errors": errors}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Đã ghi {len(errors)} lỗi luật -> {out_path}")

    if cand_path is not None and candidates is not None:
        cand_path.parent.mkdir(parents=True, exist_ok=True)
        cand_path.write_text(
            json.dumps({"candidates": candidates}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Đã ghi {len(candidates)} ứng viên cần review -> {cand_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
