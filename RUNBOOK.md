# RUNBOOK — Council of Selves

Everything the coding agent could build **offline** is already in this repo. This runbook
covers the steps that need **network access, API keys, or dashboard clicks** — i.e. the
steps marked **HUMAN** in the build plan. Run them on your own machine (WSL2 on Windows,
or macOS/Linux natively).

> **Why manual?** These were prepared in a sandbox with no outbound internet, so it could
> not install `cognee`, reach `platform.cognee.ai`, clone ClawMax, or call the
> Anthropic/OpenAI APIs. Those are exactly the steps below.

---

## 0. Secrets safety (read first)

- **Never paste API keys into chat, commits, screenshots, or the demo video.** Keys live
  only in `.env` files, which are gitignored.
- If a key was ever shared in plaintext anywhere public, **rotate it** in the provider
  dashboard before the demo.
- This repo commits `.env.example` (placeholders only). You create `.env` locally.

---

## 1. Environment (≈10 min)

```bash
# Windows: do all of this inside WSL2 (Ubuntu 22.04+), in the Linux home (~), NOT /mnt/c.
python3 --version        # need 3.11+  (this repo pins 3.11 via pyproject)
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv if missing
node --version           # need 22.19+ for ClawMax
```

Clone (if you don't already have it) and enter the repo:

```bash
git clone https://github.com/seerat16/council-of-selves.git ~/council-of-selves
cd ~/council-of-selves
git checkout build/council-of-selves     # this build branch (until it's merged to main)
```

Install Python deps:

```bash
uv sync                  # resolves cognee 1.6.x + fastapi + typer + anthropic + ...
```

---

## 2. Keys & `.env` (HUMAN, ≈5 min)

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Var | Where to get it | Notes |
|-----|-----------------|-------|
| `OPENAI_API_KEY` + `LLM_API_KEY` | platform.openai.com | **same value** in both — Cognee's default LLM + embeddings |
| `ANTHROPIC_API_KEY` | console.anthropic.com | Plan B runner + ClawMax agents |
| `SELVES_HOME` | — | absolute path, e.g. `/home/<you>/council-of-selves` |
| `ENABLE_BACKEND_ACCESS_CONTROL` | leave `true` | **VERIFY** it gives each dataset its own store (the leak test is ground truth) |

Keep `SELVES_DATA=data/seed` for the public demo.

### Cognee hosted tenant (platform.cognee.ai)

The build **cognifies locally** (cheap, uses your OpenAI key, stores under `.cognee/`),
then **pushes the already-sliced datasets** to your tenant. Slicing is preserved because
it's baked into the dataset names (`asof_grind_fall` etc.), so they arrive on the tenant
still time-sliced — and your local **leak test** already proved the isolation.

**Auth (from the Cognee docs):** the SDK attaches to a tenant with `cognee.serve()`,
which reads these env vars. Add them to `.env` (get the values from your tenant / the
VS Code extension settings; **never commit the key**):

```bash
COGNEE_SERVICE_URL=https://<your-tenant>.aws.cognee.ai
COGNEE_API_KEY=...
```

When both are set, the brain server calls `cognee.serve(url=..., api_key=...)` at startup
and enables the push command:

```bash
# 1) build + prove locally FIRST (see §4–§5)
uv run selves ingest --reset
uv run python scripts/leak_test.py       # 16/16 green

# 2) push all sliced datasets to your tenant (server must be running)
uv run selves push                       # or: selves push --dataset asof_now --dataset timeline
```

Then view the sliced datasets in the Cognee platform UI. Recall/history still run against
your **local** datasets by default (fast, and guarded by the leak test); the pushed copies
are for the tenant graph view / showing judges.

> **VERIFY:** `cognee.serve()` kwargs (`url`/`api_key`) and `cognee.push()` arg name
> (`dataset_name` vs `datasets`). Confirm with:
> ```bash
> uv run python -c "import cognee,inspect;print(inspect.signature(cognee.serve));print(inspect.signature(cognee.push))"
> ```
> The code already falls back between the common shapes, but adjust `brain/config.py:connect_cloud()`
> and `brain/ingest.py:push_datasets()` if your version differs.

Apply the **$35 onsite credits** to your tenant to cover the push/hosting.

---

## 3. First smoke test — finalize result parsing (HUMAN + agent, ≈10 min)

Cognee's `search()` return shapes vary by version. Run the smoke test **first** and read
its output, then tighten `brain/recall.py:_texts()` if the printed shapes differ from what
that function assumes.

```bash
uv run python scripts/smoke_cognee.py
```

It prints `cognee.search`'s signature, the available `SearchType` members, and the
`type()`/`repr()` of every result. **VERIFY these against the code:**

- `brain/recall.py` calls `cognee.search(query_text=..., query_type=..., datasets=[...], top_k=...)`.
  If your cognee uses a positional `query` or a different kwarg, adjust the `_search()`
  wrapper in `recall.py`.
- `brain/config.py:configure_cognee()` calls `cognee.config.data_root_directory(...)` /
  `system_root_directory(...)`. If those setters differ, fix them there (a fallback
  `cognee.config.set(...)` is already attempted).
- Prune API in `brain/ingest.py` (`cognee.prune.prune_data` / `prune_system`) — confirm.

---

## 4. Ingest the seed corpus (≈ a few minutes + cents)

```bash
uv run selves ingest --reset
uv run selves stats
```

**Gate:** `selves stats` should show cumulative counts **12 / 24 / 36 / 48** for the four
`asof_*` datasets, plus **48** for `timeline`:

```
asof_grind_fall: 12   asof_burnout_winter: 24
asof_launch_spring: 36   asof_now: 48   timeline: 48
```

(≈120 document cognifies total; cheap with a small model. Do it once. Snapshot `.cognee/`
after success so you don't have to re-run with `--reset`.)

---

## 5. THE LEAK TEST — the proof (must be 16/16 green)

```bash
uv run python scripts/leak_test.py
```

This is the Cognee story and a hard gate (Sections 8.7 / 15). It checks that each era only
knows its own canary:

| era \ canary | Vesuvio | Okafor | Pixel | Northwind |
|--------------|---------|--------|-------|-----------|
| grind-fall   | ✅ know | ❌ hide| ❌ hide| ❌ hide |
| burnout-winter| ✅     | ✅     | ❌     | ❌       |
| launch-spring | ✅     | ✅     | ✅     | ❌       |
| now          | ✅      | ✅     | ✅     | ✅       |

Every cell must PASS and `dropped_future` must be 0. **If it fails, fix dataset isolation
before doing anything else** (confirm `ENABLE_BACKEND_ACCESS_CONTROL=true` actually gives
each dataset a separate store; that's the `VERIFY` in Section 3.2). Screenshot the green
matrix for the video.

---

## 6. Plan B council — end to end, no ClawMax needed (≈2–3 min)

Start the brain server (owns Cognee, serves the UI):

```bash
uv run uvicorn brain.server:app --port 8765
```

In another shell, run a council locally:

```bash
uv run selves council "Northwind offered me a Senior PM role, +40% pay. Do I leave my 6-person startup?" --local
```

Or open <http://localhost:8765>, type the dilemma, keep the mode on **Local**, click
**Convene**, and watch the chamber fill in.

**Gate (Section 15.3):** completes in < 4 min and produces every file in
`sessions/<id>/`: `00_brief.md`, `10_testimony_<era>.md` ×3, `20_history.md`,
`30_cross_<era>.md` ×3, `90_verdict.md`. Each testimony has ≥3 `[YYYY-MM-DD]` citations and
a parseable `**Vote:**`. The Historian names the Sunday-night pattern (≥2 dates) and the
contradiction; at least one self changes its vote in cross-exam.

---

## 7. ClawMax (HUMAN + agent, ≈60–75 min)

### 7.1 Install (in WSL2)

```bash
git clone https://github.com/Maximilien-ai/clawmax.git ~/clawmax
cd ~/clawmax && ./setup.sh          # installs OpenClaw if needed, creates workspace
```

Create `~/clawmax/SYSTEM/dashboard/.env`:

```
SYSTEM_ANTHROPIC_API_KEY=sk-ant-...   # same as ANTHROPIC_API_KEY
SYSTEM_OPENAI_API_KEY=sk-...          # same as OPENAI_API_KEY
DASHBOARD_AUTH_MODE=bypass            # local dev only
```

```bash
./SYSTEM/start.sh                     # dashboard :5173, API :3001
./SYSTEM/status.sh
```

(No port conflict: our brain server is on 8765.)

### 7.2 Study the built-ins first (15 min, saves an hour) — VERIFY

Before rendering, open `TEMPLATES/` in the ClawMax repo (esp. the bundled System Test
template DAG and one `TEMPLATES/agents/` example) and confirm the conventions our templates
assume. See **`clawmax/README.md`** in this repo for the exact 5-item VERIFY checklist
(agent file set, model/runtime fields, workflow `dependsOn` DAG shape, structured inputs,
ORG/groups syntax). Adjust `clawmax/_templates/*.j2` to match, then:

### 7.3 Render + install our org

```bash
# from ~/council-of-selves
uv run python scripts/render_clawmax.py                       # writes clawmax/build/
uv run python scripts/render_clawmax.py --install ~/clawmax/WORKSPACES/default
```

This generates the Chair, the Historian, and one `self-<era>` agent per non-present era,
plus `TEMPLATE.md` and all 7 workflows.

### 7.4 Import the skill + assign it

In the dashboard's **Skills** page: "import from local directory" →
`~/council-of-selves/clawmax/skills/selves-brain` → bulk-assign `selves-brain` to all 5
council agents.

### 7.5 Run the DAG

- Make sure the brain server (step 6) is running and reachable at the
  `SELVES_BRAIN_URL` secret you set in the template.
- Run `council-1-brief` with the Northwind dilemma → produces `00_brief.md`.
- Advance through testimony ‖ history → cross → verdict. If DAG auto-advance isn't wired,
  run the stages one after another from the dashboard (each still runs its agents in
  parallel).

**Gate (Section 10.9):** all 5 agents visible with `selves-brain` assigned; the full DAG
produces every file in ~5 min; the workflow DAG view renders (screenshot it).

### 7.6 Crons

`memory-sync` (every 6h) runs `selves ingest --inbox`; `verdict-check-in` (daily 09:00)
runs `selves due` and writes `95_checkin.md`.

---

## 8. The learning loop / demo simulation

```bash
# Simulate the 30-day check-in and record how the Northwind call turned out:
uv run selves due --today 2026-10-28
uv run selves outcome <session-id> --rating 2 \
  --text "Took it with a 4-day week. Best call this year." --today 2026-10-28

# Then convene a follow-up and watch the Historian cite the earlier verdict + outcome:
uv run selves council "Should I ask for a promotion at Northwind?" --local
```

In the UI: the **Check-ins** tab lists due sessions and has the outcome form; the
**Memory Graph** tab embeds `/graph`; the **Leak Test** tab renders the matrix.

---

## 9. Demo insurance

- Keep one good local session; open the UI in **replay mode**: `http://localhost:8765/?replay=<session-id>`
  reveals the files one at a time (works even if Wi-Fi/APIs die mid-demo).
- Pre-record a screen capture of a full run as backup.

---

## 10. Definition of Done checklist (Section 15)

- [ ] `selves stats`: 12 / 24 / 36 / 48 + timeline 48; `council_records` exists after first verdict
- [ ] `scripts/leak_test.py`: 16/16 pass, `dropped_future = 0`
- [ ] `selves council "…" --local` < 4 min, all files present, ≥3 citations + parseable vote each
- [ ] ClawMax dashboard runs the council stages from the template; files appear in the session folder
- [ ] Historian names the Sunday-night pattern (P1, ≥2 dates) and the contradiction (P3)
- [ ] ≥1 self changes its vote in cross-exam (or explains why not, with evidence)
- [ ] Verdict stored; after a simulated outcome, a follow-up council's Historian cites it
- [ ] UI shows a live or replayed session end to end; the graph tab loads
- [ ] README + this RUNBOOK accurate

---

## VERIFY index (things to confirm against installed packages)

| Where | What to confirm |
|-------|-----------------|
| `brain/recall.py` | `cognee.search` kwargs (`query_text`/`query_type`/`top_k`), `SearchType` + `NodeSet` import paths, `GRAPH_COMPLETION_COT`/`TEMPORAL` availability |
| `brain/config.py` | `cognee.config.*_root_directory` setter names |
| `brain/ingest.py` | `cognee.prune.*`, `cognee.cognify(custom_prompt=..., temporal_cognify=...)`, `cognee.add(node_set=...)` |
| `brain/server.py` `/graph` | `cognee.visualize_graph()` name/return shape |
| `clawmax/_templates/*` | agent file set + fields, workflow `dependsOn` DAG shape, inputs, ORG/groups syntax (see `clawmax/README.md`) |
| stretch | `cognee.push()` signature |
