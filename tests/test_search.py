from podbase.db import Database
from podbase.search.fts import search


def _seed(db: Database) -> None:
    """Seed database with test data."""
    db.migrate()
    db.conn.execute(
        "INSERT INTO podcasts (id, title, rss_url) VALUES (?, ?, ?)",
        (1, "Test Podcast", "https://example.com/feed"),
    )
    db.conn.execute(
        "INSERT INTO episodes (id, podcast_id, guid, title, published_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, 1, "ep-001", "Episode One", "2025-01-01T00:00:00+00:00"),
    )
    db.conn.execute(
        "INSERT INTO segments (episode_id, idx, start_sec, end_sec, text) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, 0, 0.0, 30.0, "Welcome to the podcast about artificial intelligence"),
    )
    db.conn.execute(
        "INSERT INTO segments (episode_id, idx, start_sec, end_sec, text) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, 1, 30.0, 60.0, "Today we discuss machine learning and neural networks"),
    )
    db.conn.execute(
        "INSERT INTO segments (episode_id, idx, start_sec, end_sec, text) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, 2, 60.0, 90.0, "Thanks for listening to our show about cooking recipes"),
    )
    db.conn.commit()


class TestSearch:
    def test_basic_search(self, db: Database) -> None:
        _seed(db)
        results = search(db, "artificial intelligence")
        assert len(results) >= 1
        assert "artificial intelligence" in results[0].text.lower()

    def test_search_no_results(self, db: Database) -> None:
        _seed(db)
        results = search(db, "blockchain cryptocurrency")
        assert len(results) == 0

    def test_search_with_limit(self, db: Database) -> None:
        _seed(db)
        results = search(db, "the", limit=1)
        assert len(results) == 1

    def test_search_result_fields(self, db: Database) -> None:
        _seed(db)
        results = search(db, "podcast")
        assert len(results) >= 1
        r = results[0]
        assert r.episode_title == "Episode One"
        assert r.podcast_title == "Test Podcast"
        assert r.start_sec >= 0
        assert r.end_sec > r.start_sec
        assert r.text
        assert r.rank < 0  # FTS5 rank is negative (lower = better)

    def test_search_by_podcast_filter(self, db: Database) -> None:
        _seed(db)
        # Search with matching podcast_id
        results = search(db, "podcast", podcast_id=1)
        assert len(results) >= 1

        # Search with non-matching podcast_id
        results = search(db, "podcast", podcast_id=999)
        assert len(results) == 0

    def test_search_by_since_filter(self, db: Database) -> None:
        _seed(db)
        results = search(db, "podcast", since="2025-01-01T00:00:00+00:00")
        assert len(results) >= 1

        results = search(db, "podcast", since="2026-01-01T00:00:00+00:00")
        assert len(results) == 0
