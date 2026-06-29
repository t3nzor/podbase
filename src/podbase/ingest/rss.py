from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

import feedparser  # type: ignore[import-untyped]

from podbase.db import Database


def _extract_audio_url(entry: dict[str, Any]) -> str | None:
    """Return the best audio enclosure URL from a feed entry."""
    for link in entry.get("links", []):
        if link.get("type", "").startswith("audio/"):
            return str(link.get("href"))
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("audio/"):
            return str(enc.get("href"))
    return None


def _parse_duration(raw: str | None) -> float | None:
    """Parse itunes:duration like '1:23:45' or '83' into seconds."""
    if not raw:
        return None
    parts = raw.split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError:
        return None


def subscribe(db: Database, rss_url: str) -> int:
    """Subscribe to a podcast RSS feed. Returns the podcast id."""
    feed = feedparser.parse(rss_url)
    if feed.bozo and not feed.entries:
        raise ValueError(f"Failed to parse RSS feed: {rss_url}") from feed.bozo_exception

    title = feed.feed.get("title", rss_url)
    db.conn.execute(
        "INSERT OR IGNORE INTO podcasts (title, rss_url) VALUES (?, ?)",
        (title, rss_url),
    )
    db.conn.commit()
    row = db.conn.execute("SELECT id FROM podcasts WHERE rss_url = ?", (rss_url,)).fetchone()
    assert row is not None
    podcast_id: int = row["id"]
    return podcast_id


def sync(db: Database, podcast_id: int | None = None) -> tuple[int, int]:
    """Sync podcast feeds. Returns (new_episodes, total_checked)."""
    if podcast_id is not None:
        rows = db.conn.execute(
            "SELECT id, rss_url, etag FROM podcasts WHERE id = ?",
            (podcast_id,),
        ).fetchall()
    else:
        rows = db.conn.execute("SELECT id, rss_url, etag FROM podcasts").fetchall()

    total_new = 0
    total_checked = 0

    for podcast in rows:
        pid: int = podcast["id"]
        rss_url: str = podcast["rss_url"]
        etag: str | None = podcast["etag"]

        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag

        feed = feedparser.parse(rss_url, request_headers=headers)

        if feed.status == 304:
            continue

        new_etag = feed.get("etag")
        if new_etag:
            db.conn.execute(
                "UPDATE podcasts SET etag = ?, last_synced_at = ? WHERE id = ?",
                (new_etag, datetime.now(UTC).isoformat(), pid),
            )

        for entry in feed.entries:
            total_checked += 1
            guid = entry.get("id") or entry.get("link", "")
            title = entry.get("title", "Untitled")
            published = entry.get("published_parsed")
            if published:
                dt = datetime(
                    published.tm_year,
                    published.tm_mon,
                    published.tm_mday,
                    published.tm_hour,
                    published.tm_min,
                    published.tm_sec,
                    tzinfo=UTC,
                )
                published_at = dt.isoformat()
            else:
                published_at = None
            audio_url = _extract_audio_url(entry)
            duration = _parse_duration(entry.get("itunes_duration"))

            try:
                db.conn.execute(
                    """\
                    INSERT OR IGNORE INTO episodes
                        (podcast_id, guid, title, published_at, audio_url, duration_sec)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (pid, guid, title, published_at, audio_url, duration),
                )
                if db.conn.total_changes:
                    total_new += 1
                    ep_row = db.conn.execute(
                        "SELECT id FROM episodes WHERE podcast_id = ? AND guid = ?",
                        (pid, guid),
                    ).fetchone()
                    if ep_row and audio_url:
                        db.conn.execute(
                            "INSERT OR IGNORE INTO jobs (episode_id, kind) "
                            "VALUES (?, 'transcribe')",
                            (ep_row["id"],),
                        )
            except sqlite3.IntegrityError:
                pass

        db.conn.commit()

    return total_new, total_checked
