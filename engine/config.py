"""Runtime configuration from environment variables (and an optional `.env` at the repo root).

With no variables set the app runs in "FOSS mode": SQLite storage, offline assistant, browser speech,
auth off. Every sponsor service is opt-in. See plan_integrations.md.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()


def env(key, default=""):
    return os.environ.get(key, default)


def env_int(key, default):
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


def env_bool(key, default=False):
    return os.environ.get(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


# Storage: empty -> SQLite at data/app.db; postgresql://... -> Postgres (Tiger Cloud or self-hosted)
DATABASE_URL = env("DATABASE_URL")

# Gemini (optional assistant + investigation briefs)
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_MAX_CALLS_PER_DAY = env_int("GEMINI_MAX_CALLS_PER_DAY", 300)
GEMINI_MAX_OUTPUT_TOKENS = env_int("GEMINI_MAX_OUTPUT_TOKENS", 700)

# ElevenLabs (optional spoken updates)
ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = env("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_MODEL = env("ELEVENLABS_MODEL", "eleven_flash_v2_5")
ELEVENLABS_OUTPUT_FORMAT = env("ELEVENLABS_OUTPUT_FORMAT", "mp3_22050_32")
ELEVENLABS_MAX_CHARS_PER_DAY = env_int("ELEVENLABS_MAX_CHARS_PER_DAY", 15000)
ELEVENLABS_MAX_CHARS_PER_REQUEST = env_int("ELEVENLABS_MAX_CHARS_PER_REQUEST", 600)

# Auth (optional; any OIDC provider, configured for Auth0)
AUTH_ENABLED = env_bool("AUTH_ENABLED", False)
AUTH_DOMAIN = env("AUTH_DOMAIN")            # e.g. northwind-triage.us.auth0.com
AUTH_AUDIENCE = env("AUTH_AUDIENCE")        # API identifier, e.g. https://api.northwind-triage
AUTH_CLIENT_ID = env("AUTH_CLIENT_ID")      # SPA client id (public)
AUTH_ROLES_CLAIM = env("AUTH_ROLES_CLAIM", "https://northwind-triage/roles")
AUTH_ROLE_MAP = env("AUTH_ROLE_MAP")        # "alice@x.com:lead,bob@x.com:agent"
AUTH_DEFAULT_ROLE = env("AUTH_DEFAULT_ROLE", "viewer")

# Scheduler: rerun alert detection on the live feed every N minutes (0 = off)
DETECT_INTERVAL_MINUTES = env_int("DETECT_INTERVAL_MINUTES", 0)
