"""Time-slice ingestion into Cognee. Imported only by the server (sole Cognee owner)."""

from __future__ import annotations

import shutil
from pathlib import Path

import cognee

from .config import DATA_DIR, INBOX_DIR, TIMELINE_DATASET
from .entries import load_entries, node_sets, render
from .eras import era_for, load_eras, present_era
from .prompts import load_prompt


async def _prune(reset: bool) -> None:
    if not reset:
        return
    # VERIFY prune API names against installed cognee.
    try:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(metadata=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[ingest] prune warning: {exc}")


async def ingest_all(path: Path = DATA_DIR, reset: bool = False, temporal: bool = True) -> dict:
    """Build cumulative time-slice datasets + a temporal timeline dataset.

    Each era dataset asof_<era> holds every entry dated on or before era.end, so a
    past self's graph physically cannot contain its future.
    """
    await _prune(reset)

    entries = load_entries(Path(path))
    extraction = load_prompt("extraction")
    counts: dict[str, int] = {}

    for era in load_eras():
        subset = [e for e in entries if e.date <= era.end]
        for e in subset:
            await cognee.add(
                render(e, era_for(e.date)),
                dataset_name=era.dataset,
                node_set=node_sets(e, era_for(e.date)),
            )
        await cognee.cognify(datasets=[era.dataset], custom_prompt=extraction)
        counts[era.dataset] = len(subset)

    if temporal:
        for e in entries:
            await cognee.add(
                render(e, era_for(e.date)),
                dataset_name=TIMELINE_DATASET,
                node_set=node_sets(e, era_for(e.date)),
            )
        await cognee.cognify(datasets=[TIMELINE_DATASET], temporal_cognify=True)
        counts[TIMELINE_DATASET] = len(entries)

    return counts


async def ingest_inbox() -> dict:
    """New entries only touch the present era + timeline. Past selves stay frozen."""
    inbox = Path(INBOX_DIR)
    entries = load_entries(inbox)
    now = present_era()
    if not entries:
        return {"ingested": 0, "note": "inbox empty"}

    bad = [e for e in entries if not (now.start <= e.date <= now.end)]
    if bad:
        dates = ", ".join(e.date.isoformat() for e in bad)
        raise ValueError(
            f"inbox entries must fall within the present era "
            f"({now.start}..{now.end}); offending dates: {dates}"
        )

    for e in entries:
        ns = node_sets(e, now)
        await cognee.add(render(e, now), dataset_name=now.dataset, node_set=ns)
        await cognee.add(render(e, now), dataset_name=TIMELINE_DATASET, node_set=ns)
    await cognee.cognify(datasets=[now.dataset])
    await cognee.cognify(datasets=[TIMELINE_DATASET], temporal_cognify=True)

    # Move processed files into the main data dir so they aren't re-ingested.
    dest = Path(DATA_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for p in inbox.glob("**/*"):
        if p.is_file() and not p.name.startswith("."):
            shutil.move(str(p), str(dest / p.name))
            moved += 1

    return {"ingested": len(entries), "moved_files": moved, "dataset": now.dataset}
