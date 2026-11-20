#!/usr/bin/env python3
"""Record the CP3 HOLD decision and verify the affected training run."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "r76"
RELEASE = RUN / "delivery" / "release.json"


def main() -> int:
    if not RELEASE.is_file():
        raise SystemExit(
            "Missing runs/r76/delivery/release.json; create the seed-76 run first."
        )
    release_id = json.loads(RELEASE.read_text(encoding="utf-8"))["release_id"]
    command = [
        sys.executable,
        str(ROOT / "scripts" / "lineage.py"),
        "record",
        "--event",
        "decision",
        "--release-id",
        release_id,
        "--decision",
        "HOLD",
        "--detail",
        "QC 22/250 = 8.8%, above 2% threshold",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "lineage.py"),
            "impact",
            "--release-id",
            release_id,
        ],
        cwd=ROOT,
        check=True,
    )
    submission_lineage = ROOT / "submission" / "lineage.jsonl"
    shutil.copyfile(RUN.parent / "lineage.jsonl", submission_lineage)
    print(f"copied lineage to {submission_lineage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
