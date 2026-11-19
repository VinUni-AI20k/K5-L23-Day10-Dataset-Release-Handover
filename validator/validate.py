"""CLI for data-validation rules. Candidate generation belongs to member 2."""
import argparse
import json
from pathlib import Path
import sys

if __package__:
    from .rules import validate_rules
else:
    from rules import validate_rules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidates", type=Path, help="Reserved for annotation-review integration")
    args = parser.parse_args()
    if args.out.resolve().is_relative_to(args.delivery.resolve()):
        parser.error("--out must be outside delivery (v1 is read-only)")
    try:
        result = validate_rules(args.delivery)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Rules: {len(result['errors'])} findings -> {args.out}")
    if args.candidates is not None:
        print("Candidate generation is pending member 2 integration; rules saved, candidates untouched.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
