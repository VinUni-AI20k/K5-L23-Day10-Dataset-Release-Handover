"""Unified CLI for data-validation rules (Member 1) and annotation-review candidates (Member 2)."""
import argparse
import json
from pathlib import Path
import sys

if __package__:
    from .cross_check import write_candidates
    from .rules import validate_rules
else:
    from cross_check import write_candidates
    from rules import validate_rules


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidates", type=Path, help="Output JSON for detection <-> panoptic review candidates")
    args = parser.parse_args()

    delivery_resolved = args.delivery.resolve()
    if args.out.resolve().is_relative_to(delivery_resolved):
        parser.error("--out must be outside delivery (v1 is read-only)")
    if args.candidates is not None and args.candidates.resolve().is_relative_to(delivery_resolved):
        parser.error("--candidates must be outside delivery (v1 is read-only)")

    try:
        result = validate_rules(args.delivery)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Rules: {len(result['errors'])} findings -> {args.out}")

    if args.candidates is not None:
        try:
            cand_doc = write_candidates(args.delivery, args.candidates)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Candidate generation failed: {exc}", file=sys.stderr)
            return 1
        summary = cand_doc["summary"]
        print(
            f"Candidates: {summary['total_candidates']} items across "
            f"{summary['unique_candidate_images']} images -> {args.candidates}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
