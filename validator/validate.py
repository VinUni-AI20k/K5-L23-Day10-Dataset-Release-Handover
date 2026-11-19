#!/usr/bin/env python3
"""validate.py <delivery> --out errors.json [--candidates candidates.json]

Chỉ đọc thư mục delivery được truyền vào. Chỉ dùng thư viện chuẩn.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MODULES = ["rules_file_det", "rules_meta_pan"]  # Tùng, Hương


def main() -> int:
    ap = argparse.ArgumentParser(description="Validator của nhóm 30")
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True)
    ap.add_argument("--candidates", help="phần đối chiếu detection-panoptic (Việt), chưa có")
    args = ap.parse_args()
    delivery = Path(args.delivery)
    if not (delivery / "manifest.json").is_file():
        raise SystemExit(f"{delivery} không có manifest.json: không phải thư mục delivery")
    found = set()
    failed = []
    for name in MODULES:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            print(f"[bỏ qua] chưa có module {name}", file=sys.stderr)
            continue
        try:
            results = mod.check(delivery)
        except Exception:
            print(f"[LỖI] module {name} bị crash, bỏ qua kết quả của nó:", file=sys.stderr)
            traceback.print_exc()
            failed.append(name)
            continue
        for e in results:
            found.add((e["type"], e["target"]))
    errors = [{"type": t, "target": g} for t, g in sorted(found)]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"errors": errors}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(errors)} lỗi -> {out}")
    for kind, n in sorted(Counter(t for t, _ in found).items()):
        print(f"  {kind}: {n}")
    if args.candidates:
        try:
            import cross_check
            cands = cross_check.extract_candidates(delivery)
            cand_path = Path(args.candidates)
            cand_path.parent.mkdir(parents=True, exist_ok=True)
            cand_path.write_text(json.dumps({"candidates": cands}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Trích xuất {len(cands)} ứng viên gán nhãn -> {cand_path}")
        except Exception:
            print("[LỖI] Trích xuất candidates thất bại:", file=sys.stderr)
            traceback.print_exc()

    if failed:
        print(f"CẢNH BÁO: {out} THIẾU kết quả của module: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())