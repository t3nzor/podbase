from __future__ import annotations

import sqlite3
from pathlib import Path

_MIGRATIONS: list[str] = [
    # 001 — initial schema
    """\
CREATE TABLE IF NOT EXISTS podcasts (
    id            INTEGER PRIMARY KEY,
    title         TEXT    NOT NULL,
    rss_url       TEXT    NOT NULL UNIQUE,
    etag          TEXT,
    last_synced_at TEXT,
    added_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS episodes (
    id             INTEGER PRIMARY KEY,
    podcast_id     INTEGER NOT NULL REFERENCES podcasts(id),
    guid           TEXT    NOT NULL UNIQUE,
    title          TEXT    NOT NULL,
    published_at   TEXT,
    audio_url      TEXT,
    duration_sec   REAL,
    status         TEXT    NOT NULL DEFAULT 'new',
    transcribed_at TEXT,
    summary        TEXT,
    UNIQUE(podcast_id, guid)
);

CREATE TABLE IF NOT EXISTS segments (
    id         INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    idx        INTEGER NOT NULL,
    start_sec  REAL    NOT NULL,
    end_sec    REAL    NOT NULL,
    text       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_segments_episode ON segments(episode_id);

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text,
    content='segments',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TABLE IF NOT EXISTS jobs (
    id         INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL,  -- transcribe | embed
    status     TEXT    NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
    error      TEXT,
    attempts   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(episode_id, kind)
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
""",
]


class Database:
    """Thin wrapper around a SQLite connection with migration support."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def current_version(self) -> int:
        try:
            row = self.conn.execute("SELECT version FROM schema_version").fetchone()
            return row["version"] if row else 0
        except sqlite3.OperationalError:
            return 0

    def migrate(self) -> int:
        """Apply pending migrations. Returns the new schema version."""
        current = self.current_version()
        target = len(_MIGRATIONS)
        if current >= target:
            return current
        for sql in _MIGRATIONS[current:]:
            self.conn.executescript(sql)
        self.conn.execute("DELETE FROM schema_version")
        self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (target,))
        self.conn.commit()
        return target
