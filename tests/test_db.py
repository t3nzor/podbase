from pathlib import Path

from podbase.db import Database


class TestDatabase:
    def test_migrate_creates_schema(self, db: Database) -> None:
        version = db.migrate()
        assert version == 1

        # Verify tables exist
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "podcasts" in table_names
        assert "episodes" in table_names
        assert "segments" in table_names
        assert "segments_fts" in table_names
        assert "jobs" in table_names
        assert "schema_version" in table_names

    def test_migrate_is_idempotent(self, db: Database) -> None:
        v1 = db.migrate()
        v2 = db.migrate()
        assert v1 == v2 == 1

    def test_current_version_before_migrate(self, db: Database) -> None:
        assert db.current_version() == 0

    def test_insert_and_query_podcast(self, db: Database) -> None:
        db.migrate()
        db.conn.execute(
            "INSERT INTO podcasts (title, rss_url) VALUES (?, ?)",
            ("Test Podcast", "https://example.com/feed.xml"),
        )
        db.conn.commit()

        row = db.conn.execute("SELECT title, rss_url FROM podcasts").fetchone()
        assert row is not None
        assert row["title"] == "Test Podcast"
        assert row["rss_url"] == "https://example.com/feed.xml"

    def test_insert_episode(self, db: Database) -> None:
        db.migrate()
        db.conn.execute(
            "INSERT INTO podcasts (title, rss_url) VALUES (?, ?)",
            ("Test", "https://example.com/feed"),
        )
        db.conn.execute(
            "INSERT INTO episodes (podcast_id, guid, title, audio_url) "
            "VALUES (?, ?, ?, ?)",
            (1, "ep-001", "Episode 1", "https://example.com/ep1.mp3"),
        )
        db.conn.commit()

        row = db.conn.execute(
            "SELECT title, status FROM episodes WHERE guid = 'ep-001'"
        ).fetchone()
        assert row is not None
        assert row["title"] == "Episode 1"
        assert row["status"] == "new"

    def test_fts_triggers(self, db: Database) -> None:
        db.migrate()
        db.conn.execute(
            "INSERT INTO podcasts (title, rss_url) VALUES (?, ?)",
            ("Test", "https://example.com/feed"),
        )
        db.conn.execute(
            "INSERT INTO episodes (podcast_id, guid, title) VALUES (?, ?, ?)",
            (1, "ep-001", "Episode 1"),
        )
        db.conn.execute(
            "INSERT INTO segments (episode_id, idx, start_sec, end_sec, text) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 0, 0.0, 30.0, "Hello world this is a test"),
        )
        db.conn.commit()

        rows = db.conn.execute(
            "SELECT rowid FROM segments_fts WHERE segments_fts MATCH 'hello'"
        ).fetchall()
        assert len(rows) == 1

    def test_close_and_reopen(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.migrate()
        db.close()

        db2 = Database(db_path)
        assert db2.current_version() == 1
        db2.close()
