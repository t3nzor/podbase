from __future__ import annotations

from pathlib import Path

import httpx

from podbase.db import Database
from podbase.models import EpisodeStatus

CHUNK_SIZE = 1024 * 256  # 256 KB


def download_audio(
    db: Database,
    episode_id: int,
    dest_dir: Path,
    *,
    timeout: float = 300,
) -> Path:
    """Download episode audio to dest_dir. Returns the file path."""
    row = db.conn.execute(
        "SELECT id, audio_url, status FROM episodes WHERE id = ?", (episode_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Episode {episode_id} not found")
    if row["audio_url"] is None:
        raise ValueError(f"Episode {episode_id} has no audio URL")
    if row["status"] == EpisodeStatus.DOWNLOADED.value:
        # Already downloaded — return existing path if file exists
        dest_dir / f"{episode_id}.mp3"
        for p in dest_dir.glob(f"{episode_id}.*"):
            return p
        # Fall through to re-download

    audio_url: str = row["audio_url"]
    db.conn.execute(
        "UPDATE episodes SET status = ? WHERE id = ?",
        (EpisodeStatus.DOWNLOADING.value, episode_id),
    )
    db.conn.commit()

    dest_dir.mkdir(parents=True, exist_ok=True)
    # We'll detect the extension from Content-Type, fallback to .mp3
    suffix = ".mp3"
    tmp_path = dest_dir / f"{episode_id}.tmp"
    final_path = dest_dir / f"{episode_id}{suffix}"

    try:
        # Support resumable download with Range header
        existing_size = tmp_path.stat().st_size if tmp_path.exists() else 0
        headers: dict[str, str] = {}
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream("GET", audio_url, headers=headers) as resp:
                resp.raise_for_status()

                # Detect suffix from content-type
                ct = resp.headers.get("content-type", "")
                if "ogg" in ct or "opus" in ct:
                    suffix = ".ogg"
                elif "mp4" in ct or "m4a" in ct:
                    suffix = ".m4a"
                elif "wav" in ct:
                    suffix = ".wav"
                final_path = dest_dir / f"{episode_id}{suffix}"

                # If server responded with 206, append; otherwise truncate
                mode = "ab" if resp.status_code == 206 else "wb"
                with open(tmp_path, mode) as f:
                    for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                        f.write(chunk)

        tmp_path.rename(final_path)

        db.conn.execute(
            "UPDATE episodes SET status = ? WHERE id = ?",
            (EpisodeStatus.DOWNLOADED.value, episode_id),
        )
        db.conn.commit()
        return final_path

    except Exception as exc:
        db.conn.execute(
            "UPDATE episodes SET status = ? WHERE id = ?",
            (EpisodeStatus.FAILED.value, episode_id),
        )
        db.conn.commit()
        raise exc


def delete_audio(audio_path: Path) -> None:
    """Delete an audio file if it exists."""
    if audio_path.exists():
        audio_path.unlink()
