"""Prompt loader + jinja2 rendering for the templated (per-era) prompts."""

from __future__ import annotations

from jinja2 import Template

from .config import PROMPTS_DIR


def load_prompt(name: str) -> str:
    """Read brain/prompts/<name>.md as raw text."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


def render_prompt(name: str, **vars) -> str:
    """Load a prompt and fill {placeholders} via jinja2-compatible str.format.

    The prompt files use single-brace {placeholders}; we render them with
    str.format_map so missing keys don't explode.
    """
    text = load_prompt(name)
    return _safe_format(text, vars)


def _safe_format(text: str, vars: dict) -> str:
    class _Default(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    try:
        return text.format_map(_Default(vars))
    except (ValueError, IndexError):
        # Prompt contains literal braces (e.g. markdown tables); fall back to jinja2
        # with {{ }} — but our prompts use {}, so just return unformatted on failure.
        return Template(text).render(**vars)
