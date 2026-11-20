"""Gộp lỗi luật và xuất ứng viên để nhóm xem ảnh."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path, help="Thư mục lô cần kiểm tra")
    parser.add_argument("--out", required=True, type=Path, help="File JSON lỗi luật")
    parser.add_argument("--candidates", type=Path, help="File JSON ứng viên xem ảnh")
    args = parser.parse_args()

    delivery = args.delivery.resolve()
    rules_path = args.out.resolve()
    candidates_path = args.candidates.resolve() if args.candidates else None
    if not delivery.is_dir():
        parser.error(f"Không tìm thấy thư mục delivery: {delivery}")
    output_paths = (rules_path, candidates_path) if candidates_path else (rules_path,)
    for path in output_paths:
        if path.is_relative_to(delivery):
            parser.error(f"Hãy lưu kết quả bên ngoài delivery: {path}")
    if candidates_path == rules_path:
        parser.error("--out và --candidates cần hai đường dẫn khác nhau")

    try:
        import rulefiles
        import rulelabels

        if candidates_path:
            import labelmatch
            import maskchecks
    except ModuleNotFoundError as error:
        if error.name in {"rulefiles", "rulelabels", "labelmatch", "maskchecks"}:
            parser.error(f"Chưa có validator/{error.name}.py. Xem validator/README.md.")
        raise

    findings = rulefiles.find_errors(delivery) + rulelabels.find_errors(delivery)
    pairs = {(finding["type"], finding["target"]) for finding in findings}
    errors = [{"type": kind, "target": target} for kind, target in sorted(pairs)]
    if candidates_path:
        matches = labelmatch.build_matches(delivery)
        candidates = labelmatch.find_candidates(matches) + maskchecks.find_candidates(matches)
        write_json(candidates_path, {"candidates": candidates})
        print(f"{len(candidates)} ứng viên → {candidates_path}")

    write_json(rules_path, {"errors": errors})
    print(f"{len(errors)} lỗi luật → {rules_path}")


if __name__ == "__main__":
    main()
