"""Sessions, decisions, outcomes, due check-ins.

Session read/write helpers are pure filesystem ops (no cognee) so the CLI can use
them. record_decision/record_outcome write to Cognee and are only called on the
server. cognee is imported lazily inside those two functions.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import RECORDS_DATASET, SESSIONS_DIR, TIMELINE_DATASET
from .entries import Entry, node_sets, render
from .eras import era_for, present_era

_CURRENT = "CURRENT"
_CHECK_BACK = re.compile(r"Check back:\s*(\d{4}-\d{2}-\d{2})")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "dilemma"


def _session_dir(session_id: str) -> Path:
    return Path(SESSIONS_DIR) / session_id


def new_session(dilemma: str) -> dict:
    today = date.today().isoformat()
    session_id = f"{today}-{_slug(dilemma)}"
    d = _session_dir(session_id)
    d.mkdir(parents=True, exist_ok=True)
    now = present_era()
    session = {
        "id": session_id,
        "dilemma": dilemma,
        "options": [],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "brief",
        "as_of": now.end.isoformat(),
        "check_back": None,
        "votes": {},
        "outcome": None,
    }
    (d / "session.json").write_text(json.dumps(session, indent=2))
    (Path(SESSIONS_DIR) / _CURRENT).write_text(session_id)
    return session


def current_session_id() -> str | None:
    p = Path(SESSIONS_DIR) / _CURRENT
    return p.read_text().strip() if p.exists() else None


def set_status(session_id: str, status: str) -> dict:
    d = _session_dir(session_id)
    session = json.loads((d / "session.json").read_text())
    session["status"] = status
    (d / "session.json").write_text(json.dumps(session, indent=2))
    return session


def update_session(session_id: str, **fields) -> dict:
    d = _session_dir(session_id)
    session = json.loads((d / "session.json").read_text())
    session.update(fields)
    (d / "session.json").write_text(json.dumps(session, indent=2))
    return session


def read_session(session_id: str) -> dict:
    d = _session_dir(session_id)
    session = json.loads((d / "session.json").read_text())
    files = {}
    for p in sorted(d.glob("*.md")):
        files[p.name] = p.read_text()
    session["files"] = files
    from .eras import owner as _owner

    session["owner_name"] = _owner() + ", "
    return session


def list_sessions() -> list[dict]:
    base = Path(SESSIONS_DIR)
    out = []
    if not base.exists():
        return out
    for d in sorted(base.iterdir(), reverse=True):
        sj = d / "session.json"
        if d.is_dir() and sj.exists():
            s = json.loads(sj.read_text())
            out.append(
                {
                    "id": s["id"],
                    "dilemma": s["dilemma"],
                    "status": s.get("status"),
                    "created_at": s.get("created_at"),
                    "check_back": s.get("check_back"),
                }
            )
    return out


def _header(d: date, type_: str) -> str:
    wd = d.strftime("%A")
    era = era_for(d)
    return f"[[{d.isoformat()} | {type_} | era={era.id} | {wd}]]"


async def record_decision(session_id: str, today: date | None = None) -> dict:
    import cognee

    today = today or date.today()
    d = _session_dir(session_id)
    memo_path = d / "90_verdict.md"
    if not memo_path.exists():
        raise FileNotFoundError("90_verdict.md not found; run the verdict stage first")
    memo = memo_path.read_text()

    m = _CHECK_BACK.search(memo)
    check_back = m.group(1) if m else (today + timedelta(days=30)).isoformat()

    session = json.loads((d / "session.json").read_text())
    text = f"{_header(today, 'verdict')}\nDilemma: {session['dilemma']}\n\n{memo}"
    await cognee.add(
        text,
        dataset_name=RECORDS_DATASET,
        node_set=["type:verdict", f"session:{session_id}"],
    )
    await cognee.cognify(datasets=[RECORDS_DATASET])

    session["status"] = "decided"
    session["check_back"] = check_back
    (d / "session.json").write_text(json.dumps(session, indent=2))
    return {"id": session_id, "status": "decided", "check_back": check_back}


async def record_outcome(
    session_id: str, rating: int, text: str, today: date | None = None
) -> dict:
    import cognee

    today = today or date.today()
    d = _session_dir(session_id)
    session = json.loads((d / "session.json").read_text())
    now = present_era()

    label = {-2: "regret", -1: "mixed-negative", 0: "neutral", 1: "good", 2: "best call"}
    body = (
        f"{_header(today, 'outcome')}\n"
        f"Outcome of council session {session_id} on dilemma: {session['dilemma']}\n"
        f"Rating: {rating} ({label.get(rating, 'n/a')}). {text}"
    )
    outcome_entry = Entry(date=today, type="outcome", text=body, tags=["outcome"])

    # Records dataset (verdict/outcome ledger)
    await cognee.add(
        body, dataset_name=RECORDS_DATASET, node_set=["type:outcome", f"session:{session_id}"]
    )
    # Present-era dataset + timeline (it becomes life memory)
    ns = node_sets(outcome_entry, now)
    await cognee.add(render(outcome_entry, now), dataset_name=now.dataset, node_set=ns)
    await cognee.add(render(outcome_entry, now), dataset_name=TIMELINE_DATASET, node_set=ns)

    await cognee.cognify(datasets=[RECORDS_DATASET])
    await cognee.cognify(datasets=[now.dataset])
    await cognee.cognify(datasets=[TIMELINE_DATASET], temporal_cognify=True)

    session["status"] = "closed"
    session["outcome"] = {"rating": rating, "text": text, "date": today.isoformat()}
    (d / "session.json").write_text(json.dumps(session, indent=2))
    return {"id": session_id, "status": "closed", "outcome": session["outcome"]}


def due(today: date) -> list[dict]:
    out = []
    for s in list_sessions():
        if s.get("status") == "decided" and s.get("check_back"):
            if s["check_back"] <= today.isoformat():
                out.append(s)
    return out
