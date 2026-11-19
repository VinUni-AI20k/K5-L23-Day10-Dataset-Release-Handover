"""One-command Day10 QC Intelligence Engine CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qc_factory_day10.evaluation.benchmark import run_benchmarks
from qc_factory_day10.orchestration.pipeline import finalize_challenge, run_challenge_pipeline


def cmd_doctor() -> int:
    checks = {
        "python_version": sys.version.split()[0],
        "python_ok": sys.version_info >= (3, 10),
        "validator_exists": (ROOT / "validator" / "validate.py").is_file(),
        "pngutil_exists": (ROOT / "scripts" / "pngutil.py").is_file(),
        "check_handover_exists": (ROOT / "scripts" / "check_handover.py").is_file(),
        "team_md_exists": (ROOT / "submission" / "TEAM.md").is_file(),
        "r9007_delivery_exists": (ROOT / "runs" / "r9007" / "delivery" / "manifest.json").is_file(),
        "clean_delivery_exists": (ROOT / "runs" / "clean" / "delivery" / "manifest.json").is_file(),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    ok = checks["python_ok"] and checks["validator_exists"] and checks["pngutil_exists"]
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Day10 QC Intelligence Engine CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Verify environment, validator, and scripts")
    sub.add_parser("benchmark", help="Run authorized benchmarks on runs/clean and runs/r9007")

    p_ch = sub.add_parser("challenge", help="Run preflight, validator, triage, trace, and optional Review UI")
    p_ch.add_argument("--input", required=True, help="Path to delivery directory (e.g. delivery)")
    p_ch.add_argument("--out-dir", default="submission/de_an", help="Output directory (outside delivery)")
    p_ch.add_argument("--serve", action="store_true", help="Start interactive Review UI server")
    p_ch.add_argument("--port", type=int, default=8765, help="HTTP port for Review UI")

    p_fin = sub.add_parser("finalize", help="Export review_log.csv, merge confirmed errors, verify outputs")
    p_fin.add_argument("--run", default="submission/de_an", help="Output directory to finalize")

    args = ap.parse_args()
    if args.cmd == "doctor":
        return cmd_doctor()
    if args.cmd == "benchmark":
        res = run_benchmarks()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "challenge":
        res = run_challenge_pipeline(
            delivery=Path(args.input),
            out_dir=Path(args.out_dir),
            serve=args.serve,
            port=args.port,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1
    if args.cmd == "finalize":
        res = finalize_challenge(Path(args.run))
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
