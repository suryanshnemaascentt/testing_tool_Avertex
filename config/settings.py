import os

# ============================================================
# config/settings.py
# All app-level settings in one place.
# Never hardcode values in other files — import from here.
# Usage:
#   from config.settings import BASE_URL, MAX_STEPS, T_SHORT
# ============================================================

# ── App ──────────────────────────────────────────────────────
BASE_URL      = os.getenv("AVERTEX_BASE_URL", "https://orbis-dev.savetime.com/")
MAX_STEPS     = int(os.getenv("AVERTEX_MAX_STEPS", "60"))
DEFAULT_URL   = BASE_URL + "/"

# ── Credentials ──────────────────────────────────────────────
LOGIN_EMAIL    = os.getenv("AVERTEX_EMAIL",    "suryansh.nema@ascentt.com")
LOGIN_PASSWORD = os.getenv("AVERTEX_PASSWORD", "Sn94948988@")   # ← fill this

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
HEADLESS      = False   # set True to run without a visible browser window
DOM_SETTLE_MS = 5000    # max time to wait for DOM to settle per step
SSO_SETTLE_MS =  800    # extra wait on SSO pages after inputs appear
POST_RUN_S    =    3    # seconds to keep browser open after the run finishes