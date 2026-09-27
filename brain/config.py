"""Paths, environment, and Cognee store locations.

This module is import-safe without cognee installed: the cognee configuration is
applied lazily via `configure_cognee()`, which the server (the sole Cognee owner)
calls at startup. That keeps the CLI and Plan B runner cognee-free.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

HOME = Path(os.getenv("SELVES_HOME", str(ROOT)))
DATA_DIR = HOME / os.getenv("SELVES_DATA", "data/seed")
INBOX_DIR = HOME / "data/inbox"
SESSIONS_DIR = HOME / "sessions"
ERAS_FILE = HOME / "eras.yaml"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
WEB_DIR = ROOT / "web"

RECORDS_DATASET = "council_records"
TIMELINE_DATASET = "timeline"

OWNER = os.getenv("SELVES_OWNER", "Alex")
BRAIN_URL = os.getenv("SELVES_BRAIN_URL", "http://localhost:8765")

CHAIR_MODEL = os.getenv("SELVES_CHAIR_MODEL", "claude-sonnet-5")
SELF_MODEL = os.getenv("SELVES_SELF_MODEL", "claude-haiku-4-5-20251001")

COGNEE_DATA = HOME / ".cognee/data"
COGNEE_SYSTEM = HOME / ".cognee/system"

_cognee_configured = False


def configure_cognee() -> None:
    """Point Cognee's stores inside the project so they can be snapshotted/copied.

    Called once by the server at startup. VERIFY the exact config setter names
    against the installed cognee version (Section 8.1); adjust here if they differ.
    """
    global _cognee_configured
    if _cognee_configured:
        return
    import cognee

    COGNEE_DATA.mkdir(parents=True, exist_ok=True)
    COGNEE_SYSTEM.mkdir(parents=True, exist_ok=True)
    # VERIFY: setter names. Newer cognee exposes cognee.config.data_root_directory /
    # system_root_directory. If the signature differs, adapt without changing intent.
    try:
        cognee.config.data_root_directory(str(COGNEE_DATA))
        cognee.config.system_root_directory(str(COGNEE_SYSTEM))
    except AttributeError:
        # Fallback for alternative config surfaces.
        cognee.config.set("data_root_directory", str(COGNEE_DATA))
        cognee.config.set("system_root_directory", str(COGNEE_SYSTEM))
    _cognee_configured = True
