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

# --- Hosted Cognee tenant (platform.cognee.ai) ---
# When both are set, `cognee.serve()` picks them up from the environment and the
# `selves push` command uploads the locally-built sliced datasets to your tenant.
COGNEE_SERVICE_URL = os.getenv("COGNEE_SERVICE_URL")  # e.g. https://<tenant>.aws.cognee.ai
COGNEE_API_KEY = os.getenv("COGNEE_API_KEY")


def cognee_cloud_enabled() -> bool:
    return bool(COGNEE_SERVICE_URL and COGNEE_API_KEY)


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


async def connect_cloud() -> bool:
    """Attach the SDK to your hosted Cognee tenant via `cognee.serve()`.

    Per the Cognee docs, `cognee.serve()` reads COGNEE_SERVICE_URL + COGNEE_API_KEY
    from the environment (already loaded from .env above). We also pass them
    explicitly as a belt-and-braces fallback. No-op (returns False) if the tenant
    env vars aren't set, so the local-only flow is unaffected.

    VERIFY: `cognee.serve()` kwarg names (url/api_key) against your installed version.
    """
    if not cognee_cloud_enabled():
        return False
    import cognee

    try:
        await cognee.serve(url=COGNEE_SERVICE_URL, api_key=COGNEE_API_KEY)
    except TypeError:
        # Some versions read only from env vars and take no kwargs.
        await cognee.serve()
    return True
