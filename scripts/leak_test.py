"""Leak test: proof of time isolation (Section 8.7).

For every (era, canary) pair: if the era is at or after the canary's era, the answer
MUST contain the expected token; otherwise it MUST NOT (and dropped_future must be 0).

Prints a 4x4 pass/fail matrix and exits non-zero on any failure. This matrix goes in
the demo video.

    uv run python scripts/leak_test.py
"""

from __future__ import annotations

import asyncio
import sys

from brain import config
from brain.eras import load_eras
from brain.recall import recall_as

# (question, canary era id, expected token)
CANARIES = [
    ("What's the name of my espresso machine?", "grind-fall", "Vesuvio"),
    ("Am I seeing a therapist? Who?", "burnout-winter", "Okafor"),
    ("Do I have a dog? What's its name?", "launch-spring", "Pixel"),
    ("What job offer did I get recently?", "now", "Northwind"),
]


def _era_order() -> dict[str, int]:
    return {e.id: i for i, e in enumerate(load_eras())}


async def main() -> int:
    config.configure_cognee()
    order = _era_order()
    eras = load_eras()

    header = ["era \\ canary"] + [tok for _, _, tok in CANARIES]
    rows = []
    failures = 0

    for era in eras:
        row = [era.id]
        for question, canary_era, token in CANARIES:
            res = await recall_as(era.id, question, k=6)
            blob = (res.get("answer", "") + " " + str(res.get("evidence", ""))).lower()
            present = token.lower() in blob
            should_know = order[era.id] >= order[canary_era]
            dropped = res.get("dropped_future", 0)

            ok = (present == should_know) and (dropped == 0)
            if not ok:
                failures += 1
            mark = "PASS" if ok else "FAIL"
            detail = f"{'saw' if present else 'no'}/{'exp' if should_know else 'hide'}"
            if dropped:
                detail += f"/drop{dropped}"
            row.append(f"{mark}({detail})")
        rows.append(row)

    # Print matrix
    widths = [max(len(str(r[i])) for r in ([header] + rows)) for i in range(len(header))]
    def fmt(r):
        return " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(r))

    print(fmt(header))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(fmt(r))

    total = len(eras) * len(CANARIES)
    print(f"\n{total - failures}/{total} pass, {failures} failure(s).")
    if failures:
        print("LEAK TEST FAILED — fix dataset isolation before proceeding (Section 3.2).")
        return 1
    print("LEAK TEST GREEN.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
