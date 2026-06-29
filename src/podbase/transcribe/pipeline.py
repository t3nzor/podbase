from __future__ import annotations

from pathlib import Path

from podbase.db import Database
from podbase.models import EpisodeStatus
from podbase.transcribe.chunk import chunk_words
from podbase.transcribe.whisper import Transcriber


def transcribe_episode(
    db: Database,
    episode_id: int,
    transcriber: Transcriber,
    audio_dir: Path,
    *,
    keep_audio: bool = False,
) -> int:
    """Run the full transcribe pipeline for one episode.

    1. Find the downloaded audio file.
    2. Transcribe with faster-whisper → word timings.
    3. Chunk into segments.
    4. Insert segments into DB.
    5. Mark episode as transcribed, optionally delete audio.

    Returns the number of segments created.
    """
    row = db.conn.execute("SELECT id, status FROM episodes WHERE id = ?", (episode_id,)).fetchone()
    if row is None:
        raise ValueError(f"Episode {episode_id} not found")
    if row["status"] == EpisodeStatus.TRANSCRIBED.value:
        return 0

    # Find audio file
    audio_path: Path | None = None
    for p in audio_dir.glob(f"{episode_id}.*"):
        if p.suffix != ".tmp":
            audio_path = p
            break
    if audio_path is None:
        raise FileNotFoundError(f"No audio file for episode {episode_id} in {audio_dir}")

    db.conn.execute(
        "UPDATE episodes SET status = ? WHERE id = ?",
        (EpisodeStatus.TRANSCRIBING.value, episode_id),
    )
    db.conn.execute(
        "UPDATE jobs SET status = 'running' WHERE episode_id = ? AND kind = 'transcribe'",
        (episode_id,),
    )
    db.conn.commit()

    try:
        result = transcriber.transcribe(str(audio_path))
        segments = chunk_words(result.words)

        # Clear any existing segments for this episode (re-transcribe safe)
        db.conn.execute("DELETE FROM segments WHERE episode_id = ?", (episode_id,))

        for seg in segments:
            db.conn.execute(
                "INSERT INTO segments "
                "(episode_id, idx, start_sec, end_sec, text) "
                "VALUES (?, ?, ?, ?, ?)",
                (episode_id, seg.idx, seg.start_sec, seg.end_sec, seg.text),
            )

        db.conn.execute(
            "UPDATE episodes SET status = ?, transcribed_at = datetime('now') WHERE id = ?",
            (EpisodeStatus.TRANSCRIBED.value, episode_id),
        )
        db.conn.execute(
            "UPDATE jobs SET status = 'done' WHERE episode_id = ? AND kind = 'transcribe'",
            (episode_id,),
        )
        db.conn.commit()

        if not keep_audio:
            audio_path.unlink(missing_ok=True)

        return len(segments)

    except Exception as exc:
        db.conn.execute(
            "UPDATE episodes SET status = ? WHERE id = ?",
            (EpisodeStatus.FAILED.value, episode_id),
        )
        db.conn.execute(
            """\
            UPDATE jobs SET status = 'failed', error = ?, attempts = attempts + 1
            WHERE episode_id = ? AND kind = 'transcribe'
            """,
            (str(exc), episode_id),
        )
        db.conn.commit()
        raise
