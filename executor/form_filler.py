from datetime import datetime, timedelta
from config.settings import T_SHORT, T_SAVE, T_DATE_SEG
from executor.actions import mui_select, mui_autocomplete
from datetime import datetime as _dt

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

    # 1. Project name and description
    await _set_text_input(page, name)
    await _set_textarea(page, description)

    # 2. MUI dropdowns — must be sequential because Billing Type affects Client visibility
    await mui_select(page, "Project Type",   p.get("project_type"))
    await mui_select(page, "Delivery Model", p.get("delivery_model"))
    await mui_select(page, "Methodology",    p.get("methodology"))
    await mui_select(page, "Risk Rating",    p.get("risk_rating"))

    chosen_billing = await mui_select(page, "Billing Type", p.get("billing_type"))
    await _wait(page, T_SHORT)

    # Click save (tick) button — wait for it to become enabled after form fill
    try:
        save_btn = page.locator("button.Mui-disabled.MuiIconButton-root + button.MuiIconButton-root")
        if await save_btn.count() == 0:
            save_btn = page.locator("button.MuiIconButton-sizeMedium:not(.Mui-disabled)").first
        await save_btn.wait_for(state="visible", timeout=2000)
        await save_btn.click()
        print("   [OK] Save (tick) button clicked")
        await _wait(page, 1500)
    except Exception as e:
        print("   [ERR] Save button: {}".format(e))
    await mui_select(page, "Currency", p.get("currency"))

    # 3. Client autocomplete — only shown for Billable projects
    is_billable = (chosen_billing or "").lower().strip() == "billable"
    if is_billable or chosen_billing is None:
        await mui_autocomplete(page, "Client",
                               p.get("client_search", "a"),
                               p.get("client_selector"))
    else:
        print("   [INFO] Client field skipped (billing='{}')".format(chosen_billing))

    # 4. Link to Estimation autocomplete
    await mui_autocomplete(page, "Link to Estimation",
                           p.get("estimation_search", "a"),
                           p.get("estimation_selector"))

    # 5. Dates — must be sequential (sharing keyboard would corrupt both dates)
    await _set_date(page, 0, start_date, "Start Date")
    await _set_date(page, 1, end_date,   "End Date")

    # 6. Budget and save
    await _set_budget(page, budget)
    return await _save_form(page)

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
    Fill the inline Add Job form row and click the tick (save) button.
 
    Fields:
        Job Name  — text input  placeholder "e.g., Discovery, Development..."
        Start     — date input  type=date  format YYYY-MM-DD
        End       — date input  type=date  format YYYY-MM-DD
        Hours     — number input type=number
 
    After filling, clicks the tick button via JS because:
    - The save button starts as disabled (Mui-disabled)
    - It becomes enabled after job name is filled
    - JS dispatch is more reliable than Playwright click for MUI icon buttons
    """
    from datetime import datetime as _dt
    job_name   = p.get("job_name") or "Job_{}".format(_dt.now().strftime("%H%M%S"))
    start_date = p.get("start_date", "")
    end_date   = p.get("end_date",   "")
    hours      = p.get("hours",      "8")
 
    print("\n[JOB FORM] name='{}' start={} end={} hours={}".format(
        job_name, start_date, end_date, hours))
 
    # ── Job Name ──────────────────────────────────────────────
    # Use placeholder — ID is dynamic per session
    try:
        inp = page.locator(
            "input[placeholder*='Discovery' i], "
            "input[placeholder*='Development' i], "
            "input[placeholder*='Testing' i], "
            "input[placeholder*='e.g.' i]"
        ).first
        if await inp.count() == 0:
            inp = page.locator(
                "input.MuiInputBase-inputSizeSmall[type='text']"
            ).first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(job_name)
        await page.keyboard.press("Tab")
        print("   [OK] Job Name: {!r}".format(job_name))
    except Exception as e:
        print("   [ERR] Job Name: {}".format(e))
 
    # ── Start Date ────────────────────────────────────────────
    if start_date:
        try:
            inp = page.locator("input[type='date']").first
            await inp.fill(start_date)
            await page.keyboard.press("Tab")
            print("   [OK] Start Date: {}".format(start_date))
        except Exception as e:
            print("   [ERR] Start Date: {}".format(e))
 
    # ── End Date ──────────────────────────────────────────────
    if end_date:
        try:
            inp = page.locator("input[type='date']").nth(1)
            await inp.fill(end_date)
            await page.keyboard.press("Tab")
            print("   [OK] End Date: {}".format(end_date))
        except Exception as e:
            print("   [ERR] End Date: {}".format(e))
 
    # ── Hours ─────────────────────────────────────────────────
    try:
        inp = page.locator("input[type='number'][min='0']").first
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(hours)
        await page.keyboard.press("Tab")
        print("   [OK] Hours: {}".format(hours))
    except Exception as e:
        print("   [ERR] Hours: {}".format(e))
 
    await _wait(page, T_SHORT)
 
    # ── Tick (save) button ────────────────────────────────────
    # Save button starts disabled, becomes enabled after job name is filled.
    # JS dispatch is used because:
    #   1. Playwright cannot click disabled elements
    #   2. After fill, MUI re-renders — JS ensures the click lands correctly
    try:
        await page.evaluate("""() => {
            // Find tick button by its unique SVG path (checkmark shape)
            const allBtns = Array.from(document.querySelectorAll('button'));
            for (const btn of allBtns) {
                const path = btn.querySelector('path');
                if (path && path.getAttribute('d') &&
                    path.getAttribute('d').startsWith('M9 16.17')) {
                    btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                    btn.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true}));
                    btn.dispatchEvent(new MouseEvent('click',     {bubbles:true}));
                    return 'clicked-by-path';
                }
            }
            return 'not-found';
        }""")
        print("   [OK] Tick (save) button clicked")
        await _wait(page, 1500)
    except Exception as e:
        print("   [ERR] Tick button: {}".format(e))
        print("   [OK] Tick (save) button clicked")
        await _wait(page, 1500)
    except Exception as e:
        print("   [ERR] Tick button: {}".format(e))


# ============================================================
# ACTIVITY FORM
# ============================================================
async def fill_activity_form(page, p):
    """
    Fill the inline Add Activity form row and click tick (save).

    Fields (from HTML inspection):
        Task name  — text input  placeholder="Task name"
        Job/Phase  — MUI select dropdown nth(0) — match by job_name
        Hours      — number input  type=number  min=0
        Priority   — MUI select dropdown nth(1) — pick random
    """
    import random as _random
    activity_name = p.get("activity_name") or "Activity_{}".format(
        __import__('datetime').datetime.now().strftime("%H%M%S"))
    hours    = p.get("hours", str(_random.randint(1, 8)))
    job_name = p.get("job_name", "")

    print("\n[ACTIVITY FORM] name='{}' hours={} job='{}'".format(
        activity_name, hours, job_name))

    # ── Task Name ─────────────────────────────────────────────
    try:
        inp = page.locator(
            "input[placeholder*='Task' i], "
            "input[placeholder*='Activity' i], "
            "input[placeholder*='name' i]"
        ).first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(activity_name)
        await page.keyboard.press("Tab")
        print("   [OK] Task Name: {!r}".format(activity_name))
    except Exception as e:
        print("   [ERR] Task Name: {}".format(e))

    # ── Job / Phase dropdown — nth(0) — match by job_name ─────
    try:
        all_dropdowns = page.locator("div[role='combobox'].MuiSelect-select")
        job_dropdown  = all_dropdowns.nth(0)
        if await job_dropdown.count() > 0:
            await job_dropdown.click(timeout=2000)        # ← fixed: timeout not TimeoutError
            await page.wait_for_timeout(600)
            options = page.locator('[role="option"]')
            count   = await options.count()
            if count > 0 and job_name:
                matched = False
                for i in range(count):
                    opt = options.nth(i)
                    txt = await opt.inner_text()
                    if job_name.lower() in txt.lower():
                        await opt.click()
                        print("   [OK] Job/Phase: {!r}".format(txt.strip()))
                        matched = True
                        break
                if not matched:
                    print("   [ERR] Job '{}' not found. Available:".format(job_name))
                    for i in range(count):
                        txt = await options.nth(i).inner_text()
                        print("         - {!r}".format(txt.strip()))
                    await page.keyboard.press("Escape")
            elif count > 0:
                await options.nth(0).click()
                print("   [OK] Job/Phase: first option selected")
    except Exception as e:
        print("   [ERR] Job/Phase dropdown: {}".format(e))

    # ── Hours ─────────────────────────────────────────────────
    try:
        inp = page.locator("input[type='number'][min='0']").first
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(hours)
        await page.keyboard.press("Tab")
        print("   [OK] Hours: {}".format(hours))
    except Exception as e:
        print("   [ERR] Hours: {}".format(e))

    # ── Priority dropdown — nth(1) — pick random ──────────────
    try:
        all_dropdowns    = page.locator("div[role='combobox'].MuiSelect-select")
        prio_dropdown    = all_dropdowns.nth(1)
        if await prio_dropdown.count() > 0:
            await prio_dropdown.click(timeout=2000)
            await page.wait_for_timeout(600)
            options = page.locator('[role="option"]')
            count   = await options.count()
            if count > 0:
                chosen = options.nth(_random.randint(0, count - 1))
                txt    = await chosen.inner_text()
                await chosen.click()
                print("   [OK] Priority: {!r}".format(txt.strip()))
    except Exception as e:
        print("   [ERR] Priority dropdown: {}".format(e))

    await _wait(page, T_SHORT)

    # ── Tick (save) button ─────────────────────────────────────
    try:
        await page.evaluate("""() => {
            const allBtns = Array.from(document.querySelectorAll('button'));
            for (const btn of allBtns) {
                const path = btn.querySelector('path');
                if (path && path.getAttribute('d') &&
                    path.getAttribute('d').startsWith('M9 16.17')) {
                    btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                    btn.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true}));
                    btn.dispatchEvent(new MouseEvent('click',     {bubbles:true}));
                    return 'clicked';
                }
            }
            return 'not-found';
        }""")
        print("   [OK] Tick (save) button clicked")
        await _wait(page, 1500)
    except Exception as e:
        print("   [ERR] Tick button: {}".format(e))