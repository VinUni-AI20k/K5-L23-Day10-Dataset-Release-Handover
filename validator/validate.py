"""Run the available validator rules from the command line."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validator.cross_check import generate_candidates
from validator.detection_rules import validate_detection_rules
from validator.rules_metadata import check_metadata
from validator.rules_panoptic import check_panoptic


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidates", type=Path)
    args = parser.parse_args()

    errors = (
        validate_detection_rules(args.delivery)
        + check_metadata(args.delivery)
        + check_panoptic(args.delivery)
    )
    errors.sort(key=lambda item: (item["type"], item["target"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"errors": errors}, indent=2) + "\n", encoding="utf-8")


    if args.candidates is not None:
        candidates = generate_candidates(args.delivery)
        args.candidates.parent.mkdir(parents=True, exist_ok=True)
        args.candidates.write_text(
            json.dumps({"candidates": candidates}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
