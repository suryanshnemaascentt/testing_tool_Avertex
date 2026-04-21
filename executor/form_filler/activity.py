import random
from datetime import datetime
from config.settings import T_SHORT
from report.test_report import get_reporter
from ._shared import _wait

# ============================================================
# executor/form_filler/activity.py — Activity form fill logic.
# ============================================================


async def fill_activity_form(page, p):
    """
    Fill the inline Add Activity form row and click the tick (save) button.

    Form fields (confirmed from DOM inspection):
        [0] Task Name  — input[placeholder='Task name']
        [1] Job/Phase  — MuiSelect-select index 0  (shows "No Phase" by default)
        [2] Hours      — input[type='number'][min='0']
        [3] Priority   — MuiSelect-select index 1  (shows "Medium" by default)
    """
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
