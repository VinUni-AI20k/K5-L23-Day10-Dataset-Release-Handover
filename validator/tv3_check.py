

from __future__ import annotations

import argparse
import json
from pathlib import Path

from metadata import validate_metadata
from panoptic import validate_panoptic


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the four TV3 rule types")
    parser.add_argument("delivery")
    parser.add_argument("--out", required=True)
    parser.add_argument("--scope", choices=["all", "metadata", "panoptic"], default="all")
    args = parser.parse_args()
    delivery = Path(args.delivery).resolve(strict=True)
    output = Path(args.out).resolve()
    if output.is_relative_to(delivery):
        parser.error("--out must be outside delivery; v1 must remain unchanged")

    findings = []
    if args.scope in ("all", "metadata"):
        print("Checking metadata...", flush=True)
        findings.extend(validate_metadata(delivery))
    if args.scope in ("all", "panoptic"):
        print("Checking panoptic masks...", flush=True)
        findings.extend(validate_panoptic(delivery))
    pairs = sorted({(row["type"], row["target"]) for row in findings})
    document = {"errors": [{"type": kind, "target": target} for kind, target in pairs]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"TV3: {len(pairs)} findings -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
