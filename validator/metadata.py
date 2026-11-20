from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


def _input_path(delivery: Path, relative: str) -> Path:
    path = (delivery / relative).resolve()
    if not path.is_relative_to(delivery):
        raise ValueError(f"Input is outside delivery: {relative}")
    return path


def validate_metadata(delivery_path: str | Path) -> list[dict[str, str]]:
    """Return scene_leak and guideline_mismatch findings, without writing inputs."""
    delivery = Path(delivery_path).resolve(strict=True)
    metadata = json.loads(
        _input_path(delivery, "metadata.json").read_text(encoding="utf-8-sig")
    )["items"]
    with _input_path(delivery, "jobs.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        jobs = {row["job_id"]: row for row in csv.DictReader(stream)}

    splits_by_scene: dict[str, set[str]] = defaultdict(set)
    findings: set[tuple[str, str]] = set()
    for row in metadata:
        image = Path(row["image"]).stem
        splits_by_scene[row["scene_id"]].add(row["split"])
        job_id = row["job_id"]
        if job_id not in jobs:
            raise ValueError(f"Unknown job {job_id!r} for image {image!r}")
        if row["guideline_version"] != jobs[job_id]["guideline"]:
            findings.add(("guideline_mismatch", image))

    for scene, splits in splits_by_scene.items():
        if len(splits) > 1:
            findings.add(("scene_leak", scene))

    return [{"type": kind, "target": target} for kind, target in sorted(findings)]
