"""Validator nhóm 30.

python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

Gộp các module kiểm:
- checks_file_detection.py : file + detection     (Đỗ Quang Tùng)
- checks_meta_panoptic.py  : metadata + panoptic  (Đặng Thu Hương)
- candidates.py            : đối chiếu det <-> panoptic (Nguyễn Quốc Việt)
Module nào chưa có thì bỏ qua.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RULE_MODULES = ["checks_file_detection", "checks_meta_panoptic"]


def _optional(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        print(f"[validate] chưa có module {name}, bỏ qua", file=sys.stderr)
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Validator nhóm 30")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--candidates", type=Path)
    args = ap.parse_args()

    errors: list[dict] = []
    for name in RULE_MODULES:
        mod = _optional(name)
        if mod is not None:
            errors += mod.check(args.delivery)

    # mỗi cặp (type, target) một lần
    seen, unique = set(), []
    for e in errors:
        key = (e["type"], e["target"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"errors": unique}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(unique)} lỗi luật -> {args.out}")

    if args.candidates:
        mod = _optional("candidates")
        cands = mod.candidates(args.delivery) if mod is not None else []
        args.candidates.parent.mkdir(parents=True, exist_ok=True)
        args.candidates.write_text(json.dumps({"candidates": cands}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(cands)} ứng viên -> {args.candidates}")


if __name__ == "__main__":
    main()
