# Council of Selves

> Before you decide, ask everyone you've been.

A personal agent that convenes your **past selves** — each rebuilt from only what you
knew at the time — to argue about a decision in front of you. A **Historian** checks the
whole record for patterns and base rates, and every verdict goes back into memory so the
council learns which version of you tends to be right.

Built for the Personal Agent Hackathon (**Cognee × ClawMax**, NYU Tandon). Uses **Cognee**
for a time-sliced personal brain and **ClawMax** for the agent team, workflows and cron.

## How it works

1. **Ingest** — Dated notes/journals/decisions become *cumulative time-slice* Cognee
   datasets: `asof_grind_fall` holds everything up to Nov 30, `asof_burnout_winter`
   everything up to Feb 28, and so on. A past self's graph physically cannot contain its
   future.
2. **Convene** — A workflow DAG runs `brief → (testimony ‖ history) → cross-exam → verdict`.
3. **Testify** — Each self queries only its own time-slice, speaks in that era's voice,
   cites entry dates, and votes.
4. **Audit** — The Historian uses temporal search + `node_set` filters + past verdicts to
   report patterns, base rates and contradictions.
5. **Close the loop** — The verdict and, later, the real outcome are written back into
   Cognee. A daily cron surfaces due check-ins.

## Architecture

```
Your dated notes ──ingest──▶  Cognee · Personal Brain
 (data/seed|mine)             asof_grind_fall → Fall self
        │                     asof_burnout_winter → Winter self
        ▼                     asof_launch_spring → Spring self
 Brain server :8765           asof_now → Chair, Historian
 (FastAPI · sole Cognee owner)timeline (temporal) → Historian
        ▲                     council_records → Historian, Chair
        │ selves-brain skill
 ClawMax · Council of Selves team          sessions/<id>/ (file contract)
 Chair · Historian · Self×3                00_brief · 10_testimony_<era>
 DAG + cron                                20_history · 30_cross_<era>
                                           90_verdict · 95_checkin
        │                                        ▲
        └── Plan B runner (Anthropic SDK) ───────┘   Chamber UI (live · replay)
```

The **brain server is the only process that touches Cognee.** ClawMax agents reach it
through the `selves-brain` skill / the `selves` CLI. Sessions are plain files shared by the
UI and Plan B.

## Repository layout

```
council-of-selves/
  eras.yaml                 # life chapters — single source of truth for the roster
  data/seed/                # 48 synthetic entries (committed)
  data/mine/                # your real notes (gitignored)
  data/inbox/               # new entries picked up by memory-sync
  brain/                    # config, eras, entries, ingest, recall, records, server, cli
    prompts/                # extraction + chair/self/historian prompts
    council_local.py        # Plan B orchestrator (Anthropic SDK)
  web/index.html            # Council Chamber UI
  scripts/                  # smoke_cognee, leak_test, render_clawmax
  clawmax/                  # jinja2 templates, selves-brain skill, rendered build/
  sessions/                 # runtime output, one folder per council
```

## Quick start

> Requires network access + API keys, so these run on **your machine**, not in the
> Kiro sandbox. See **[RUNBOOK.md](RUNBOOK.md)** for the full step-by-step (Cognee
> platform setup, ClawMax install, and the acceptance gates).

```bash
# 1. Python 3.11+ and uv
uv sync

# 2. Configure secrets
cp .env.example .env         # then fill in the HUMAN keys

# 3. Ingest the seed corpus into Cognee time-slice datasets
uv run selves ingest --reset
uv run selves stats          # expect 12 / 24 / 36 / 48 + timeline 48

# 4. Prove time isolation (must be 16/16 green)
uv run python scripts/leak_test.py

# 5. Run a council locally (Plan B — no ClawMax needed)
uv run selves council "Northwind offered me a Senior PM role, +40% pay. Do I leave my startup?" --local

# 6. Start the brain server + Chamber UI
uv run uvicorn brain.server:app --port 8765
# open http://localhost:8765
```

## Using your own data

Put dated Markdown/TXT/JSONL under `data/mine/` (gitignored), define your own eras in
`eras.yaml`, set `SELVES_DATA=data/mine` in `.env`, then `selves ingest --reset`. Entry
format and loader rules are documented in [RUNBOOK.md](RUNBOOK.md).

## Safety & privacy

- Local-first. `data/mine/`, `.env`, `.cognee/` and `sessions/` are gitignored.
- The public demo uses the synthetic **Alex** persona in `data/seed/`.
- API keys live only in `.env` files — never in chat, commits or screenshots.
- The Chair screens for crisis content and never gives medical/legal/financial advice;
  the verdict is always framed as a *leaning*, not an instruction.
