"""Release Gate logic and Lineage management (P3).

Implements the 2% threshold decision rule (Day 7) and lineage blast radius tracking.
Owner: Đỗ Anh Hoàng (2A202604061 · @AnhHoangDepTrai)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import lineage  # noqa: E402


RELEASE_THRESHOLD = 0.02  # Max allowed error rate (2.0%)


def evaluate_release_gate(
    run_dir: Path,
    lineage_root: Path | None = None,
    record: bool = True,
) -> dict:
    """Evaluate whether delivery v1 passes the release gate and optionally record to lineage.

    Args:
        run_dir: Path to the run folder (e.g. runs/r9007)
        lineage_root: Root directory where lineage.jsonl lives (defaults to run_dir.parent)
        record: Whether to write the decision event to lineage.jsonl

    Returns:
        Dict with metrics, decision, and impact analysis.
    """
    delivery_dir = run_dir / "delivery"
    if not delivery_dir.is_dir():
        raise FileNotFoundError(f"Delivery directory not found: {delivery_dir}")

    release_info = json.loads((delivery_dir / "release.json").read_text(encoding="utf-8"))
    release_id = release_info["release_id"]

    manifest_info = json.loads((delivery_dir / "manifest.json").read_text(encoding="utf-8"))
    total_images = len(manifest_info.get("items", {}))
    if total_images == 0:
        raise ValueError("manifest.json has 0 items")

    errors_path = run_dir / "errors.json"
    if not errors_path.is_file():
        raise FileNotFoundError(f"errors.json not found in {run_dir}")

    errors_data = json.loads(errors_path.read_text(encoding="utf-8"))
    errors_list = errors_data.get("errors", [])

    # Target-level error count (each image / scene counts at most once)
    err_targets = {e["target"] for e in errors_list}
    error_count = len(err_targets)
    error_rate = error_count / total_images

    # Decision rule: > 2% -> HOLD, <= 2% -> RELEASE
    if error_rate > RELEASE_THRESHOLD:
        decision = "HOLD"
        reason = f"Tỉ lệ ảnh lỗi {error_rate:.1%} ({error_count}/{total_images}) vượt ngưỡng cho phép 2.0%"
    else:
        decision = "RELEASE"
        reason = f"Tỉ lệ ảnh lỗi {error_rate:.1%} ({error_count}/{total_images}) đạt chuẩn dưới ngưỡng 2.0%"

    if lineage_root is None:
        lineage_root = run_dir.parent

    # Record decision to lineage if requested
    if record:
        events = lineage.read(lineage_root)
        already_recorded = any(
            e.get("event") == "decision"
            and e.get("release_id") == release_id
            and e.get("decision") == decision
            for e in events
        )
        if not already_recorded:
            lineage.append(
                lineage_root,
                {
                    "event": "decision",
                    "release_id": release_id,
                    "decision": decision,
                    "detail": reason,
                },
            )

    # Query blast radius / impact
    impacted_runs = lineage.impact(lineage_root, release_id)

    return {
        "release_id": release_id,
        "total_images": total_images,
        "error_count": error_count,
        "error_rate": error_rate,
        "threshold": RELEASE_THRESHOLD,
        "decision": decision,
        "reason": reason,
        "impacted_runs": impacted_runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 Release Gate & Lineage Evaluator")
    parser.add_argument("--run", required=True, help="Path to run directory, e.g. runs/r9007")
    parser.add_argument("--no-record", action="store_true", help="Do not write to lineage.jsonl")
    args = parser.parse_args()

    run_path = Path(args.run).resolve()
    result = evaluate_release_gate(run_path, record=not args.no_record)

    print("==================================================")
    print("           P3 RELEASE GATE EVALUATION             ")
    print("==================================================")
    print(f"Release ID   : {result['release_id']}")
    print(f"Total Images : {result['total_images']}")
    print(f"Error Count  : {result['error_count']}")
    print(f"Error Rate   : {result['error_rate']:.1%} (Threshold: {result['threshold']:.1%})")
    print(f"Decision     : {result['decision']}")
    print(f"Reason       : {result['reason']}")
    print("--------------------------------------------------")
    print("Lineage Impact / Blast Radius:")
    if result["impacted_runs"]:
        for run in result["impacted_runs"]:
            print(f"  Run {run['run_id']}: affected={run['affected']} action={run['action']}")
    else:
        print("  Không có training run nào gắn với release này.")
    print("==================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
