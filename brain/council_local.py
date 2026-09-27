"""Plan B: local orchestrator. Same prompts, file contract and brain API, no ClawMax.

Retrieval is pre-fetched in Python (via the recall layer) and passed into each prompt,
so there is no agent tool loop. Deterministic and fast. Validates citations and vote
lines per Section 9.6.

Runs in the server process, so it calls the recall layer directly (that layer owns
Cognee reads). Writes to Cognee only at record_decision, guarded by the shared
write lock passed in from the server.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from pathlib import Path

from anthropic import AsyncAnthropic

from . import records
from .config import CHAIR_MODEL, OWNER, SELF_MODEL, SESSIONS_DIR
from .eras import past_eras, present_era
from .prompts import load_prompt
from .recall import history, recall_as, voice

_client = AsyncAnthropic()

VOTE_RE = re.compile(r"^\*\*Vote:\*\*\s*(.+)$", re.M | re.I)
CITE_RE = re.compile(r"\[\d{4}-\d{2}-\d{2}\]")
CHANGED_RE = re.compile(r"\*\*Changed:\*\*\s*(yes|no)", re.I)


async def llm(model: str, system: str, user: str, max_tokens: int = 1600) -> str:
    msg = await _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


def _dir(session_id: str) -> Path:
    return Path(SESSIONS_DIR) / session_id


def _write(session_id: str, filename: str, content: str) -> None:
    (_dir(session_id) / filename).write_text(content)


def parse_vote(md: str) -> str:
    m = VOTE_RE.search(md)
    return m.group(1).strip() if m else "ABSTAIN"


def count_citations(md: str) -> int:
    return len(CITE_RE.findall(md))


def _evidence_block(title: str, payload: dict) -> str:
    """Render a recall/voice/history payload into a compact context block."""
    lines = [f"### {title}"]
    if "answer" in payload and payload["answer"]:
        lines.append(f"Answer: {payload['answer']}")
    for ev in payload.get("evidence", []) or payload.get("samples", []):
        lines.append(f"- [{ev['date']}] ({ev['type']}) {ev['text']}")
    for key in ("patterns", "decisions", "timeline", "past_verdicts"):
        if payload.get(key):
            lines.append(f"{key}:")
            for item in payload[key]:
                lines.append(f"  - {item}")
    return "\n".join(lines)


async def run_council(
    dilemma: str,
    session_id: str | None = None,
    write_lock: asyncio.Lock | None = None,
) -> str:
    session = (
        records.read_session(session_id)
        if session_id and (_dir(session_id) / "session.json").exists()
        else records.new_session(dilemma)
    )
    sid = session["id"]
    now = present_era()

    # ------------------------------------------------------------------ 1. BRIEF
    records.set_status(sid, "brief")
    brief_ctx = []
    for q in (dilemma, f"my values and priorities around: {dilemma}"):
        r = await recall_as("now", q, k=6)
        brief_ctx.append(_evidence_block(f"present-me on '{q[:50]}'", r))
    chair_brief_sys = load_prompt("chair_brief").format(owner=OWNER)
    brief_user = (
        f"Dilemma: {dilemma}\n\nContext from present-day {OWNER} (asof_now):\n"
        + "\n\n".join(brief_ctx)
        + "\n\nWrite 00_brief.md now, following the required shape."
    )
    brief = await llm(CHAIR_MODEL, chair_brief_sys, brief_user)
    _write(sid, "00_brief.md", brief)

    # ------------------------------------------------------------------ 2. PARALLEL
    records.set_status(sid, "testimony")

    async def testify(era) -> tuple[str, str]:
        v = await voice(era.id)
        recalls = await asyncio.gather(
            recall_as(era.id, dilemma, k=6),
            recall_as(era.id, "what I valued and what I feared", k=6),
            recall_as(era.id, "a similar choice I faced and how it felt", k=6),
        )
        mem = [_evidence_block("voice samples", v)]
        mem += [_evidence_block(f"recall {i+1}", r) for i, r in enumerate(recalls)]
        sys = _fill_self("self", era)
        user = (
            f"THE BRIEF:\n{brief}\n\n"
            f"YOUR MEMORY (as of {era.end}, use only this):\n" + "\n\n".join(mem)
            + f"\n\nWrite 10_testimony_{era.id}.md now."
        )
        md = await llm(SELF_MODEL, sys, user)
        md = await _ensure_citations(md, sys, user, SELF_MODEL)
        _write(sid, f"10_testimony_{era.id}.md", md)
        return era.id, md

    async def historian_report() -> str:
        h = await history(dilemma)
        follow1 = await history("decisions I made after low-rated weeks and how they turned out")
        follow2 = await history(f"times I changed my mind about {dilemma}")
        ctx = "\n\n".join(
            _evidence_block(t, p)
            for t, p in [("history", h), ("after low weeks", follow1), ("changed my mind", follow2)]
        )
        sys = load_prompt("historian").format(owner=OWNER, session_dir=str(_dir(sid)))
        user = f"THE BRIEF:\n{brief}\n\nRECORD:\n{ctx}\n\nWrite 20_history.md now."
        md = await llm(CHAIR_MODEL, sys, user)
        _write(sid, "20_history.md", md)
        return md

    testimonies_task = asyncio.gather(*[testify(e) for e in past_eras()])
    history_task = asyncio.create_task(historian_report())
    testimonies = dict(await testimonies_task)
    history_md = await history_task
    records.update_session(
        sid, votes={eid: {"testimony": parse_vote(md)} for eid, md in testimonies.items()}
    )

    # ------------------------------------------------------------------ 3. CROSS-EXAM
    records.set_status(sid, "cross")

    async def cross(era) -> tuple[str, str]:
        others = "\n\n".join(
            f"--- {eid} testimony ---\n{md}" for eid, md in testimonies.items() if eid != era.id
        )
        sys = _fill_self("self_cross", era)
        user = (
            f"YOUR OWN TESTIMONY:\n{testimonies[era.id]}\n\n"
            f"OTHER SELVES' TESTIMONIES:\n{others}\n\n"
            f"THE HISTORIAN'S RECORD:\n{history_md}\n\n"
            f"Write 30_cross_{era.id}.md now (<=150 words)."
        )
        md = await llm(SELF_MODEL, sys, user, max_tokens=600)
        _write(sid, f"30_cross_{era.id}.md", md)
        return era.id, md

    crosses = dict(await asyncio.gather(*[cross(e) for e in past_eras()]))
    votes = {}
    for eid in testimonies:
        votes[eid] = {
            "testimony": parse_vote(testimonies[eid]),
            "cross": parse_vote(crosses[eid]),
            "changed": bool(CHANGED_RE.search(crosses[eid]) and "yes" in CHANGED_RE.search(crosses[eid]).group(1).lower()),
        }
    records.update_session(sid, votes=votes)

    # ------------------------------------------------------------------ 4. VERDICT
    records.set_status(sid, "verdict")
    all_files = _read_all_md(sid)
    verdict_sys = load_prompt("chair_verdict").format(owner=OWNER)
    verdict_user = (
        f"Dilemma: {dilemma}\n\nALL SESSION FILES:\n{all_files}\n\n"
        f"Today is {date.today().isoformat()}. Write 90_verdict.md now, "
        "including the 'Check back: YYYY-MM-DD' line."
    )
    verdict = await llm(CHAIR_MODEL, verdict_sys, verdict_user, max_tokens=2000)
    if "Check back:" not in verdict:
        from datetime import timedelta

        verdict += f"\n\nCheck back: {(date.today() + timedelta(days=30)).isoformat()}\n"
    _write(sid, "90_verdict.md", verdict)

    # Write the verdict into Cognee memory (guarded).
    if write_lock is not None:
        async with write_lock:
            await records.record_decision(sid)
    else:
        await records.record_decision(sid)

    records.set_status(sid, "decided")
    return sid


# --------------------------------------------------------------------------- helpers
def _fill_self(prompt_name: str, era) -> str:
    text = load_prompt(prompt_name)

    class _D(dict):
        def __missing__(self, k):
            return "{" + k + "}"

    return text.format_map(
        _D(
            owner=OWNER,
            era_id=era.id,
            era_name=era.name,
            start=era.start.isoformat(),
            end=era.end.isoformat(),
            blurb=era.blurb,
            session_dir=str(Path(SESSIONS_DIR)),
        )
    )


async def _ensure_citations(md: str, sys: str, user: str, model: str, minimum: int = 3) -> str:
    """Citation rule (9.6): a testimony needs >=3 [YYYY-MM-DD] citations; retry once."""
    if count_citations(md) >= minimum:
        return md
    retry_user = (
        user
        + "\n\nYOUR DRAFT WAS REJECTED: it had fewer than 3 dated [YYYY-MM-DD] citations. "
        "Rewrite it now with at least 3 citations drawn only from your evidence above."
    )
    md2 = await llm(model, sys, retry_user)
    return md2 if count_citations(md2) >= minimum else md


def _read_all_md(session_id: str) -> str:
    parts = []
    for p in sorted(_dir(session_id).glob("*.md")):
        parts.append(f"===== {p.name} =====\n{p.read_text()}")
    return "\n\n".join(parts)
