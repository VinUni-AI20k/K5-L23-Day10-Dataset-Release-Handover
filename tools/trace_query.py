"""Truy vết ticket của team AI -> trace.json (thư viện chuẩn).

    py -X utf8 tools/trace_query.py <delivery> --out <trace.json>

Tiêu chí (không gõ cứng lớp / scene; đọc từ ticket + changelog):
  * Lớp bị đổi quy tắc: tên trong dấu `` ở changelog (mục phiên bản mới nhất)
    mà có trong classes.txt.
  * Guideline cũ: mọi guideline ghi ở JOB (jobs.csv) khác phiên bản mới nhất.
    Không dùng guideline ghi ở từng ảnh (có thể là lỗi guideline_mismatch).
  * Tập nền: ảnh thuộc job guideline cũ và có >= 1 box detection lớp đó
    trong labels/.
  * tier_a: tập nền ∩ scene ticket nêu; tier_b: phần còn lại của tập nền.
  * notify: annotator + reviewer của các job chứa ảnh tier_a và tier_b.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def read_classes(path: Path) -> dict[str, int]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            out[parts[1].strip()] = int(parts[0])
    return out


def version_key(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def changed_classes(changelog: str, classes: dict[str, int]):
    """Trả về (phiên bản mới nhất, tập lớp bị đổi quy tắc ở phiên bản đó)."""
    sections = re.split(r"^##\s+", changelog, flags=re.M)[1:]
    parsed = []
    for sec in sections:
        head, _, body = sec.partition("\n")
        m = re.match(r"v?(\d+(?:\.\d+)*)", head.strip())
        if m:
            parsed.append(("v" + m.group(1), body))
    if not parsed:
        raise SystemExit("changelog không có mục phiên bản")
    newest, body = max(parsed, key=lambda p: version_key(p[0]))
    found = {n for n in re.findall(r"`([^`]+)`", body) if n in classes}
    return newest, found


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.delivery)

    classes = read_classes(d / "classes.txt")
    changelog = (d / "guideline" / "changelog.md").read_text(encoding="utf-8")
    ticket = (d / "incoming" / "ticket.md").read_text(encoding="utf-8")
    newest, rule_names = changed_classes(changelog, classes)
    rule_ids = {classes[n] for n in rule_names}
    ticket_scenes = set(re.findall(r"scene_\d+", ticket))

    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {r["job_id"]: r for r in csv.DictReader(f)}
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]

    tier_a, tier_b, notify = [], [], set()
    for it in sorted(meta, key=lambda x: x["image"]):
        job = jobs.get(it["job_id"])
        if not job or job["guideline"].strip() == newest:
            continue  # job theo guideline mới -> đã gán box cho lớp đó
        lab = d / "labels" / f"{it['image']}.txt"
        if not lab.exists():
            continue
        ids = set()
        for line in lab.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if p and p[0].lstrip("-").isdigit():
                ids.add(int(p[0]))
        if not (ids & rule_ids):
            continue
        (tier_a if it["scene_id"] in ticket_scenes else tier_b).append(it["image"])
        notify.update((job["annotator"], job["reviewer"]))

    out = {"tier_a": tier_a, "tier_b": tier_b, "notify": sorted(notify)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"lớp đổi quy tắc: {sorted(rule_names)} ({newest}); scene ticket: {sorted(ticket_scenes)}")
    print(f"tier_a={len(tier_a)} tier_b={len(tier_b)} notify={out['notify']} -> {a.out}")


if __name__ == "__main__":
    main()
