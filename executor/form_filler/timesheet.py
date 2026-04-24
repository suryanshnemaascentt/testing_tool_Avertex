import asyncio
from report.test_report import get_reporter
from ._shared import _wait

# ============================================================
# executor/form_filler/timesheet.py — Timesheet form fill logic.
# ============================================================

# ── Report integration metadata ──────────────────────────────
FORM_ACTION_NAME        = "fill_timesheet_row_form"
FORM_MODULE             = None
FORM_ACTION_VERB        = "Filled Timesheet Row"
FORM_DESCRIPTION_PARAMS = [
    ("project_name", "project"),
    ("job_name",     "job"),
    ("hours",        "hours"),
]
FORM_SUB_STEPS = []  # timesheet uses step-by-step internal logging

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
    r = get_reporter()
    try:
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
            try:
                add_btns = await page.query_selector_all("button:has-text('Add Row')")
                if add_btns:
                    await add_btns[0].scroll_into_view_if_needed()
                    await add_btns[0].click()
                    await page.wait_for_timeout(900)
                    print("[STEP 0] ✓")
                    if r:
                        r.log_sub_step("Add Row", row_index, "PASS")
                else:
                    print("[STEP 0] ⚠ Not found")
                    if r:
                        r.log_sub_step("Add Row", row_index, "FAIL",
                                       error="Add Row button not found")
            except Exception as e:
                print("[STEP 0] ERROR: {}".format(e))
                if r:
                    r.log_sub_step("Add Row", row_index, "FAIL",
                                   error="Could not add row: {}".format(e))

        # STEP 1+2: Project + Job in one tree
        print("\n[STEP 1+2] Opening project/job tree...")
        project_btns = await page.query_selector_all("#timesheet-project-select")
        if not project_btns:
            project_btns = await page.query_selector_all('button:has-text("Select Project")')

        if not project_btns:
            print("[STEP 1+2] ✗ Project button not found")
            if r:
                r.log_sub_step("Project Selection", project_name, "FAIL",
                               error="Project button not found")
            return False

        trigger = project_btns[-1]
        await trigger.scroll_into_view_if_needed()
        await trigger.click()
        await page.wait_for_timeout(800)

        project_ok, job_ok = await _pick_project_and_job(
            page, project_name, job_name, timeout=8000)

        print("[STEP 1] {}".format("✓ OK" if project_ok else "✗ FAILED"))
        print("[STEP 2] {}".format("✓ OK" if job_ok else "✗ FAILED"))
        if r:
            r.log_sub_step("Project Selection", project_name, "PASS" if project_ok else "FAIL",
                           error="" if project_ok else "Could not select project")
            r.log_sub_step("Job Selection", job_name, "PASS" if job_ok else "FAIL",
                           error="" if job_ok else "Could not select job")

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
                    if r:
                        r.log_sub_step("Hours {}".format(day), "(disabled)", "PASS")
                    continue
                await inp.scroll_into_view_if_needed()
                await inp.click()
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                await inp.type(hours, delay=50)
                await page.wait_for_timeout(200)
                print("   {} → {} hrs ✓".format(day, hours))
                hours_filled += 1
                if r:
                    r.log_sub_step("Hours {}".format(day), hours, "PASS")
            except Exception as e:
                print("   {} → ERROR: {}".format(day, e))
                if r:
                    r.log_sub_step("Hours {}".format(day), hours, "FAIL",
                                   error="Could not fill hours for {}: {}".format(day, e))

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
        if r:
            r.log_sub_step("Location", location_opt, "PASS" if set_count > 0 else "FAIL",
                           error="" if set_count > 0 else "Could not set location")
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
                    if r:
                        r.log_sub_step("Remarks", remarks, "PASS")
                else:
                    print("[STEP 5] ⚠ Textarea not found")
                    if r:
                        r.log_sub_step("Remarks", remarks, "FAIL",
                                       error="Remarks textarea not found")
            except Exception as e:
                print("[STEP 5] ERROR: {}".format(e))
                if r:
                    r.log_sub_step("Remarks", remarks, "FAIL",
                                   error="Could not fill remarks: {}".format(e))

        await page.wait_for_timeout(500)
        print("\n[ROW {}] ✓ COMPLETE".format(row_index))
        return True
    except Exception as e:
        print("[ROW] ERROR: {}".format(e))
        if r:
            r.log_sub_step("Timesheet Row", None, "FAIL",
                           error="Unexpected timesheet row error: {}".format(e))
        return False
