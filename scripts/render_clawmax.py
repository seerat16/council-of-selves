"""Render ClawMax agents / TEMPLATE.md / workflows from eras.yaml + brain/prompts/*.md.

Reads jinja2 sources under clawmax/_templates/ and writes rendered output to
clawmax/build/. With --install <workspace>, also copies the output into the ClawMax
workspace (e.g. ~/clawmax/WORKSPACES/default). Creates one self-<era> agent per
non-present era, plus Chair and Historian.

    uv run python scripts/render_clawmax.py [--install ~/clawmax/WORKSPACES/default]

VERIFY: the exact agent file set (IDENTITY/SOUL/AGENTS/TOOLS.md), field names, and the
WORKFLOW.md DAG field ("dependsOn") against the installed ClawMax TEMPLATES/ and specs
(Section 10.2). Adjust the templates in clawmax/_templates/ to match; this renderer
just fills variables.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "clawmax" / "_templates"
BUILD = ROOT / "clawmax" / "build"
PROMPTS = ROOT / "brain" / "prompts"
ERAS_FILE = ROOT / "eras.yaml"


def load_config() -> dict:
    raw = yaml.safe_load(ERAS_FILE.read_text())
    eras = raw["eras"]
    for e in eras:
        e["start"] = str(e["start"])
        e["end"] = str(e["end"])
        e["dataset"] = "asof_" + e["id"].replace("-", "_")
    return {
        "owner": raw.get("owner", "Alex"),
        "eras": eras,
        "past_eras": [e for e in eras if not e.get("present")],
        "present_era": next((e for e in eras if e.get("present")), eras[-1]),
    }


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["prompt"] = prompt
    return env


def render_str(template_str: str, **ctx) -> str:
    return _env().from_string(template_str).render(**ctx)


def write(rel: str, content: str) -> None:
    dest = BUILD / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    print(f"  wrote {dest.relative_to(ROOT)}")


def render_all() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    env = _env()

    def r(tpl: str, **extra) -> str:
        return env.get_template(tpl).render(**cfg, **extra)

    print("Rendering ClawMax build ...")

    # Organization template
    write("TEMPLATES/council-of-selves/TEMPLATE.md", r("TEMPLATE.md.j2"))

    # Skill (copied verbatim from source skill dir)
    skill_src = ROOT / "clawmax" / "skills" / "selves-brain" / "SKILL.md"
    if skill_src.exists():
        write("skills/selves-brain/SKILL.md", skill_src.read_text())

    # Chair + Historian agents
    for agent_id, role, model_key, prompt_name in [
        ("chair", "Convenes, briefs, writes the verdict", "chair", "chair_brief"),
        ("historian", "Patterns, base rates, contradictions", "chair", "historian"),
    ]:
        _render_agent(env, cfg, agent_id, cfg["present_era"], role, model_key, prompt_name)

    # One self agent per non-present era
    for era in cfg["past_eras"]:
        _render_self_agent(env, cfg, era)

    # Workflows
    for wf in [
        "council-1-brief",
        "council-2-testimony",
        "council-2-history",
        "council-3-cross",
        "council-4-verdict",
        "memory-sync",
        "verdict-check-in",
    ]:
        write(f"WORKFLOWS/{wf}/WORKFLOW.md", r(f"workflows/{wf}.md.j2"))

    print("Done. Build at clawmax/build/")


def _render_agent(env, cfg, agent_id, era, role, model_key, prompt_name) -> None:
    model = "anthropic/claude-sonnet-5"
    soul = _fill_prompt(prompt_name, cfg, era)
    ctx = dict(
        agent_id=agent_id,
        name={"chair": "The Chair", "historian": "The Historian"}.get(agent_id, agent_id),
        role=role,
        model=model,
        tags=f"council,{agent_id}",
        soul=soul,
        **cfg,
    )
    write(f"AGENTS/{agent_id}/IDENTITY.md", env.get_template("agents/IDENTITY.md.j2").render(**ctx))
    write(f"AGENTS/{agent_id}/SOUL.md", soul)
    write(f"AGENTS/{agent_id}/AGENTS.md", env.get_template("agents/AGENTS.md.j2").render(**ctx))
    write(f"AGENTS/{agent_id}/TOOLS.md", env.get_template("agents/TOOLS.md.j2").render(**ctx))


def _render_self_agent(env, cfg, era) -> None:
    agent_id = f"self-{era['id']}"
    soul = _fill_prompt("self", cfg, era)
    ctx = dict(
        agent_id=agent_id,
        name=f"{cfg['owner']}, {era['name']}",
        role=f"Past self (knowledge frozen at {era['end']})",
        model="anthropic/claude-haiku-4-5-20251001",
        tags=f"council,self,era-{era['id']}",
        soul=soul,
        era=era,
        **cfg,
    )
    write(f"AGENTS/{agent_id}/IDENTITY.md", env.get_template("agents/IDENTITY.md.j2").render(**ctx))
    write(f"AGENTS/{agent_id}/SOUL.md", soul)
    write(f"AGENTS/{agent_id}/AGENTS.md", env.get_template("agents/AGENTS.md.j2").render(**ctx))
    write(f"AGENTS/{agent_id}/TOOLS.md", env.get_template("agents/TOOLS.md.j2").render(**ctx))


def _fill_prompt(prompt_name: str, cfg, era) -> str:
    """Fill a brain/prompts/*.md with era vars using str.format_map (single-brace)."""
    text = prompt(prompt_name)

    class _D(dict):
        def __missing__(self, k):
            return "{" + k + "}"

    vals = _D(
        owner=cfg["owner"],
        era_id=era["id"],
        era_name=era["name"],
        start=era["start"],
        end=era["end"],
        blurb=era.get("blurb", ""),
        session_dir="$SELVES_HOME/sessions/<current>",
    )
    try:
        return text.format_map(vals)
    except (ValueError, IndexError):
        return text  # prompt has literal braces (tables); leave as-is


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", metavar="WORKSPACE", help="copy build into ClawMax workspace")
    args = ap.parse_args()

    render_all()

    if args.install:
        ws = Path(args.install).expanduser()
        for sub in ["AGENTS", "WORKFLOWS", "TEMPLATES", "skills"]:
            src = BUILD / sub
            if not src.exists():
                continue
            dst = ws / sub
            dst.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                target = dst / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
        print(f"Installed into {ws}")


if __name__ == "__main__":
    main()
