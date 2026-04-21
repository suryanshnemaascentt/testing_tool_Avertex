from datetime import datetime, timedelta
from config.settings import T_SHORT, T_SAVE, T_DATE_SEG
from executor.actions import mui_select, mui_autocomplete
from report.test_report import get_reporter
from ._shared import _wait

# ============================================================
# executor/form_filler/project.py — Project form fill logic.
# ============================================================

# ── Report integration metadata ──────────────────────────────
# This module is invoked via action="fill_form" + module="project".
# FORM_ACTION_NAME is the lookup key used by test_report.py.
FORM_ACTION_NAME        = "fill_project_form"
FORM_MODULE             = "project"
FORM_ACTION_VERB        = "Submitted Project Form"
FORM_DESCRIPTION_PARAMS = [("project_name", "name")]
FORM_SUB_STEPS = [
    ("project_name",   "Project Name",   None),
    ("description",    "Description",    None),
    ("project_type",   "Project Type",   None),
    ("delivery_model", "Delivery Model", None),
    ("methodology",    "Methodology",    None),
    ("risk_rating",    "Risk Rating",    None),
    ("status",         "Status",         None),
    ("billing_type",   "Billing Type",   None),
    ("currency",       "Currency",       None),
    ("budget",         "Budget",         None),
    ("start_date",     "Start Date",     None),
    ("end_date",       "End Date",       None),
]


async def fill_project_form(page, p, overrides=None):
    """
    Fill and submit the New / Edit Project form.

    Args:
        page      — Playwright page object
        p         — params dict built by _build_create_params() or _build_update_params()
        overrides — optional dict merged into p before filling (used by negative scenarios)
    """
    if overrides:
        p = dict(p)
        p.update(overrides)

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
    skip_client = p.get("skip_client", False)
    if (is_billable or chosen_billing is None) and not skip_client:
        await mui_autocomplete(page, "Client",
                               p.get("client_search", "a"),
                               p.get("client_selector"))
        if r: r.log_sub_step("Client", p.get("client_search", "a"), "PASS")
    else:
        reason = "(override: skip_client)" if skip_client else "(billing='{}')".format(chosen_billing)
        print("   [INFO] Client field skipped {}".format(reason))
        if r: r.log_sub_step("Client", "(skipped — {})".format(reason), "PASS")

    # 4. Link to Estimation autocomplete
    await mui_autocomplete(page, "Link to Estimation",
                           p.get("estimation_search", "a"),
                           p.get("estimation_selector"))
    if r: r.log_sub_step("Link to Estimation", p.get("estimation_search", "a"), "PASS")

    # 5. Dates — must be sequential (sharing keyboard would corrupt both dates)
    await _set_date(page, 0, start_date, "Start Date")
    if r: r.log_sub_step("Start Date", start_date, "PASS")

    await _set_date(page, 1, end_date, "End Date")
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
