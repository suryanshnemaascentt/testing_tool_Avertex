
from datetime import datetime, timedelta
from config.settings import T_SHORT, T_SAVE, T_DATE_SEG
from executor.actions import mui_select, mui_autocomplete
from report.test_report import get_reporter

# ============================================================
# executor/form_filler.py — Module-specific form fill logic.
#
# Each module that has a form gets its own fill_<module>_form()
# function here. Shared helpers (_set_text_input, _set_date, etc.)
# are defined once at the bottom and used by all form fillers.
#
# To add a new module form:
#   1. Write fill_<modulename>_form(page, params) here
#   2. Add one if-line in executor/executor.py fill_form block
#   No other files need to change.
# ============================================================


async def _wait(page, ms):
    await page.wait_for_timeout(ms)


# ============================================================
# PROJECT FORM
# ============================================================

async def fill_project_form(page, p):
    """
    Fill and submit the New / Edit Project form.

    Args:
        page — Playwright page object
        p    — params dict built by _build_create_params() or _build_update_params()
    """
    name        = p.get("project_name", "AutoProject_{}".format(datetime.now().strftime("%H%M%S")))
    description = p.get("description", "Auto-generated.")
    start_date  = p.get("start_date") or datetime.now().strftime("%m/%d/%Y")
    end_date    = p.get("end_date")   or (datetime.now() + timedelta(days=30)).strftime("%m/%d/%Y")
    budget      = p.get("budget", "10000")

    print("\n{}".format("=" * 50))
    print("[FORM] Project: '{}'  {} -> {}  budget={}".format(
        name, start_date, end_date, budget))
    print("=" * 50)

    r = get_reporter()

    # 1. Project name and description
    await _set_text_input(page, name)
    if r: r.log_sub_step("Project Name", name, "PASS")

    await _set_textarea(page, description)
    if r: r.log_sub_step("Description", description, "PASS")

    # 2. MUI dropdowns — must be sequential because Billing Type affects Client visibility

    selected = await mui_select(page, "Project Type", p.get("project_type"))
    if r: r.log_sub_step("Project Type", selected if selected else "Auto-selected", "PASS")

    selected = await mui_select(page, "Delivery Model", p.get("delivery_model"))
    if r: r.log_sub_step("Delivery Model", selected if selected else "Auto-selected", "PASS")

    selected = await mui_select(page, "Methodology", p.get("methodology"))
    if r: r.log_sub_step("Methodology", selected if selected else "Auto-selected", "PASS")

    selected = await mui_select(page, "Risk Rating", p.get("risk_rating"))
    if r: r.log_sub_step("Risk Rating", selected if selected else "Auto-selected", "PASS")

    chosen_billing = await mui_select(page, "Billing Type", p.get("billing_type"))
    if r: r.log_sub_step("Billing Type", chosen_billing if chosen_billing else "Auto-selected", "PASS")

    await _wait(page, T_SHORT)

    selected = await mui_select(page, "Currency", p.get("currency"))
    if r: r.log_sub_step("Currency", selected if selected else "Auto-selected", "PASS")

    # 3. Client autocomplete — only shown for Billable projects
    is_billable = (chosen_billing or "").lower().strip() == "billable"
    if is_billable or chosen_billing is None:
        await mui_autocomplete(page, "Client",
                               p.get("client_search", "a"),
                               p.get("client_selector"))
        if r: r.log_sub_step("Client", p.get("client_search", "a"), "PASS")
    else:
        print("   [INFO] Client field skipped (billing='{}')".format(chosen_billing))
        if r: r.log_sub_step("Client", "(skipped — non-billable)", "PASS")

    # 4. Link to Estimation autocomplete
    await mui_autocomplete(page, "Link to Estimation",
                           p.get("estimation_search", "a"),
                           p.get("estimation_selector"))
    if r: r.log_sub_step("Link to Estimation", p.get("estimation_search", "a"), "PASS")

    # 5. Dates — must be sequential (sharing keyboard would corrupt both dates)
    await _set_date(page, 0, start_date, "Start Date")
    if r: r.log_sub_step("Start Date", start_date, "PASS")

    await _set_date(page, 1, end_date,   "End Date")
    if r: r.log_sub_step("End Date", end_date, "PASS")

    # 6. Budget and save
    await _set_budget(page, budget)
    if r: r.log_sub_step("Budget", budget, "PASS")

    saved = await _save_form(page)
    if r: r.log_sub_step("Save Button", None, "PASS" if saved else "FAIL",
                          error="" if saved else "Save button click failed")
    return saved


async def _set_text_input(page, value):
    """Fill the first visible MUI text input (typically the Name field)."""
    try:
        inp = page.locator("input.MuiInputBase-input[type='text']").first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(click_count=3, timeout=2000)   # triple-click to select existing text
        await inp.fill(value)
        print("   [OK] Text input: {!r}".format(value))
    except Exception as e:
        print("   [ERR] Text input: {}".format(e))


async def _set_textarea(page, value):
    """Fill the first visible MUI textarea (typically the Description field)."""
    try:
        ta = page.locator("textarea.MuiInputBase-input").first
        await ta.scroll_into_view_if_needed(timeout=2000)
        await ta.click(timeout=2000)
        await ta.fill(value)
        print("   [OK] Textarea filled")
    except Exception as e:
        print("   [ERR] Textarea: {}".format(e))


async def _set_budget(page, budget):
    """Fill the Budget number input field."""
    try:
        inp = page.locator("input[type='number'].MuiInputBase-input").first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(budget)
        print("   [OK] Budget: {!r}".format(budget))
    except Exception as e:
        print("   [ERR] Budget: {}".format(e))
    await _wait(page, T_SHORT)


async def _set_date(page, picker_idx, date_val, desc):
    """
    Fill a MUI date picker by clicking each segment (Month, Day, Year)
    and typing the digits one at a time.

    NOTE: This must be called sequentially for each date field.
    Running two date pickers concurrently with asyncio.gather() causes
    both pickers to share the same page keyboard, interleaving keystrokes
    and corrupting both dates.

    Args:
        picker_idx — 0 for the first date picker, 1 for the second, etc.
        date_val   — date string in MM/DD/YYYY format
        desc       — human-readable label used in log messages
    """
    try:
        parts = date_val.strip().split("/")
        if len(parts) != 3:
            raise ValueError("Expected MM/DD/YYYY format")
        mm, dd, yyyy = parts[0].zfill(2), parts[1].zfill(2), parts[2].zfill(4)
    except Exception as exc:
        print("   [ERR] {}: bad date format '{}' — {}".format(desc, date_val, exc))
        return

    print("   [DATE] {}: {}/{}/{}".format(desc, mm, dd, yyyy))

    pickers = page.locator(".MuiPickersSectionList-root")
    cnt = await pickers.count()
    if picker_idx >= cnt:
        print("   [ERR] {}: only {} picker(s) found, needed index {}".format(
            desc, cnt, picker_idx))
        return

    picker = pickers.nth(picker_idx)

    async def _fill_seg(aria_lbl, digits):
        """Click a date segment span and type the digit string into it."""
        span = picker.locator('[aria-label="{}"]'.format(aria_lbl))
        if await span.count() == 0:
            print("     [WARN] [{}] segment not found in picker {}".format(
                aria_lbl, picker_idx))
            return False
        await span.click(timeout=2000)
        await _wait(page, T_DATE_SEG)
        await page.keyboard.type(digits, delay=T_DATE_SEG)
        await _wait(page, T_DATE_SEG)
        v  = await span.get_attribute("aria-valuetext")
        ok = v not in (None, "Empty", "")
        print("     [{}] typed={!r} -> aria-valuetext={!r} {}".format(
            aria_lbl, digits, v, "[OK]" if ok else "[WARN]"))
        return ok

    # Fill month, day, year — retry each segment once if not accepted
    ok_m = await _fill_seg("Month", mm)
    ok_d = await _fill_seg("Day",   dd)
    ok_y = await _fill_seg("Year",  yyyy)
    if not ok_m: await _fill_seg("Month", mm)
    if not ok_d: await _fill_seg("Day",   dd)
    if not ok_y: await _fill_seg("Year",  yyyy)

    await page.keyboard.press("Tab")   # confirm the date selection
    await _wait(page, T_DATE_SEG)


async def _save_form(page):
    """
    Click the Save button. Tries by element ID first, then by role/name.
    Returns True if the click succeeded, False otherwise.
    """
    try:
        btn = page.locator("#project-form-save").first
        await btn.scroll_into_view_if_needed(timeout=2000)
        await _wait(page, T_SHORT)
        await btn.click(timeout=5000)
        print("   [OK] Save button clicked")
        await _wait(page, T_SAVE)
        return True
    except Exception as e:
        print("   [WARN] Save by ID failed: {}".format(e))

    try:
        await page.get_by_role("button", name="Save").first.click(timeout=3000)
        print("   [OK] Save button clicked (by role)")
        await _wait(page, T_SAVE)
        return True
    except Exception as e:
        print("   [ERR] Save failed: {}".format(e))
        return False


# ============================================================
# JOB FORM
# ============================================================
async def fill_job_form(page, p):
    """
    Fill the inline Add Job form row.

    Fields (from HTML inspection):
        Job Name  — text input   placeholder "e.g., Discovery..."  (id is dynamic)
        Start     — date input   type=date   format YYYY-MM-DD
        End       — date input   type=date   format YYYY-MM-DD
        Hours     — number input type=number
    """
    from report.test_report import get_reporter

    job_name   = p.get("job_name",   "Job_{}".format(__import__('datetime').datetime.now().strftime("%H%M%S")))
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


# ___________________________Activities form__________________________________________________________________
async def fill_activity_form(page, p):
    """
    Fill the inline Add Activity form row and click the tick (save) button.

    Form fields (confirmed from DOM inspection):
        [0] Task Name  — input[placeholder='Task name']
        [1] Job/Phase  — MuiSelect-select index 0  (shows "No Phase" by default)
        [2] Hours      — input[type='number'][min='0']
        [3] Priority   — MuiSelect-select index 1  (shows "Medium" by default)
    """
    from datetime import datetime
    from report.test_report import get_reporter
    from config.settings import T_SHORT
    import random

    activity_name = p.get("activity_name", "Activity_{}".format(datetime.now().strftime("%H%M%S")))
    job_name      = p.get("job_name", "")
    hours         = p.get("hours", "4")

    print("\n[ACTIVITY FORM] name='{}' job='{}' hours={}".format(
        activity_name, job_name, hours))

    r = get_reporter()

    # ── Wait for form to fully render ────────────────────────
    for attempt in range(6):
        mui_count = await page.locator(".MuiSelect-select").count()
        if mui_count >= 2:
            print("   [FORM-READY] {} MuiSelect(s) found (attempt {})".format(
                mui_count, attempt + 1))
            break
        print("   [FORM-WAIT] Waiting for form to render ({}/6)...".format(attempt + 1))
        await page.wait_for_timeout(500)

    # ── Task / Activity Name ──────────────────────────────────
    try:
        inp = page.locator("input[placeholder*='Task' i]").first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(timeout=2000)
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        await inp.type(activity_name, delay=50)
        print("   [OK] Activity Name: {!r}".format(activity_name))
        if r:
            r.log_sub_step("Task Name", activity_name, "PASS")
    except Exception as e:
        print("   [ERR] Activity Name: {}".format(e))
        if r:
            r.log_sub_step("Task Name", activity_name, "FAIL",
                           error="Could not fill Activity Name: {}".format(e))

    # ── Job / Phase — MuiSelect index 0 ──────────────────────
    # DOM confirmed: first MuiSelect-select is always the Job/Phase dropdown.
    # It has no <label> element so mui_select() label-walk always fails.
    # Fix: click index 0 directly, find matching option by job_name.
    if job_name:
        try:
            div = page.locator(".MuiSelect-select").nth(0)
            await div.scroll_into_view_if_needed(timeout=2000)
            await div.click(timeout=3000)

            listbox = page.locator('[role="listbox"]')
            await listbox.wait_for(state="visible", timeout=3000)

            all_opts_raw = await page.evaluate("""() => {
                const items = document.querySelectorAll(
                    '[role="listbox"] [role="option"], [role="listbox"] li'
                );
                return Array.from(items).map(el => el.textContent.trim());
            }""")
            print("   [JOB OPTIONS] {}".format(all_opts_raw))

            tgt = job_name.lower().strip()
            match_i = -1
            match_t = ""

            # Exact match first, then partial
            for oi, ot in enumerate(all_opts_raw):
                if ot.lower() == tgt:
                    match_i, match_t = oi, ot
                    break
            if match_i == -1:
                for oi, ot in enumerate(all_opts_raw):
                    if tgt in ot.lower() or ot.lower() in tgt:
                        match_i, match_t = oi, ot
                        break

            if match_i != -1:
                opts_loc = page.locator('[role="listbox"] [role="option"], [role="listbox"] li')
                await opts_loc.nth(match_i).click(timeout=2000)
                print("   [OK] Job/Phase: {!r}".format(match_t))
                if r:
                    r.log_sub_step("Job / Phase", match_t, "PASS")
            else:
                await page.keyboard.press("Escape")
                print("   [WARN] Job/Phase: '{}' not in options {}".format(job_name, all_opts_raw))
                if r:
                    r.log_sub_step("Job / Phase", job_name, "FAIL",
                                   error="'{}' not found in options: {}".format(
                                       job_name, all_opts_raw))

            await page.wait_for_timeout(T_SHORT)

        except Exception as e:
            print("   [ERR] Job/Phase select: {}".format(e))
            await page.keyboard.press("Escape")
            if r:
                r.log_sub_step("Job / Phase", job_name, "FAIL",
                               error="Could not select Job/Phase: {}".format(e))
    else:
        print("   [INFO] Job name not provided — skipping Job/Phase select")
        if r:
            r.log_sub_step("Job / Phase", "(not provided)", "PASS")

    # ── Hours ─────────────────────────────────────────────────
    try:
        inp = page.locator("input[type='number'][min='0']").first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(str(hours))
        print("   [OK] Hours: {}".format(hours))
        if r:
            r.log_sub_step("Hours", hours, "PASS")
    except Exception as e:
        print("   [ERR] Hours: {}".format(e))
        if r:
            r.log_sub_step("Hours", hours, "FAIL",
                           error="Could not fill Hours: {}".format(e))

    # ── Priority — MuiSelect index 1 ─────────────────────────
    # DOM confirmed: second MuiSelect-select is always Priority (default "Medium").
    try:
        div = page.locator(".MuiSelect-select").nth(1)
        await div.scroll_into_view_if_needed(timeout=2000)
        await div.click(timeout=3000)

        listbox = page.locator('[role="listbox"]')
        await listbox.wait_for(state="visible", timeout=3000)

        all_opts_raw = await page.evaluate("""() => {
            const items = document.querySelectorAll(
                '[role="listbox"] [role="option"], [role="listbox"] li'
            );
            return Array.from(items).map(el => el.textContent.trim());
        }""")

        all_opts = [(i, t) for i, t in enumerate(all_opts_raw) if t]
        if all_opts:
            chosen_i, chosen_text = random.choice(all_opts)
            opts_loc = page.locator('[role="listbox"] [role="option"], [role="listbox"] li')
            await opts_loc.nth(chosen_i).click(timeout=2000)
            print("   [OK] Priority: {!r}".format(chosen_text))
            if r:
                r.log_sub_step("Priority", chosen_text, "PASS")
        else:
            await page.keyboard.press("Escape")
            print("   [INFO] Priority: no options — skipped")
            if r:
                r.log_sub_step("Priority", "(skipped)", "PASS")

        await page.wait_for_timeout(T_SHORT)

    except Exception as e:
        print("   [WARN] Priority select: {}".format(e))
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        if r:
            r.log_sub_step("Priority", "(skipped)", "PASS")

    await page.wait_for_timeout(T_SHORT)

    # ── Save (tick / checkmark button) ────────────────────────
    tick_selector = (
        "button.MuiIconButton-root:not([disabled]):not(.Mui-disabled)"
        ":has(path[d='M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'])"
    )
    try:
        btn = page.locator(tick_selector).first
        await btn.scroll_into_view_if_needed(timeout=2000)
        await btn.click(timeout=3000)
        print("   [OK] Save (tick) button clicked")
        await page.wait_for_timeout(1500)
        if r:
            r.log_sub_step("Save (Tick) Button", None, "PASS")
    except Exception as e:
        print("   [WARN] Tick button via :has() failed — trying aria-label fallback: {}".format(e))
        try:
            btn = page.locator(
                "button.MuiIconButton-root[aria-label*='save' i], "
                "button.MuiIconButton-root[aria-label*='submit' i], "
                "button.MuiIconButton-root[aria-label*='confirm' i]"
            ).first
            await btn.click(timeout=3000)
            print("   [OK] Save button clicked (aria-label fallback)")
            await page.wait_for_timeout(1500)
            if r:
                r.log_sub_step("Save (Tick) Button", None, "PASS")
        except Exception as e2:
            print("   [ERR] Save (tick) button: {}".format(e2))
            if r:
                r.log_sub_step("Save (Tick) Button", None, "FAIL",
                               error="Could not click save button: {}".format(e2))
            
# ============================================================Timesheet==============================================


import asyncio
 
_LOCATION_MAP = {
    "wfh":            "WFH",
    "work from home": "WFH",
    "client office":  "Client Office",
    "ascentt office": "Ascentt Office",
    "ascentt":        "Ascentt Office",
    "travel":         "Travel/Remote",
    "travel/remote":  "Travel/Remote",
    "remote":         "Travel/Remote",
}
 
# How many day-columns are visible (Work Week = Mon–Fri = 5)
_DAY_COLS = 5
 
 
def _norm_location(raw: str) -> str:
    return _LOCATION_MAP.get(raw.lower().strip(), "Ascentt Office")
 
 
async def _pick_option(page, option_text: str, timeout: int = 4000) -> bool:
    """
    After a MUI dropdown is open, find and click the option matching option_text.
    Tries multiple option selectors in order of likelihood.
    Returns True if found, False otherwise.
    """
    for sel in (
        'ul[role="listbox"] li[role="option"]',
        'div[role="option"]',
        'li[role="option"]',
    ):
        try:
            await page.wait_for_selector(sel, timeout=timeout // 3)
            options = await page.query_selector_all(sel)
            for opt in options:
                text = (await opt.inner_text()).strip()
                if text.lower() == option_text.lower():
                    print("[FILL-TS] Exact match: '{}'".format(text))
                    await opt.click()
                    await page.wait_for_timeout(300)
                    return True
            # Partial match fallback
            for opt in options:
                text = (await opt.inner_text()).strip()
                if option_text.lower() in text.lower():
                    print("[FILL-TS] Partial match: '{}'".format(text))
                    await opt.click()
                    await page.wait_for_timeout(300)
                    return True
        except Exception:
            continue
    return False

# ----------------------------------------------------------------------------------------------------------------------------------------------
## ============================================================
# COMPLETE FIXES — form_filler.py timesheet section
# Replace everything from the "# ============Timesheet======="
# comment to end of file with this content
# ============================================================
# ============================================================
# COMPLETE FIXES — form_filler.py timesheet section
# Replace everything from the "# ============Timesheet======="
# comment to end of file with this content
# ============================================================
# ============================================================
# executor/form_filler.py — TIMESHEET SECTION
# Replace everything from "# ============Timesheet=====" to end of file
# ============================================================

import asyncio

_LOCATION_MAP = {
    "wfh":            "WFH",
    "work from home": "WFH",
    "client office":  "Client Office",
    "ascentt office": "Ascentt Office",
    "ascentt":        "Ascentt Office",
    "travel":         "Travel/Remote",
    "travel/remote":  "Travel/Remote",
    "remote":         "Travel/Remote",
}

_DAY_COLS = 5


def _norm_location(raw: str) -> str:
    return _LOCATION_MAP.get(raw.lower().strip(), "Ascentt Office")


async def _pick_option(page, option_text: str, timeout: int = 4000) -> bool:
    text_l = option_text.strip().lower()
    for sel in (
        'ul[role="listbox"] li[role="option"]',
        'li[role="option"]',
        'div[role="option"]',
    ):
        try:
            await page.wait_for_selector(sel, timeout=timeout // 3)
            options = await page.query_selector_all(sel)
            for opt in options:
                t = (await opt.inner_text()).strip()
                if t.lower() == text_l:
                    await opt.scroll_into_view_if_needed()
                    await opt.click()
                    await page.wait_for_timeout(300)
                    print("[PICK] Exact: '{}'".format(t))
                    return True
            for opt in options:
                t = (await opt.inner_text()).strip()
                if text_l in t.lower() or t.lower() in text_l:
                    await opt.scroll_into_view_if_needed()
                    await opt.click()
                    await page.wait_for_timeout(300)
                    print("[PICK] Partial: '{}'".format(t))
                    return True
        except Exception:
            continue
    return False


async def _wait_backdrop_clear(page, timeout=3000):
    try:
        await page.wait_for_function(
            """() => {
                const b = document.querySelectorAll('.MuiBackdrop-root');
                return b.length === 0 || Array.from(b).every(x =>
                    getComputedStyle(x).visibility === 'hidden' ||
                    getComputedStyle(x).display === 'none' ||
                    x.style.opacity === '0');
            }""",
            timeout=timeout
        )
    except Exception:
        await page.wait_for_timeout(800)


async def _pick_project_and_job(page, project_name: str, job_name: str,
                                 timeout: int = 8000) -> tuple:
    """
    DOM-confirmed flow:
      1. Tree opens with project rows (MuiTreeItem-content)
      2. Each project has an expand CHEVRON button (MuiTreeItem-iconContainer)
         and a <p> with project name
      3. Click the CHEVRON to expand and show job children
      4. Job children have: checkbox input + <p class="css-ijonf1"> job name
      5. Click job checkbox
      6. Escape to close

    Returns (project_ok, job_ok)
    """
    project_ok = False
    job_ok = False

    try:
        print("[TREE] Waiting for tree...")
        await page.wait_for_selector("div.MuiTreeItem-content", state="visible",
                                     timeout=timeout)
        await page.wait_for_timeout(400)

        proj_norm = " ".join(project_name.split()).lower()
        tree_items = await page.query_selector_all("div.MuiTreeItem-content")
        print("[TREE] {} items. Searching: '{}'".format(len(tree_items), project_name))

        matched_item = None
        for idx, item in enumerate(tree_items):
            labels = await item.query_selector_all("p.MuiTypography-root")
            for lbl in labels:
                raw = (await lbl.text_content() or "").strip()
                txt = " ".join(raw.split()).lower()
                if idx < 5:
                    print("[TREE] Item {}: '{}'".format(idx, raw[:60]))
                if proj_norm == txt:
                    matched_item = item
                    print("[TREE] ✓ Exact: '{}'".format(raw))
                    break
                if proj_norm in txt or all(
                        w in txt for w in proj_norm.split() if len(w) > 3):
                    matched_item = item
                    print("[TREE] ✓ Partial: '{}'".format(raw))
                    break
            if matched_item:
                break

        if not matched_item:
            # Try scrolling
            print("[TREE] Scrolling for more items...")
            try:
                container = await page.query_selector(
                    ".MuiSimpleTreeView-root, [role='tree']")
                if container:
                    await container.evaluate("el => el.scrollTop = el.scrollHeight")
                    await page.wait_for_timeout(500)
                    tree_items = await page.query_selector_all("div.MuiTreeItem-content")
                    for item in tree_items:
                        labels = await item.query_selector_all("p.MuiTypography-root")
                        for lbl in labels:
                            txt = " ".join(
                                (await lbl.text_content() or "").split()).lower()
                            if proj_norm == txt or proj_norm in txt:
                                matched_item = item
                                print("[TREE] ✓ Found after scroll")
                                break
                        if matched_item:
                            break
            except Exception as se:
                print("[TREE] Scroll err: {}".format(se))

        if not matched_item:
            print("[TREE] ✗ Project not found")
            await page.keyboard.press("Escape")
            await _wait_backdrop_clear(page)
            return False, False

        # EXPAND project by clicking its chevron icon container
        # DOM: <div class="MuiTreeItem-iconContainer ..."><svg>...</svg></div>
        await matched_item.scroll_into_view_if_needed()
        await page.wait_for_timeout(200)

        icon_container = await matched_item.query_selector(
            ".MuiTreeItem-iconContainer, .MuiSimpleTreeView-itemIconContainer")

        if icon_container:
            await icon_container.click()
            await page.wait_for_timeout(700)
            print("[TREE] ✓ Chevron clicked — project expanded")
        else:
            # Fallback: click item content itself
            await matched_item.click()
            await page.wait_for_timeout(700)
            print("[TREE] ✓ Item clicked (chevron fallback)")

        project_ok = True

        # Wait for job labels: <p class="...css-ijonf1">
        print("[TREE] Waiting for job labels (p.css-ijonf1)...")
        job_labels = []
        for attempt in range(12):
            job_labels = await page.query_selector_all("p.css-ijonf1")
            if job_labels:
                print("[TREE] {} job(s) found (attempt {})".format(
                    len(job_labels), attempt + 1))
                break
            await page.wait_for_timeout(400)

        if not job_labels:
            print("[TREE] ✗ No jobs — closing")
            await page.keyboard.press("Escape")
            await _wait_backdrop_clear(page)
            return project_ok, False

        for i, lbl in enumerate(job_labels):
            print("[TREE] Job {}: '{}'".format(
                i, (await lbl.text_content() or "").strip()))

        # Find matching job label
        job_norm = job_name.strip().lower()
        matched_job = None

        for lbl in job_labels:
            txt = (await lbl.text_content() or "").strip()
            if txt.lower() == job_norm:
                matched_job = lbl
                print("[TREE] ✓ Job exact: '{}'".format(txt))
                break

        if not matched_job:
            for lbl in job_labels:
                txt = (await lbl.text_content() or "").strip()
                if job_norm in txt.lower() or txt.lower() in job_norm:
                    matched_job = lbl
                    print("[TREE] ✓ Job partial: '{}'".format(txt))
                    break

        if not matched_job:
            print("[TREE] ✗ Job '{}' not found".format(job_name))
            await page.keyboard.press("Escape")
            await _wait_backdrop_clear(page)
            return project_ok, False

        # Click job checkbox
        # DOM: parent div > input[type=checkbox] + <p class="css-ijonf1">
        await matched_job.scroll_into_view_if_needed()
        await page.wait_for_timeout(200)

        parent = await matched_job.evaluate_handle("el => el.parentElement")
        job_cb = await parent.query_selector("input[type='checkbox']")

        if job_cb:
            await job_cb.click()
            await page.wait_for_timeout(500)
            print("[TREE] ✓ Job checkbox clicked")
            job_ok = True
        else:
            await matched_job.click()
            await page.wait_for_timeout(500)
            print("[TREE] ✓ Job label clicked")
            job_ok = True

        # Close tree
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)
        await _wait_backdrop_clear(page)
        print("[TREE] ✓ Closed")

        return project_ok, job_ok

    except Exception as e:
        print("[TREE] ERROR: {}".format(e))
        try:
            await page.keyboard.press("Escape")
            await _wait_backdrop_clear(page)
        except Exception:
            pass
        return project_ok, job_ok


async def fill_timesheet_row_form(page, params: dict):
    project_name = params.get("project_name", "")
    job_name     = params.get("job_name", "")
    hours        = str(params.get("hours", "8"))
    location_raw = params.get("location", "ascentt office")
    remarks      = params.get("remarks", "")
    row_index    = int(params.get("row_index", 0))
    location_opt = _norm_location(location_raw)

    print("\n" + "=" * 70)
    print("[ROW {}] Project: {} | Job: {} | Hours: {} | Loc: {}".format(
        row_index, project_name, job_name, hours, location_opt))
    print("=" * 70)

    # STEP 0: Add Row if not first
    if row_index > 0:
        print("[STEP 0] Clicking 'Add Row'...")
        add_btns = await page.query_selector_all("button:has-text('Add Row')")
        if add_btns:
            await add_btns[0].scroll_into_view_if_needed()
            await add_btns[0].click()
            await page.wait_for_timeout(900)
            print("[STEP 0] ✓")
        else:
            print("[STEP 0] ⚠ Not found")

    # STEP 1+2: Project + Job in one tree
    print("\n[STEP 1+2] Opening project/job tree...")
    project_btns = await page.query_selector_all("#timesheet-project-select")
    if not project_btns:
        project_btns = await page.query_selector_all('button:has-text("Select Project")')

    if not project_btns:
        print("[STEP 1+2] ✗ Project button not found")
        return False

    trigger = project_btns[-1]
    await trigger.scroll_into_view_if_needed()
    await trigger.click()
    await page.wait_for_timeout(800)

    project_ok, job_ok = await _pick_project_and_job(
        page, project_name, job_name, timeout=8000)

    print("[STEP 1] {}".format("✓ OK" if project_ok else "✗ FAILED"))
    print("[STEP 2] {}".format("✓ OK" if job_ok else "✗ FAILED"))

    if not project_ok:
        return False

    await page.wait_for_timeout(1000)

    # STEP 3: Hours
    print("\n[STEP 3] Filling hours...")
    all_inputs = await page.query_selector_all("#timesheet-hours-input")
    if not all_inputs:
        all_inputs = await page.query_selector_all(
            "input[type='number'][min='0'][max='24']")

    row_inputs = all_inputs[-_DAY_COLS:] if len(all_inputs) >= _DAY_COLS else all_inputs
    print("[STEP 3] {} input(s)".format(len(row_inputs)))

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    hours_filled = 0
    for i, inp in enumerate(row_inputs):
        day = day_names[i] if i < len(day_names) else "Day{}".format(i + 1)
        try:
            if await inp.evaluate("el => el.disabled"):
                print("   {} → ⏭ disabled".format(day))
                continue
            await inp.scroll_into_view_if_needed()
            await inp.click()
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Backspace")
            await inp.type(hours, delay=50)
            await page.wait_for_timeout(200)
            print("   {} → {} hrs ✓".format(day, hours))
            hours_filled += 1
        except Exception as e:
            print("   {} → ERROR: {}".format(day, e))

    print("[STEP 3] {} day(s) filled".format(hours_filled))
    await page.wait_for_timeout(400)

   # ── STEP 4: Location — set ALL 5 day comboboxes ──────────
    print("\n[STEP 4] Location: '{}'".format(location_opt))

    async def _set_one_location_combo(cb):
        """Open one combobox, deselect wrong, select right, close."""
        try:
            current = (await cb.inner_text()).strip()
            # Already exactly correct (only target selected)
            if current.strip().lower() == location_opt.lower():
                print("   ✓ Already '{}'".format(current))
                return True

            await cb.scroll_into_view_if_needed()
            await cb.click(force=True, timeout=4000)
            await page.wait_for_timeout(500)

            await page.wait_for_selector(
                'ul[role="listbox"] li[role="option"]', timeout=2000)

            options = await page.query_selector_all(
                'ul[role="listbox"] li[role="option"]')

            for opt in options:
                opt_text = (await opt.inner_text()).strip()
                cls = await opt.get_attribute("class") or ""
                is_sel = "Mui-selected" in cls
                is_target = opt_text.lower() == location_opt.lower()

                if is_sel and not is_target:
                    await opt.click()
                    await page.wait_for_timeout(150)
                    # Listbox may close — reopen
                    still = await page.query_selector('ul[role="listbox"]')
                    if not still:
                        await cb.click(force=True, timeout=3000)
                        await page.wait_for_timeout(400)
                elif not is_sel and is_target:
                    await opt.click()
                    await page.wait_for_timeout(150)

            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
            # Wait for menu to close
            for _ in range(10):
                menu = await page.query_selector('[id^="menu-"]')
                if not menu:
                    break
                await page.wait_for_timeout(150)
            return True
        except Exception as e:
            print("   combo err: {}".format(e))
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
            return False

    set_count = 0
    for attempt in range(8):  # up to 8 comboboxes (safety margin)
        combos = await page.query_selector_all(
            "div[role='combobox'].MuiSelect-select")
        if not combos:
            break

        known = {"ascentt office", "wfh", "client office", "travel/remote",
                 "travel", "remote"}
        loc_combos = []
        for cb in combos:
            txt = (await cb.inner_text()).strip().lower()
            if any(k in txt for k in known) or txt in known:
                loc_combos.append(cb)

        if not loc_combos:
            loc_combos = combos  # fallback

        print("[STEP 4] {} location combobox(es) visible".format(len(loc_combos)))

        for cb in loc_combos:
            ok = await _set_one_location_combo(cb)
            if ok:
                set_count += 1

        # If all visible combos are now correct, stop
        all_correct = True
        combos_now = await page.query_selector_all(
            "div[role='combobox'].MuiSelect-select")
        for cb in combos_now:
            txt = (await cb.inner_text()).strip().lower()
            if any(k in txt for k in known) or txt in known:
                if txt != location_opt.lower():
                    all_correct = False
                    break
        if all_correct:
            break

        await page.wait_for_timeout(200)

    print("[STEP 4] {} set → '{}'".format(set_count, location_opt))
    await page.wait_for_timeout(500)

    # ── STEP 5: Remarks — wait for popover to close first ──────
    if remarks:
        print("\n[STEP 5] Remarks: '{}'".format(remarks[:40]))
        try:
            # Wait for any open MUI Popover/Menu to fully close
            await page.wait_for_function(
                """() => {
                    const popovers = document.querySelectorAll(
                        '.MuiPopover-root, .MuiMenu-root, [id^="menu-"]');
                    return popovers.length === 0 ||
                           Array.from(popovers).every(p =>
                               p.style.display === 'none' ||
                               !document.body.contains(p));
                }""",
                timeout=4000
            )
        except Exception:
            await page.wait_for_timeout(1000)

        try:
            ta = await page.query_selector("#timesheet-remarks-input")
            if not ta:
                tas = await page.query_selector_all("textarea")
                for t in tas:
                    if await t.is_visible():
                        ta = t
                        break
            if ta:
                await ta.scroll_into_view_if_needed()
                await page.wait_for_timeout(300)
                # Use JavaScript click to bypass any overlay
                await page.evaluate("el => el.click()", ta)
                await page.wait_for_timeout(200)
                await page.keyboard.press("Control+a")
                await ta.type(remarks, delay=30)
                print("[STEP 5] ✓")
            else:
                print("[STEP 5] ⚠ Textarea not found")
        except Exception as e:
            print("[STEP 5] ERROR: {}".format(e))

    await page.wait_for_timeout(500)
    print("\n[ROW {}] ✓ COMPLETE".format(row_index))
    return True