"""Orchestration pipeline for Day10 challenge and practice runs."""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from qc_factory_day10.adapters.delivery_reader import load_delivery, run_preflight, safe_rel_path
from qc_factory_day10.engine.difficulty import build_triage
from qc_factory_day10.review.review_store import ReviewStore
from qc_factory_day10.review.reviewer_assignment import assign_reviewers, load_team_members
from qc_factory_day10.review.server import serve_blocking

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PY = ROOT / "validator" / "validate.py"


def build_trace_from_delivery(delivery: Path, out_path: Path) -> dict[str, Any]:
    """Deterministically build trace.json using job-level guideline in jobs.csv (not image metadata)."""
    ctx = load_delivery(delivery)
    ticket_path = delivery / "incoming" / "ticket.md"
    changelog_path = delivery / "guideline" / "changelog.md"
    ticket_text = ticket_path.read_text(encoding="utf-8") if ticket_path.is_file() else ""
    changelog_text = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else ""

    # Parse scenes mentioned in ticket.md (e.g., scene_123)
    reported_scenes = set(re.findall(r"scene_\d+", ticket_text))

    # Parse old guideline version and changed class names from changelog.md + classes.txt
    old_ver_match = re.search(r"(v\d+\.\d+)\s*(?:→|->|to)\s*(v\d+\.\d+)", changelog_text)
    old_ver = old_ver_match.group(1) if old_ver_match else "v1.2"
    cls_names = set(ctx.classes.values())
    changed_classes = {
        cname for cname in cls_names
        if re.search(rf"\b{re.escape(cname)}\b", changelog_text + "\n" + ticket_text, re.IGNORECASE)
    }
    changed_cls_ids = {cid for cid, cname in ctx.classes.items() if cname in changed_classes}

    meta_items = ctx.metadata.get("items", [])
    items = ctx.manifest.get("items", {})

    tier_a: list[str] = []
    tier_b: list[str] = []
    notify_people: set[str] = set()

    for m in meta_items:
        img = m.get("image", "")
        jid = m.get("job_id", "")
        scene = m.get("scene_id", "")
        job = ctx.jobs.get(jid, {})
        if job.get("guideline") != old_ver:
            continue
        lbl_rel = items.get(img, {}).get("label", "")
        lbl_path = safe_rel_path(delivery, lbl_rel) if lbl_rel else None
        has_changed_cls = False
        if lbl_path and lbl_path.is_file():
            for line in lbl_path.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if parts and parts[0].isdigit() and int(parts[0]) in changed_cls_ids:
                    has_changed_cls = True
                    break
        if not has_changed_cls:
            continue

        if scene in reported_scenes:
            tier_a.append(img)
        else:
            tier_b.append(img)
        if job.get("annotator"):
            notify_people.add(job["annotator"].strip())
        if job.get("reviewer"):
            notify_people.add(job["reviewer"].strip())

    trace = {
        "tier_a": sorted(set(tier_a)),
        "tier_b": sorted(set(tier_b)),
        "notify": sorted(notify_people),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace


def run_challenge_pipeline(
    delivery: Path,
    out_dir: Path,
    team_md: Path | None = None,
    serve: bool = False,
    port: int = 8765,
) -> dict[str, Any]:
    """Run preflight, official validator, triage, reviewer assignment, SQLite seeding, and trace."""
    t0 = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)

    preflight = run_preflight(delivery, out_path=out_dir / "preflight_report.json")
    if not preflight["ready_for_qc"]:
        return {"ok": False, "stage": "preflight", "preflight": preflight}

    rules_errors_path = out_dir / "rules_errors.json"
    errors_path = out_dir / "errors.json"
    candidates_path = out_dir / "candidates.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PY),
            str(delivery),
            "--out",
            str(rules_errors_path),
            "--candidates",
            str(candidates_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    if not errors_path.is_file():
        errors_path.write_text(rules_errors_path.read_text(encoding="utf-8"), encoding="utf-8")

    rule_errors = json.loads(rules_errors_path.read_text(encoding="utf-8")).get("errors", [])
    candidates = json.loads(candidates_path.read_text(encoding="utf-8")).get("candidates", [])

    ctx = load_delivery(delivery)
    triage_rows, summary = build_triage(ctx, rule_errors, candidates, out_dir=None)
    reviewers = load_team_members(team_md or (ROOT / "submission" / "TEAM.md"))
    assign_reviewers(triage_rows, reviewers)

    # Write triage.csv & difficulty_summary.json with assigned_reviewer included
    summary["elapsed_sec"] = round(time.perf_counter() - t0, 3)
    csv_path = out_dir / "triage.csv"
    fieldnames = [
        "image_id", "kind", "candidate_type", "difficulty_tier",
        "difficulty_score", "error_evidence_score", "review_value_score",
        "priority", "assigned_reviewer", "reason", "handling",
        "num_detections", "num_panoptic_instances", "evidence",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in triage_rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    (out_dir / "difficulty_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    store = ReviewStore(out_dir / "review_state.db")
    store.seed_candidates(triage_rows, candidates)

    trace = build_trace_from_delivery(delivery, out_dir / "trace.json")

    result = {
        "ok": True,
        "elapsed_sec": summary["elapsed_sec"],
        "preflight_fingerprint": preflight["fingerprint"],
        "rule_errors": len(rule_errors),
        "semantic_candidates": len(candidates),
        "tiers": summary["tiers"],
        "trace_counts": {k: len(v) for k, v in trace.items()},
        "validator_stdout": proc.stdout.strip(),
    }

    if serve:
        serve_blocking(ctx, store, out_dir, reviewers, port=port)

    return result


def finalize_challenge(out_dir: Path) -> dict[str, Any]:
    """Export human review_log.csv, merge confirmed errors into errors.json, and verify schemas."""
    db_path = out_dir / "review_state.db"
    if db_path.is_file():
        store = ReviewStore(db_path)
        review_rows = store.export_review_log(out_dir / "review_log.csv")
        base_errs = out_dir / "rules_errors.json"
        if not base_errs.is_file():
            base_errs = out_dir / "errors.json"
        total_errors = store.merge_confirmed_into_errors(base_errs, out_dir / "errors.json")
        st = store.stats()
    else:
        review_rows = 0
        total_errors = len(json.loads((out_dir / "errors.json").read_text(encoding="utf-8")).get("errors", []))
        st = {"pending": 0, "reviewed": 0}

    required = ["errors.json", "candidates.json", "review_log.csv", "trace.json"]
    missing = [f for f in required if not (out_dir / f).is_file()]
    return {
        "ok": len(missing) == 0,
        "missing_files": missing,
        "review_rows_exported": review_rows,
        "total_errors": total_errors,
        "pending_reviews": st.get("pending", 0),
        "reviewed": st.get("reviewed", 0),
    }
