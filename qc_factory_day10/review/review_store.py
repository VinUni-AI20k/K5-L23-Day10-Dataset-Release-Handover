"""SQLite-backed persistent review store (adapted from cvat_tools.core.shapestore)."""
from __future__ import annotations

import csv
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

VALID_VERDICTS = ("pending", "confirmed", "rejected", "skip")
SEMANTIC_TYPES = ("class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge")


class ReviewStore:
    """Thread-safe SQLite store for human review decisions outside delivery/."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    image_id TEXT NOT NULL,
                    candidate_type TEXT NOT NULL,
                    resolved_type TEXT NOT NULL,
                    difficulty_tier TEXT NOT NULL,
                    priority REAL NOT NULL,
                    score REAL NOT NULL,
                    evidence TEXT NOT NULL,
                    assigned_reviewer TEXT NOT NULL DEFAULT '',
                    verdict TEXT NOT NULL DEFAULT 'pending',
                    note TEXT NOT NULL DEFAULT '',
                    reviewer TEXT NOT NULL DEFAULT '',
                    updated_at REAL NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def seed_candidates(self, triage_rows: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> int:
        """Insert new semantic candidates without overwriting existing human decisions."""
        triage_by_key = {
            (r["image_id"], r["candidate_type"]): r
            for r in triage_rows
            if r.get("kind") == "semantic"
        }
        inserted = 0
        with self._connect() as conn:
            for idx, c in enumerate(candidates):
                img = c["target"]
                ctype = c["type"]
                cid = f"{img}__{ctype}__{idx}"
                tr = triage_by_key.get((img, ctype), {})
                tier = tr.get("difficulty_tier", "MEDIUM")
                prio = float(tr.get("priority", c.get("score", 0.5)))
                assigned = tr.get("assigned_reviewer", "")
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO candidates
                    (candidate_id, image_id, candidate_type, resolved_type, difficulty_tier,
                     priority, score, evidence, assigned_reviewer)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        img,
                        ctype,
                        ctype,
                        tier,
                        prio,
                        float(c.get("score", 0.5)),
                        c.get("evidence", ""),
                        assigned,
                    ),
                )
                inserted += cur.rowcount
            conn.commit()
        return inserted

    def list_candidates(self, verdict: str | None = None, tier: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM candidates WHERE 1=1"
        params: list[Any] = []
        if verdict:
            query += " AND verdict = ?"
            params.append(verdict)
        if tier:
            query += " AND difficulty_tier = ?"
            params.append(tier)
        query += " ORDER BY priority DESC, image_id ASC, candidate_id ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def record_decision(
        self,
        candidate_id: str,
        verdict: str,
        resolved_type: str,
        note: str,
        reviewer: str,
    ) -> dict[str, Any]:
        if verdict not in VALID_VERDICTS:
            raise ValueError(f"Invalid verdict: {verdict}")
        if resolved_type not in SEMANTIC_TYPES:
            raise ValueError(f"Invalid semantic type: {resolved_type}")
        clean_note = note.strip()
        if verdict in ("confirmed", "rejected") and len(clean_note) < 20:
            raise ValueError("Ghi chú (note) phải có ít nhất 20 ký tự mô tả thấy gì trong ảnh.")
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE candidates
                SET verdict = ?, resolved_type = ?, note = ?, reviewer = ?, updated_at = ?
                WHERE candidate_id = ?
                """,
                (verdict, resolved_type, clean_note, reviewer.strip(), now, candidate_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"Unknown candidate_id: {candidate_id}")
            conn.commit()
            row = conn.execute("SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            return dict(row)

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("SELECT verdict, difficulty_tier, reviewer FROM candidates").fetchall()
        total = len(rows)
        by_verdict: dict[str, int] = {v: 0 for v in VALID_VERDICTS}
        by_tier: dict[str, int] = {"MEDIUM": 0, "HARD": 0}
        by_reviewer: dict[str, int] = {}
        for r in rows:
            by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
            by_tier[r["difficulty_tier"]] = by_tier.get(r["difficulty_tier"], 0) + 1
            if r["reviewer"]:
                by_reviewer[r["reviewer"]] = by_reviewer.get(r["reviewer"], 0) + 1
        return {
            "total": total,
            "by_verdict": by_verdict,
            "by_tier": by_tier,
            "by_reviewer": by_reviewer,
            "reviewed": by_verdict["confirmed"] + by_verdict["rejected"],
            "pending": by_verdict["pending"] + by_verdict["skip"],
        }

    def export_review_log(self, csv_path: Path) -> int:
        """Export only actual human confirmed/rejected decisions to official review_log.csv."""
        rows = [r for r in self.list_candidates() if r["verdict"] in ("confirmed", "rejected")]
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["image", "type", "verdict", "note"])
            for r in rows:
                note = r["note"]
                if r["reviewer"] and f"[{r['reviewer']}]" not in note:
                    note = f"[{r['reviewer']}] {note}"
                writer.writerow([r["image_id"], r["resolved_type"], r["verdict"], note])
        return len(rows)

    def merge_confirmed_into_errors(self, base_errors_path: Path, out_errors_path: Path) -> int:
        """Merge rule errors + confirmed human review errors into final errors.json."""
        base = json.loads(base_errors_path.read_text(encoding="utf-8")) if base_errors_path.is_file() else {"errors": []}
        pairs = {(e["type"], e["target"]) for e in base.get("errors", [])}
        confirmed = self.list_candidates(verdict="confirmed")
        for r in confirmed:
            pairs.add((r["resolved_type"], r["image_id"]))
        merged = [{"type": t, "target": tgt} for t, tgt in sorted(pairs)]
        out_errors_path.parent.mkdir(parents=True, exist_ok=True)
        out_errors_path.write_text(json.dumps({"errors": merged}, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(merged)
