"""Era model + helpers. The single source of truth for the agent roster is eras.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import yaml

from .config import ERAS_FILE


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v), "%Y-%m-%d").date()


@dataclass(frozen=True)
class Era:
    id: str
    name: str
    start: date
    end: date
    blurb: str = ""
    color: str = "#888"
    present: bool = False

    @property
    def dataset(self) -> str:
        return "asof_" + self.id.replace("-", "_")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "blurb": self.blurb,
            "color": self.color,
            "present": self.present,
            "dataset": self.dataset,
        }


def load_eras() -> list[Era]:
    raw = yaml.safe_load(ERAS_FILE.read_text())
    eras = []
    for e in raw["eras"]:
        eras.append(
            Era(
                id=e["id"],
                name=e["name"],
                start=_as_date(e["start"]),
                end=_as_date(e["end"]),
                blurb=e.get("blurb", ""),
                color=e.get("color", "#888"),
                present=bool(e.get("present", False)),
            )
        )
    return sorted(eras, key=lambda x: x.start)


def get_era(era_id: str) -> Era:
    for e in load_eras():
        if e.id == era_id:
            return e
    raise KeyError(era_id)  # -> 404 in server


def era_for(d: date) -> Era:
    for e in load_eras():
        if e.start <= d <= e.end:
            return e
    # Before the first era or after the last: clamp to nearest.
    eras = load_eras()
    if d < eras[0].start:
        return eras[0]
    return eras[-1]


def past_eras() -> list[Era]:
    return [e for e in load_eras() if not e.present]


def present_era() -> Era:
    return next(e for e in load_eras() if e.present)


def owner() -> str:
    raw = yaml.safe_load(ERAS_FILE.read_text())
    return raw.get("owner", "Alex")
