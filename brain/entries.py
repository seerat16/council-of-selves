"""Load, parse and render corpus entries (.md frontmatter, .txt, .jsonl)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import frontmatter

from .eras import Era

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _as_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass
class Entry:
    date: date
    type: str
    text: str
    tags: list[str] = field(default_factory=list)
    time: str | None = None
    week_rating: int | None = None
    source: str = ""


def _from_markdown(path: Path) -> Entry | None:
    post = frontmatter.load(path)
    d = _as_date(post.get("date"))
    if d is None:
        print(f"[entries] WARNING: no valid date, skipping {path.name}")
        return None
    tags = post.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    wr = post.get("week_rating")
    return Entry(
        date=d,
        type=str(post.get("type", "note")),
        text=post.content.strip(),
        tags=list(tags),
        time=(str(post["time"]) if post.get("time") else None),
        week_rating=(int(wr) if wr is not None else None),
        source=path.name,
    )


def _from_txt(path: Path) -> Entry | None:
    m = _DATE_PREFIX.match(path.stem)
    if not m:
        print(f"[entries] WARNING: .txt without date prefix, skipping {path.name}")
        return None
    return Entry(
        date=_as_date(m.group(1)),
        type="note",
        text=path.read_text().strip(),
        tags=[],
        source=path.name,
    )


def _from_jsonl(path: Path) -> list[Entry]:
    out: list[Entry] = []
    for i, line in enumerate(path.read_text().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            print(f"[entries] WARNING: bad JSONL line {i} in {path.name}")
            continue
        d = _as_date(obj.get("date"))
        if d is None:
            print(f"[entries] WARNING: JSONL line {i} has no date in {path.name}")
            continue
        out.append(
            Entry(
                date=d,
                type=str(obj.get("type", "message")),
                text=str(obj.get("text", "")).strip(),
                tags=list(obj.get("tags", []) or []),
                source=f"{path.name}#{i}",
            )
        )
    return out


def load_entries(path: Path) -> list[Entry]:
    """Load every supported file under `path`, sorted by date."""
    entries: list[Entry] = []
    for p in sorted(Path(path).glob("**/*")):
        if p.name.startswith("."):
            continue
        if p.suffix == ".md":
            e = _from_markdown(p)
            if e:
                entries.append(e)
        elif p.suffix == ".txt":
            e = _from_txt(p)
            if e:
                entries.append(e)
        elif p.suffix == ".jsonl":
            entries.extend(_from_jsonl(p))
    return sorted(entries, key=lambda e: (e.date, e.time or ""))


def render(e: Entry, era: Era) -> str:
    wd = e.date.strftime("%A")
    extra = f" | {e.time}" if e.time else ""
    rating = f" | week_rating={e.week_rating}" if e.week_rating else ""
    return (
        f"[[{e.date.isoformat()} | {e.type} | era={era.id} | {wd}{extra}{rating}]]\n"
        f"{e.text}"
    )


def node_sets(e: Entry, era: Era) -> list[str]:
    return [f"era:{era.id}", f"type:{e.type}", *[f"tag:{t}" for t in e.tags]]
