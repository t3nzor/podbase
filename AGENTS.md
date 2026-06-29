# AGENTS.md

## Project

podbase — maintain a searchable database of podcast transcripts.
Language: Python 3.11+. License: MIT. Package manager: **uv**.

## Quick reference

```bash
uv sync                          # install deps (including dev)
uv run podbase --help            # CLI help
uv run podbase subscribe <url>   # add podcast RSS feed
uv run podbase sync              # pull new episodes from all feeds
uv run podbase download <id>     # download audio for an episode
uv run podbase transcribe --pending  # transcribe all pending episodes
uv run podbase search "query"    # FTS5 search across transcripts
uv run podbase list podcasts     # list subscriptions
uv run podbase list episodes     # list episodes
uv run podbase db migrate        # run pending migrations
uv run podbase db reset --confirm  # delete database
```

## Quality checks

```bash
uv run ruff check src/           # lint
uv run ruff format src/          # format
uv run ruff format --check src/  # format check (CI)
uv run mypy src/                 # type-check
uv run pytest -v                 # tests
```

Run all three before committing: `uv run ruff check src/ && uv run ruff format --check src/ && uv run mypy src/ && uv run pytest`

## Architecture

```
src/podbase/
  cli.py              # typer CLI entry point
  config.py           # Config dataclass (data_dir, whisper settings)
  db.py               # SQLite connection, migration runner, schema DDL
  models.py           # dataclasses: Podcast, Episode, Segment, Job, SearchResult
  ingest/
    rss.py            # feedparser subscribe + sync
    download.py       # resumable httpx audio download
  transcribe/
    whisper.py        # faster-whisper Transcriber wrapper
    chunk.py          # word timings → ~30s text segments
    pipeline.py       # glue: download → transcribe → chunk → DB insert
  search/
    fts.py            # FTS5 keyword search
```

### Data storage

Everything lives in a single SQLite database at `data/podbase.db` (gitignored).
Audio downloads go to `data/audio/` and are **deleted after successful transcription** by default.
Set `PODBASE_DATA_DIR` env var to override the data directory.

### Schema

- `podcasts` — subscribed feeds
- `episodes` — per-episode metadata + status (`new` → `downloaded` → `transcribing` → `transcribed` | `failed`)
- `segments` — transcript text chunked into ~30s windows with timestamps
- `segments_fts` — FTS5 virtual table (external content), auto-synced via triggers
- `jobs` — transcribe/embed job queue
- `schema_version` — migration tracking

### Transcription

Uses **faster-whisper** with `large-v3` model, `device="cuda"`, `compute_type="int8"`.
Falls back to CPU if no GPU available. Config is in `config.py`.

### Search

FTS5 keyword search with BM25 ranking. Filters: `--podcast`, `--since`, `--limit`.
Phase 2 will add semantic vector search via `sqlite-vec`.

## Conventions

- Default branch: `main`
- Remote: `git@github.com:t3nzor/podbase.git`
- Python 3.11+ (uses `from __future__ import annotations`)
- Type annotations required (mypy strict mode)
- Line length: 100 (ruff)
- Imports: sorted by ruff (isort rules enabled)
- Enums use `StrEnum` (not `str, Enum`)

## Phase roadmap

- **Phase 1** (current): CLI MVP — RSS subscribe, sync, download, transcribe, FTS5 search
- **Phase 2**: Semantic search (sentence-transformers + sqlite-vec) + FastAPI web UI
- **Phase 3**: Background worker, resume, CI
- **Phase 4**: LLM chatbot (RAG over transcripts via Ollama or API)
