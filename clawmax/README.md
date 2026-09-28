# ClawMax integration

This folder holds the **sources** for the Council of Selves ClawMax organization. The
rendered, ready-to-install output goes to `clawmax/build/` (gitignored).

```
clawmax/
  _templates/          # jinja2 sources (edit these)
    TEMPLATE.md.j2       # organization template (agents/communities/groups/workflows)
    agents/              # IDENTITY.md / AGENTS.md / TOOLS.md per agent
    workflows/           # the 5 council stages + memory-sync + verdict-check-in
  skills/selves-brain/
    SKILL.md             # the skill definition (imported in the dashboard)
  build/               # rendered output (gitignored) — produced by the renderer
```

## Render + install

```bash
# render only (writes clawmax/build/)
uv run python scripts/render_clawmax.py

# render AND copy into your ClawMax workspace
uv run python scripts/render_clawmax.py --install ~/clawmax/WORKSPACES/default
```

The renderer creates one `self-<era>` agent per non-present era in `eras.yaml`, plus the
Chair and Historian, the `TEMPLATE.md`, and all workflows. Re-run it whenever `eras.yaml`
or `brain/prompts/*.md` change.

## ⚠️ VERIFY before you rely on this (Section 10.2)

These templates encode the *design*; the exact ClawMax conventions must be confirmed
against the **installed** ClawMax repo, because they may differ by version:

1. **Agent file set + field names** — read `TEMPLATES/agents/` in the ClawMax repo. If the
   real set isn't `IDENTITY.md / SOUL.md / AGENTS.md / TOOLS.md`, or the front-matter field
   names differ, adjust `clawmax/_templates/agents/*.j2` to match.
2. **Model + runtime declaration** — confirm how the model/runtime are declared and where.
3. **Workflow DAG edges** — the `dependsOn:` line is left **commented** in each
   `workflows/*.md.j2`. Confirm the real field name/shape from the ClawMax System Test
   template DAG and the workflow spec, then uncomment/adapt.
4. **Structured workflow inputs** — confirm how `inputs:` (the `dilemma`) is declared;
   `council-1-brief` uses a placeholder shape.
5. **ORG / communities / groups format** — the `TEMPLATE.md` lists them in prose; match the
   spec's exact syntax.

Specs:
- Template: https://github.com/Maximilien-ai/templates/blob/main/spec/template-spec.md
- Workflow: https://github.com/Maximilien-ai/workflows/blob/main/spec/workflow-spec.md

If DAG auto-advance can't be wired in time, run the stages one after another from the
dashboard (each still runs its targeted agents in parallel) — you're still demonstrating
ClawMax orchestration.
