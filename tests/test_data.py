import random
from datetime import datetime, timedelta

# ============================================================
# tests/test_data.py
#
# Single source of truth for all auto-generated test data.
# No manual input required — everything is computed at import time.
#
# BEFORE RUNNING --auto:
#   Set FALLBACK_PROJECT and FALLBACK_JOB to names that already
#   exist in your environment. These are used for Activities and
#   Timesheet tests which require a pre-existing project + job.
# ============================================================

_today = datetime.now()
_TS    = _today.strftime("%H%M%S")


def _random_past_monday(days_back=90):
    """
    Pick a random date within the last `days_back` days,
    then snap to the Monday of that week.
    Guards against landing on a future Monday at week boundaries.
    """
    lower  = _today - timedelta(days=days_back)
    offset = random.randint(0, days_back)
    picked = lower + timedelta(days=offset)
    monday = picked - timedelta(days=picked.weekday())
    if monday > _today:
        monday -= timedelta(weeks=1)
    return monday.strftime("%Y-%m-%d")


# ── Job data ─────────────────────────────────────────────────
class JobData:
    NAME = "AutoJob_{}".format(_TS)


# ── Activity data ─────────────────────────────────────────────
class ActivityData:
    NAME = "AutoActivity_{}".format(_TS)


# ── Timesheet data ────────────────────────────────────────────
class TimesheetData:
    START_DATE = _random_past_monday(days_back=90)
    HOURS      = "8"
    LOCATION   = "ascentt office"
    REMARKS    = "Automated test entry"
