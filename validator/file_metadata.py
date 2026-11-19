"""File and metadata rule checks for the Day 10 lab validator.

This module only reads files inside the supplied delivery directory. It does
not inspect training data, private truth, or network resources.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _safe_delivery_file(delivery: Path, relative_name: str) -> Path | None:
    """Resolve a manifest path, rejecting absolute paths and traversal."""
    candidate = Path(relative_name)
    if candidate.is_absolute():
        return None
    root = delivery.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _image_target(record: dict[str, Any]) -> str:
    """Get the canonical image stem used by errors.json targets."""
    name = record.get("_manifest_key") or record.get("file_name") or record.get("image") or record.get("name")
    if isinstance(name, dict):
        name = name.get("file_name") or name.get("path")
    if not isinstance(name, str) or not name.strip():
        return ""
    return Path(name).stem


def _manifest_image_rows(manifest: Any) -> list[dict[str, Any]]:
    """Accept the documented list form and common wrapped forms."""
    if isinstance(manifest, list):
        rows = manifest
    elif isinstance(manifest, dict):
        rows = manifest.get("items", manifest.get("images", manifest.get("files", [])))
        if isinstance(rows, dict):
            rows = [dict(value, _manifest_key=key) for key, value in rows.items() if isinstance(value, dict)]
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _manifest_image_path(record: dict[str, Any]) -> str | None:
    image = record.get("image")
    if isinstance(image, dict):
        image = image.get("file_name") or image.get("path")
    if isinstance(image, str):
        return image
    for key in ("image_path", "file_name", "path"):
        value = record.get(key)
        if isinstance(value, str) and (key != "path" or value.lower().endswith((".jpg", ".jpeg", ".png"))):
            return value
    return None


def _manifest_hash(record: dict[str, Any]) -> str | None:
    image = record.get("image")
    if isinstance(image, dict):
        for key in ("sha256", "hash"):
            if isinstance(image.get(key), str):
                return image[key]
    hashes = record.get("sha256")
    if isinstance(hashes, dict):
        for key in ("image", "image_file"):
            if isinstance(hashes.get(key), str):
                return hashes[key]
    for key in ("image_sha256", "sha256_image", "sha256"):
        value = record.get(key)
        if isinstance(value, str):
            return value
    return None


def check_file_metadata(delivery_dir: str | Path) -> list[dict[str, str]]:
    """Return findings for missing_image, wrong_hash, scene_leak,
    and guideline_mismatch.

    Each finding uses the shared schema {"type": ..., "target": ...}.
    Missing or malformed required metadata files raise ValueError so an
    incomplete delivery is not silently reported as clean.
    """
    delivery = Path(delivery_dir).resolve()
    if not delivery.is_dir():
        raise ValueError(f"Delivery directory does not exist: {delivery}")

    manifest_path = delivery / "manifest.json"
    metadata_path = delivery / "metadata.json"
    jobs_path = delivery / "jobs.csv"
    for required in (manifest_path, metadata_path, jobs_path):
        if not required.is_file():
            raise ValueError(f"Required delivery file is missing: {required.name}")

    manifest = _load_json(manifest_path)
    metadata = _load_json(metadata_path)
    manifest_rows = _manifest_image_rows(manifest)
    if not manifest_rows:
        raise ValueError("manifest.json has no image records")

    findings: set[tuple[str, str]] = set()

    # Image existence and byte-for-byte SHA-256 verification.
    for record in manifest_rows:
        target = _image_target(record)
        image_name = _manifest_image_path(record)
        if not target or not image_name:
            continue
        image_path = _safe_delivery_file(delivery, image_name)
        if image_path is None or not image_path.is_file():
            findings.add(("missing_image", target))
            continue
        expected_hash = _manifest_hash(record)
        if expected_hash is not None:
            digest = hashlib.sha256()
            with image_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest().lower() != expected_hash.strip().lower():
                findings.add(("wrong_hash", target))

    # Scene split consistency. One scene is one finding, regardless of how
    # many images in that scene appear in both train and val.
    scene_splits: dict[str, set[str]] = {}
    metadata_rows = metadata if isinstance(metadata, list) else metadata.get("items", metadata.get("images", [])) if isinstance(metadata, dict) else []
    if isinstance(metadata_rows, dict):
        metadata_rows = list(metadata_rows.values())
    if not isinstance(metadata_rows, list):
        raise ValueError("metadata.json must contain an image list")
    for row in metadata_rows:
        if not isinstance(row, dict):
            continue
        scene = row.get("scene_id")
        split = row.get("split")
        if isinstance(scene, str) and isinstance(split, str):
            scene_splits.setdefault(scene, set()).add(split.strip().lower())
    for scene, splits in scene_splits.items():
        if "train" in splits and "val" in splits:
            findings.add(("scene_leak", scene))

    # Guideline recorded on each image must match the guideline assigned to
    # its job in jobs.csv (the job is the authoritative source).
    with jobs_path.open("r", encoding="utf-8-sig", newline="") as handle:
        jobs = {
            row.get("job_id", "").strip(): row.get("guideline", "").strip()
            for row in csv.DictReader(handle)
            if row.get("job_id")
        }
    for row in metadata_rows:
        if not isinstance(row, dict):
            continue
        job_id = row.get("job_id")
        image_guideline = row.get("guideline_version")
        target = _image_target(row)
        if not target and isinstance(row.get("image_id"), (int, str)):
            target = str(row["image_id"])
        if not isinstance(job_id, str) or job_id not in jobs or not isinstance(image_guideline, str):
            continue
        if image_guideline.strip() != jobs[job_id].strip():
            findings.add(("guideline_mismatch", target))

    return [{"type": kind, "target": target} for kind, target in sorted(findings)]
