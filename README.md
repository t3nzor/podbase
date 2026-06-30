# podbase

Maintain a searchable database of podcast transcripts.

Subscribe to podcast RSS feeds, automatically download and transcribe episodes with Whisper, and search across all your transcripts with full-text search.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- A CUDA-compatible GPU (recommended) or CPU for transcription

## Installation

```bash
git clone git@github.com:t3nzor/podbase.git
cd podbase
uv sync
```

This installs all dependencies including dev tools (ruff, mypy, pytest).

## Quick start

```bash
# Add a podcast
uv run podbase subscribe "https://feeds.example.com/podcast.xml"

# Pull new episodes from all feeds
uv run podbase sync

# Download and transcribe all pending episodes
uv run podbase transcribe --pending

# Search transcripts
uv run podbase search "artificial intelligence"
```

## Usage

### Subscribe to a podcast

```bash
uv run podbase subscribe <rss-url>
```

Parses the RSS feed, stores the podcast and its episodes, and creates transcribe jobs for episodes with audio.

### Sync feeds

```bash
uv run podbase sync
uv run podbase sync --podcast 1   # sync a single podcast
```

Fetches new episodes from all subscribed feeds using ETag caching.

### Download audio

```bash
uv run podbase download <episode-id>             # single episode
uv run podbase download --latest 10 --podcast 1  # 10 most recent of podcast 1
uv run podbase download --latest 5               # 5 most recent across all podcasts
```

Only `new` episodes are picked by `--latest`; already-downloaded ones are skipped. Supports resume on interrupted downloads. The `--podcast` filter works with both single-episode and `--latest` modes.

### Transcribe episodes

```bash
uv run podbase transcribe --pending       # transcribe all pending jobs
uv run podbase transcribe --episode 42    # transcribe a specific episode
uv run podbase transcribe --all-new       # transcribe all episodes in 'new' status
uv run podbase transcribe --latest 10 --podcast 1  # 10 most recent of podcast 1
uv run podbase transcribe --latest 5      # 5 most recent across all podcasts
```

Only one selector (`--episode`, `--pending`, `--all-new`, `--latest`) may be used at a time. The `--podcast` filter works with all selectors.

Uses faster-whisper with the `large-v3` model. Automatically uses GPU if available, falls back to CPU. Audio files are deleted after successful transcription by default.

### Search transcripts

```bash
uv run podbase search "machine learning"
uv run podbase search "climate change" --podcast 1
uv run podbase search "neural networks" --since 2025-01-01
uv run podbase search "deep learning" --limit 50
```

FTS5 keyword search with BM25 ranking. Results include episode title, podcast name, timestamp, and matched text.

### List podcasts and episodes

```bash
uv run podbase list podcasts
uv run podbase list episodes
uv run podbase list episodes --podcast 1
uv run podbase list episodes --status transcribed
```

### Database management

```bash
uv run podbase db migrate          # run pending migrations
uv run podbase db reset --confirm  # delete database and start fresh
```

## Configuration

The data directory (database + temp audio) is resolved in this order:

1. **`PODBASE_DATA_DIR` env var** — explicit override, takes highest priority
2. **Project root detection** — walks up from the current directory looking for `pyproject.toml` with `name = "podbase"`, uses `<root>/data`
3. **XDG fallback** — `~/.local/share/podbase` (used when running outside the project)

```bash
# Override the data directory
export PODBASE_DATA_DIR="/path/to/storage"
```

The database is stored at `<data_dir>/podbase.db` and audio files temporarily go to `<data_dir>/audio/`.

## Development

```bash
uv run ruff check src/           # lint
uv run ruff format src/          # format
uv run mypy src/                 # type-check
uv run pytest -v                 # run tests
```

## License

MIT
