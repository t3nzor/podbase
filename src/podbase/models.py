from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EpisodeStatus(StrEnum):
    NEW = "new"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    FAILED = "failed"


class JobKind(StrEnum):
    TRANSCRIBE = "transcribe"
    EMBED = "embed"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Podcast:
    id: int
    title: str
    rss_url: str
    etag: str | None
    last_synced_at: str | None
    added_at: str


@dataclass
class Episode:
    id: int
    podcast_id: int
    guid: str
    title: str
    published_at: str | None
    audio_url: str | None
    duration_sec: float | None
    status: EpisodeStatus
    transcribed_at: str | None
    summary: str | None


@dataclass
class Segment:
    id: int
    episode_id: int
    idx: int
    start_sec: float
    end_sec: float
    text: str


@dataclass
class Job:
    id: int
    episode_id: int
    kind: JobKind
    status: JobStatus
    error: str | None
    attempts: int
    created_at: str


@dataclass
class SearchResult:
    episode_title: str
    podcast_title: str
    published_at: str | None
    start_sec: float
    end_sec: float
    text: str
    rank: float
