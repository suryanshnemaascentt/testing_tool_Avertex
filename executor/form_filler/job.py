from datetime import datetime
from config.settings import T_SHORT
from report.test_report import get_reporter
from ._shared import _wait

# ============================================================
# executor/form_filler/job.py — Job form fill logic.
# ============================================================

# ── Report integration metadata ──────────────────────────────
FORM_ACTION_NAME        = "fill_job_form"
FORM_MODULE             = None
FORM_ACTION_VERB        = "Filled Job Form"
FORM_DESCRIPTION_PARAMS = [
    ("job_name",   "name"),
    ("start_date", "start"),
    ("end_date",   "end"),
    ("hours",      "hours"),
]
FORM_SUB_STEPS = [
    ("job_name",   "Job Name",           None),
    ("start_date", "Start Date",         None),
    ("end_date",   "End Date",           None),
    ("hours",      "Hours",              None),
    (None,         "Save (Tick) Button", None),
]


async def fill_job_form(page, p):
    """
    Fill the inline Add Job form row.

    Fields (from HTML inspection):
        Job Name  — text input   placeholder "e.g., Discovery..."  (id is dynamic)
        Start     — date input   type=date   format YYYY-MM-DD
        End       — date input   type=date   format YYYY-MM-DD
        Hours     — number input type=number
    """
    job_name   = p.get("job_name",   "Job_{}".format(datetime.now().strftime("%H%M%S")))
    start_date = p.get("start_date", "")
    end_date   = p.get("end_date",   "")
    hours      = p.get("hours",      "8")

    print("\n[JOB FORM] name='{}' start={} end={} hours={}".format(
        job_name, start_date, end_date, hours))

    r = get_reporter()

    # ── Job Name ──────────────────────────────────────────────
    try:
        # Primary: match by placeholder (covers dynamic ids like _r_4_, _r_rk_, etc.)
        inp = page.locator(
            "input[placeholder*='Discovery' i], "
            "input[placeholder*='Development' i], "
            "input[placeholder*='Testing' i], "
            "input[placeholder*='e.g.' i]"
        ).first

        # Fallback: any small MUI text input that is NOT a search box
        if await inp.count() == 0:
            inp = page.locator(
                "input.MuiInputBase-inputSizeSmall[type='text']:not([class*='search'])"
            ).first

        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(timeout=2000)           # single click to focus
        await page.keyboard.press("Control+a")  # select all existing text
        await page.keyboard.press("Backspace")  # clear it
        await inp.type(job_name, delay=50)      # type char-by-char (more reliable than fill)

        print("   [OK] Job Name: {!r}".format(job_name))
        if r:
            r.log_sub_step("Job Name", job_name, "PASS")

    except Exception as e:
        print("   [ERR] Job Name: {}".format(e))
        if r:
            r.log_sub_step("Job Name", job_name, "FAIL",
                           error="Could not fill Job Name: {}".format(e))

    # ── Start Date ────────────────────────────────────────────
    if start_date:
        try:
            inp = page.locator("input[type='date']").first
            await inp.fill(start_date)
            print("   [OK] Start Date: {}".format(start_date))
            if r:
                r.log_sub_step("Start Date", start_date, "PASS")

        except Exception as e:
            print("   [ERR] Start Date: {}".format(e))
            if r:
                r.log_sub_step("Start Date", start_date, "FAIL",
                               error="Could not fill Start Date: {}".format(e))
    else:
        if r:
            r.log_sub_step("Start Date", "(not provided)", "PASS")

    # ── End Date ──────────────────────────────────────────────
    if end_date:
        try:
            inp = page.locator("input[type='date']").nth(1)
            await inp.fill(end_date)
            print("   [OK] End Date: {}".format(end_date))
            if r:
                r.log_sub_step("End Date", end_date, "PASS")

        except Exception as e:
            print("   [ERR] End Date: {}".format(e))
            if r:
                r.log_sub_step("End Date", end_date, "FAIL",
                               error="Could not fill End Date: {}".format(e))
    else:
        if r:
            r.log_sub_step("End Date", "(not provided)", "PASS")

    # ── Hours ─────────────────────────────────────────────────
    try:
        inp = page.locator("input[type='number'][min='0']").first
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(hours)
        print("   [OK] Hours: {}".format(hours))
        if r:
            r.log_sub_step("Hours", hours, "PASS")

    except Exception as e:
        print("   [ERR] Hours: {}".format(e))
        if r:
            r.log_sub_step("Hours", hours, "FAIL",
                           error="Could not fill Hours: {}".format(e))

    # ── Save Button (pending — resolved after tick click in job.py Step 6b) ──
    if r:
        r.log_sub_step("Save Button", None, "pending")

    await _wait(page, T_SHORT)
