from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.table import Table

from podbase.config import Config
from podbase.db import Database
from podbase.models import EpisodeStatus

app = typer.Typer(
    name="podbase",
    help="Maintain a searchable database of podcast transcripts.",
    no_args_is_help=True,
)
console = Console()


def _cfg() -> Config:
    return Config()


def _db(cfg: Config) -> Database:
    db = Database(cfg.db_path)
    db.migrate()
    return db


# ── subscribe ────────────────────────────────────────────────────────────────


@app.command()
def subscribe(rss_url: str) -> None:
    """Subscribe to a podcast RSS feed."""
    from podbase.ingest.rss import subscribe as do_subscribe

    cfg = _cfg()
    db = _db(cfg)
    try:
        pid = do_subscribe(db, rss_url)
        row = db.conn.execute("SELECT title FROM podcasts WHERE id = ?", (pid,)).fetchone()
        console.print(f"[green]✓[/green] Subscribed: [bold]{row['title']}[/bold] (id={pid})")
    finally:
        db.close()


# ── sync ─────────────────────────────────────────────────────────────────────


@app.command()
def sync(
    podcast: int | None = typer.Option(None, "--podcast", "-p", help="Sync only this podcast ID"),
) -> None:
    """Fetch new episodes from subscribed feeds."""
    from podbase.ingest.rss import sync as do_sync

    cfg = _cfg()
    db = _db(cfg)
    try:
        new, checked = do_sync(db, podcast_id=podcast)
        console.print(f"[green]✓[/green] Synced: {new} new episodes ({checked} checked)")
    finally:
        db.close()


# ── download ─────────────────────────────────────────────────────────────────


@app.command()
def download(
    episode: int | None = typer.Argument(None, help="Episode ID to download"),
    latest: int | None = typer.Option(
        None,
        "--latest",
        "-l",
        help="Download the N most recent new episodes",
    ),
    podcast: int | None = typer.Option(None, "--podcast", "-p", help="Limit to a specific podcast"),
) -> None:
    """Download audio for one or more episodes."""
    from podbase.ingest.download import download_audio

    cfg = _cfg()
    db = _db(cfg)
    try:
        selectors = [episode is not None, latest is not None]
        if sum(selectors) == 0:
            console.print("[red]Provide an episode ID or --latest[/red]")
            raise typer.Exit(1)
        if sum(selectors) > 1:
            console.print("[red]Use either an episode ID or --latest, not both[/red]")
            raise typer.Exit(1)

        if episode is not None:
            ep_ids = [episode]
        else:
            assert latest is not None
            sql = "SELECT id FROM episodes WHERE status = ?"
            params: list[object] = [EpisodeStatus.NEW.value]
            if podcast is not None:
                sql += " AND podcast_id = ?"
                params.append(podcast)
            sql += " ORDER BY COALESCE(published_at, '') DESC LIMIT ?"
            params.append(latest)
            rows = db.conn.execute(sql, params).fetchall()
            ep_ids = [r["id"] for r in rows]

        if not ep_ids:
            console.print("[yellow]No episodes to download.[/yellow]")
            return

        ok = 0
        for i, eid in enumerate(ep_ids, 1):
            console.print(f"[{i}/{len(ep_ids)}] Downloading episode {eid}...")
            try:
                path = download_audio(db, eid, cfg.audio_dir)
                console.print(f"  [green]✓[/green] {path}")
                ok += 1
            except Exception as exc:
                console.print(f"  [red]✗[/red] {exc}")

        console.print(f"[green]✓[/green] Downloaded {ok}/{len(ep_ids)} episodes")
    finally:
        db.close()


# ── transcribe ───────────────────────────────────────────────────────────────


@app.command()
def transcribe(
    episode: int | None = typer.Option(
        None, "--episode", "-e", help="Transcribe a specific episode"
    ),
    pending: bool = typer.Option(False, "--pending", help="Transcribe all pending episodes"),
    all_new: bool = typer.Option(
        False, "--all-new", help="Transcribe all episodes in 'new' status"
    ),
    latest: int | None = typer.Option(
        None,
        "--latest",
        "-l",
        help="Transcribe the N most recent new episodes",
    ),
    podcast: int | None = typer.Option(None, "--podcast", "-p", help="Limit to a specific podcast"),
) -> None:
    """Transcribe downloaded episodes using Whisper."""
    from podbase.ingest.download import download_audio
    from podbase.transcribe.pipeline import transcribe_episode
    from podbase.transcribe.whisper import Transcriber

    cfg = _cfg()
    db = _db(cfg)
    try:
        selectors = [
            episode is not None,
            pending,
            all_new,
            latest is not None,
        ]
        if sum(selectors) == 0:
            console.print("[red]Provide one of: --episode, --pending, --all-new, --latest[/red]")
            raise typer.Exit(1)
        if sum(selectors) > 1:
            console.print("[red]Use only one of: --episode, --pending, --all-new, --latest[/red]")
            raise typer.Exit(1)

        # Collect episode IDs
        if episode is not None:
            ep_ids = [episode]
        elif latest is not None:
            sql = "SELECT id FROM episodes WHERE status = ?"
            params: list[object] = [EpisodeStatus.NEW.value]
            if podcast is not None:
                sql += " AND podcast_id = ?"
                params.append(podcast)
            sql += " ORDER BY COALESCE(published_at, '') DESC LIMIT ?"
            params.append(latest)
            rows = db.conn.execute(sql, params).fetchall()
            ep_ids = [r["id"] for r in rows]
        elif all_new:
            sql = "SELECT id FROM episodes WHERE status = ?"
            params = [EpisodeStatus.NEW.value]
            if podcast is not None:
                sql += " AND podcast_id = ?"
                params.append(podcast)
            rows = db.conn.execute(sql, params).fetchall()
            ep_ids = [r["id"] for r in rows]
        else:  # pending
            sql = """\
                SELECT e.id FROM episodes e
                JOIN jobs j ON j.episode_id = e.id
                WHERE j.kind = 'transcribe' AND j.status IN ('pending', 'failed')
            """
            params = []
            if podcast is not None:
                sql += " AND e.podcast_id = ?"
                params.append(podcast)
            rows = db.conn.execute(sql, params).fetchall()
            ep_ids = [r["id"] for r in rows]

        if not ep_ids:
            console.print("[yellow]No episodes to transcribe.[/yellow]")
            return

        console.print(f"Loading Whisper model [bold]{cfg.whisper_model}[/bold]...")
        transcriber = Transcriber(
            model_name=cfg.whisper_model,
            device=cfg.whisper_device,
            compute_type=cfg.whisper_compute_type,
        )

        for i, eid in enumerate(ep_ids, 1):
            # Download first if needed
            ep_row = db.conn.execute(
                "SELECT status, title FROM episodes WHERE id = ?", (eid,)
            ).fetchone()
            if ep_row is None:
                console.print(f"[red]Episode {eid} not found, skipping.[/red]")
                continue

            if ep_row["status"] in (
                EpisodeStatus.NEW.value,
                EpisodeStatus.FAILED.value,
            ):
                console.print(f"[dim]Downloading episode {eid}...[/dim]")
                try:
                    download_audio(db, eid, cfg.audio_dir)
                except Exception as exc:
                    console.print(f"[red]Download failed for {eid}: {exc}[/red]")
                    continue

            title = ep_row["title"]
            console.print(f"[{i}/{len(ep_ids)}] Transcribing: [bold]{title}[/bold]")
            t0 = time.time()
            try:
                n = transcribe_episode(
                    db, eid, transcriber, cfg.audio_dir, keep_audio=cfg.keep_audio
                )
                elapsed = time.time() - t0
                console.print(f"  [green]✓[/green] {n} segments in {elapsed:.1f}s")
            except Exception as exc:
                console.print(f"  [red]✗[/red] Failed: {exc}")

    finally:
        db.close()


# ── search ───────────────────────────────────────────────────────────────────


@app.command("search")
def search_cmd(
    query: str = typer.Argument(help="Search query"),
    podcast: int | None = typer.Option(None, "--podcast", "-p"),
    since: str | None = typer.Option(None, "--since", "-s", help="ISO date lower bound"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """Search transcript segments."""
    from podbase.search.fts import search as do_search

    cfg = _cfg()
    db = _db(cfg)
    try:
        results = do_search(db, query, podcast_id=podcast, since=since, limit=limit)
        if not results:
            console.print("[yellow]No results.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Podcast", style="cyan", max_width=25)
        table.add_column("Episode", style="white", max_width=35)
        table.add_column("Time", style="green", justify="right", width=8)
        table.add_column("Text", style="white", max_width=60)

        for r in results:
            ts = _fmt_ts(r.start_sec)
            table.add_row(r.podcast_title, r.episode_title, ts, r.text)

        console.print(table)
    finally:
        db.close()


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ── list ─────────────────────────────────────────────────────────────────────

list_app = typer.Typer(help="List podcasts or episodes.")
app.add_typer(list_app, name="list")


@list_app.command("podcasts")
def list_podcasts() -> None:
    """List all subscribed podcasts."""
    cfg = _cfg()
    db = _db(cfg)
    try:
        rows = db.conn.execute(
            "SELECT id, title, rss_url, last_synced_at FROM podcasts ORDER BY title"
        ).fetchall()
        if not rows:
            console.print("[yellow]No podcasts subscribed yet.[/yellow]")
            return
        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Title", style="cyan")
        table.add_column("Last Synced", style="dim")
        for r in rows:
            table.add_row(str(r["id"]), r["title"], r["last_synced_at"] or "never")
        console.print(table)
    finally:
        db.close()


@list_app.command("episodes")
def list_episodes(
    podcast: int | None = typer.Option(None, "--podcast", "-p"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
) -> None:
    """List episodes."""
    cfg = _cfg()
    db = _db(cfg)
    try:
        sql = """\
        SELECT e.id, e.title, e.status, e.published_at, p.title AS podcast_title
        FROM episodes e JOIN podcasts p ON p.id = e.podcast_id
        WHERE 1=1
        """
        params: list[object] = []
        if podcast is not None:
            sql += " AND e.podcast_id = ?"
            params.append(podcast)
        if status is not None:
            sql += " AND e.status = ?"
            params.append(status)
        sql += " ORDER BY e.published_at DESC LIMIT 100"

        rows = db.conn.execute(sql, params).fetchall()
        if not rows:
            console.print("[yellow]No episodes found.[/yellow]")
            return
        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Podcast", style="cyan", max_width=25)
        table.add_column("Title", style="white", max_width=40)
        table.add_column("Status", style="yellow")
        table.add_column("Published", style="dim")
        for r in rows:
            table.add_row(
                str(r["id"]),
                r["podcast_title"],
                r["title"],
                r["status"],
                r["published_at"] or "",
            )
        console.print(table)
    finally:
        db.close()


# ── db ───────────────────────────────────────────────────────────────────────

db_app = typer.Typer(help="Database management.")
app.add_typer(db_app, name="db")


@db_app.command("migrate")
def db_migrate() -> None:
    """Run pending database migrations."""
    cfg = _cfg()
    db = Database(cfg.db_path)
    v = db.migrate()
    console.print(f"[green]✓[/green] Schema at version {v}")
    db.close()


@db_app.command("reset")
def db_reset(
    confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion"),
) -> None:
    """Delete the database and start fresh."""
    if not confirm:
        console.print("[red]Pass --confirm to actually delete the database.[/red]")
        raise typer.Exit(1)
    cfg = _cfg()
    if cfg.db_path.exists():
        cfg.db_path.unlink()
        console.print("[green]✓[/green] Database deleted.")
    else:
        console.print("[yellow]No database file found.[/yellow]")


if __name__ == "__main__":
    app()
