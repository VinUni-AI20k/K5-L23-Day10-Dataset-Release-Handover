"""CLI: validate.py DELIVERY --out rules.json [--candidates candidates.json]."""

import argparse
import json
from pathlib import Path
import sys

import common
import crosscheck
import rules_detection
import rules_file
import rules_meta
import rules_panoptic


def collect_errors(ctx):
    """First image rule wins; scene-level findings remain independent."""
    errors, seen_pairs, skip_images = [], set(), set()
    for module in (rules_file, rules_meta, rules_detection, rules_panoptic):
        for error in module.check(ctx):
            pair = (error["type"], error["target"])
            is_scene = error["type"] == "scene_leak"
            if pair in seen_pairs or (not is_scene and error["target"] in skip_images):
                continue
            seen_pairs.add(pair)
            errors.append(error)
            if not is_scene:
                skip_images.add(error["target"])
    return sorted(errors, key=lambda e: (e["type"], e["target"])), skip_images


def output_path(value, root):
    path = Path(value).resolve()
    if path.is_relative_to(root):
        raise ValueError("Output must be outside delivery: v1 is read-only")
    return path


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidates", type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.delivery.resolve()
        out = output_path(args.out, root)
        candidates_out = output_path(args.candidates, root) if args.candidates else None
        if out == candidates_out:
            raise ValueError("--out and --candidates must be different files")
        ctx = common.load(root)
        errors, skip_images = collect_errors(ctx)
        candidates = crosscheck.candidates(ctx, skip_images) if candidates_out else None
        write_json(out, {"errors": errors})
        if candidates_out:
            write_json(candidates_out, candidates)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Validator input/output error: {exc}", file=sys.stderr)
        return 2
    if getattr(rules_panoptic, "IMPLEMENTED", True) is False:
        print("WARNING: panoptic rules are a P1a stub; only 7 rules active.", file=sys.stderr)
    if candidates_out and getattr(crosscheck, "IMPLEMENTED", True) is False:
        print("WARNING: crosscheck is a P1a stub; empty candidates are not a QC result.", file=sys.stderr)
    print(f"Wrote {len(errors)} rule findings to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
