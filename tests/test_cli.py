from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from podbase.cli import app
from podbase.db import Database

runner = CliRunner()


def _seed_episodes(db: Database, podcast_id: int, n: int) -> None:
    """Insert n episodes for a podcast, published one day apart (newest first)."""
    for i in range(n):
        db.conn.execute(
            "INSERT INTO episodes (podcast_id, guid, title, published_at, status) "
            "VALUES (?, ?, ?, ?, 'new')",
            (
                podcast_id,
                f"ep-{podcast_id}-{i}",
                f"Episode {i}",
                f"2025-06-{30 - i:02d}T00:00:00+00:00",
            ),
        )
    db.conn.commit()


def _run_with_capture(
    tmp_path: Path,
    args: list[str],
) -> list[int]:
    """Run `podbase transcribe <args>` and return the episode IDs
    that were passed to transcribe_episode."""
    captured: list[int] = []

    def fake_transcribe_episode(
        db: Database,
        episode_id: int,
        transcriber: object,
        audio_dir: Path,
        *,
        keep_audio: bool = False,
    ) -> int:
        captured.append(episode_id)
        return 10

    mock_transcriber = MagicMock()

    with (
        patch(
            "podbase.transcribe.whisper.Transcriber",
            return_value=mock_transcriber,
        ),
        patch(
            "podbase.transcribe.pipeline.transcribe_episode",
            side_effect=fake_transcribe_episode,
        ),
        patch(
            "podbase.ingest.download.download_audio",
            return_value=Path("/dev/null"),
        ),
    ):
        result = runner.invoke(
            app,
            ["transcribe", *args],
            env={"PODBASE_DATA_DIR": str(tmp_path)},
        )

    assert result.exit_code == 0, result.output
    return captured


class TestTranscribeLatest:
    def _setup_db(self, tmp_path: Path) -> Database:
        db = Database(tmp_path / "podbase.db")
        db.migrate()
        db.conn.execute(
            "INSERT INTO podcasts (id, title, rss_url) VALUES (1, 'A', 'https://a')",
        )
        db.conn.execute(
            "INSERT INTO podcasts (id, title, rss_url) VALUES (2, 'B', 'https://b')",
        )
        db.conn.commit()
        _seed_episodes(db, 1, 15)
        _seed_episodes(db, 2, 15)
        return db

    def test_latest_selects_most_recent(self, tmp_path: Path) -> None:
        """--latest 10 --podcast 1 picks the 10 most recent new episodes."""
        self._setup_db(tmp_path)
        captured = _run_with_capture(
            tmp_path, ["--latest", "10", "--podcast", "1"]
        )
        assert len(captured) == 10
        # Episodes are numbered 0..14, published newest-first.
        # Episode IDs are assigned by SQLite autoincrement (podcast 1 starts at 1).
        # The 10 most recent should be ep-1-0 through ep-1-9 → IDs 1..10.
        assert all(eid in range(1, 11) for eid in captured)

    def test_latest_without_podcast(self, tmp_path: Path) -> None:
        """--latest 5 across both podcasts picks the 5 globally most recent."""
        self._setup_db(tmp_path)
        captured = _run_with_capture(tmp_path, ["--latest", "5"])
        assert len(captured) == 5

    def test_latest_fewer_than_n(self, tmp_path: Path) -> None:
        """If a podcast has fewer than N new episodes, return all of them."""
        db = Database(tmp_path / "podbase.db")
        db.migrate()
        db.conn.execute(
            "INSERT INTO podcasts (id, title, rss_url) VALUES (1, 'A', 'https://a')",
        )
        db.conn.commit()
        _seed_episodes(db, 1, 3)

        captured = _run_with_capture(
            tmp_path, ["--latest", "10", "--podcast", "1"]
        )
        assert len(captured) == 3

    def test_latest_excludes_non_new(self, tmp_path: Path) -> None:
        """Episodes already transcribed or failed should not be picked."""
        db = self._setup_db(tmp_path)
        # Mark episodes 0..4 as transcribed, 5..9 as failed
        for i in range(5):
            db.conn.execute(
                "UPDATE episodes SET status = 'transcribed' WHERE guid = ?",
                (f"ep-1-{i}",),
            )
        for i in range(5, 10):
            db.conn.execute(
                "UPDATE episodes SET status = 'failed' WHERE guid = ?",
                (f"ep-1-{i}",),
            )
        db.conn.commit()

        captured = _run_with_capture(
            tmp_path, ["--latest", "10", "--podcast", "1"]
        )
        # Only episodes 10..14 are still 'new' (5 episodes)
        assert len(captured) == 5

    def test_mutual_exclusivity(self, tmp_path: Path) -> None:
        """Passing two selectors should error."""
        self._setup_db(tmp_path)
        result = runner.invoke(
            app,
            ["transcribe", "--latest", "10", "--all-new"],
            env={"PODBASE_DATA_DIR": str(tmp_path)},
        )
        assert result.exit_code != 0
        assert "only one" in result.output.lower()

    def test_podcast_filter_on_all_new(self, tmp_path: Path) -> None:
        """--all-new --podcast 1 should only select podcast 1 episodes."""
        self._setup_db(tmp_path)
        captured = _run_with_capture(
            tmp_path, ["--all-new", "--podcast", "1"]
        )
        assert len(captured) == 15

    def test_podcast_filter_on_pending(self, tmp_path: Path) -> None:
        """--pending --podcast 1 selects only podcast 1 pending jobs."""
        db = self._setup_db(tmp_path)
        # Mark first episode of podcast 1 as downloaded with a pending job
        db.conn.execute(
            "UPDATE episodes SET status = 'downloaded' WHERE guid = 'ep-1-0'"
        )
        db.conn.execute(
            "INSERT INTO jobs (episode_id, kind, status) "
            "VALUES (1, 'transcribe', 'pending')"
        )
        db.conn.commit()

        captured = _run_with_capture(
            tmp_path, ["--pending", "--podcast", "1"]
        )
        assert captured == [1]
