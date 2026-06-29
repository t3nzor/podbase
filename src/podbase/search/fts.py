from __future__ import annotations

from podbase.db import Database
from podbase.models import SearchResult


def search(
    db: Database,
    query: str,
    *,
    podcast_id: int | None = None,
    since: str | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    """Full-text search across transcript segments.

    Returns results ranked by FTS5 BM25, joined with episode/podcast metadata.
    """
    # FTS5 requires the query to be escaped for special characters
    safe_query = query.replace('"', '""')

    sql = """\
    SELECT
        s.text,
        s.start_sec,
        s.end_sec,
        e.title        AS episode_title,
        e.published_at,
        p.title        AS podcast_title,
        rank
    FROM segments_fts fts
    JOIN segments s ON s.id = fts.rowid
    JOIN episodes e ON e.id = s.episode_id
    JOIN podcasts p ON p.id = e.podcast_id
    WHERE fts.text MATCH ?
    """
    params: list[object] = [safe_query]

    if podcast_id is not None:
        sql += " AND p.id = ?"
        params.append(podcast_id)

    if since is not None:
        sql += " AND e.published_at >= ?"
        params.append(since)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    rows = db.conn.execute(sql, params).fetchall()

    return [
        SearchResult(
            episode_title=row["episode_title"],
            podcast_title=row["podcast_title"],
            published_at=row["published_at"],
            start_sec=row["start_sec"],
            end_sec=row["end_sec"],
            text=row["text"],
            rank=row["rank"],
        )
        for row in rows
    ]
