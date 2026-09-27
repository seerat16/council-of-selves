"""Recall layer: era-scoped recall (with leak guard), voice samples, and history.

Imported only by the server (sole Cognee owner). All searches are wrapped in
try/except and return an `errors` field; council_records is empty before the first
verdict and TEMPORAL may fail if temporal cognify was skipped.
"""

from __future__ import annotations

import asyncio
import re

import cognee

from .config import OWNER, RECORDS_DATASET, TIMELINE_DATASET
from .eras import get_era, present_era

# VERIFY import path for SearchType against installed cognee.
try:
    from cognee import SearchType
except ImportError:  # pragma: no cover - fallback path
    from cognee.modules.search.types import SearchType  # type: ignore

# VERIFY import path for NodeSet.
try:
    from cognee.modules.engine.models.node_set import NodeSet  # type: ignore
except ImportError:  # pragma: no cover
    NodeSet = None  # type: ignore

HDR = re.compile(r"\[\[(\d{4}-\d{2}-\d{2}) \| (\w+) \| era=([\w-]+)")

# If concurrent searches cause embedded-store lock errors, flip to sequential.
_LOCK = asyncio.Lock()
SEQUENTIAL = False

SELF_SYS = (
    "You are answering from the memory of {owner} as of {end}. Use only the provided "
    "context. Answer in first person as {owner} would have then. Cite dates like "
    "[YYYY-MM-DD]. If the context is silent, say 'I don't remember thinking about that.'"
)


def _texts(results) -> list[str]:
    """Normalize Cognee results (str | dict | object | nested lists) to strings.

    VERIFY the real shapes with scripts/smoke_cognee.py and tighten this if needed.
    """
    out: list[str] = []

    def walk(x):
        if x is None:
            return
        if isinstance(x, str):
            if x.strip():
                out.append(x.strip())
        elif isinstance(x, dict):
            for key in ("text", "answer", "content", "chunk", "value", "payload"):
                if key in x and isinstance(x[key], str):
                    out.append(x[key].strip())
                    return
            # dict without a known text key: stringify shallowly
            out.append(str(x))
        elif isinstance(x, (list, tuple, set)):
            for item in x:
                walk(item)
        else:
            # SearchResult-like object: try common attributes
            for attr in ("text", "answer", "content", "value"):
                v = getattr(x, attr, None)
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                    return
            out.append(str(x))

    walk(results)
    return out


def _evidence(text: str) -> dict | None:
    m = HDR.search(text)
    if not m:
        return None
    return {
        "date": m.group(1),
        "type": m.group(2),
        "era": m.group(3),
        "text": text[m.end():].strip(" ]\n")[:600],
    }


async def _search(**kwargs):
    """Run a single cognee.search, optionally serialized behind a lock."""
    if SEQUENTIAL:
        async with _LOCK:
            return await cognee.search(**kwargs)
    return await cognee.search(**kwargs)


async def _gather(*coros):
    if SEQUENTIAL:
        results = []
        for c in coros:
            try:
                results.append(await c)
            except Exception as exc:  # noqa: BLE001
                results.append(exc)
        return results
    return await asyncio.gather(*coros, return_exceptions=True)


async def recall_as(era_id: str, q: str, k: int = 6) -> dict:
    era = get_era(era_id)
    errors: list[str] = []

    results = await _gather(
        _search(
            query_text=q,
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[era.dataset],
            system_prompt=SELF_SYS.format(owner=OWNER, end=era.end),
            top_k=k,
        ),
        _search(query_text=q, query_type=SearchType.CHUNKS, datasets=[era.dataset], top_k=k),
    )
    ans_res, chunk_res = results
    if isinstance(ans_res, Exception):
        errors.append(f"graph_completion: {ans_res}")
        ans_res = []
    if isinstance(chunk_res, Exception):
        errors.append(f"chunks: {chunk_res}")
        chunk_res = []

    ev = [e for e in map(_evidence, _texts(chunk_res)) if e]
    kept = [e for e in ev if e["date"] <= era.end.isoformat()]
    return {
        "as": era.id,
        "as_of": era.end.isoformat(),
        "question": q,
        "answer": "\n".join(_texts(ans_res)),
        "evidence": kept,
        "dropped_future": len(ev) - len(kept),
        "errors": errors,
    }


async def voice(era_id: str, k: int = 4) -> dict:
    era = get_era(era_id)
    kwargs = dict(
        query_text="how I feel this week, what worries me, what I want",
        query_type=SearchType.CHUNKS,
        datasets=[era.dataset],
        top_k=k,
    )
    if NodeSet is not None:
        kwargs.update(node_type=NodeSet, node_name=[f"era:{era.id}"])
    try:
        r = await _search(**kwargs)
    except Exception as exc:  # noqa: BLE001
        # Retry without node filters if that surface is unsupported.
        try:
            r = await _search(
                query_text=kwargs["query_text"],
                query_type=SearchType.CHUNKS,
                datasets=[era.dataset],
                top_k=k,
            )
        except Exception as exc2:  # noqa: BLE001
            return {"as": era.id, "samples": [], "errors": [str(exc), str(exc2)]}
    samples = [e for e in map(_evidence, _texts(r)) if e and e["date"] <= era.end.isoformat()]
    return {"as": era.id, "samples": samples, "errors": []}


async def history(q: str) -> dict:
    now = present_era()
    errors: list[str] = []

    decisions_prompt = (
        f"Past decisions related to: {q}. For each: date, weekday, time, week rating, "
        "what was chosen, and any later outcome or reversal."
    )

    def node_kw(names):
        return dict(node_type=NodeSet, node_name=names) if NodeSet is not None else {}

    results = await _gather(
        _search(query_text=q, query_type=_cot(), datasets=[now.dataset]),
        _search(
            query_text=decisions_prompt,
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[now.dataset],
            **node_kw(["type:decision", "type:outcome"]),
        ),
        _search(query_text=q, query_type=_temporal(), datasets=[TIMELINE_DATASET]),
        _search(query_text=q, query_type=SearchType.GRAPH_COMPLETION, datasets=[RECORDS_DATASET]),
        _search(query_text=q, query_type=SearchType.CHUNKS, datasets=[now.dataset], top_k=10),
    )
    keys = ["patterns", "decisions", "timeline", "past_verdicts", "evidence"]
    parsed: dict = {}
    for key, res in zip(keys, results):
        if isinstance(res, Exception):
            errors.append(f"{key}: {res}")
            parsed[key] = []
        else:
            parsed[key] = res

    evidence = [e for e in map(_evidence, _texts(parsed["evidence"])) if e]
    return {
        "patterns": _texts(parsed["patterns"]),
        "decisions": _texts(parsed["decisions"]),
        "timeline": _texts(parsed["timeline"]),
        "past_verdicts": _texts(parsed["past_verdicts"]),
        "evidence": evidence,
        "errors": errors,
    }


def _cot():
    return getattr(SearchType, "GRAPH_COMPLETION_COT", SearchType.GRAPH_COMPLETION)


def _temporal():
    return getattr(SearchType, "TEMPORAL", SearchType.GRAPH_COMPLETION)
