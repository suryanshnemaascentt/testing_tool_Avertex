
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