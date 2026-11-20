"""Metadata rules for a delivered dataset."""

import csv
import json
from collections import defaultdict
from pathlib import Path


def check_metadata(delivery: Path) -> list[dict[str, str]]:
    """Return scene leaks and image guidelines that disagree with their jobs."""
    items = json.loads(
        (delivery / "metadata.json").read_text(encoding="utf-8")
    )["items"]
    with (delivery / "jobs.csv").open(encoding="utf-8", newline="") as handle:
        guidelines = {row["job_id"]: row["guideline"] for row in csv.DictReader(handle)}

    splits_by_scene = defaultdict(set)
    findings = []
    for item in items:
        splits_by_scene[item["scene_id"]].add(item["split"])
        expected = guidelines.get(item["job_id"])
        if expected is not None and item["guideline_version"] != expected:
            findings.append({
                "type": "guideline_mismatch",
                "target": Path(item["image"]).stem,
            })

    for scene_id, splits in splits_by_scene.items():
        if {"train", "val"} <= splits:
            findings.append({"type": "scene_leak", "target": scene_id})

    return sorted(findings, key=lambda item: (item["type"], item["target"]))
