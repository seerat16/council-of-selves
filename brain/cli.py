"""`selves` — a thin httpx client over the brain server. Prints JSON.

This module MUST NOT import cognee. It talks to the server over HTTP only, so it can
run inside ClawMax agents (via the selves-brain skill) and from your shell.
"""

from __future__ import annotations

import json
import os

import httpx
import typer

BRAIN_URL = os.getenv("SELVES_BRAIN_URL", "http://localhost:8765")

app = typer.Typer(add_completion=False, help="Council of Selves CLI (HTTP client).")
session_app = typer.Typer(help="Session commands.")
app.add_typer(session_app, name="session")


def _print(obj) -> None:
    typer.echo(json.dumps(obj, indent=2, ensure_ascii=False))


def _get(path: str, **params):
    with httpx.Client(base_url=BRAIN_URL, timeout=120) as c:
        r = c.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()


def _post(path: str, body: dict):
    with httpx.Client(base_url=BRAIN_URL, timeout=600) as c:
        r = c.post(path, json=body)
        r.raise_for_status()
        return r.json()


@app.command()
def eras() -> None:
    """List eras + dataset names."""
    _print(_get("/api/eras"))


@app.command()
def ingest(
    reset: bool = typer.Option(False, "--reset"),
    inbox: bool = typer.Option(False, "--inbox"),
    path: str = typer.Option(None, "--path"),
) -> None:
    """Ingest the corpus into Cognee time-slice datasets."""
    _print(_post("/api/ingest", {"reset": reset, "inbox": inbox, "path": path}))


@app.command()
def recall(
    as_: str = typer.Option(..., "--as", help="era id (or 'now')"),
    q: str = typer.Option(..., "-q", "--question"),
    k: int = typer.Option(6, "-k"),
) -> None:
    """Recall as a given era (time-leak guarded)."""
    _print(_post("/api/recall", {"as": as_, "q": q, "k": k}))


@app.command()
def voice(as_: str = typer.Option(..., "--as")) -> None:
    """Get tone/voice samples for an era."""
    _print(_post("/api/voice", {"as": as_}))


@app.command()
def history(q: str = typer.Option(..., "-q", "--question")) -> None:
    """Cross-era history: patterns, decisions, temporal, past verdicts."""
    _print(_post("/api/history", {"q": q}))


@session_app.command("new")
def session_new(dilemma: str = typer.Argument(...)) -> None:
    """Create a session (mode=clawmax; does not auto-run Plan B)."""
    _print(_post("/api/sessions", {"dilemma": dilemma, "mode": "clawmax"}))


@session_app.command("current")
def session_current() -> None:
    """Print the current session id."""
    from . import records

    _print({"id": records.current_session_id()})


@session_app.command("show")
def session_show(session_id: str = typer.Argument(None)) -> None:
    """Show a session's brief + files (defaults to current)."""
    from . import records

    sid = session_id or records.current_session_id()
    if not sid:
        _print({"error": "no current session"})
        raise typer.Exit(1)
    _print(_get(f"/api/sessions/{sid}"))


@app.command()
def council(
    dilemma: str = typer.Argument(...),
    local: bool = typer.Option(False, "--local", help="Run Plan B end to end"),
) -> None:
    """Convene a council. With --local, runs Plan B on the server end-to-end."""
    mode = "local" if local else "clawmax"
    _print(_post("/api/sessions", {"dilemma": dilemma, "mode": mode}))


@app.command()
def record(
    what: str = typer.Argument(..., help="'decision'"),
    session_id: str = typer.Argument(None),
) -> None:
    """Record the verdict of a session into Cognee memory."""
    from . import records

    if what != "decision":
        _print({"error": "usage: selves record decision [<id>]"})
        raise typer.Exit(1)
    sid = session_id or records.current_session_id()
    _print(_post(f"/api/sessions/{sid}/decision", {}))


@app.command()
def outcome(
    session_id: str = typer.Argument(...),
    rating: int = typer.Option(..., "--rating", help="-2..+2"),
    text: str = typer.Option(..., "--text"),
    today: str = typer.Option(None, "--today", help="YYYY-MM-DD (demo simulation)"),
) -> None:
    """Record how a decision turned out."""
    _print(
        _post(
            f"/api/sessions/{session_id}/outcome",
            {"rating": rating, "text": text, "today": today},
        )
    )


@app.command()
def due(today: str = typer.Option(None, "--today", help="YYYY-MM-DD")) -> None:
    """List sessions whose check-in is due."""
    _print(_get("/api/due", today=today))


@app.command()
def stats() -> None:
    """Datasets + entry counts (expected cumulative counts per era + timeline)."""
    _print(_get("/api/stats"))


@app.command()
def push(dataset: list[str] = typer.Option(None, "--dataset", help="repeatable; default = all")) -> None:
    """Push locally-built sliced datasets to your hosted Cognee tenant."""
    _print(_post("/api/push", {"datasets": list(dataset) if dataset else None}))


if __name__ == "__main__":
    app()
