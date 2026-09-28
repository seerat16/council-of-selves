"""Smoke test: add 2 texts to a scratch dataset, cognify, run each SearchType, and
print type()/repr() of every result so you can finalize brain/recall.py:_texts().

Run FIRST (Section 8.11). Requires network + LLM keys.

    uv run python scripts/smoke_cognee.py
"""

from __future__ import annotations

import asyncio

import cognee

from brain import config

try:
    from cognee import SearchType
except ImportError:  # pragma: no cover
    from cognee.modules.search.types import SearchType  # type: ignore

SCRATCH = "smoke_scratch"


def _show(label: str, result) -> None:
    print(f"\n===== {label} =====")
    print("type:", type(result))
    print("repr:", repr(result)[:1500])
    if isinstance(result, (list, tuple)) and result:
        print("first item type:", type(result[0]))
        print("first item repr:", repr(result[0])[:800])


async def main() -> None:
    config.configure_cognee()

    print("Inspecting cognee.search signature:")
    import inspect

    try:
        print(inspect.signature(cognee.search))
    except (TypeError, ValueError) as exc:
        print("  (could not introspect):", exc)

    print("\nAvailable SearchType members:")
    print("  ", [m for m in dir(SearchType) if m.isupper()])

    await cognee.add(
        "[[2025-10-03 | note | era=grind-fall | Friday]]\n"
        "Bought a red espresso machine and named it Vesuvio.",
        dataset_name=SCRATCH,
    )
    await cognee.add(
        "[[2026-09-20 | note | era=now | Sunday]]\n"
        "Northwind offered me a Senior PM role, +40% pay.",
        dataset_name=SCRATCH,
    )
    await cognee.cognify(datasets=[SCRATCH])

    q = "What did I buy and what job offer did I get?"
    for name in ("GRAPH_COMPLETION", "CHUNKS", "TEMPORAL", "GRAPH_COMPLETION_COT"):
        st = getattr(SearchType, name, None)
        if st is None:
            print(f"\n(SearchType.{name} not available in this cognee version)")
            continue
        try:
            res = await cognee.search(query_text=q, query_type=st, datasets=[SCRATCH])
            _show(name, res)
        except Exception as exc:  # noqa: BLE001
            print(f"\n===== {name} raised {type(exc).__name__}: {exc} =====")

    print("\nDone. Use the printed shapes to finalize brain/recall.py:_texts().")


if __name__ == "__main__":
    asyncio.run(main())
