"""収集結果の保存（SQLite）。初出日時を持たせて「新着」判定に使う。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    source_name TEXT NOT NULL,
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    published   TEXT,           -- YYYY-MM-DD（取得できなければ NULL）
    summary     TEXT,
    tag         TEXT,
    laws        TEXT,           -- JSON 配列
    signals     TEXT,           -- JSON 配列
    keywords    TEXT,           -- JSON 配列
    score       INTEGER,
    dupkey      TEXT,           -- 媒体違いの同一記事をまとめる照合キー
    first_seen  TEXT NOT NULL,  -- このツールが最初に見つけた日時
    last_seen   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published);
CREATE INDEX IF NOT EXISTS idx_items_first_seen ON items(first_seen);
CREATE INDEX IF NOT EXISTS idx_items_dupkey ON items(dupkey);
CREATE TABLE IF NOT EXISTS runs (
    started_at TEXT PRIMARY KEY,
    summary    TEXT
);
"""


def make_id(url: str, title: str) -> str:
    return hashlib.sha1(f"{url}\n{title}".encode("utf-8")).hexdigest()[:16]


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert(self, rec: dict) -> bool:
        """新規なら True。既出（同一 ID または同一記事の別媒体）なら False。"""
        now = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute("SELECT id FROM items WHERE id = ?", (rec["id"],))
        row = cur.fetchone()
        if row is None and rec.get("dupkey"):
            row = self.conn.execute(
                "SELECT id FROM items WHERE dupkey = ? LIMIT 1", (rec["dupkey"],)
            ).fetchone()
        if row:
            self.conn.execute("UPDATE items SET last_seen = ? WHERE id = ?", (now, row["id"]))
            return False
        self.conn.execute(
            """INSERT INTO items (id, source_id, source_name, category, title, url,
               published, summary, tag, laws, signals, keywords, score, dupkey,
               first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec["id"], rec["source_id"], rec["source_name"], rec["category"],
                rec["title"], rec["url"], rec.get("published"), rec.get("summary", ""),
                rec.get("tag", ""), json.dumps(rec.get("laws", []), ensure_ascii=False),
                json.dumps(rec.get("signals", []), ensure_ascii=False),
                json.dumps(rec.get("keywords", []), ensure_ascii=False),
                rec.get("score", 0), rec.get("dupkey", ""), now, now,
            ),
        )
        return True

    def record_run(self, summary: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs (started_at, summary) VALUES (?, ?)",
            (datetime.now().isoformat(timespec="seconds"), json.dumps(summary, ensure_ascii=False)),
        )

    def previous_run_at(self) -> str | None:
        cur = self.conn.execute("SELECT started_at FROM runs ORDER BY started_at DESC LIMIT 1")
        row = cur.fetchone()
        return row["started_at"] if row else None

    def all_items(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM items ORDER BY COALESCE(published, substr(first_seen,1,10)) DESC, score DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for key in ("laws", "signals", "keywords"):
                d[key] = json.loads(d[key] or "[]")
            out.append(d)
        return out

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()
