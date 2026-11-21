
import argparse
import json
from pathlib import Path

from detection import validate_detection
from panoptic import validate_panoptic
from metadata import validate_metadata
from cross_check import generate_candidates


def main():
    parser = argparse.ArgumentParser(
        description="Day 10 - Dataset Validator"
    )
    parser.add_argument("delivery")
    parser.add_argument("--out", required=True)
    parser.add_argument("--candidates")

    args = parser.parse_args()

    delivery = Path(args.delivery)

    if not delivery.is_dir():
        parser.error(f"Khong tim thay delivery: {delivery}")

    print("1. Kiem tra Detection...")
    detection_errors = validate_detection(delivery)

    print("2. Kiem tra Panoptic...")
    panoptic_errors = validate_panoptic(delivery)

    print("3. Kiem tra Metadata...")
    metadata_errors = validate_metadata(delivery)

    errors = (
        detection_errors
        + panoptic_errors
        + metadata_errors
    )

    errors = sorted(
        errors,
        key=lambda item: (item["type"], item["target"])
    )

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
    json.dumps(
        {"errors": errors},
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

    print(f"Da ghi {len(errors)} loi vao {output}")

    if args.candidates:
        candidates = generate_candidates(delivery)
        candidate_output = Path(args.candidates)
        candidate_output.parent.mkdir(parents=True, exist_ok=True)
        candidate_output.write_text(
            json.dumps({"candidates": candidates}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Da ghi {len(candidates)} ung vien vao {candidate_output}")


if __name__ == "__main__":
    main()
