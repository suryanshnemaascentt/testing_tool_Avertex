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


def random_monday_in_range(start_date_str, end_date_str):
    """
    Pick a random Monday whose week falls within [start_date_str, end_date_str].
    Both dates must be ISO format YYYY-MM-DD.
    Falls back to _random_past_monday() if the range is invalid or empty.
    """
    try:
        start = datetime.strptime(start_date_str, "%Y-%m-%d")
        end   = datetime.strptime(end_date_str,   "%Y-%m-%d")

        # Snap start forward to the nearest Monday (stay on start if already Monday)
        days_to_monday = (7 - start.weekday()) % 7
        first_monday   = start + timedelta(days=days_to_monday)

        # If the first Monday overshoots the end, fall back to start's own Monday
        if first_monday > end:
            first_monday = start - timedelta(days=start.weekday())

        # Clamp first_monday so it never exceeds end
        if first_monday > end:
            first_monday = end - timedelta(days=end.weekday())

        total_weeks = max(1, (end - first_monday).days // 7 + 1)
        chosen = first_monday + timedelta(weeks=random.randint(0, total_weeks - 1))
        return chosen.strftime("%Y-%m-%d")
    except Exception:
        return _random_past_monday()


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
