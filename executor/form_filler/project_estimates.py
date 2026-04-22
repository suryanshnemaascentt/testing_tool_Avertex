import random
from datetime import datetime, timedelta

from config.settings    import T_SHORT, T_SAVE
from report.test_report import get_reporter
from ._shared           import _wait

# ============================================================
# executor/form_filler/project_estimates.py
#
# Playwright form-fill logic for both estimate types.
#
# Exposes two fill functions (auto-discovered by __init__.py):
#   fill_manual_estimate_form(page, p)
#   fill_ai_estimate_form(page, p)
#
# Called after the respective entry dialog has been opened by
# modules/project_estimates.py.
# ============================================================

# ── Report integration metadata (primary action) ─────────────
FORM_ACTION_NAME        = "fill_manual_estimate_form"
FORM_MODULE             = "project_estimates"
FORM_ACTION_VERB        = "Filled Estimate Form"
FORM_DESCRIPTION_PARAMS = [("project_name", "name")]

FORM_SUB_STEPS = [
    ("project_name", "Project Name", None),
    ("description",  "Description",  None),
    ("start_date",   "Start Date",   None),
    ("end_date",     "End Date",     None),
]

_AI_SUB_STEPS = [
    ("description",   "Description",      None),
    ("tech",          "Technology",        None),
    ("timeline",      "Timeline Interval", None),
    ("start_date",    "Start Date",        None),
    ("end_date",      "End Date",          None),
    ("team_size",     "Team Size",         None),
    ("currency",      "Currency",          None),
    ("delivery_model","Delivery Model",    None),
    ("portfolio",     "Portfolio",         None),
    ("category",      "Category",          None),
    ("generate",      "Generate Estimate", None),
]


# ============================================================
# DATA GENERATORS  (same logic as original module)
# ============================================================

_PROJECT_NAMES = [
    "Apollo", "Neptune", "Orion", "Phoenix", "Atlas",
    "Quantum", "Nova", "Vertex", "Nimbus", "Zenith",
]


def _generate_project_name():
    return "{}_{}".format(
        random.choice(_PROJECT_NAMES),
        datetime.now().strftime("%H%M%S"),
    )


def _generate_description():
    return "Automation_Project_{}".format(
        datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    )


def _generate_manual_dates():
    """Returns (start_str, end_str) in DD-MM-YYYY format for manual form."""
    start_base = datetime(2026, 1, 1)
    end_base   = datetime(2031, 1, 1)
    delta      = (end_base - start_base).days
    start      = start_base + timedelta(days=random.randint(0, delta))
    end        = start + timedelta(days=365 * 3 + random.randint(1, 365))
    return start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y")


def _get_ai_dates():
    """Returns (start_str, end_str) in YYYY-MM-DD format for AI form."""
    today = datetime.today()
    start = today + timedelta(days=1)
    end   = start + timedelta(days=30)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _get_team_size():
    return str(random.randint(5, 50))


# ============================================================
# SHARED HELPERS
# ============================================================

async def _pick_listbox_option(page, nth=0):
    """Select the nth item from an open MUI select listbox."""
    try:
        await page.wait_for_selector("ul[role='listbox'] li", timeout=3000)
        opts = page.locator("ul[role='listbox'] li")
        cnt  = await opts.count()
        if cnt > 0:
            await opts.nth(min(nth, cnt - 1)).click(timeout=2000)
            await _wait(page, T_SHORT)
            return True
    except Exception as e:
        print("   [WARN] listbox pick failed: {}".format(e))
    return False


async def _pick_autocomplete_option(page):
    """Select the first item from an open MUI Autocomplete listbox."""
    try:
        await page.wait_for_selector(
            "ul.MuiAutocomplete-listbox li", timeout=3000
        )
        await page.locator("ul.MuiAutocomplete-listbox li").first.click(
            timeout=2000
        )
        await _wait(page, T_SHORT)
        return True
    except Exception as e:
        print("   [WARN] autocomplete pick failed: {}".format(e))
    return False


# ============================================================
# MANUAL ESTIMATE FORM
# ============================================================

async def fill_manual_estimate_form(page, p):
    """
    Fill the Create Manual Estimate form.
    Expects the 'Create Manually' dialog to already be open.

    Params (all optional — values are auto-generated if absent):
        project_name, description, start_date (DD-MM-YYYY), end_date (DD-MM-YYYY)
    """
    project_name       = p.get("project_name") or _generate_project_name()
    description        = p.get("description")  or _generate_description()
    start_date, end_date = (
        (p["start_date"], p["end_date"])
        if p.get("start_date") and p.get("end_date")
        else _generate_manual_dates()
    )

    print("\n[MANUAL ESTIMATE FORM] name='{}' {} -> {}".format(
        project_name, start_date, end_date))

    r = get_reporter()

    # ── 1. Project Name ───────────────────────────────────────
    try:
        inp = page.locator(
            "input[placeholder*='project name' i], "
            "input[placeholder*='enter project' i]"
        ).first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(project_name)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step("Project Name", project_name, "PASS")
        print("[MANUAL FORM] 1. Project name: '{}'".format(project_name))
    except Exception as e:
        if r:
            r.log_sub_step("Project Name", project_name, "FAIL", str(e))
        print("[MANUAL FORM] ! Project name failed: {}".format(e))

    # ── 2. Description ────────────────────────────────────────
    try:
        ta = page.locator(
            "textarea[placeholder*='project description' i], "
            "textarea"
        ).first
        await ta.scroll_into_view_if_needed(timeout=2000)
        await ta.click(timeout=2000)
        await ta.fill(description)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step("Description", description, "PASS")
        print("[MANUAL FORM] 2. Description filled")
    except Exception as e:
        if r:
            r.log_sub_step("Description", description, "FAIL", str(e))
        print("[MANUAL FORM] ! Description failed: {}".format(e))

    # ── 3. Start Date ─────────────────────────────────────────
    try:
        inp = page.locator("input[type='date']").nth(0)
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(timeout=2000)
        await inp.fill(start_date)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step("Start Date", start_date, "PASS")
        print("[MANUAL FORM] 3. Start date: {}".format(start_date))
    except Exception as e:
        if r:
            r.log_sub_step("Start Date", start_date, "FAIL", str(e))
        print("[MANUAL FORM] ! Start date failed: {}".format(e))

    # ── 4. End Date ───────────────────────────────────────────
    try:
        inp = page.locator("input[type='date']").nth(1)
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(timeout=2000)
        await inp.fill(end_date)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step("End Date", end_date, "PASS")
        print("[MANUAL FORM] 4. End date: {}".format(end_date))
    except Exception as e:
        if r:
            r.log_sub_step("End Date", end_date, "FAIL", str(e))
        print("[MANUAL FORM] ! End date failed: {}".format(e))

    # ── Submit (Create / Save button) ─────────────────────────
    saved = False
    for selector, desc in [
        ("//button[normalize-space()='Create']",    "Create button"),
        ("//button[normalize-space()='Save']",      "Save button"),
        ("//button[contains(.,'Submit')]",          "Submit button"),
    ]:
        try:
            btn = page.locator(selector).first
            if await btn.count() > 0:
                await btn.scroll_into_view_if_needed(timeout=2000)
                await btn.click(timeout=3000)
                await _wait(page, T_SAVE)
                print("[MANUAL FORM] Submit: {}".format(desc))
                saved = True
                break
        except Exception as e:
            print("[MANUAL FORM] ! {} failed: {}".format(desc, e))

    if not saved:
        print("[MANUAL FORM] No explicit submit button found — assuming auto-submit")

    return True


# ============================================================
# AI ESTIMATE FORM
# ============================================================

async def fill_ai_estimate_form(page, p):
    """
    Fill the AI Estimate form and click Generate Estimate.
    Expects the 'Start with AI' dialog to already be open.

    Params (all optional — values are auto-generated if absent):
        description, start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), team_size
    """
    description          = p.get("description") or _generate_description()
    start_date, end_date = (
        (p["start_date"], p["end_date"])
        if p.get("start_date") and p.get("end_date")
        else _get_ai_dates()
    )
    team_size = p.get("team_size") or _get_team_size()

    print("\n[AI ESTIMATE FORM] {} -> {}  team={}".format(
        start_date, end_date, team_size))

    r = get_reporter()

    # ── 1. Description ────────────────────────────────────────
    try:
        ta = page.locator(
            "textarea[placeholder*='project description' i], "
            "textarea[placeholder*='brief' i], "
            "textarea"
        ).first
        await ta.scroll_into_view_if_needed(timeout=2000)
        await ta.click(timeout=2000)
        await ta.fill(description)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step("Description", description, "PASS")
        print("[AI FORM] 1. Description filled")
    except Exception as e:
        if r:
            r.log_sub_step("Description", description, "FAIL", str(e))
        print("[AI FORM] ! Description failed: {}".format(e))

    # ── 2. Technology autocomplete ────────────────────────────
    try:
        tech_inp = page.locator(
            "input[placeholder*='search and select tech' i], "
            "input[placeholder*='technologies' i]"
        ).first
        if await tech_inp.count() > 0:
            await tech_inp.scroll_into_view_if_needed(timeout=2000)
            await tech_inp.click(timeout=2000)
            await _wait(page, 2000)
            await _pick_autocomplete_option(page)
            if r:
                r.log_sub_step("Technology", "(first option)", "PASS")
            print("[AI FORM] 2. Technology selected")
        else:
            if r:
                r.log_sub_step("Technology", "(skipped — not found)", "PASS")
            print("[AI FORM] 2. Technology input not found — skipped")
    except Exception as e:
        if r:
            r.log_sub_step("Technology", None, "FAIL", str(e))
        print("[AI FORM] ! Technology failed: {}".format(e))

    # ── 3. Timeline Interval dropdown ─────────────────────────
    try:
        sel = page.locator("#mui-component-select-gantt_interval").first
        if await sel.count() > 0:
            await sel.scroll_into_view_if_needed(timeout=2000)
            await sel.click(timeout=2000)
            await _wait(page, 2000)
            await _pick_listbox_option(page, nth=0)
            if r:
                r.log_sub_step("Timeline Interval", "(first option)", "PASS")
            print("[AI FORM] 3. Timeline interval selected")
        else:
            if r:
                r.log_sub_step("Timeline Interval", "(skipped — not found)", "PASS")
            print("[AI FORM] 3. Timeline dropdown not found — skipped")
    except Exception as e:
        if r:
            r.log_sub_step("Timeline Interval", None, "FAIL", str(e))
        print("[AI FORM] ! Timeline failed: {}".format(e))

    # ── 4. Start Date ─────────────────────────────────────────
    try:
        inp = page.locator("input[name='project_start_date']").first
        if await inp.count() == 0:
            inp = page.locator("input[type='date']").nth(0)
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.fill(start_date)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step("Start Date", start_date, "PASS")
        print("[AI FORM] 4. Start date: {}".format(start_date))
    except Exception as e:
        if r:
            r.log_sub_step("Start Date", start_date, "FAIL", str(e))
        print("[AI FORM] ! Start date failed: {}".format(e))

    # ── 5. End Date ───────────────────────────────────────────
    try:
        inp = page.locator("input[name='project_end_date']").first
        if await inp.count() == 0:
            inp = page.locator("input[type='date']").nth(1)
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.fill(end_date)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step("End Date", end_date, "PASS")
        print("[AI FORM] 5. End date: {}".format(end_date))
    except Exception as e:
        if r:
            r.log_sub_step("End Date", end_date, "FAIL", str(e))
        print("[AI FORM] ! End date failed: {}".format(e))

    # ── 6. Fixed Size + Team Size ─────────────────────────────
    try:
        fixed_btn = page.locator("//button[contains(.,'Fixed Size')]").first
        if await fixed_btn.count() > 0:
            await fixed_btn.scroll_into_view_if_needed(timeout=2000)
            await fixed_btn.click(timeout=2000)
            await _wait(page, T_SHORT)

        team_inp = page.locator("input[name='team_size']").first
        await team_inp.scroll_into_view_if_needed(timeout=2000)
        await team_inp.click(click_count=3, timeout=2000)
        await team_inp.fill(team_size)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step("Team Size", team_size, "PASS")
        print("[AI FORM] 6. Team size: {}".format(team_size))
    except Exception as e:
        if r:
            r.log_sub_step("Team Size", team_size, "FAIL", str(e))
        print("[AI FORM] ! Team size failed: {}".format(e))

    # ── 7. Currency dropdown ──────────────────────────────────
    try:
        sel = page.locator("#mui-component-select-display_currency").first
        await sel.scroll_into_view_if_needed(timeout=2000)
        await sel.click(timeout=2000)
        await _wait(page, 2000)
        nth = random.randint(1, 5)
        await _pick_listbox_option(page, nth=nth)
        if r:
            r.log_sub_step("Currency", "(option {})".format(nth + 1), "PASS")
        print("[AI FORM] 7. Currency selected")
    except Exception as e:
        if r:
            r.log_sub_step("Currency", None, "FAIL", str(e))
        print("[AI FORM] ! Currency failed: {}".format(e))

    # ── 8. Delivery Model: Onsite → Offshore → Hybrid ─────────
    for label in ("Onsite", "Offshore", "Hybrid"):
        try:
            btn = page.locator(
                "//button[contains(.,'{}')]".format(label)
            ).first
            if await btn.count() > 0:
                await btn.scroll_into_view_if_needed(timeout=2000)
                await btn.click(timeout=2000)
                await _wait(page, T_SHORT)
                print("[AI FORM] 8. Clicked {}".format(label))
        except Exception as e:
            print("[AI FORM] ! {} click failed: {}".format(label, e))
    if r:
        r.log_sub_step("Delivery Model", "Onsite / Offshore / Hybrid", "PASS")

    # ── 9. Portfolio dropdown ─────────────────────────────────
    try:
        sel = page.locator("#mui-component-select-portfolio").first
        await sel.scroll_into_view_if_needed(timeout=2000)
        await sel.click(timeout=2000)
        await _wait(page, 2000)
        nth = random.randint(1, 5)
        await _pick_listbox_option(page, nth=nth)
        if r:
            r.log_sub_step("Portfolio", "(option {})".format(nth + 1), "PASS")
        print("[AI FORM] 9. Portfolio selected")
    except Exception as e:
        if r:
            r.log_sub_step("Portfolio", None, "FAIL", str(e))
        print("[AI FORM] ! Portfolio failed: {}".format(e))

    # ── 10. Category dropdown ─────────────────────────────────
    try:
        sel = page.locator("#mui-component-select-category").first
        await sel.scroll_into_view_if_needed(timeout=2000)
        await sel.click(timeout=2000)
        await _wait(page, 2000)
        await _pick_listbox_option(page, nth=0)
        if r:
            r.log_sub_step("Category", "(first option)", "PASS")
        print("[AI FORM] 10. Category selected")
    except Exception as e:
        if r:
            r.log_sub_step("Category", None, "FAIL", str(e))
        print("[AI FORM] ! Category failed: {}".format(e))

    # ── 11. Customize Rates ───────────────────────────────────
    try:
        btn = page.locator("//button[contains(.,'Customize Rates')]").first
        if await btn.count() > 0:
            await btn.scroll_into_view_if_needed(timeout=2000)
            await btn.click(timeout=2000)
            await _wait(page, T_SHORT)
            print("[AI FORM] 11. Customize Rates clicked")
    except Exception as e:
        print("[AI FORM] ! Customize Rates failed: {}".format(e))

    # ── 12. Hide Rates ────────────────────────────────────────
    try:
        btn = page.locator("//button[contains(.,'Hide Rates')]").first
        if await btn.count() > 0:
            await btn.scroll_into_view_if_needed(timeout=2000)
            await btn.click(timeout=2000)
            await _wait(page, T_SHORT)
            print("[AI FORM] 12. Hide Rates clicked")
    except Exception as e:
        print("[AI FORM] ! Hide Rates failed: {}".format(e))

    # ── 13. Generate Estimate ─────────────────────────────────
    try:
        btn = page.locator("//button[contains(.,'Generate Estimate')]").first
        await btn.scroll_into_view_if_needed(timeout=2000)
        await btn.click(timeout=5000)
        await _wait(page, T_SAVE)
        if r:
            r.log_sub_step("Generate Estimate", None, "PASS")
        print("[AI FORM] 13. Generate Estimate clicked")
        return True
    except Exception as e:
        if r:
            r.log_sub_step("Generate Estimate", None, "FAIL", str(e))
        print("[AI FORM] ! Generate Estimate failed: {}".format(e))
        return False
