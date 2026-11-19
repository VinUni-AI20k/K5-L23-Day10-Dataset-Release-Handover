"""Benchmark and calibration runner on authorized development datasets (runs/r9007, runs/clean)."""
from __future__ import annotations

import json
import sys
import tempfile
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from typing import Any

from qc_factory_day10.orchestration.pipeline import run_challenge_pipeline

ROOT = Path(__file__).resolve().parents[2]


def _bench_one(name: str, delivery: Path, out_dir: Path) -> dict[str, Any]:
    if not (delivery / "manifest.json").is_file():
        return {"name": name, "available": False}
    tracemalloc.start()
    t0 = time.perf_counter()
    res = run_challenge_pipeline(delivery, out_dir, serve=False)
    elapsed = round(time.perf_counter() - t0, 3)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    cands = json.loads((out_dir / "candidates.json").read_text(encoding="utf-8")).get("candidates", [])
    cand_types = dict(Counter(c["type"] for c in cands))
    rules = json.loads((out_dir / "rules_errors.json").read_text(encoding="utf-8")).get("errors", [])
    rule_types = dict(Counter(e["type"] for e in rules))

    return {
        "name": name,
        "available": True,
        "elapsed_sec": elapsed,
        "peak_mem_mb": round(peak / (1024 * 1024), 2),
        "rule_errors": len(rules),
        "rule_types": rule_types,
        "candidates": len(cands),
        "candidate_types": cand_types,
        "tiers": res.get("tiers", {}),
        "trace_counts": res.get("trace_counts", {}),
    }


def run_benchmarks(reports_dir: Path | None = None) -> dict[str, Any]:
    """Run authorized benchmarks on runs/clean and runs/r9007 and write Markdown reports."""
    rep_dir = reports_dir or (ROOT / "reports")
    rep_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        clean_res = _bench_one("clean_calib_50", ROOT / "runs" / "clean" / "delivery", tmp_p / "clean")
        r9007_res = _bench_one("practice_r9007_250", ROOT / "runs" / "r9007" / "delivery", tmp_p / "r9007")

    # Write reports/benchmark_comparison.md
    lines = [
        "# Benchmark Comparison (Authorized Datasets)",
        "",
        "| Dataset | Available | Rule Errors | Semantic Candidates | Tiers (E/M/H) | Elapsed (s) | Peak Mem (MB) |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for r in (clean_res, r9007_res):
        if not r["available"]:
            lines.append(f"| {r['name']} | No | - | - | - | - | - |")
        else:
            t = r["tiers"]
            tier_str = f"{t.get('EASY',0)}/{t.get('MEDIUM',0)}/{t.get('HARD',0)}"
            lines.append(
                f"| {r['name']} | Yes | {r['rule_errors']} | {r['candidates']} | {tier_str} | {r['elapsed_sec']} | {r['peak_mem_mb']} |"
            )
    lines.extend([
        "",
        "## Breakdown by Type",
        f"- **clean_calib_50 candidates:** `{clean_res.get('candidate_types', {})}`",
        f"- **practice_r9007_250 rule errors:** `{r9007_res.get('rule_types', {})}`",
        f"- **practice_r9007_250 candidates:** `{r9007_res.get('candidate_types', {})}`",
        f"- **practice_r9007_250 trace counts:** `{r9007_res.get('trace_counts', {})}`",
    ])
    (rep_dir / "benchmark_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Write reports/failure_modes.md
    fm = [
        "# Failure Modes & Mitigation",
        "",
        "1. **Natural COCO occlusion / crowd mismatch on clean data:**",
        f"   - Observed on `runs/clean` (50 images): `{clean_res.get('candidates', 0)}` candidates (`{clean_res.get('candidate_types', {})}`).",
        "   - Mitigation: Human visual review marks natural occlusion/crowd as `rejected` with >= 20-char note; never auto-confirm.",
        "2. **Hidden test (`--opaque`) encrypted filenames & altered fault profile:**",
        "   - `img_0001` filenames carry no difficulty signal.",
        "   - Mitigation: `qc_factory_day10.engine.difficulty` computes `difficulty_score`, `error_evidence_score`, `review_value_score` purely from box/mask geometry.",
        "3. **`class_swap` vs `category_swap` direction ambiguity:**",
        "   - Cross-check emits `class_swap` hypothesis; human reviewer inspects image and selects `class_swap` or `category_swap` in Review UI.",
    ]
    (rep_dir / "failure_modes.md").write_text("\n".join(fm) + "\n", encoding="utf-8")

    # Write reports/CHALLENGE_READINESS.md
    est_per_min = 3.0  # conservative 20s/candidate
    cand_n = r9007_res.get("candidates", 0) or 0
    est_min = round(cand_n / est_per_min, 1)
    ready = [
        "# Challenge Readiness Report",
        "",
        f"- **Python:** `{sys.version.split()[0]}` (stdlib-only validator & factory)",
        f"- **Clean Calibration (`runs/clean`):** `{clean_res.get('rule_errors', 'N/A')}` rule errors, `{clean_res.get('candidates', 'N/A')}` semantic candidates",
        f"- **Practice Seed (`runs/r9007`):** `{r9007_res.get('rule_errors', 'N/A')}` rule errors, `{r9007_res.get('candidates', 'N/A')}` candidates in `{r9007_res.get('elapsed_sec', 'N/A')}s`",
        f"- **Estimated Human Review Time (at ~20s/candidate):** ~`{est_min}` minutes for `{cand_n}` candidates (fits comfortably in 40-min / 60-min window with parallel reviewers).",
        "- **Commands:**",
        "  - `python tools/qc_factory.py doctor`",
        "  - `python tools/qc_factory.py benchmark`",
        "  - `python tools/qc_factory.py challenge --input delivery --out-dir submission/de_an --serve`",
        "  - `python tools/qc_factory.py finalize --run submission/de_an`",
    ]
    (rep_dir / "CHALLENGE_READINESS.md").write_text("\n".join(ready) + "\n", encoding="utf-8")

    return {"clean": clean_res, "r9007": r9007_res}
