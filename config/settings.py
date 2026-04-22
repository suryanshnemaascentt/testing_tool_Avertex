import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# config/settings.py
# All app-level settings in one place.
# Never hardcode values in other files — import from here.
# Usage:
#   from config.settings import BASE_URL, MAX_STEPS, T_SHORT
#
# .env file is loaded automatically if present.
# Existing environment variables are NOT overridden by .env —
# so CI/production can set vars directly without a .env file.
# ============================================================

# ── Load .env (no-op if file doesn't exist) ──────────────────
load_dotenv()

# ── Logging setup ────────────────────────────────────────────
# Logs go to both console and logs/automation.log
_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "automation.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# ── App ──────────────────────────────────────────────────────
BASE_URL      = os.getenv("AVERTEX_BASE_URL", "https://orbis-dev.savetime.com/")
MAX_STEPS     = int(os.getenv("AVERTEX_MAX_STEPS", "60"))
DEFAULT_URL   = BASE_URL + "/"

# ── Credentials ──────────────────────────────────────────────
# Set these in a .env file (see .env.example) — never hardcode here.
LOGIN_EMAIL    = os.getenv("AVERTEX_EMAIL",    "suryansh.nema@ascentt.com")
LOGIN_PASSWORD = os.getenv("AVERTEX_PASSWORD")  # Must be set via .env or environment — no default allowed

# ── Timing constants (ms) ─────────────────────────────────────
T_SHORT       =   80    # brief pause after a click
T_MEDIUM      =  200    # standard wait after interactions
T_OPTION_LOAD =  800    # wait for dropdown options to appear
T_SAVE        = 1500    # wait after clicking Save
T_NAV         =  800    # wait after a page navigation
T_KEY         =  150    # wait after a keyboard press
T_DATE_SEG    =  120    # delay between each date segment (month/day/year)

# ── Browser ──────────────────────────────────────────────────
VIEWPORT      = {"width": 1440, "height": 900}
# HEADLESS defaults True so CI/production never opens a display.
# Set HEADLESS=false in .env (or env) for local development.
HEADLESS      = os.getenv("HEADLESS", "true").lower() == "true"
DOM_SETTLE_MS = 2000    # max time to wait for DOM to settle per step
SSO_SETTLE_MS =  800    # extra wait on SSO pages after inputs appear
POST_RUN_S    =    1.5   # seconds to keep browser open after the run finishes