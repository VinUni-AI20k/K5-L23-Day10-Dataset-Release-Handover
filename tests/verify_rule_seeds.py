"""Chạy toàn bộ luật trên hai seed và lô sạch; dùng scorer chế độ học viên.

    py -X utf8 tests/verify_rule_seeds.py

Không đọc đáp án, không sửa delivery, không ghi đè thư mục đã tồn tại.
Đây là công cụ kiểm thử, không phải validator chạy trên đề ẩn.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(relative, *args):
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT / relative), *map(str, args)],
                   cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs=2, default=[24007, 24008])
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "b_checks")
    args = parser.parse_args()
    if len(set(args.seeds)) != 2:
        parser.error("Cần hai seed khác nhau.")
    for pool in ("coco_panoptic250", "coco_panoptic250_calib"):
        if not (ROOT / "data_source" / pool / "panoptic.json").is_file():
            raise SystemExit("Chưa đủ dữ liệu. Chạy py -X utf8 scripts/download_public.py trước.")
    out = args.out.resolve()
    if out.exists():
        raise SystemExit(f"Không ghi đè {out}. Chọn --out là một thư mục mới.")
    cases = [(f"r{seed}", seed, False) for seed in args.seeds] + [("clean", 5, True)]
    summary = []
    for name, seed, clean in cases:
        dest = out / name
        extra = ["--no-faults"] if clean else []
        run("scripts/inject_release.py", "--seed", seed, "--out", dest, *extra)
        run("validator/validate.py", dest / "delivery", "--out", dest / "rules.json")
        # Các thư mục ở đây mới tạo riêng cho kiểm thử, chưa có kết quả review.
        rules = (dest / "rules.json").read_bytes()
        (dest / "errors.json").write_bytes(rules)
        run("scripts/score_findings.py", "--run", dest)
        errors = json.loads(rules)["errors"]
        summary.append({"case": name, "seed": seed, "clean": clean, "error_count": len(errors),
                        "report": (dest / "report.md").read_text(encoding="utf-8")})
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
        if clean and errors:
            raise SystemExit(f"Lô sạch còn {len(errors)} lỗi luật; kiểm tra {dest / 'rules.json'}.")
    print(f"Đã kiểm hai seed và lô sạch. Số liệu thật: {out / 'summary.json'}")
    print("Đọc F1 lỗi luật trong report từng seed; phần gán nhãn chưa do công cụ này kiểm.")


if __name__ == "__main__":
    main()
