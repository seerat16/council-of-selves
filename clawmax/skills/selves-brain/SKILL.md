---
name: selves-brain
description: Query the Council of Selves personal brain (Cognee). Time-sliced recall
  as a past self, cross-era history, voice samples, and council session files.
---

# selves-brain

Requires the brain server at `$SELVES_BRAIN_URL` (default http://localhost:8765) and the
`selves` CLI on PATH (fallback: curl the same endpoints; see the table below).

| Command | Who may use it | Returns |
| ------- | -------------- | ------- |
| `selves session current` / `selves session show` | everyone | current session id / brief + files |
| `selves recall --as <era> -q "..."` | selves (own era only), chair (`--as now`) | answer + dated evidence |
| `selves voice --as <era>` | selves (own era only) | tone samples |
| `selves history -q "..."` | historian, chair | patterns, decisions, timeline, past verdicts |
| `selves record decision` | chair | stores verdict in memory |
| `selves due` | chair | check-ins that are due |

## Rules
- Past-self agents MUST pass `--as <their own era id>`. Never call `history`.
- Cite evidence as `[YYYY-MM-DD]`. Never cite a date after your era's end.
- Session files live in `$SELVES_HOME/sessions/<id>/`. Follow the file names exactly.

## curl fallback
```
curl -s -X POST $SELVES_BRAIN_URL/api/recall \
  -H 'content-type: application/json' \
  -d '{"as":"<era>","q":"..."}'
```

Import this with the ClawMax dashboard's Skills page ("import from local directory") and
assign it to all council agents (bulk assign).
