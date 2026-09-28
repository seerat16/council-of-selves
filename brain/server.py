"""FastAPI brain server (port 8765). The ONLY process that touches Cognee.

All Cognee writes (ingest, record_decision, record_outcome) are serialized behind a
single asyncio.Lock. Recall/history/voice are reads and run without the write lock.
"""

from __future__ import annotations

import asyncio
from datetime import date

import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import config, records
from .config import WEB_DIR
from .eras import load_eras, owner

app = FastAPI(title="Council of Selves — Brain", version="0.1.0")

# Serialize all Cognee writes.
_WRITE_LOCK = asyncio.Lock()


@app.exception_handler(Exception)
async def _all_errors(request: Request, exc: Exception) -> JSONResponse:
    """Surface the real error (type, message, traceback) to the client instead of a
    bare 500, and print it server-side too. Makes debugging far easier."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(tb)
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc), "traceback": tb[-4000:]},
    )


@app.on_event("startup")
async def _startup() -> None:
    config.configure_cognee()
    if config.cognee_cloud_enabled():
        try:
            await config.connect_cloud()
            print(f"[server] connected to Cognee tenant: {config.COGNEE_SERVICE_URL}")
        except Exception as exc:  # noqa: BLE001
            print(f"[server] Cognee cloud connect failed (continuing local): {exc}")


# --------------------------------------------------------------------------- models
class IngestBody(BaseModel):
    path: str | None = None
    reset: bool = False
    inbox: bool = False


class RecallBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    as_: str | None = Field(default=None, alias="as")
    q: str
    k: int = 6


class VoiceBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    as_: str | None = Field(default=None, alias="as")


class HistoryBody(BaseModel):
    q: str


class SessionBody(BaseModel):
    dilemma: str
    mode: str = "local"  # "local" | "clawmax"


class OutcomeBody(BaseModel):
    rating: int
    text: str
    today: str | None = None


# --------------------------------------------------------------------------- eras
@app.get("/api/eras")
async def api_eras() -> dict:
    return {"owner": owner(), "eras": [e.to_dict() for e in load_eras()]}


@app.get("/api/stats")
async def api_stats() -> dict:
    """Entry counts per era dataset + timeline, derived from the corpus on disk.

    These are the *expected* cumulative counts (12/24/36/48 for the seed persona);
    the actual cognified document counts should match after `selves ingest --reset`.
    """
    from .entries import load_entries

    entries = load_entries(config.DATA_DIR)
    per_dataset: dict[str, int] = {}
    for era in load_eras():
        per_dataset[era.dataset] = len([e for e in entries if e.date <= era.end])
    per_dataset[config.TIMELINE_DATASET] = len(entries)
    return {
        "data_dir": str(config.DATA_DIR),
        "total_entries": len(entries),
        "datasets": per_dataset,
        "sessions": len(records.list_sessions()),
    }


# --------------------------------------------------------------------------- ingest
@app.post("/api/ingest")
async def api_ingest(body: IngestBody) -> dict:
    from . import ingest as ingest_mod
    from pathlib import Path

    async with _WRITE_LOCK:
        if body.inbox:
            return await ingest_mod.ingest_inbox()
        path = Path(body.path) if body.path else config.DATA_DIR
        return await ingest_mod.ingest_all(path=path, reset=body.reset)


# --------------------------------------------------------------------------- recall
@app.post("/api/recall")
async def api_recall(body: RecallBody) -> dict:
    from . import recall as recall_mod

    era_id = body.as_ or "now"
    try:
        return await recall_mod.recall_as(era_id, body.q, k=body.k)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown era: {era_id}")


@app.post("/api/voice")
async def api_voice(body: VoiceBody) -> dict:
    from . import recall as recall_mod

    era_id = body.as_ or "now"
    try:
        return await recall_mod.voice(era_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown era: {era_id}")


@app.post("/api/history")
async def api_history(body: HistoryBody) -> dict:
    from . import recall as recall_mod

    return await recall_mod.history(body.q)


# --------------------------------------------------------------------------- sessions
@app.post("/api/sessions")
async def api_new_session(body: SessionBody) -> dict:
    session = records.new_session(body.dilemma)
    if body.mode == "local":
        # Run Plan B end-to-end as a background task. It writes to Cognee only at
        # record_decision, guarded by the shared write lock passed in.
        asyncio.create_task(_run_local(session["id"], body.dilemma))
        session["mode"] = "local"
        session["note"] = "Plan B council running in background; poll this session."
    else:
        session["mode"] = "clawmax"
        session["note"] = "Run council-1-brief in ClawMax to begin."
    return session


async def _run_local(session_id: str, dilemma: str) -> None:
    from . import council_local

    try:
        await council_local.run_council(dilemma, session_id=session_id, write_lock=_WRITE_LOCK)
    except Exception as exc:  # noqa: BLE001
        records.set_status(session_id, "error")
        print(f"[server] local council failed for {session_id}: {exc}")


@app.get("/api/sessions")
async def api_list_sessions() -> list[dict]:
    return records.list_sessions()


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str) -> dict:
    try:
        return records.read_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")


@app.post("/api/sessions/{session_id}/decision")
async def api_decision(session_id: str) -> dict:
    async with _WRITE_LOCK:
        try:
            return await records.record_decision(session_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/sessions/{session_id}/outcome")
async def api_outcome(session_id: str, body: OutcomeBody) -> dict:
    today = date.fromisoformat(body.today) if body.today else None
    async with _WRITE_LOCK:
        return await records.record_outcome(session_id, body.rating, body.text, today=today)


class PushBody(BaseModel):
    datasets: list[str] | None = None


@app.post("/api/push")
async def api_push(body: PushBody) -> dict:
    """Push locally-built sliced datasets to the hosted Cognee tenant."""
    from . import ingest as ingest_mod

    async with _WRITE_LOCK:
        return await ingest_mod.push_datasets(body.datasets)


@app.get("/api/due")
async def api_due(today: str | None = None) -> list[dict]:
    d = date.fromisoformat(today) if today else date.today()
    return records.due(d)


# --------------------------------------------------------------------------- graph + UI
@app.get("/graph", response_class=HTMLResponse)
async def api_graph(dataset: str | None = None) -> HTMLResponse:
    """Cognee graph visualization.

    With ENABLE_BACKEND_ACCESS_CONTROL=true, cognee requires a dataset. Default to the
    present era (asof_now); override with ?dataset=asof_grind_fall etc.
    VERIFY the visualize API + arg name against the installed cognee.
    """
    from pathlib import Path

    import cognee

    from .eras import present_era

    ds = dataset or present_era().dataset

    # Try the common call shapes; cognee's arg name varies by version.
    last_exc = None
    for call in (
        lambda: cognee.visualize_graph(dataset_name=ds),
        lambda: cognee.visualize_graph(datasets=[ds]),
        lambda: cognee.visualize_graph(dataset=ds),
        lambda: cognee.visualize_graph(ds),
        lambda: cognee.visualize_graph(),
    ):
        try:
            html = await call()  # type: ignore
        except TypeError as exc:
            last_exc = exc
            continue
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
        # Success: html may be markup or a file path.
        if isinstance(html, str) and "<html" in html.lower():
            return HTMLResponse(html)
        p = Path(str(html))
        if p.exists():
            return HTMLResponse(p.read_text())
        return HTMLResponse(f"<pre>graph rendered to: {html}</pre>")

    return HTMLResponse(
        f"<h3>Graph visualization unavailable</h3>"
        f"<p>dataset tried: <code>{ds}</code></p><pre>{last_exc}</pre>"
        "<p>Add <code>?dataset=asof_now</code> (or another dataset) to the URL, "
        "or VERIFY cognee.visualize_graph() against the installed version.</p>",
        status_code=200,
    )


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))
