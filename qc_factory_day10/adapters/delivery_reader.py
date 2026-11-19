"""Read-only Day10 delivery adapter and fast preflight validator."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_FILES = (
    "manifest.json",
    "metadata.json",
    "panoptic.json",
    "jobs.csv",
    "classes.txt",
    "release.json",
)


def safe_rel_path(delivery: Path, rel: str) -> Path | None:
    """Resolve relative path inside delivery; reject traversal or symlink escape."""
    if not rel or Path(rel).is_absolute():
        return None
    try:
        base = delivery.resolve()
        target = (delivery / rel).resolve()
        target.relative_to(base)
        return target
    except (OSError, ValueError):
        return None


def compute_dataset_fingerprint(delivery: Path) -> str:
    """Deterministic fingerprint from manifest.json + metadata.json + release.json."""
    h = hashlib.sha256()
    for name in ("manifest.json", "metadata.json", "release.json"):
        p = delivery / name
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


@dataclass(frozen=True)
class DeliveryContext:
    root: Path
    fingerprint: str
    release_id: str
    manifest: dict[str, Any]
    metadata: dict[str, Any]
    panoptic: dict[str, Any]
    jobs: dict[str, dict[str, str]]
    classes: dict[int, str]


def _load_json_safe(path: Path, fatal: list[str]) -> dict[str, Any]:
    if not path.is_file():
        fatal.append(f"Missing required JSON: {path.name}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            fatal.append(f"Expected JSON object in {path.name}")
            return {}
        return data
    except (OSError, ValueError) as exc:
        fatal.append(f"Invalid JSON in {path.name}: {exc}")
        return {}


def load_delivery(delivery: Path) -> DeliveryContext:
    """Load delivery metadata read-only."""
    fatal: list[str] = []
    manifest = _load_json_safe(delivery / "manifest.json", fatal)
    metadata = _load_json_safe(delivery / "metadata.json", fatal)
    panoptic = _load_json_safe(delivery / "panoptic.json", fatal)
    release = _load_json_safe(delivery / "release.json", fatal)

    jobs: dict[str, dict[str, str]] = {}
    jobs_path = delivery / "jobs.csv"
    if jobs_path.is_file():
        with jobs_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                jid = (row.get("job_id") or "").strip()
                if jid:
                    jobs[jid] = row

    classes: dict[int, str] = {}
    cls_path = delivery / "classes.txt"
    if cls_path.is_file():
        for line in cls_path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0].isdigit():
                classes[int(parts[0])] = parts[1].strip()

    return DeliveryContext(
        root=delivery,
        fingerprint=compute_dataset_fingerprint(delivery),
        release_id=str(release.get("release_id", "")),
        manifest=manifest,
        metadata=metadata,
        panoptic=panoptic,
        jobs=jobs,
        classes=classes,
    )


def run_preflight(delivery: Path, out_path: Path | None = None) -> dict[str, Any]:
    """Run read-only preflight checks and optionally write preflight_report.json."""
    fatal: list[str] = []
    recoverable: list[str] = []
    invalid_assets: list[dict[str, str]] = []

    if not delivery.is_dir():
        fatal.append(f"Delivery directory not found: {delivery}")
        report = {
            "delivery": str(delivery),
            "ready_for_qc": False,
            "fatal_errors": fatal,
            "recoverable_errors": recoverable,
            "invalid_assets": invalid_assets,
            "fingerprint": "",
            "release_id": "",
            "counts": {},
        }
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    for req in REQUIRED_FILES:
        if not (delivery / req).is_file():
            fatal.append(f"Missing required file: {req}")

    ctx = load_delivery(delivery)
    items = ctx.manifest.get("items", {})
    if not isinstance(items, dict) or not items:
        fatal.append("manifest.json has no 'items'")
        items = {}

    if not ctx.jobs:
        fatal.append("jobs.csv is empty or missing")
    if not ctx.classes:
        fatal.append("classes.txt is empty or missing")

    meta_items = ctx.metadata.get("items", [])
    meta_by_img = {m.get("image"): m for m in meta_items if isinstance(m, dict) and m.get("image")}
    pan_imgs = {Path(im["file_name"]).stem: im for im in ctx.panoptic.get("images", []) if "file_name" in im}

    for name, entry in sorted(items.items()):
        for kind in ("image", "label", "mask"):
            rel = entry.get(kind)
            if not rel:
                recoverable.append(f"{name}: missing manifest key '{kind}'")
                continue
            resolved = safe_rel_path(delivery, rel)
            if resolved is None:
                fatal.append(f"{name}: unsafe path traversal/symlink in {kind}: {rel}")
                invalid_assets.append({"image": name, "asset": kind, "reason": "unsafe_path"})
            elif not resolved.is_file():
                recoverable.append(f"{name}: missing {kind} file {rel}")
                invalid_assets.append({"image": name, "asset": kind, "reason": "missing_file"})
        if name not in meta_by_img:
            recoverable.append(f"{name}: missing metadata entry")
        if name not in pan_imgs:
            recoverable.append(f"{name}: missing panoptic image entry")

    for m in meta_items:
        jid = m.get("job_id")
        if jid and jid not in ctx.jobs:
            recoverable.append(f"{m.get('image', '?')}: unknown job_id {jid}")

    report = {
        "delivery": str(delivery),
        "ready_for_qc": len(fatal) == 0,
        "fingerprint": ctx.fingerprint,
        "release_id": ctx.release_id,
        "counts": {
            "manifest_items": len(items),
            "metadata_items": len(meta_items),
            "panoptic_images": len(pan_imgs),
            "panoptic_annotations": len(ctx.panoptic.get("annotations", [])),
            "jobs": len(ctx.jobs),
            "classes": len(ctx.classes),
            "invalid_assets": len(invalid_assets),
        },
        "fatal_errors": fatal,
        "recoverable_errors": recoverable[:100],
        "recoverable_total": len(recoverable),
        "invalid_assets": invalid_assets[:100],
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
